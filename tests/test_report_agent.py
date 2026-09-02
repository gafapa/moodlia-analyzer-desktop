import unittest

from src.report_agent import ReportAgent


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, mapping):
        self.mapping = mapping
        self.headers = {}

    def update(self, payload):
        self.headers.update(payload)

    def get(self, url, headers=None, timeout=20, allow_redirects=False):
        return FakeResponse(self.mapping[url])

    def post(self, url, headers=None, json=None, timeout=90, allow_redirects=False):
        return FakeResponse({
            "choices": [{"message": {"content": "ok"}}],
        })


class StubReportAgent(ReportAgent):
    def __init__(self):
        super().__init__(api_key="test-key")
        self.prompts = []

    def _request_completion(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "ok"


def sample_analysis():
    return {
        "course": {"id": 10, "fullname": "Curso de ejemplo", "categoryname": "Demo"},
        "pass_threshold_pct": 60.0,
        "course_metrics": {"total_students": 1, "avg_engagement": 72.0},
        "teacher_recommendations": ["Contactar con alumnado inactivo."],
        "assignments": [{"id": 5, "name": "Tarea 1", "duedate": 1_700_000_000}],
        "submissions_by_assign": {
            5: [{"userid": 7, "status": "submitted", "timemodified": 1_700_000_100}]
        },
        "students": [
            {
                "id": 7,
                "fullname": "Ana",
                "email": "ana@example.com",
                "risk_level": "medio",
                "risk_factors": ["Acceso irregular"],
                "recommendations": ["Planificar entregas."],
                "submissions": [{"assignid": 5, "status": "submitted", "timemodified": 1_700_000_100}],
                "metrics": {
                    "final_grade_pct": 68.0,
                    "engagement_score": 72.0,
                    "completion_rate": 80.0,
                    "submission_rate": 100.0,
                    "last_access_str": "01/03/2026",
                    "days_since_access": 2,
                    "grade_items": [{"name": "Tarea 1", "grade_pct": 75.0}],
                },
                "prediction": {"predicted_grade_pct": 74.0, "risk_probability": 0.22},
            }
        ],
    }


class ReportAgentTests(unittest.TestCase):
    def test_course_report_uses_course_context(self):
        agent = StubReportAgent()

        result = agent.generate_course_report(sample_analysis())

        self.assertEqual(result, "ok")
        self.assertNotIn("Curso de ejemplo", agent.prompts[0])
        self.assertNotIn("Ana", agent.prompts[0])
        self.assertIn("Tarea 1", agent.prompts[0])
        self.assertIn("\"umbral_aprobado_pct\": 60.0", agent.prompts[0])

    def test_student_assignment_report_uses_student_and_assignment_context(self):
        agent = StubReportAgent()
        analysis = sample_analysis()
        student = analysis["students"][0]

        result = agent.generate_student_assignment_report(analysis, student, 5)

        self.assertEqual(result, "ok")
        self.assertNotIn("Ana", agent.prompts[0])
        self.assertNotIn("ana@example.com", agent.prompts[0])
        self.assertIn('"id": 7', agent.prompts[0])
        self.assertIn("Tarea 1", agent.prompts[0])

    def test_list_available_models_for_ollama_uses_tags_endpoint(self):
        session = FakeSession({
            "http://127.0.0.1:11434/api/tags": {
                "models": [{"name": "llama3.2"}, {"name": "mistral"}]
            }
        })
        agent = ReportAgent(
            provider="ollama",
            base_url="http://127.0.0.1:11434",
            model="llama3.2",
            session=session,
        )

        models = agent.list_available_models()

        self.assertEqual(models, ["llama3.2", "mistral"])

    def test_list_available_models_for_lmstudio_uses_models_endpoint(self):
        session = FakeSession({
            "http://127.0.0.1:1234/v1/models": {
                "data": [{"id": "qwen2.5-7b-instruct"}]
            }
        })
        agent = ReportAgent(
            provider="lmstudio",
            base_url="http://127.0.0.1:1234",
            model="qwen2.5-7b-instruct",
            session=session,
        )

        models = agent.list_available_models()

        self.assertEqual(models, ["qwen2.5-7b-instruct"])


if __name__ == "__main__":
    unittest.main()
