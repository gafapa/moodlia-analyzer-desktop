"""Generate AI reports through a configured OpenAI-compatible endpoint."""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import requests

from .ai_settings import load_ai_settings
from . import i18n
from .url_security import normalize_service_base_url, reject_redirect


class ReportAgentError(Exception):
    """Controlled report-agent error."""


class ReportAgent:
    SYSTEM_PROMPT = (
        "Eres un analista educativo experto en Moodle. "
        "Genera informes en español, claros, ejecutivos y bien redactados, usando Markdown simple. "
        "No inventes datos. Si falta información, dilo explícitamente. "
        "Estructura la respuesta con estos bloques cuando apliquen: "
        "# Título, ## Resumen ejecutivo, ## Hallazgos clave, ## Riesgos, ## Acciones recomendadas. "
        "Usa viñetas cortas, evita tablas, evita JSON, evita repetir métricas sin interpretarlas. "
        "El tono debe ser profesional y útil para toma de decisiones."
    )

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        settings = load_ai_settings()
        self.provider = (provider or settings.get("provider") or "ollama").strip().lower()
        self.api_key = (api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")).strip()
        self.model = (model if model is not None else settings.get("model") or os.getenv("OPENAI_MODEL", "")).strip()
        default_base = "http://127.0.0.1:11434" if self.provider == "ollama" else "http://127.0.0.1:1234"
        raw_base_url = base_url if base_url is not None else settings.get("base_url") or os.getenv("OPENAI_BASE_URL", default_base)
        try:
            self.base_url = normalize_service_base_url(raw_base_url, "AI provider URL")
        except ValueError as exc:
            raise ReportAgentError(str(exc)) from exc
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "MoodleAnalyzerReportAgent/1.0"})

    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)

    def setup_message(self) -> str:
        return i18n.translate_text(
            "Informes IA no configurados.\n\nAbre 'Configurar IA' y define proveedor local, URL base y modelo."
        )

    def generate_course_report(self, analysis: Dict) -> str:
        context = self._build_course_context(analysis)
        return self._request_completion(self._render_prompt("curso", context))

    def generate_assignment_report(self, analysis: Dict, assignment_id: int) -> str:
        context = self._build_assignment_context(analysis, assignment_id)
        return self._request_completion(self._render_prompt("tarea", context))

    def generate_student_report(self, analysis: Dict, student: Dict) -> str:
        context = self._build_student_context(analysis, student)
        return self._request_completion(self._render_prompt("alumno", context))

    def generate_student_assignment_report(
        self, analysis: Dict, student: Dict, assignment_id: int
    ) -> str:
        context = self._build_student_assignment_context(analysis, student, assignment_id)
        return self._request_completion(self._render_prompt("alumno/tarea", context))

    def _request_completion(self, prompt: str) -> str:
        if not self.is_configured():
            raise ReportAgentError(self.setup_message())

        url = f"{self._v1_base_url()}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=90, allow_redirects=False)
            reject_redirect(response, "AI report request")
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout as exc:
            raise ReportAgentError("Tiempo de espera agotado al generar el informe IA.") from exc
        except requests.exceptions.RequestException as exc:
            raise ReportAgentError(f"Error HTTP al generar el informe IA: {exc}") from exc
        except ValueError as exc:
            if "redirected" in str(exc):
                raise ReportAgentError(str(exc)) from exc
            raise ReportAgentError("La respuesta del proveedor IA no es JSON válido.") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ReportAgentError("La respuesta del proveedor IA no contiene texto utilizable.") from exc

        if isinstance(content, list):
            fragments = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    fragments.append(item.get("text", ""))
            content = "\n".join(fragments).strip()

        if not isinstance(content, str) or not content.strip():
            raise ReportAgentError("El proveedor IA devolvió una respuesta vacía.")
        return content.strip()

    def list_available_models(self) -> List[str]:
        candidates = []
        if self.provider == "ollama":
            candidates = [self._ollama_tags_url(), f"{self._v1_base_url()}/models"]
        else:
            candidates = [f"{self._v1_base_url()}/models", self._ollama_tags_url()]

        last_error = None
        for url in candidates:
            try:
                return self._fetch_models(url)
            except ReportAgentError as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise ReportAgentError("No se pudieron consultar modelos disponibles.")

    def _fetch_models(self, url: str) -> List[str]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = self.session.get(url, headers=headers, timeout=20, allow_redirects=False)
            reject_redirect(response, "AI model request")
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.Timeout as exc:
            raise ReportAgentError("Tiempo de espera agotado al consultar modelos.") from exc
        except requests.exceptions.RequestException as exc:
            raise ReportAgentError(f"No se pudieron consultar modelos: {exc}") from exc
        except ValueError as exc:
            if "redirected" in str(exc):
                raise ReportAgentError(str(exc)) from exc
            raise ReportAgentError("La lista de modelos no es JSON válido.") from exc

        models = []
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            models = [item.get("id", "").strip() for item in data["data"] if item.get("id")]
        elif isinstance(data, dict) and isinstance(data.get("models"), list):
            models = [item.get("name", "").strip() for item in data["models"] if item.get("name")]

        models = [model for model in models if model]
        if not models:
            raise ReportAgentError("La instancia local no devolvió modelos disponibles.")
        return sorted(models)

    def _render_prompt(self, scope: str, context: Dict) -> str:
        language_name = i18n.report_language_name()
        translated_context = i18n.translate_data(context)
        return (
            f"Genera un informe IA de alcance {scope}.\n\n"
            "Requisitos:\n"
            f"- Usa {language_name}.\n"
            "- Redacta con buena presentación y lectura fluida.\n"
            "- Sé concreto y prioriza decisiones docentes.\n"
            "- Si detectas lagunas de datos, menciónalas sin rellenarlas.\n"
            "- Cierra con acciones priorizadas.\n"
            "- Usa Markdown simple con títulos y viñetas, no tablas.\n\n"
            "Contexto estructurado:\n"
            f"{json.dumps(translated_context, ensure_ascii=False, indent=2)}"
        )

    def _system_prompt(self) -> str:
        language_name = i18n.report_language_name()
        return (
            "You are an expert Moodle education analyst. "
            f"Write the report in {language_name}, clearly, concisely and with strong executive style, using simple Markdown. "
            "Do not invent data. If information is missing, say so explicitly. "
            "Structure the response with these blocks when they apply: "
            "# Title, ## Executive summary, ## Key findings, ## Risks, ## Recommended actions. "
            "Use short bullets, avoid tables, avoid JSON, and avoid repeating metrics without interpretation. "
            "The tone must be professional and useful for decision-making."
        )

    def _v1_base_url(self) -> str:
        return self.base_url if self.base_url.endswith("/v1") else f"{self.base_url}/v1"

    def _root_base_url(self) -> str:
        return (self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url).rstrip("/")

    def _ollama_tags_url(self) -> str:
        return f"{self._root_base_url()}/api/tags"

    def _build_course_context(self, analysis: Dict) -> Dict:
        students = analysis.get("students", [])
        high_risk = sorted(
            (
                {
                    "id_alumno": s.get("id"),
                    "riesgo": s.get("risk_level"),
                    "prob_suspenso": s.get("prediction", {}).get("risk_probability"),
                    "nota_actual_pct": s.get("metrics", {}).get("final_grade_pct"),
                    "engagement": s.get("metrics", {}).get("engagement_score"),
                }
                for s in students
            ),
            key=lambda item: item.get("prob_suspenso") or 0,
            reverse=True,
        )[:8]

        return {
            "curso": self._course_snapshot(analysis),
            "metricas_curso": analysis.get("course_metrics", {}),
            "umbral_aprobado_pct": analysis.get("pass_threshold_pct", 50.0),
            "recomendaciones_docente": analysis.get("teacher_recommendations", []),
            "top_alumnos_en_riesgo": high_risk,
            "resumen_tareas": self._assignment_snapshots(analysis, limit=8),
            "fecha_informe": datetime.now().isoformat(),
        }

    def _build_assignment_context(self, analysis: Dict, assignment_id: int) -> Dict:
        snapshot = self._assignment_snapshot(analysis, assignment_id)
        if snapshot is None:
            raise ReportAgentError("No se ha encontrado la tarea seleccionada.")

        return {
            "curso": self._course_snapshot(analysis),
            "tarea": snapshot,
            "umbral_aprobado_pct": analysis.get("pass_threshold_pct", 50.0),
            "fecha_informe": datetime.now().isoformat(),
        }

    def _build_student_context(self, analysis: Dict, student: Dict) -> Dict:
        return {
            "curso": self._course_snapshot(analysis),
            "alumno": self._student_snapshot(student),
            "umbral_aprobado_pct": analysis.get("pass_threshold_pct", 50.0),
            "fecha_informe": datetime.now().isoformat(),
        }

    def _build_student_assignment_context(
        self, analysis: Dict, student: Dict, assignment_id: int
    ) -> Dict:
        assignment = self._assignment_snapshot(analysis, assignment_id)
        if assignment is None:
            raise ReportAgentError("No se ha encontrado la tarea seleccionada.")

        submission = self._student_submission_snapshot(student, analysis, assignment_id)
        return {
            "curso": self._course_snapshot(analysis),
            "alumno": self._student_snapshot(student),
            "tarea": assignment,
            "entrega_alumno": submission,
            "umbral_aprobado_pct": analysis.get("pass_threshold_pct", 50.0),
            "fecha_informe": datetime.now().isoformat(),
        }

    def _course_snapshot(self, analysis: Dict) -> Dict:
        course = analysis.get("course", {})
        return {
            "id": course.get("id"),
            "total_alumnos": analysis.get("course_metrics", {}).get("total_students", 0),
        }

    def _student_snapshot(self, student: Dict) -> Dict:
        metrics = student.get("metrics", {})
        prediction = student.get("prediction", {})
        return {
            "id": student.get("id"),
            "riesgo": student.get("risk_level"),
            "factores_riesgo": student.get("risk_factors", []),
            "recomendaciones": student.get("recommendations", []),
            "metricas": {
                "nota_actual_pct": metrics.get("final_grade_pct"),
                "nota_predicha_pct": prediction.get("predicted_grade_pct"),
                "prob_suspenso": prediction.get("risk_probability"),
                "engagement": metrics.get("engagement_score"),
                "completitud": metrics.get("completion_rate"),
                "entregas": metrics.get("submission_rate"),
                "ultimo_acceso": metrics.get("last_access_str"),
                "dias_sin_acceso": metrics.get("days_since_access"),
            },
        }

    def _assignment_snapshots(self, analysis: Dict, limit: int = 8) -> List[Dict]:
        assignments = []
        for assignment in analysis.get("assignments", []):
            snapshot = self._assignment_snapshot(analysis, assignment.get("id"))
            if snapshot is not None:
                assignments.append(snapshot)

        assignments.sort(
            key=lambda item: (
                item.get("tasa_entrega_pct") if item.get("tasa_entrega_pct") is not None else 101,
                item.get("entregas_fuera_plazo", 0) * -1,
            )
        )
        return assignments[:limit]

    def _assignment_snapshot(self, analysis: Dict, assignment_id: Optional[int]) -> Optional[Dict]:
        if not assignment_id:
            return None

        assignment = next(
            (a for a in analysis.get("assignments", []) if a.get("id") == assignment_id),
            None,
        )
        if assignment is None:
            return None

        student_map = {s.get("id"): s for s in analysis.get("students", [])}
        submissions = analysis.get("submissions_by_assign", {}).get(assignment_id)
        if submissions is None:
            submissions = self._submissions_from_students(analysis, assignment_id)

        submitted = {}
        drafts = {}
        late = {}
        for submission in submissions:
            user_id = submission.get("userid")
            if not user_id:
                continue
            status = submission.get("status", "submitted")
            if status in ("new", "draft", "reopened"):
                drafts[user_id] = status
                continue
            submitted[user_id] = status
            due = assignment.get("duedate", 0) or 0
            ts = submission.get("timemodified", 0) or submission.get("timecreated", 0) or 0
            if due and ts and ts > due:
                late[user_id] = True

        total_students = len(student_map)
        missing_ids = [
            student_id for student_id in student_map
            if student_id not in submitted and student_id not in drafts
        ]
        return {
            "id": assignment.get("id"),
            "nombre": assignment.get("name", f"Tarea {assignment_id}"),
            "fecha_limite": self._format_timestamp(assignment.get("duedate")),
            "permite_entrega_fuera_plazo": bool(assignment.get("allowsubmissionsfromdate")),
            "total_alumnos": total_students,
            "entregas_confirmadas": len(submitted),
            "borradores": len(drafts),
            "sin_entrega": len(missing_ids),
            "entregas_fuera_plazo": len(late),
            "tasa_entrega_pct": round((len(submitted) / total_students) * 100, 1)
            if total_students else None,
            "alumnos_pendientes": [
                student_id for student_id in missing_ids[:10]
            ],
            "alumnos_con_retraso": [
                student_id for student_id in list(late.keys())[:10]
            ],
        }

    def _student_submission_snapshot(
        self, student: Dict, analysis: Dict, assignment_id: int
    ) -> Dict:
        assignment = next(
            (a for a in analysis.get("assignments", []) if a.get("id") == assignment_id),
            None,
        )
        submission = next(
            (s for s in student.get("submissions", []) if s.get("assignid") == assignment_id),
            None,
        )
        grade_item = self._match_grade_item(student.get("metrics", {}).get("grade_items", []), assignment)

        if submission is None:
            return {
                "estado": "sin entrega registrada",
                "fecha_entrega": None,
                "fuera_de_plazo": None,
                "calificacion_pct": grade_item.get("grade_pct") if grade_item else None,
            }

        due = assignment.get("duedate", 0) if assignment else 0
        ts = submission.get("timemodified", 0) or submission.get("timecreated", 0) or 0
        return {
            "estado": submission.get("status", "submitted"),
            "fecha_entrega": self._format_timestamp(ts),
            "fuera_de_plazo": bool(due and ts and ts > due),
            "calificacion_pct": grade_item.get("grade_pct") if grade_item else None,
        }

    def _match_grade_item(self, grade_items: List[Dict], assignment: Optional[Dict]) -> Optional[Dict]:
        if assignment is None:
            return None
        target_name = (assignment.get("name") or "").strip().lower()
        if not target_name:
            return None
        for item in grade_items:
            item_name = (item.get("name") or "").strip().lower()
            if item_name == target_name or target_name in item_name or item_name in target_name:
                return item
        return None

    def _submissions_from_students(self, analysis: Dict, assignment_id: int) -> List[Dict]:
        submissions = []
        for student in analysis.get("students", []):
            for submission in student.get("submissions", []):
                if submission.get("assignid") == assignment_id:
                    submissions.append(submission)
        return submissions

    @staticmethod
    def _format_timestamp(timestamp: Optional[int]) -> Optional[str]:
        if not timestamp:
            return None
        try:
            return datetime.fromtimestamp(int(timestamp)).strftime("%d/%m/%Y %H:%M")
        except (OSError, OverflowError, TypeError, ValueError):
            return None
