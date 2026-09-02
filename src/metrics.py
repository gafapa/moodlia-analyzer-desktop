"""Student metric computation. Calculates engagement, academic, submission and quiz metrics per student."""
import math
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

TREND_IMPROVING = "mejorando"
TREND_STABLE = "estable"
TREND_DECLINING = "empeorando"


class StudentMetrics:
    """Compute the complete metric set for one student."""

    def __init__(self, student_data: Dict, course_data: Dict):
        self.s = student_data
        self.course = course_data
        self.now = int(time.time())

    def compute(self) -> Dict:
        """Compute and return all metrics as a dictionary."""
        m: Dict[str, Any] = {}

        # Recent access
        last = self.s.get("lastaccess", 0)
        m["last_access_ts"] = last
        m["days_since_access"] = max(0, (self.now - last) // 86400) if last else 999
        m["last_access_str"] = (
            datetime.fromtimestamp(last).strftime("%d/%m/%Y")
            if last else "Nunca"
        )

        # --- Calificaciones ---
        grade_data = self.s.get("grades", {})
        m["final_grade"] = grade_data.get("final_grade")
        m["final_grade_pct"] = grade_data.get("final_grade_pct")
        m["course_total_max"] = grade_data.get("course_total_max") or 10.0
        m["grade_items"] = grade_data.get("items", [])
        m["graded_items"] = [
            gi for gi in m["grade_items"] if gi.get("grade") is not None
        ]
        m["grade_avg_pct"] = (
            sum(gi["grade_pct"] for gi in m["graded_items"] if gi.get("grade_pct") is not None)
            / max(len(m["graded_items"]), 1)
            if m["graded_items"] else None
        )

        # Grade trend from a simple linear slope.
        m["grade_trend"] = self._compute_grade_trend(m["grade_items"])

        # --- Completitud ---
        comp = self.s.get("completion", {})
        total_act = comp.get("total", 0)
        completed_act = comp.get("completed", 0)
        m["completion_rate"] = (completed_act / total_act) * 100 if total_act else None
        m["completed_activities"] = completed_act
        m["total_activities"] = total_act

        # --- Tareas ---
        assigns = self.course.get("assignments", [])
        subs = self.s.get("submissions", [])
        # Count only records with status="submitted" as submitted work.
        # Treat missing status values from older APIs as submitted for compatibility.
        submitted_subs = [
            s for s in subs
            if s.get("status", "submitted") not in ("new", "draft", "reopened")
        ]
        m["total_assignments"] = len(assigns)
        m["submitted_assignments"] = len(submitted_subs)
        m["submission_rate"] = (
            (m["submitted_assignments"] / m["total_assignments"]) * 100
            if m["total_assignments"] else None
        )
        m["late_submissions"] = self._count_late_submissions(assigns, submitted_subs)
        m["on_time_rate"] = (
            ((m["submitted_assignments"] - m["late_submissions"]) / max(m["submitted_assignments"], 1)) * 100
            if m["submitted_assignments"] else 0
        )
        if not m["total_assignments"]:
            m["on_time_rate"] = None

        # --- Cuestionarios ---
        attempts = self.s.get("quiz_attempts", [])
        quiz_scores = self._compute_quiz_scores(attempts)
        m["total_quizzes"] = len(self.course.get("quizzes", []))
        m["quiz_attempts_count"] = len(attempts)
        m["quiz_scores"] = quiz_scores
        m["quiz_avg_pct"] = (
            sum(quiz_scores) / len(quiz_scores) if quiz_scores else None
        )
        m["quiz_trend"] = self._compute_quiz_trend(quiz_scores)
        # Unique quizzes with at least one completed attempt
        _finished_states = ("finished", "gradedright", "gradedwrong", "gradedpartial")
        attempted_quiz_ids = set(
            att.get("quizid") for att in attempts
            if att.get("state") in _finished_states and att.get("quizid") is not None
        )
        m["quiz_unique_attempted"] = len(attempted_quiz_ids)
        m["quiz_coverage_rate"] = (
            (len(attempted_quiz_ids) / m["total_quizzes"]) * 100
            if m["total_quizzes"] else None
        )

        # --- Foros ---
        posts = self.s.get("forum_posts", [])
        m["total_forums"] = len(self.course.get("forums", []))
        m["forum_posts_count"] = len(posts)
        m["forum_discussions_started"] = len(set(
            p.get("discussionid") for p in posts if p.get("parent", 0) == 0
        ))

        # --- Logs ---
        logs = self.s.get("logs", [])
        m["log_count"] = len(logs)
        m["login_days"] = self._count_unique_days(logs)

        # --- Patrones temporales y sesiones ---
        all_ts = self._collect_all_timestamps()
        m["activity_timestamps"] = all_ts
        m["weeks_active"] = self._count_unique_weeks_from_timestamps(all_ts)
        m["submission_avg_advance_days"] = self._compute_submission_advance(assigns, submitted_subs)
        m["quiz_avg_time_min"] = self._compute_quiz_avg_time(self.s.get("quiz_attempts", []))

        if logs:
            m["session_count"], m["avg_session_duration_min"] = self._estimate_sessions(logs)
        else:
            m["session_count"] = None
            m["avg_session_duration_min"] = None

        # --- Puntuaciones compuestas ---
        m["engagement_score"] = self._compute_engagement(m)
        m["academic_score"] = self._compute_academic_score(m)

        return m

    # ------------------------------------------------------------------
    # Metric helpers
    # ------------------------------------------------------------------

    def _compute_grade_trend(self, items: List[Dict]) -> Optional[str]:
        """Classify the slope of date-ordered grades as improving, stable, or declining."""
        dated = [
            (i["gradedate"], i["grade_pct"])
            for i in items
            if i.get("gradedate") and i.get("grade_pct") is not None
        ]
        dated.sort(key=lambda x: x[0])
        pcts = [d[1] for d in dated]
        if len(pcts) < 2:
            return TREND_STABLE
        slope = self._linear_slope(list(range(len(pcts))), pcts)
        if slope > 2:
            return TREND_IMPROVING
        if slope < -2:
            return TREND_DECLINING
        return TREND_STABLE

    def _compute_quiz_scores(self, attempts: List[Dict]) -> List[float]:
        """Return percentage scores for completed attempts."""
        scores = []
        for att in attempts:
            state = att.get("state", "")
            if state not in ("finished", "gradedright", "gradedwrong", "gradedpartial"):
                continue
            grade = att.get("grade")
            quiz_id = att.get("quizid")
            if grade is None:
                continue
            # Find the quiz maximum grade
            quizzes = self.course.get("quizzes", [])
            max_grade = next(
                (q.get("grade", 10) for q in quizzes if q.get("id") == quiz_id),
                10,
            )
            try:
                pct = (float(grade) / float(max_grade)) * 100 if float(max_grade) > 0 else 0
                scores.append(pct)
            except (ValueError, TypeError):
                pass
        return scores

    def _compute_quiz_trend(self, scores: List[float]) -> Optional[str]:
        if len(scores) < 2:
            return TREND_STABLE
        slope = self._linear_slope(list(range(len(scores))), scores)
        if slope > 3:
            return TREND_IMPROVING
        if slope < -3:
            return TREND_DECLINING
        return TREND_STABLE

    def _count_late_submissions(self, assigns: List[Dict], subs: List[Dict]) -> int:
        late = 0
        sub_by_assign = {s["assignid"]: s for s in subs}
        for assign in assigns:
            aid = assign.get("id")
            duedate = assign.get("duedate", 0)
            if not duedate or not aid:
                continue
            sub = sub_by_assign.get(aid)
            if sub and sub.get("timemodified", 0) > duedate:
                late += 1
        return late

    def _collect_all_timestamps(self) -> List[int]:
        """Collect every available activity timestamp for a student."""
        tss: List[int] = []
        for s in self.s.get("submissions", []):
            t = s.get("timemodified") or s.get("timecreated")
            if t:
                tss.append(t)
        for a in self.s.get("quiz_attempts", []):
            t = a.get("timestart") or a.get("timefinish")
            if t:
                tss.append(t)
        for p in self.s.get("forum_posts", []):
            t = p.get("created") or p.get("modified") or p.get("timecreated")
            if t:
                tss.append(t)
        for lg in self.s.get("logs", []):
            t = lg.get("timecreated") or lg.get("time")
            if t:
                tss.append(t)
        return sorted(set(tss))

    def _count_unique_weeks_from_timestamps(self, timestamps: List[int]) -> int:
        """Count calendar weeks that contain recorded activity."""
        weeks: set = set()
        for ts in timestamps:
            try:
                dt = datetime.fromtimestamp(ts)
                weeks.add((dt.year, dt.isocalendar()[1]))
            except (OSError, ValueError, OverflowError):
                pass
        return len(weeks)

    def _compute_submission_advance(
        self, assigns: List[Dict], submitted_subs: List[Dict]
    ) -> Optional[float]:
        """Return mean submission lead time in days; negative values are late."""
        sub_map = {s["assignid"]: s for s in submitted_subs}
        advances: List[float] = []
        for a in assigns:
            aid = a.get("id")
            due = a.get("duedate", 0)
            if not due or not aid:
                continue
            sub = sub_map.get(aid)
            if sub:
                ts = sub.get("timemodified", 0) or sub.get("timecreated", 0)
                if ts:
                    advances.append((due - ts) / 86400)
        return round(sum(advances) / len(advances), 1) if advances else None

    def _compute_quiz_avg_time(self, attempts: List[Dict]) -> Optional[float]:
        """Return the average duration of completed quiz attempts in minutes."""
        times: List[float] = []
        for att in attempts:
            start = att.get("timestart", 0)
            finish = att.get("timefinish", 0)
            if start and finish and 0 < (finish - start) < 28800:  # < 8 h
                times.append((finish - start) / 60.0)
        return round(sum(times) / len(times), 1) if times else None

    def _estimate_sessions(self, logs: List[Dict]) -> Tuple[int, float]:
        """Estimate session count and mean duration using a 30-minute inactivity gap."""
        tss = sorted([
            lg.get("timecreated") or lg.get("time", 0)
            for lg in logs
            if lg.get("timecreated") or lg.get("time")
        ])
        if not tss:
            return 0, 0.0
        GAP = 1800  # 30 minutos = nueva sesión
        sessions: List[Tuple[int, int]] = []
        s_start, s_end = tss[0], tss[0]
        for t in tss[1:]:
            if t - s_end > GAP:
                sessions.append((s_start, s_end))
                s_start = t
            s_end = t
        sessions.append((s_start, s_end))
        avg_min = sum((e - s) / 60.0 for s, e in sessions) / len(sessions)
        return len(sessions), round(avg_min, 1)

    def _count_unique_days(self, logs: List[Dict]) -> int:
        days = set()
        for log in logs:
            ts = log.get("timecreated") or log.get("time", 0)
            if ts:
                try:
                    day = datetime.fromtimestamp(ts).date()
                    days.add(day)
                except (OSError, ValueError, OverflowError):
                    pass
        return len(days)

    def _compute_engagement(self, m: Dict) -> float:
        """Compute a weighted engagement score from 0 to 100."""
        weighted_scores = []

        # Activity completion (25%).
        if m.get("completion_rate") is not None:
            weighted_scores.append((m["completion_rate"], 0.25))

        # Submission rate (25%)
        if m.get("submission_rate") is not None:
            weighted_scores.append((m["submission_rate"], 0.25))

        # Recent access (20%)
        days = m["days_since_access"]
        access_score = max(0, 100 - days * (100.0 / 30))  # exactamente 0 a los 30 días sin acceso
        weighted_scores.append((access_score, 0.20))

        # Forum participation (15%).
        # Normalizar: 10 posts = 100%
        if m.get("total_forums", 0) > 0:
            forum_score = min(100, m["forum_posts_count"] * 10)
            weighted_scores.append((forum_score, 0.15))

        # Quiz coverage (15%): unique quizzes attempted divided by total quizzes
        quizzes_total = m.get("total_quizzes", 0)
        if quizzes_total > 0:
            quiz_score = min(100, (m.get("quiz_unique_attempted", 0) / quizzes_total) * 100)
            weighted_scores.append((quiz_score, 0.15))

        total_weight = sum(weight for _, weight in weighted_scores)
        score = sum(value * weight for value, weight in weighted_scores) / total_weight
        return round(min(max(score, 0), 100), 1)

    def _compute_academic_score(self, m: Dict) -> float:
        """Compute a grade-based academic score from 0 to 100."""
        scores = []
        if m.get("final_grade_pct") is not None:
            scores.append(m["final_grade_pct"])
        if m.get("grade_avg_pct") is not None:
            scores.append(m["grade_avg_pct"])
        if m.get("quiz_avg_pct") is not None:
            scores.append(m["quiz_avg_pct"])
        return round(sum(scores) / len(scores), 1) if scores else 0.0

    @staticmethod
    def _linear_slope(x: List[float], y: List[float]) -> float:
        """Calculate the slope of a simple linear regression."""
        n = len(x)
        if n < 2:
            return 0.0
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den = sum((xi - mean_x) ** 2 for xi in x)
        return num / den if den != 0 else 0.0
