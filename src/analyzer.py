"""Analysis engine for metrics, predictions, and actionable recommendations."""
import math
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from .metrics import StudentMetrics, TREND_IMPROVING, TREND_STABLE, TREND_DECLINING

# Use scikit-learn when available and fall back to a heuristic otherwise.
try:
    import numpy as np
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import cross_val_score
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False


# ============================================================
# Constants
# ============================================================

RISK_HIGH = "alto"
RISK_MEDIUM = "medio"
RISK_LOW = "bajo"

RISK_COLORS = {
    RISK_HIGH: "#e74c3c",
    RISK_MEDIUM: "#f39c12",
    RISK_LOW: "#27ae60",
}

DEFAULT_PASS_THRESHOLD_PCT = 50.0


# ============================================================
# Performance predictor
# ============================================================

class GradePredictor:
    """
    Predict the final grade and classify student risk.

    Use scikit-learn when enough data is available, or a weighted heuristic
    as a fallback.
    """

    def __init__(self, pass_threshold_pct: float = DEFAULT_PASS_THRESHOLD_PCT):
        self.model_trained = False
        self.scaler = None
        self.reg_model = None
        self.clf_model = None
        self.pass_threshold_pct = float(pass_threshold_pct)

    def _extract_features(self, m: Dict) -> List[float]:
        """Build the feature vector used by the machine-learning model."""
        return [
            m.get("engagement_score", 0),
            m.get("completion_rate", 0),
            m.get("submission_rate", 0),
            m.get("on_time_rate", 0),
            m.get("quiz_avg_pct") if m.get("quiz_avg_pct") is not None else 0,
            m.get("forum_posts_count", 0),
            min(m.get("days_since_access", 999), 90),
            m.get("academic_score", 0),
        ]

    def train(self, all_student_metrics: List[Dict]):
        """Train the models with data from every student in the course."""
        if not ML_AVAILABLE:
            return

        students_with_grades = [
            m for m in all_student_metrics
            if m.get("final_grade_pct") is not None
        ]
        if len(students_with_grades) < 5:
            return

        X = [self._extract_features(m) for m in students_with_grades]
        y_grade = [m["final_grade_pct"] for m in students_with_grades]
        y_risk = [1 if m["final_grade_pct"] < self.pass_threshold_pct else 0 for m in students_with_grades]

        try:
            X_arr = np.array(X)
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X_arr)

            self.reg_model = GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42)
            self.reg_model.fit(X_scaled, y_grade)

            self.clf_model = RandomForestClassifier(n_estimators=50, random_state=42)
            self.clf_model.fit(X_scaled, y_risk)

            self.model_trained = True
        except Exception:
            self.model_trained = False

    def predict(self, metrics: Dict) -> Dict:
        """Predict a student's final grade and risk."""
        features = self._extract_features(metrics)

        if self.model_trained and ML_AVAILABLE:
            return self._predict_ml(features, metrics)
        return self._predict_heuristic(metrics)

    def _predict_ml(self, features: List[float], metrics: Dict) -> Dict:
        try:
            X = np.array([features])
            X_scaled = self.scaler.transform(X)
            predicted_grade_pct = float(self.reg_model.predict(X_scaled)[0])
            predicted_grade_pct = max(0, min(100, predicted_grade_pct))
            risk_prob = float(self.clf_model.predict_proba(X_scaled)[0][1])

            max_grade = metrics.get("course_total_max") or 10.0
            predicted_grade = (predicted_grade_pct / 100) * max_grade

            return {
                "predicted_grade": round(predicted_grade, 2),
                "predicted_grade_pct": round(predicted_grade_pct, 1),
                "risk_probability": round(risk_prob, 2),
                "method": "ml",
            }
        except Exception:
            return self._predict_heuristic(metrics)

    def _predict_heuristic(self, metrics: Dict) -> Dict:
        """Use a weighted formula when machine learning is unavailable."""
        eng = metrics.get("engagement_score", 0)
        acad = metrics.get("academic_score", 0)
        sub_rate = metrics.get("submission_rate")
        days = min(metrics.get("days_since_access", 999), 90)

        # Recent-access penalty
        access_penalty = max(0, days - 7) * 0.5

        weighted_scores = [(eng, 0.35), (acad, 0.45)]
        if sub_rate is not None:
            weighted_scores.append((sub_rate, 0.20))
        total_weight = sum(weight for _, weight in weighted_scores)
        predicted_pct = (
            sum(value * weight for value, weight in weighted_scores) / total_weight
        ) - access_penalty
        predicted_pct = max(0, min(100, predicted_pct))

        # Approximate the probability of falling below the passing threshold.
        threshold = max(self.pass_threshold_pct, 1.0)
        risk_prob = max(0, min(1, (threshold - predicted_pct) / threshold)) if predicted_pct < threshold else 0

        max_grade = metrics.get("course_total_max") or 10.0
        predicted_grade = (predicted_pct / 100) * max_grade

        return {
            "predicted_grade": round(predicted_grade, 2),
            "predicted_grade_pct": round(predicted_pct, 1),
            "risk_probability": round(risk_prob, 2),
            "method": "heuristic",
        }


# ============================================================
# Risk evaluator
# ============================================================

class RiskAssessor:
    """Determine a student's risk level and contributing factors."""

    def __init__(self, pass_threshold_pct: float = DEFAULT_PASS_THRESHOLD_PCT):
        self.pass_threshold_pct = float(pass_threshold_pct)

    def assess(self, metrics: Dict, prediction: Dict) -> Tuple[str, List[str]]:
        """Return the risk level and the list of contributing factors."""
        factors = []
        risk_points = 0

        # Factor: recent access
        days = metrics.get("days_since_access", 0)
        if days > 14:
            factors.append(f"Sin acceso desde hace {days} días")
            risk_points += 3 if days > 30 else 2
        elif days > 7:
            factors.append(f"No ha accedido en {days} días")
            risk_points += 1

        # Factor: submission rate
        sub_rate = metrics.get("submission_rate", 100)
        if metrics.get("total_assignments", 0) > 0 and sub_rate is not None:
            if sub_rate < 50:
                factors.append(f"Solo ha entregado el {sub_rate:.0f}% de las tareas")
                risk_points += 3
            elif sub_rate < 75:
                factors.append(f"Tasa de entregas baja: {sub_rate:.0f}%")
                risk_points += 1

        # Factor: current grade
        grade_pct = metrics.get("final_grade_pct")
        if grade_pct is not None:
            if grade_pct < self.pass_threshold_pct - 10:
                factors.append(f"Calificación muy baja: {grade_pct:.0f}%")
                risk_points += 3
            elif grade_pct < self.pass_threshold_pct + 5:
                factors.append(f"Calificación en riesgo de suspenso: {grade_pct:.0f}%")
                risk_points += 2

        # Factor: grade trend
        trend = metrics.get("grade_trend")
        if trend == TREND_DECLINING:
            factors.append("Tendencia de notas a la baja")
            risk_points += 2

        # Factor: low engagement
        eng = metrics.get("engagement_score", 100)
        if eng < 30:
            factors.append(f"Índice de engagement muy bajo: {eng:.0f}/100")
            risk_points += 2
        elif eng < 50:
            factors.append(f"Engagement por debajo de la media: {eng:.0f}/100")
            risk_points += 1

        # Factor: low completion
        comp_rate = metrics.get("completion_rate", 100)
        if metrics.get("total_activities", 0) > 0 and comp_rate is not None and comp_rate < 40:
            factors.append(f"Solo ha completado el {comp_rate:.0f}% de las actividades")
            risk_points += 2

        # Factor: no forum participation when forums are present
        if metrics.get("total_forums", 0) > 0 and metrics.get("forum_posts_count", 0) == 0:
            factors.append("Sin participación en foros")
            risk_points += 1

        # Factor: low quiz coverage when the course contains quizzes
        quiz_cov = metrics.get("quiz_coverage_rate")
        if metrics.get("total_quizzes", 0) > 0 and quiz_cov is not None:
            if quiz_cov < 30:
                factors.append(f"Solo ha intentado el {quiz_cov:.0f}% de los cuestionarios")
                risk_points += 2
            elif quiz_cov < 60:
                factors.append(f"Cobertura baja de cuestionarios: {quiz_cov:.0f}%")
                risk_points += 1

        # Factor: predicted risk probability
        risk_prob = prediction.get("risk_probability", 0)
        if risk_prob > 0.7:
            risk_points += 2
        elif risk_prob > 0.4:
            risk_points += 1

        # Two-stage mitigation when current and predicted grades clearly exceed the threshold
        # reduce risk proportionally to avoid false positives.
        predicted_grade_pct = prediction.get("predicted_grade_pct")
        if grade_pct is not None and predicted_grade_pct is not None:
            very_safe = (
                grade_pct >= self.pass_threshold_pct + 30
                and risk_prob < 0.2
            )
            clearly_safe = (
                grade_pct >= self.pass_threshold_pct + 20
                and predicted_grade_pct >= self.pass_threshold_pct + 10
                and risk_prob < 0.35
            )
            if very_safe:
                risk_points = max(0, risk_points - 3)
            elif clearly_safe:
                risk_points = max(0, risk_points - 2)

        # Determine the risk level.
        if risk_points >= 6:
            level = RISK_HIGH
        elif risk_points >= 3:
            level = RISK_MEDIUM
        else:
            level = RISK_LOW

        return level, factors


# ============================================================
# Recommendation generator
# ============================================================

class RecommendationEngine:
    """Generate tailored recommendations for students and the teacher."""

    def __init__(self, pass_threshold_pct: float = DEFAULT_PASS_THRESHOLD_PCT):
        self.pass_threshold_pct = float(pass_threshold_pct)

    def for_student(self, metrics: Dict, risk_level: str, risk_factors: List[str]) -> List[str]:
        """Generate student-facing recommendations."""
        recs = []

        days = metrics.get("days_since_access", 0)
        if days > 7:
            recs.append(
                f"Accede al curso cuanto antes — llevas {days} días sin conectarte."
            )

        sub_rate = metrics.get("submission_rate", 100)
        missing = metrics.get("total_assignments", 0) - metrics.get("submitted_assignments", 0)
        if metrics.get("total_assignments", 0) > 0 and missing > 0:
            recs.append(
                f"Tienes {missing} tarea(s) sin entregar. Consúltalas en la sección de tareas."
            )

        if metrics.get("late_submissions", 0) > 0:
            recs.append(
                "Has entregado tareas tarde. Organiza tu tiempo con un calendario de fechas límite."
            )

        if metrics.get("total_activities", 0) > 0 and (metrics.get("completion_rate") or 0) < 60:
            recs.append(
                "Hay materiales del curso que aún no has completado. Revisa el progreso de actividades."
            )

        quiz_avg = metrics.get("quiz_avg_pct")
        if quiz_avg is not None and quiz_avg < self.pass_threshold_pct:
            recs.append(
                "Tu rendimiento en los cuestionarios es bajo. Repasa los materiales antes de intentarlos de nuevo."
            )

        if metrics.get("quiz_trend") == TREND_DECLINING:
            recs.append("Tu rendimiento en cuestionarios está disminuyendo. Considera pedir ayuda al docente.")

        if metrics.get("total_forums", 0) > 0 and metrics.get("forum_posts_count", 0) == 0:
            recs.append(
                "Participa en los foros del curso — son una buena oportunidad para resolver dudas."
            )

        if metrics.get("grade_trend") == TREND_DECLINING:
            recs.append(
                "Tus calificaciones muestran tendencia a la baja. Revisa los últimos temas con el docente."
            )

        if not recs:
            recs.append("¡Vas por buen camino! Mantén el ritmo de participación.")

        return recs

    def for_teacher(self, all_metrics: List[Dict], course_data: Dict) -> List[str]:
        """Generate course-level recommendations for the teacher."""
        recs = []
        total = len(all_metrics)
        if total == 0:
            return recs

        high_risk = sum(1 for m in all_metrics if m.get("risk_level") == RISK_HIGH)
        no_access_7d = sum(1 for m in all_metrics if m.get("days_since_access", 0) > 7)
        avg_eng = sum(m.get("engagement_score", 0) for m in all_metrics) / total
        submission_rates = [m.get("submission_rate") for m in all_metrics if m.get("submission_rate") is not None]
        avg_sub = sum(submission_rates) / len(submission_rates) if submission_rates else None
        forum_metrics = [m for m in all_metrics if m.get("total_forums", 0) > 0]
        zero_posts = sum(1 for m in forum_metrics if m.get("forum_posts_count", 0) == 0)

        if high_risk > 0:
            recs.append(
                f"{high_risk} alumno(s) en riesgo alto — considera contactar con ellos directamente."
            )

        if no_access_7d / total > 0.3:
            recs.append(
                f"El {no_access_7d/total*100:.0f}% del alumnado lleva más de 7 días sin acceder al curso."
            )

        if avg_eng < 50:
            recs.append(
                f"El engagement medio del curso es bajo ({avg_eng:.0f}/100). Considera añadir actividades más interactivas."
            )

        if avg_sub is not None and avg_sub < 70:
            recs.append(
                f"La tasa media de entrega de tareas es del {avg_sub:.0f}%. Revisa si las instrucciones son claras."
            )

        if forum_metrics and zero_posts / len(forum_metrics) > 0.5:
            recs.append(
                "Más de la mitad del alumnado no ha participado en los foros. Incentiva la discusión."
            )

        forums = course_data.get("forums", [])
        if not forums:
            recs.append("El curso no tiene foros. Considera añadir uno para fomentar la interacción.")

        return recs


# ============================================================
# Full course analyzer
# ============================================================

class CourseAnalyzer:
    """
    Orchestrate the complete analysis of a course.

    Convert raw DataCollector output into metrics, predictions, and
    recommendations.
    """

    def __init__(self, pass_threshold_pct: float = DEFAULT_PASS_THRESHOLD_PCT):
        self.pass_threshold_pct = float(pass_threshold_pct)
        self.predictor = GradePredictor(self.pass_threshold_pct)
        self.risk_assessor = RiskAssessor(self.pass_threshold_pct)
        self.rec_engine = RecommendationEngine(self.pass_threshold_pct)

    def analyze(self, course_data: Dict) -> Dict:
        """Process course data and return the complete analysis."""
        students_raw = course_data.get("students", [])
        result_students = []
        all_metrics = []

        # Step 1: Compute individual metrics
        for student in students_raw:
            m = StudentMetrics(student, course_data).compute()
            all_metrics.append({**m, "id": student.get("id"), "fullname": student.get("fullname")})

        # Step 2: Train the predictor with course-wide data
        self.predictor.train(all_metrics)

        # Step 3: Predict risk for each student
        teacher_metrics = []
        for student, m in zip(students_raw, all_metrics):
            prediction = self.predictor.predict(m)
            risk_level, risk_factors = self.risk_assessor.assess(m, prediction)
            student_recs = self.rec_engine.for_student(m, risk_level, risk_factors)

            result = {
                **student,
                "metrics": m,
                "prediction": prediction,
                "risk_level": risk_level,
                "risk_factors": risk_factors,
                "recommendations": student_recs,
            }
            result_students.append(result)
            teacher_metrics.append({**m, "risk_level": risk_level})

        # Step 4: Generate teacher recommendations
        teacher_recs = self.rec_engine.for_teacher(teacher_metrics, course_data)

        # Step 5: Compute course-wide metrics
        course_metrics = self._compute_course_metrics(teacher_metrics)

        return {
            "course": course_data.get("course", {}),
            "students": result_students,
            "course_metrics": course_metrics,
            "teacher_recommendations": teacher_recs,
            "pass_threshold_pct": self.pass_threshold_pct,
            "logs_available": course_data.get("logs_available", False),
            "ml_used": self.predictor.model_trained,
            "analyzed_at": datetime.now().isoformat(),
        }

    def _compute_course_metrics(self, all_metrics: List[Dict]) -> Dict:
        if not all_metrics:
            return {}

        n = len(all_metrics)
        has_completion = any((m.get("total_activities") or 0) > 0 for m in all_metrics)
        has_assignments = any((m.get("total_assignments") or 0) > 0 for m in all_metrics)
        has_quizzes = any((m.get("total_quizzes") or 0) > 0 for m in all_metrics)
        has_forums = any((m.get("total_forums") or 0) > 0 for m in all_metrics)

        def safe_avg(key, default=None):
            vals = [m.get(key) for m in all_metrics if m.get(key) is not None]
            return round(sum(vals) / len(vals), 1) if vals else default

        grades = [m.get("final_grade_pct") for m in all_metrics if m.get("final_grade_pct") is not None]

        return {
            "total_students": n,
            "at_risk_high": sum(1 for m in all_metrics if m.get("risk_level") == RISK_HIGH),
            "at_risk_medium": sum(1 for m in all_metrics if m.get("risk_level") == RISK_MEDIUM),
            "at_risk_low": sum(1 for m in all_metrics if m.get("risk_level") == RISK_LOW),
            "has_completion": has_completion,
            "has_assignments": has_assignments,
            "has_quizzes": has_quizzes,
            "has_forums": has_forums,
            "avg_engagement": safe_avg("engagement_score"),
            "avg_completion": safe_avg("completion_rate"),
            "avg_submission_rate": safe_avg("submission_rate"),
            "avg_grade_pct": round(sum(grades) / len(grades), 1) if grades else None,
            "grade_distribution": self._grade_distribution(grades),
            "never_accessed": sum(1 for m in all_metrics if m.get("days_since_access", 0) > 90),
            "inactive_7d": sum(1 for m in all_metrics if m.get("days_since_access", 0) > 7),
            "no_submissions": sum(
                1 for m in all_metrics
                if m.get("total_assignments", 0) > 0 and m.get("submission_rate") == 0
            ) if has_assignments else None,
            "no_forum": sum(
                1 for m in all_metrics
                if m.get("total_forums", 0) > 0 and m.get("forum_posts_count", 0) == 0
            ) if has_forums else None,
        }

    def _grade_distribution(self, grades: List[float]) -> Dict[str, int]:
        """Group grades into percentage ranges."""
        dist = {"0-19": 0, "20-39": 0, "40-59": 0, "60-79": 0, "80-100": 0}
        for g in grades:
            if g < 20:
                dist["0-19"] += 1
            elif g < 40:
                dist["20-39"] += 1
            elif g < 60:
                dist["40-59"] += 1
            elif g < 80:
                dist["60-79"] += 1
            else:
                dist["80-100"] += 1
        return dist
