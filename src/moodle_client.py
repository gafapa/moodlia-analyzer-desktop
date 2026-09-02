"""Read-only client for the Moodle REST API."""
import requests
import json
from typing import Optional, List, Dict, Any

from .url_security import normalize_service_base_url, reject_redirect


class MoodleAPIError(Exception):
    pass


class MoodleClient:
    """Read-only Moodle REST client with token or credential authentication."""

    def __init__(self, base_url: str, token: str):
        try:
            self.base_url = normalize_service_base_url(base_url, "Moodle URL")
        except ValueError as exc:
            raise MoodleAPIError(str(exc)) from exc
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "MoodleAnalyzer/1.0"})
        # Authenticated site and user information
        self.site_name = ""
        self.user_id = None
        self.user_fullname = ""
        self._test_connection()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    @classmethod
    def from_credentials(
        cls,
        base_url: str,
        username: str,
        password: str,
        service: str = "moodle_mobile_app",
    ) -> "MoodleClient":
        """Create a client from credentials by requesting a Moodle token."""
        try:
            normalized_base_url = normalize_service_base_url(base_url, "Moodle URL")
        except ValueError as exc:
            raise MoodleAPIError(str(exc)) from exc
        token_url = f"{normalized_base_url}/login/token.php"
        try:
            resp = requests.post(
                token_url,
                data={"username": username, "password": password, "service": service},
                timeout=30,
                allow_redirects=False,
            )
            reject_redirect(resp, "Moodle token request")
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise MoodleAPIError(
                    f"Login fallido: {data.get('error', 'Credenciales inválidas')}"
                )
            token = data.get("token")
            if not token:
                raise MoodleAPIError("No se recibió token del servidor")
            return cls(normalized_base_url, token)
        except requests.exceptions.ConnectionError:
            raise MoodleAPIError(f"No se puede conectar a: {base_url}")
        except requests.exceptions.Timeout:
            raise MoodleAPIError("Tiempo de espera agotado al conectar")
        except requests.exceptions.RequestException as e:
            raise MoodleAPIError(f"Error de conexión: {e}")
        except ValueError as exc:
            raise MoodleAPIError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Base API request
    # ------------------------------------------------------------------

    def _api_call(self, function: str, params: Optional[Dict] = None) -> Any:
        """Call a Moodle REST function."""
        url = f"{self.base_url}/webservice/rest/server.php"
        payload = {
            "wstoken": self.token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
        }
        if params:
            payload.update(self._flatten(params))

        try:
            resp = self.session.post(url, data=payload, timeout=60, allow_redirects=False)
            reject_redirect(resp, f"Moodle API request [{function}]")
            resp.raise_for_status()
            result = resp.json()
            if isinstance(result, dict) and "exception" in result:
                msg = result.get("message", result.get("debuginfo", "Error desconocido"))
                raise MoodleAPIError(f"API [{function}]: {msg}")
            return result
        except requests.exceptions.ConnectionError:
            raise MoodleAPIError(f"Sin conexión al servidor: {self.base_url}")
        except requests.exceptions.Timeout:
            raise MoodleAPIError(f"Tiempo de espera agotado en [{function}]")
        except requests.exceptions.RequestException as e:
            raise MoodleAPIError(f"Error HTTP: {e}")
        except json.JSONDecodeError:
            raise MoodleAPIError("Respuesta inválida del servidor (no es JSON)")
        except ValueError as exc:
            raise MoodleAPIError(str(exc)) from exc

    def _api_call_safe(self, function: str, params: Optional[Dict] = None, default=None):
        """Call the API and return a default value instead of raising on failure."""
        try:
            return self._api_call(function, params)
        except MoodleAPIError:
            return default

    @staticmethod
    def _flatten(params: Dict, prefix: str = "") -> Dict:
        """Flatten nested dictionaries and lists into Moodle REST parameters."""
        result = {}
        for key, value in params.items():
            full_key = f"{prefix}[{key}]" if prefix else key
            if isinstance(value, dict):
                result.update(MoodleClient._flatten(value, full_key))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        result.update(MoodleClient._flatten(item, f"{full_key}[{i}]"))
                    else:
                        result[f"{full_key}[{i}]"] = item
            else:
                result[full_key] = value
        return result

    # ------------------------------------------------------------------
    # Connection and site
    # ------------------------------------------------------------------

    def _test_connection(self):
        info = self._api_call("core_webservice_get_site_info")
        self.site_name = info.get("sitename", "Moodle")
        self.user_id = info.get("userid")
        self.user_fullname = info.get("fullname", "")

    def get_site_info(self) -> Dict:
        return self._api_call("core_webservice_get_site_info")

    # ------------------------------------------------------------------
    # Courses
    # ------------------------------------------------------------------

    def get_my_courses(self) -> List[Dict]:
        """Return courses accessible to the authenticated user.

        Try three endpoints in order and return the first successful result:
          1. core_enrol_get_my_courses for general student or teacher enrollment.
          2. core_enrol_get_users_courses for explicit user course roles.
          3. core_course_get_courses for privileged site-wide access.
        """
        # Attempt 1: broadly enrolled courses
        result = self._api_call_safe(
            "core_enrol_get_my_courses",
            {"returnusercount": 1},
            default=[],
        )
        if isinstance(result, list):
            courses = [c for c in result if c.get("id", 0) > 1]
            if courses:
                return courses

        # Attempt 2: courses by user id, including teachers and course creators
        if self.user_id:
            result = self._api_call_safe(
                "core_enrol_get_users_courses",
                {"userid": self.user_id},
                default=[],
            )
            if isinstance(result, list):
                courses = [c for c in result if c.get("id", 0) > 1]
                if courses:
                    return courses

        # Attempt 3: all site courses for privileged users
        return self.get_all_courses()

    def get_all_courses(self) -> List[Dict]:
        """Return all courses when the user has manager or administrator access."""
        result = self._api_call_safe("core_course_get_courses", default=[])
        if isinstance(result, list):
            return [c for c in result if c.get("id", 0) > 1]
        return []

    def get_enrollment_count(self, course_id: int) -> int:
        """Return the enrolled-user count for a course."""
        users = self._api_call_safe(
            "core_enrol_get_enrolled_users",
            {"courseid": course_id},
            default=[],
        )
        return len(users) if isinstance(users, list) else 0

    def get_courses(self) -> List[Dict]:
        """Return available courses without blocking on enrollment enrichment."""
        courses = self.get_my_courses()
        if not courses:
            courses = self.get_all_courses()
        return courses

    def get_course_contents(self, course_id: int) -> List[Dict]:
        """Return course sections and activities."""
        return self._api_call_safe(
            "core_course_get_contents", {"courseid": course_id}, default=[]
        )

    # ------------------------------------------------------------------
    # Users and enrollment
    # ------------------------------------------------------------------

    def get_enrolled_users(self, course_id: int) -> List[Dict]:
        """Return users enrolled in a course."""
        return self._api_call_safe(
            "core_enrol_get_enrolled_users", {"courseid": course_id}, default=[]
        )

    def get_course_user_profiles(self, course_id: int, user_ids: List[int]) -> List[Dict]:
        """Return complete user profiles for a course."""
        params: Dict[str, Any] = {"courseid": course_id}
        for i, uid in enumerate(user_ids):
            params[f"userids[{i}]"] = uid
        return self._api_call_safe("core_user_get_course_user_profiles", params, default=[])

    # ------------------------------------------------------------------
    # Grades
    # ------------------------------------------------------------------

    def get_grade_items_for_user(self, course_id: int, user_id: int) -> Dict:
        """Return grade items for one user in a course."""
        return self._api_call_safe(
            "gradereport_user_get_grade_items",
            {"courseid": course_id, "userid": user_id},
            default={},
        )

    def get_grades(self, course_id: int, user_ids: List[int]) -> Dict:
        """Return grades for multiple users through the simplified API."""
        params: Dict[str, Any] = {"courseid": course_id}
        for i, uid in enumerate(user_ids):
            params[f"userids[{i}]"] = uid
        return self._api_call_safe("core_grades_get_grades", params, default={})

    def get_gradebook_overview(self, course_id: int) -> List[Dict]:
        """Return the gradebook overview for the authenticated user."""
        result = self._api_call_safe(
            "gradereport_overview_get_course_grades",
            {"userid": self.user_id},
            default={},
        )
        return result.get("grades", []) if isinstance(result, dict) else []

    # ------------------------------------------------------------------
    # Activity completion
    # ------------------------------------------------------------------

    def get_activities_completion(self, course_id: int, user_id: int) -> Dict:
        """Return activity completion status for one user."""
        return self._api_call_safe(
            "core_completion_get_activities_completion_status",
            {"courseid": course_id, "userid": user_id},
            default={},
        )

    def get_course_completion_status(self, course_id: int, user_id: int) -> Dict:
        """Return course completion information for one user."""
        return self._api_call_safe(
            "core_completion_get_course_completion_status",
            {"courseid": course_id, "userid": user_id},
            default={},
        )

    # ------------------------------------------------------------------
    # Assignments
    # ------------------------------------------------------------------

    def get_assignments(self, course_id: int) -> List[Dict]:
        """Return course assignments."""
        result = self._api_call_safe(
            "mod_assign_get_assignments",
            {"courseids[0]": course_id},
            default={"courses": []},
        )
        courses = result.get("courses", []) if isinstance(result, dict) else []
        return courses[0].get("assignments", []) if courses else []

    def get_submissions(self, assign_id: int) -> List[Dict]:
        """Return submissions for an assignment."""
        result = self._api_call_safe(
            "mod_assign_get_submissions",
            {"assignmentids[0]": assign_id},
            default={"assignments": []},
        )
        assignments = result.get("assignments", []) if isinstance(result, dict) else []
        return assignments[0].get("submissions", []) if assignments else []

    def get_submission_statuses(self, assign_id: int) -> List[Dict]:
        """Return one user's submission status for an assignment."""
        result = self._api_call_safe(
            "mod_assign_get_submission_status",
            {"assignid": assign_id},
            default={},
        )
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # Quizzes
    # ------------------------------------------------------------------

    def get_quizzes(self, course_id: int) -> List[Dict]:
        """Return course quizzes."""
        result = self._api_call_safe(
            "mod_quiz_get_quizzes_by_courses",
            {"courseids[0]": course_id},
            default={"quizzes": []},
        )
        return result.get("quizzes", []) if isinstance(result, dict) else []

    def get_user_attempts(self, quiz_id: int, user_id: int = 0) -> List[Dict]:
        """Return quiz attempts, using user_id=0 for all users."""
        params: Dict[str, Any] = {"quizid": quiz_id}
        if user_id:
            params["userid"] = user_id
        result = self._api_call_safe("mod_quiz_get_user_attempts", params, default={"attempts": []})
        return result.get("attempts", []) if isinstance(result, dict) else []

    def get_quiz_attempt_review(self, attempt_id: int) -> Dict:
        """Return the review of a quiz attempt."""
        return self._api_call_safe(
            "mod_quiz_get_attempt_review",
            {"attemptid": attempt_id},
            default={},
        )

    # ------------------------------------------------------------------
    # Forums
    # ------------------------------------------------------------------

    def get_forums(self, course_id: int) -> List[Dict]:
        """Return course forums."""
        return self._api_call_safe(
            "mod_forum_get_forums_by_courses",
            {"courseids[0]": course_id},
            default=[],
        )

    def get_forum_discussions(self, forum_id: int, page: int = 0, per_page: int = 100) -> List[Dict]:
        """Return discussions for a forum."""
        result = self._api_call_safe(
            "mod_forum_get_forum_discussions",
            {"forumid": forum_id, "page": page, "perpage": per_page},
            default={"discussions": []},
        )
        if isinstance(result, dict):
            return result.get("discussions", [])
        if isinstance(result, list):
            return result
        return []

    def get_discussion_posts(self, discussion_id: int) -> List[Dict]:
        """Return posts from a forum discussion."""
        result = self._api_call_safe(
            "mod_forum_get_forum_discussion_posts",
            {"discussionid": discussion_id},
            default={"posts": []},
        )
        return result.get("posts", []) if isinstance(result, dict) else []

    # ------------------------------------------------------------------
    # Activity logs
    # ------------------------------------------------------------------

    def get_user_logs(
        self,
        course_id: int,
        user_id: int = 0,
        date: int = 0,
        modname: str = "",
        action: str = "",
    ) -> List[Dict]:
        """Return activity logs, or an empty list when permissions are unavailable."""
        params: Dict[str, Any] = {"courseid": course_id, "edulevel": -1}
        if user_id:
            params["userid"] = user_id
        if date:
            params["date"] = date
        if modname:
            params["modname"] = modname
        if action:
            params["action"] = action
        result = self._api_call_safe("report_log_get_log", params, default={"logs": []})
        if isinstance(result, dict):
            return result.get("logs", [])
        if isinstance(result, list):
            return result
        return []

    def get_insights(self, course_id: int) -> List[Dict]:
        """Return Moodle predictions and insights when analytics is enabled."""
        result = self._api_call_safe(
            "tool_analytics_potential_contexts",
            {"modelid": 1},
            default=[],
        )
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # Resources and modules
    # ------------------------------------------------------------------

    def get_course_module(self, cm_id: int) -> Dict:
        """Return course-module information."""
        return self._api_call_safe(
            "core_course_get_course_module",
            {"cmid": cm_id},
            default={},
        )

    def get_pages(self, course_id: int) -> List[Dict]:
        """Return course page resources."""
        result = self._api_call_safe(
            "mod_page_get_pages_by_courses",
            {"courseids[0]": course_id},
            default={"pages": []},
        )
        return result.get("pages", []) if isinstance(result, dict) else []

    def get_resources(self, course_id: int) -> List[Dict]:
        """Return course file resources."""
        result = self._api_call_safe(
            "mod_resource_get_resources_by_courses",
            {"courseids[0]": course_id},
            default={"resources": []},
        )
        return result.get("resources", []) if isinstance(result, dict) else []
