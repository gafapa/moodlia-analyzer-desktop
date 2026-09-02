"""Student detail panel."""
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Dict, List, Any

import customtkinter as ctk

from .ui_widgets import C, FONT_TITLE, FONT_SUBTITLE, FONT_BODY, FONT_SMALL, FONT_MONO, ChartFrame, MetricCard, _div
from .analyzer import RISK_COLORS, RISK_HIGH, RISK_MEDIUM, RISK_LOW
from .report_agent import ReportAgent, ReportAgentError
from .pdf_export import export_markdown_pdf
from .report_preview import ReportPreview
from . import charts_student
from . import i18n
T = i18n.translate_text


# ============================================================
# Student detail panel
# ============================================================

POSITIVE_RECOMMENDATION = "¡Vas por buen camino! Mantén el ritmo de participación."

class StudentDetailPanel(ctk.CTkFrame):
    def __init__(self, parent, student: Dict, analysis: Dict, on_back):
        super().__init__(parent, fg_color=C["bg"], corner_radius=0)
        self._student = student
        self._analysis = analysis
        self._on_back = on_back
        self._metrics = student.get("metrics", {})
        self._prediction = student.get("prediction", {})
        self._pass_threshold_pct = float(analysis.get("pass_threshold_pct", 50.0))
        self._report_agent = ReportAgent()
        self._current_ai_report_title = f"{T('Informe de IA del alumno')} {student.get('fullname', '')}".strip()
        self._current_ai_report_markdown = ""
        self._student_ai_report_ready = False
        self._build()

    def _build(self):
        # ── Header ──
        header = ctk.CTkFrame(self, fg_color=C["bg_sidebar"], corner_radius=0, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkButton(header, text=f"← {T('Resumen')}", command=self._on_back,
                      fg_color=C["bg_card"], hover_color=C["select"],
                      text_color=C["fg"], height=34, corner_radius=8,
                      width=140, font=("Segoe UI", 12)).pack(
            side="left", padx=14, pady=9)

        risk = self._student.get("risk_level", "bajo")
        risk_labels = {"alto": "🔴  RIESGO ALTO",
                       "medio": "🟡  RIESGO MEDIO",
                       "bajo": "🟢  RIESGO BAJO"}
        risk_colors = {"alto": C["high"], "medio": C["medium"], "bajo": C["low"]}

        ctk.CTkLabel(header, text=self._student.get("fullname", ""),
                     font=("Segoe UI", 15, "bold"),
                     text_color=C["fg"]).pack(side="left", padx=14, pady=9)
        ctk.CTkLabel(header, text=risk_labels.get(risk, ""),
                     font=("Segoe UI", 12, "bold"),
                     text_color=risk_colors.get(risk, C["fg"])).pack(side="left")
        ctk.CTkLabel(header, text=f"📧  {self._student.get('email', '')}",
                     text_color=C["fg_dim"], font=("Segoe UI", 11)).pack(
            side="right", padx=14)

        _div(self)

        # ── KPIs ──
        kpi_row = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        kpi_row.pack(fill="x", padx=14, pady=10)

        m = self._metrics
        grade_pct = m.get("final_grade_pct")
        pred_pct = self._prediction.get("predicted_grade_pct", 0)

        # First row: primary metrics.
        adv = m.get("submission_avg_advance_days")
        adv_str = (f"+{adv:.1f}d" if adv and adv >= 0
                   else (f"{adv:.1f}d" if adv is not None else "N/D"))
        adv_color = (C["low"] if adv and adv >= 0
                     else (C["high"] if adv is not None else C["fg"]))

        qt = m.get("quiz_avg_time_min")
        qt_str = f"{qt:.0f} min" if qt is not None else "N/D"

        sc = m.get("session_count")
        sc_str = str(sc) if sc is not None else "N/D"
        weeks = m.get("weeks_active", 0)
        completion_total = m.get("total_activities", 0)
        submission_rate = m.get("submission_rate")
        total_forums = m.get("total_forums", 0)

        kpi_data = [
            ("Último acceso",  m.get("last_access_str", "N/D"),         C["fg"]),
            ("Nota actual",
             f"{grade_pct:.0f}%" if grade_pct is not None else "N/D",
             C["low"] if (grade_pct or 0) >= self._pass_threshold_pct else C["high"]),
            ("Nota predicha",  f"{pred_pct:.0f}%",
             C["low"] if pred_pct >= self._pass_threshold_pct else C["high"]),
            ("Engagement",     f"{m.get('engagement_score', 0):.0f}/100", C["accent"]),
            ("Actividades",
             f"{m.get('completed_activities', 0)}/{completion_total}" if completion_total else "N/D",
             C["fg"] if completion_total else C["fg_dim"]),
            ("Entregas",       f"{submission_rate:.0f}%" if submission_rate is not None else "N/D",
             C["low"] if submission_rate is not None and submission_rate >= 70
             else (C["high"] if submission_rate is not None else C["fg_dim"])),
            ("Posts foros",    str(m.get("forum_posts_count", 0)) if total_forums else "N/D",
             C["fg"] if total_forums else C["fg_dim"]),
        ]
        for i, (lbl, val, color) in enumerate(kpi_data):
            card = MetricCard(kpi_row, lbl, val, color)
            card.grid(row=0, column=i, padx=4, sticky="nsew")
            kpi_row.columnconfigure(i, weight=1)

        # Second row: session and pattern metrics.
        kpi_row2 = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        kpi_row2.pack(fill="x", padx=14, pady=(0, 6))
        kpi_data2 = [
            ("Sesiones (logs)",  sc_str,
             C["accent"] if sc else C["fg_dim"]),
            ("Antelación media", adv_str,    adv_color),
            ("Tiempo en quizzes", qt_str,    C["accent2"]),
            ("Semanas activas",  str(weeks) if weeks else "N/D", C["fg"]),
            ("Días con acceso",  str(m.get("login_days", 0)),    C["fg"]),
        ]
        for i, (lbl, val, color) in enumerate(kpi_data2):
            card = MetricCard(kpi_row2, lbl, val, color)
            card.grid(row=0, column=i, padx=4, sticky="nsew")
            kpi_row2.columnconfigure(i, weight=1)

        _div(self)

        # ── Tabs ──
        nb = ctk.CTkTabview(
            self,
            fg_color=C["bg_card"],
            segmented_button_fg_color=C["bg_sidebar"],
            segmented_button_selected_color=C["tab_active"],
            segmented_button_selected_hover_color=C["hover"],
            segmented_button_unselected_color=C["bg_sidebar"],
            segmented_button_unselected_hover_color=C["select"],
            text_color=C["fg"],
        )
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        tabs = [
            ("Perfil", self._build_tab_profile),
            ("Calificaciones", self._build_tab_grades),
            ("Actividad", self._build_tab_activity),
        ]
        if (self._metrics.get("total_quizzes") or 0) > 0:
            tabs.append(("Cuestionarios", self._build_tab_quizzes))
        if (self._metrics.get("total_assignments") or 0) > 0:
            tabs.append(("Entregas", self._build_tab_submissions))
        tabs.extend([
            ("Sesiones", self._build_tab_sessions),
            ("Predicción", self._build_tab_prediction),
            ("Percentil", self._build_tab_percentile),
            ("Alertas", self._build_tab_alerts),
            ("Informe IA", self._build_tab_ai_report),
        ])

        for title, builder in tabs:
            translated_title = T(title)
            nb.add(translated_title)
            builder(nb.tab(translated_title))

    def _student_data_rows(self) -> List[tuple[str, str]]:
        return [
            (T("Email"), self._student.get("email", T("N/D"))),
            (T("País"), self._student.get("country", T("N/D"))),
            (T("Días sin acceso"), str(self._metrics.get("days_since_access", "?"))),
            (
                T("Tareas entregadas"),
                f"{self._metrics.get('submitted_assignments', 0)} / "
                f"{self._metrics.get('total_assignments', 0)}",
            ),
            (T("Entregas tardías"), str(self._metrics.get("late_submissions", 0))),
            (T("Intentos de quiz"), str(self._metrics.get("quiz_attempts_count", 0))),
        ]

    def _prediction_info_rows(self) -> List[tuple[str, str]]:
        pred = self._prediction
        max_grade = self._metrics.get("course_total_max") or 10.0
        return [
            (T("Nota estimada"), f"{pred.get('predicted_grade', 0):.2f} / {max_grade:.0f}"),
            (T("Porcentaje estimado"), f"{pred.get('predicted_grade_pct', 0):.1f}%"),
            (T("Prob. de suspenso"), f"{pred.get('risk_probability', 0)*100:.0f}%"),
            (
                T("Método"),
                T("Machine Learning") if pred.get("method") == "ml" else T("Heurístico"),
            ),
            (
                T("Nota real actual"),
                f"{self._metrics.get('final_grade_pct', 0):.1f}%"
                if self._metrics.get("final_grade_pct") is not None
                else T("Sin datos"),
            ),
            (T("Tendencia"), T(self._metrics.get("grade_trend", "N/D").capitalize())),
        ]

    # ── Tabs detalle ──

    def _build_tab_profile(self, parent):
        paned = ctk.CTkFrame(parent, fg_color=C["bg"], corner_radius=0)
        paned.pack(fill="both", expand=True)

        left = ChartFrame(paned)
        left.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

        # Compute the course average for the radar-chart overlay
        _all = self._analysis.get("students", [])
        _radar_keys = ["engagement_score", "completion_rate", "submission_rate",
                       "on_time_rate", "quiz_avg_pct", "academic_score"]
        _course_avg: Dict = {}
        for _k in _radar_keys:
            _vals = [s["metrics"].get(_k) for s in _all
                     if s.get("metrics", {}).get(_k) is not None]
            _course_avg[_k] = round(sum(_vals) / len(_vals), 1) if _vals else 0.0
        for _k in ("total_activities", "total_assignments", "total_quizzes"):
            _course_avg[_k] = self._metrics.get(_k, 0)

        left.show_figure(charts_student.chart_student_radar(
            self._metrics, course_avg_metrics=_course_avg, figsize=(5, 4.5)))

        right = ctk.CTkScrollableFrame(paned, fg_color=C["bg"], corner_radius=0, width=290)
        right.pack(side="left", fill="both", padx=(4, 8), pady=8)

        ctk.CTkLabel(right, text=T("Factores de riesgo"),
                     font=FONT_SUBTITLE, text_color=C["fg_dim"]).pack(
            anchor="w", pady=(8, 6))

        factors = self._student.get("risk_factors", [])
        if not factors:
            ctk.CTkLabel(right, text=f"✅  {T('Sin factores de riesgo detectados')}",
                         text_color=C["low"], font=("Segoe UI", 12)).pack(
                anchor="w", pady=4)
        else:
            for f in factors:
                card = ctk.CTkFrame(right, fg_color=C["bg_card"], corner_radius=8)
                card.pack(fill="x", pady=3)
                ctk.CTkLabel(card, text="⚠  " + f, text_color=C["fg"],
                             wraplength=250, justify="left",
                             font=("Segoe UI", 12)).pack(anchor="w", padx=12, pady=10)

        ctk.CTkFrame(right, fg_color=C["border"], height=1,
                     corner_radius=0).pack(fill="x", pady=12)
        ctk.CTkLabel(right, text=T("Datos del Alumno"),
                     font=FONT_SUBTITLE, text_color=C["fg_dim"]).pack(
            anchor="w", pady=(0, 6))

        for label, value in self._student_data_rows():
            row = ctk.CTkFrame(right, fg_color=C["bg"], corner_radius=0)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{label}:", text_color=C["fg_dim"],
                         font=("Segoe UI", 11), width=130,
                         anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=value, text_color=C["fg"],
                         font=("Segoe UI", 11), anchor="w").pack(side="left")

    def _build_tab_grades(self, parent):
        cf = ChartFrame(parent)
        cf.pack(fill="both", expand=True, padx=8, pady=8)
        cf.show_figure(charts_student.chart_student_grade_timeline(
            self._metrics, figsize=(9, 4.5), pass_threshold_pct=self._pass_threshold_pct))

        items = self._metrics.get("grade_items", [])
        if items:
            table_f = ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=8)
            table_f.pack(fill="x", padx=8, pady=(0, 8))
            tree = ttk.Treeview(table_f, columns=("name", "grade", "max", "pct"),
                                show="headings", height=6)
            tree.heading("name",  text=T("Actividad"),   anchor="w")
            tree.heading("grade", text=T("Nota"),        anchor="center")
            tree.heading("max",   text=T("Máx."),        anchor="center")
            tree.heading("pct",   text="%",           anchor="center")
            tree.column("name",  width=320)
            tree.column("grade", width=90,  anchor="center")
            tree.column("max",   width=90,  anchor="center")
            tree.column("pct",   width=90,  anchor="center")
            for item in items:
                g = item.get("grade")
                p = item.get("grade_pct")
                tree.insert("", "end", values=(
                    item.get("name", ""),
                    f"{g:.2f}" if g is not None else "-",
                    f"{item.get('max_grade', 10):.1f}",
                    f"{p:.0f}%" if p is not None else "-",
                ))
            tree.pack(fill="x", padx=3, pady=3)

    def _build_tab_activity(self, parent):
        paned = ctk.CTkFrame(parent, fg_color=C["bg"], corner_radius=0)
        paned.pack(fill="both", expand=True)
        left = ChartFrame(paned)
        left.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)
        left.show_figure(charts_student.chart_student_activity_bars(
            self._metrics, figsize=(5, 4.5)))
        right = ChartFrame(paned)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        right.show_figure(charts_student.chart_student_activity_heatmap_week(
            self._metrics.get("activity_timestamps", []), figsize=(5, 4.5)))

    def _build_tab_sessions(self, parent):
        """Build session activity and assignment lead-time visualizations."""
        paned = ctk.CTkFrame(parent, fg_color=C["bg"], corner_radius=0)
        paned.pack(fill="both", expand=True)

        left = ChartFrame(paned)
        left.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)
        left.show_figure(charts_student.chart_student_weekly_activity(
            self._metrics.get("activity_timestamps", []),
            session_count=self._metrics.get("session_count"),
            avg_session_min=self._metrics.get("avg_session_duration_min"),
            weeks_active=self._metrics.get("weeks_active"),
            figsize=(5, 4.5),
        ))

        right = ChartFrame(paned)
        right.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=8)
        right.show_figure(charts_student.chart_submission_advance_bars(
            self._student.get("submissions", []),
            self._analysis.get("assignments", []),
            figsize=(5, 4.5),
        ))

    def _build_tab_quizzes(self, parent):
        cf = ChartFrame(parent)
        cf.pack(fill="both", expand=True, padx=8, pady=8)
        cf.show_figure(charts_student.chart_student_quiz_history(
            self._student.get("quiz_attempts", []),
            self._analysis.get("quizzes", []),
            figsize=(9, 4.5),
            pass_threshold_pct=self._pass_threshold_pct))

    def _build_tab_submissions(self, parent):
        cf = ChartFrame(parent)
        cf.pack(fill="both", expand=True, padx=8, pady=8)
        n_assigns = len(self._analysis.get("assignments", []))
        # Dynamic height: 0.45 per assignment, from 5 to 20 inches, with zoom available
        fig_h = max(5.0, min(20.0, n_assigns * 0.45 + 1.5))
        cf.show_figure(charts_student.chart_student_submissions_timeline(
            self._student.get("submissions", []),
            self._analysis.get("assignments", []),
            figsize=(9, fig_h)))

    def _build_tab_prediction(self, parent):
        top = ChartFrame(parent)
        top.pack(fill="x", padx=8, pady=8)
        top.show_figure(charts_student.chart_prediction_gauge(
            self._prediction, self._metrics, figsize=(9, 2.8),
            pass_threshold_pct=self._pass_threshold_pct),
            show_toolbar=False)

        info_f = ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=10)
        info_f.pack(fill="x", padx=8, pady=(0, 8))
        info_f.grid_columnconfigure((0, 1, 2), weight=1)

        for i, (label, value) in enumerate(self._prediction_info_rows()):
            col, row_n = i % 3, i // 3
            cell = ctk.CTkFrame(info_f, fg_color=C["bg_card"], corner_radius=8)
            cell.grid(row=row_n, column=col, padx=10, pady=10, sticky="nsew")
            ctk.CTkLabel(cell, text=label, text_color=C["fg_dim"],
                         font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(10, 2))
            ctk.CTkLabel(cell, text=value, text_color=C["fg"],
                         font=("Segoe UI", 12, "bold")).pack(
                anchor="w", padx=12, pady=(0, 10))

    def _build_tab_percentile(self, parent):
        """Build a horizontal chart of the student's percentile for each metric."""
        all_students = self._analysis.get("students", [])
        cf = ChartFrame(parent)
        cf.pack(fill="both", expand=True, padx=8, pady=8)
        cf.show_figure(charts_student.chart_student_percentile(
            self._student, all_students, figsize=(8, 4.5)))

    def _build_tab_alerts(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color=C["bg"], corner_radius=0)
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text=T("Recomendaciones personalizadas"),
                     font=FONT_TITLE, text_color=C["accent"]).pack(
            anchor="w", padx=16, pady=(14, 16))

        for rec in self._student.get("recommendations", []):
            card = ctk.CTkFrame(scroll, fg_color=C["bg_card"], corner_radius=10)
            card.pack(fill="x", padx=12, pady=5)
            icon = "✅" if POSITIVE_RECOMMENDATION in rec or "Vas por buen camino" in rec else "💡"
            ctk.CTkLabel(card, text=icon, font=("Segoe UI", 16)).pack(
                side="left", padx=(14, 10), pady=12)
            ctk.CTkLabel(card, text=rec, text_color=C["fg"],
                         font=("Segoe UI", 12), wraplength=560,
                         justify="left").pack(
                side="left", fill="x", expand=True, padx=(0, 14), pady=12)

        factors = self._student.get("risk_factors", [])
        if factors:
            ctk.CTkFrame(scroll, fg_color=C["border"], height=1,
                         corner_radius=0).pack(fill="x", padx=12, pady=14)
            ctk.CTkLabel(scroll, text=T("Factores de Riesgo Detectados"),
                         font=FONT_SUBTITLE, text_color=C["high"]).pack(
                anchor="w", padx=14, pady=(0, 8))
            for f in factors:
                row = ctk.CTkFrame(scroll, fg_color=C["bg_card"], corner_radius=8)
                row.pack(fill="x", padx=12, pady=3)
                ctk.CTkLabel(row, text="⚠  " + f, text_color=C["medium"],
                             font=("Segoe UI", 12),
                             wraplength=560).pack(anchor="w", padx=12, pady=10)

    def _build_tab_ai_report(self, parent):
        wrapper = ctk.CTkFrame(parent, fg_color=C["bg"], corner_radius=0)
        wrapper.pack(fill="both", expand=True)

        controls = ctk.CTkFrame(wrapper, fg_color=C["bg_card"], corner_radius=10)
        controls.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(controls, text=T("Informe de IA del alumno"),
                     font=FONT_TITLE, text_color=C["accent"]).pack(
            anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            controls,
            text=T("Genera un informe del alumno o un informe cruzado alumno/tarea."),
            text_color=C["fg_dim"], font=("Segoe UI", 11)
        ).pack(anchor="w", padx=14, pady=(0, 10))

        btn_row = ctk.CTkFrame(controls, fg_color=C["bg_card"], corner_radius=0)
        btn_row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(
            btn_row, text=T("Informe del alumno"), command=self._generate_student_ai_report,
            fg_color=C["accent"], hover_color=C["hover"], text_color="white",
            height=34, width=160
        ).pack(side="left", padx=(0, 8))

        self._student_assignment_label_map = self._build_student_assignment_label_map()
        assignment_values = list(self._student_assignment_label_map.keys()) or [T("Sin tareas disponibles")]
        self._student_assignment_var = tk.StringVar(value=assignment_values[0])
        assign_menu = ctk.CTkOptionMenu(
            btn_row,
            values=assignment_values,
            variable=self._student_assignment_var,
            fg_color=C["bg_sidebar"],
            button_color=C["accent2"],
            button_hover_color=C["hover"],
            text_color=C["fg"],
            width=260,
        )
        assign_menu.pack(side="left", padx=(0, 8))
        if not self._student_assignment_label_map:
            assign_menu.configure(state="disabled")

        ctk.CTkButton(
            btn_row, text=T("Informe alumno/tarea"), command=self._generate_student_assignment_ai_report,
            fg_color=C["accent2"], hover_color=C["hover"], text_color="white",
            height=34, width=180
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="Exportar PDF", command=self._export_student_ai_report_pdf,
            fg_color=C["bg"], border_width=1, border_color=C["accent"],
            hover_color=C["select"], text_color=C["accent"],
            height=34, width=130
        ).pack(side="right")

        self._student_ai_status = ctk.CTkLabel(
            controls, text=T("Listo para generar informes."), text_color=C["fg_dim"],
            font=("Segoe UI", 11)
        )
        self._student_ai_status.pack(anchor="w", padx=14, pady=(0, 12))

        self._student_ai_box = ReportPreview(wrapper)
        self._student_ai_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._set_detail_report_text(
            f"# {T('Informe de IA del alumno')}\n\n"
            f"{T('Pulsa uno de los botones para generar el informe.')}\n\n"
            f"## {T('Ámbitos disponibles')}\n"
            f"- {T('Alumno')}\n"
            f"- {T('Alumno/tarea')}"
        )

    def _build_student_assignment_label_map(self) -> Dict[str, int]:
        mapping = {}
        for assignment in self._analysis.get("assignments", []):
            aid = assignment.get("id")
            if not aid:
                continue
            label = f"{assignment.get('name', f'Tarea {aid}')} [{aid}]"
            mapping[label] = aid
        return mapping

    def _generate_student_ai_report(self):
        self._current_ai_report_title = f"{T('Informe del alumno')} {self._student.get('fullname', 'alumno')}"
        self._run_student_ai_report(
            lambda: ReportAgent().generate_student_report(self._analysis, self._student)
        )

    def _generate_student_assignment_ai_report(self):
        assignment_id = self._student_assignment_label_map.get(self._student_assignment_var.get())
        if not assignment_id:
            self._student_ai_status.configure(text=T("Sin tareas disponibles."), text_color=C["medium"])
            self._set_detail_report_text(T("No hay tareas disponibles para generar el informe."))
            return

        assignment = next(
            (a for a in self._analysis.get("assignments", []) if a.get("id") == assignment_id),
            {},
        )
        self._current_ai_report_title = f"{T('Informe alumno/tarea')} {self._student.get('fullname', 'alumno')} - {assignment.get('name', assignment_id)}"
        self._run_student_ai_report(
            lambda: ReportAgent().generate_student_assignment_report(
                self._analysis, self._student, assignment_id
            )
        )

    def _run_student_ai_report(self, builder):
        agent = ReportAgent()
        if not agent.is_configured():
            self._student_ai_report_ready = False
            self._student_ai_status.configure(
                text=T("Falta configurar el proveedor de IA."), text_color=C["medium"]
            )
            self._set_detail_report_text(agent.setup_message())
            return

        self._student_ai_report_ready = False
        self._student_ai_status.configure(text=T("Generando informe IA..."), text_color=C["accent"])
        self._set_detail_report_text(
            f"## {T('Generando informe IA...')}\n\n{T('Espera unos segundos.')}"
        )

        def worker():
            try:
                report = builder()
                self.after(0, lambda: self._finish_student_ai_report(report))
            except ReportAgentError as exc:
                self.after(0, lambda: self._fail_student_ai_report(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_student_ai_report(self, report: str):
        self._student_ai_report_ready = True
        self._student_ai_status.configure(text=T("Informe IA generado."), text_color=C["low"])
        self._set_detail_report_text(report)

    def _fail_student_ai_report(self, error: str):
        self._student_ai_report_ready = False
        self._student_ai_status.configure(text=T("Error al generar el informe IA."), text_color=C["high"])
        self._set_detail_report_text(T(error))

    def _export_student_ai_report_pdf(self):
        content = self._current_ai_report_markdown.strip()
        if not content or not self._student_ai_report_ready:
            messagebox.showinfo("Exportar PDF", "Genera primero un informe para exportarlo.")
            return

        path = filedialog.asksaveasfilename(
            title="Guardar informe en PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile="informe-alumno.pdf",
        )
        if not path:
            return
        try:
            export_markdown_pdf(path, self._current_ai_report_title, content)
            self._student_ai_status.configure(text="Informe exportado a PDF.", text_color=C["low"])
        except OSError as exc:
            messagebox.showerror("Exportar PDF", f"No se pudo guardar el PDF:\n{exc}")

    def _set_detail_report_text(self, text: str):
        self._current_ai_report_markdown = text
        self._student_ai_box.render(text)
