"""Course selection, loading and main analysis dashboard panels."""
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Dict, List, Any

import customtkinter as ctk

from .ui_widgets import C, FONT_TITLE, FONT_SUBTITLE, FONT_BODY, FONT_SMALL, FONT_MONO, ChartFrame, MetricCard, _div
from .moodle_client import MoodleClient, MoodleAPIError
from .analyzer import CourseAnalyzer, RISK_COLORS, RISK_HIGH, RISK_MEDIUM, RISK_LOW
from .report_agent import ReportAgent, ReportAgentError
from .pdf_export import export_markdown_pdf
from .report_preview import ReportPreview
from . import charts_course
from . import i18n
T = i18n.translate_text


# ============================================================
# Course selection panel
# ============================================================

class CourseSelectionPanel(ctk.CTkFrame):
    _MODE_MINE = "📚  Mis cursos"
    _MODE_ALL  = "🌐  Todos los cursos"

    def __init__(self, parent, client: MoodleClient, on_select, on_back=None, initial_pass_threshold_pct: float = 50.0):
        super().__init__(parent, fg_color=C["bg"], corner_radius=0)
        self._client = client
        self._on_select = on_select
        self._on_back = on_back
        self._pass_threshold_var = tk.StringVar(value=f"{float(initial_pass_threshold_pct):.0f}")
        self._mode_mine_label = f"📚  {T('Mis cursos')}"
        self._mode_all_label = f"🌐  {T('Todos los cursos')}"
        self._courses_tab_label = f"📋  {T('Cursos')}"
        self._analysis_tab_label = f"📊  {T('Análisis global')}"
        self._courses: List[Dict] = []
        self._analysis_built = False
        self._alive = True
        self._load_request_id = 0
        self._course_mode = self._mode_mine_label   # "mine" o "all"
        self._build()
        self._load_courses()

    def destroy(self):
        """Mark the panel as destroyed so callbacks cannot target a stale widget."""
        self._alive = False
        super().destroy()

    def _safe_after(self, ms, fn):
        """Schedule a callback only while the widget remains alive."""
        if self._alive:
            try:
                self.after(ms, fn)
            except tk.TclError:
                pass

    def _use_all_courses(self) -> bool:
        return self._course_mode == self._mode_all_label

    def _is_active_load(self, request_id: int) -> bool:
        return request_id == self._load_request_id

    def _build(self):
        # ── Header ──
        header = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        header.pack(fill="x", padx=18, pady=(16, 0))

        if self._on_back:
            ctk.CTkButton(header, text=f"← {T('Inicio')}", command=self._on_back,
                          fg_color=C["bg_card"], hover_color=C["select"],
                          text_color=C["fg_dim"], width=90, height=34,
                          corner_radius=8, font=("Segoe UI", 12)).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(header, text="Selecciona un curso",
                     font=("Segoe UI", 18, "bold"), text_color=C["fg"]).pack(side="left")
        ctk.CTkLabel(header, text=f"  •  {self._client.site_name}",
                     text_color=C["fg_dim"], font=("Segoe UI", 12)).pack(side="left", padx=8)
        ctk.CTkButton(header, text=f"↺ {T('Recargar')}", command=self._load_courses,
                      fg_color=C["bg_card"], hover_color=C["select"],
                      text_color=C["fg"], width=110, height=34,
                      corner_radius=8, font=("Segoe UI", 12)).pack(side="right")

        # Course source selector
        self._mode_btn = ctk.CTkSegmentedButton(
            self,
            values=[self._mode_mine_label, self._mode_all_label],
            command=self._on_course_mode_changed,
            fg_color=C["bg_sidebar"],
            selected_color=C["accent"],
            selected_hover_color=C["hover"],
            unselected_color=C["bg_sidebar"],
            unselected_hover_color=C["select"],
            text_color=C["fg"],
            font=("Segoe UI", 12),
            height=32,
        )
        self._mode_btn.set(self._mode_mine_label)
        self._mode_btn.pack(fill="x", padx=18, pady=(10, 0))

        # Main tabs: courses and global analysis.
        self._tabs = ctk.CTkTabview(
            self,
            fg_color=C["bg_card"],
            segmented_button_fg_color=C["bg_sidebar"],
            segmented_button_selected_color=C["tab_active"],
            segmented_button_selected_hover_color=C["hover"],
            segmented_button_unselected_color=C["bg_sidebar"],
            segmented_button_unselected_hover_color=C["select"],
            text_color=C["fg"],
            command=self._on_tab_change,
        )
        self._tabs.pack(fill="both", expand=True, padx=18, pady=8)
        self._tabs.add(self._courses_tab_label)
        self._tabs.add(self._analysis_tab_label)

        self._build_courses_tab(self._tabs.tab(self._courses_tab_label))

        # ── Footer siempre visible ──
        foot = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        foot.pack(fill="x", padx=18, pady=(0, 10))
        self._status = ctk.CTkLabel(foot, text="Cargando cursos...",
                                     text_color=C["fg_dim"], font=("Segoe UI", 11))
        self._status.pack(side="left")
        analyze_btn = ctk.CTkButton(
            foot, text=f"📊  {T('Analizar curso seleccionado')}",
            command=self._select, fg_color=C["low"], hover_color="#2ecc71",
            text_color="white", height=38, corner_radius=8,
            font=("Segoe UI", 12, "bold")
        )
        analyze_btn.pack(side="right")
        threshold_f = ctk.CTkFrame(foot, fg_color=C["bg"], corner_radius=0)
        threshold_f.pack(side="right", padx=(0, 20))
        ctk.CTkLabel(
            threshold_f,
            text=T("Nota mínima para aprobar (%)"),
            text_color=C["fg_dim"],
            font=("Segoe UI", 11),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkEntry(
            threshold_f,
            textvariable=self._pass_threshold_var,
            width=70,
            height=34,
            fg_color=C["bg_card"],
            border_color=C["border"],
            text_color=C["fg"],
            font=("Segoe UI", 12),
        ).pack(side="left")

    def _build_courses_tab(self, parent):
        search_f = ctk.CTkFrame(parent, fg_color=C["bg_sidebar"],
                                corner_radius=10, border_width=1,
                                border_color=C["border"])
        search_f.pack(fill="x", pady=(6, 8))
        ctk.CTkLabel(search_f, text="🔍", text_color=C["fg_dim"],
                     font=("Segoe UI", 14)).pack(side="left", padx=10)
        self._search_var = tk.StringVar()
        self._search_var.trace("w", self._filter_courses)
        ctk.CTkEntry(search_f, textvariable=self._search_var,
                     fg_color=C["bg_sidebar"], border_width=0,
                     text_color=C["fg"], placeholder_text=T("Buscar curso..."),
                     font=("Segoe UI", 12), height=38).pack(
            side="left", fill="x", expand=True, padx=6, pady=6)

        list_f = ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=10)
        list_f.pack(fill="both", expand=True)

        cols = ("name", "shortname", "category", "students")
        self._tree = ttk.Treeview(list_f, columns=cols, show="headings",
                                  selectmode="browse")
        self._tree.heading("name", text=T("Nombre del curso"), anchor="w")
        self._tree.heading("shortname", text=T("Clave"), anchor="w")
        self._tree.heading("category", text=T("Categoría"), anchor="w")
        self._tree.heading("students", text=T("Alumnos"), anchor="center")
        self._tree.column("name", width=380, minwidth=200)
        self._tree.column("shortname", width=110)
        self._tree.column("category", width=220)
        self._tree.column("students", width=90, anchor="center")

        sb = ttk.Scrollbar(list_f, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=3, pady=3)
        sb.pack(side="right", fill="y", pady=3)

        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.tag_configure("even", background=C["bg_card"])
        self._tree.tag_configure("odd", background="#f1f5f9")

    # Global analysis tab.

    def _on_tab_change(self):
        tab = self._tabs.get()
        if tab == self._analysis_tab_label and not self._analysis_built and self._courses:
            self._build_analysis_tab(self._tabs.tab(self._analysis_tab_label))

    def _build_analysis_tab(self, parent):
        self._analysis_built = True
        for w in parent.winfo_children():
            w.destroy()

        paned = ctk.CTkFrame(parent, fg_color=C["bg"], corner_radius=0)
        paned.pack(fill="both", expand=True)
        paned.columnconfigure(0, weight=3)
        paned.columnconfigure(1, weight=2)
        paned.rowconfigure(0, weight=1)

        left_f = ChartFrame(paned)
        left_f.grid(row=0, column=0, padx=(0, 4), pady=4, sticky="nsew")
        left_f.show_figure(charts_course.chart_all_courses_enrollment(self._courses))

        right_f = ChartFrame(paned)
        right_f.grid(row=0, column=1, padx=(4, 0), pady=4, sticky="nsew")
        right_f.show_figure(charts_course.chart_all_courses_categories(self._courses))

    # Course loading

    def _on_course_mode_changed(self, mode: str):
        self._course_mode = mode
        self._load_courses()

    def _load_courses(self):
        self._load_request_id += 1
        request_id = self._load_request_id
        self._status.configure(text="⏳ Cargando cursos...", text_color=C["fg_dim"])
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._analysis_built = False
        if self._tabs.get() == self._analysis_tab_label:
            self._clear_analysis_tab()
        use_all = self._use_all_courses()

        def fetch():
            try:
                courses = (self._client.get_all_courses()
                           if use_all
                           else self._client.get_my_courses())
                self._safe_after(0, lambda req=request_id, result=courses: self._populate(req, result))
            except MoodleAPIError as e:
                err = str(e)
                self._safe_after(0, lambda req=request_id, msg=err: self._show_load_error(req, msg))

        threading.Thread(target=fetch, daemon=True).start()

    def _clear_analysis_tab(self):
        analysis_tab = self._tabs.tab(self._analysis_tab_label)
        for child in analysis_tab.winfo_children():
            child.destroy()

    def _show_load_error(self, request_id: int, err: str):
        if not self._is_active_load(request_id):
            return
        self._status.configure(text=f"❌ Error: {err}", text_color=C["high"])

    def _populate(self, request_id: int, courses):
        if not self._is_active_load(request_id):
            return
        self._courses = courses
        self._status.configure(
            text=f"✅ {len(courses)} curso(s) encontrado(s)", text_color=C["low"])
        self._render_courses(courses)
        # Progressive loading of missing enrollment counts
        missing = [c for c in courses if c.get("enrolledusercount") is None]
        if missing:
            self._load_enrollment_counts(request_id, missing)
        if self._tabs.get() == self._analysis_tab_label:
            self._build_analysis_tab(self._tabs.tab(self._analysis_tab_label))

    def _load_enrollment_counts(self, request_id: int, missing: List[Dict]):
        """Load enrollment counts in the background, one row at a time."""
        total = len(missing)

        def fetch_all():
            for i, course in enumerate(missing):
                if not self._alive or not self._is_active_load(request_id):
                    return
                try:
                    count = self._client.get_enrollment_count(course["id"])
                    course["enrolledusercount"] = count
                    done = (i + 1 == total)
                    cid, idx = course["id"], i + 1
                    self._safe_after(0, lambda req=request_id, c=cid, n=count, d=done, x=idx:
                                     self._update_enrollment_in_tree(req, c, n, d, x, total))
                except Exception:
                    pass

        threading.Thread(target=fetch_all, daemon=True).start()

    def _update_enrollment_in_tree(self, request_id: int, course_id: int, count: int,
                                    done: bool, idx: int, total: int):
        if not self._alive or not self._is_active_load(request_id):
            return
        try:
            iid = str(course_id)
            if self._tree.exists(iid):
                self._tree.set(iid, "students", count)
            if done:
                self._status.configure(
                    text=f"✅ {len(self._courses)} curso(s)  —  matrículas cargadas",
                    text_color=C["low"])
            else:
                self._status.configure(
                    text=f"⏳ Cargando matrículas... {idx}/{total}",
                    text_color=C["fg_dim"])
        except tk.TclError:
            pass

    def _render_courses(self, courses):
        for row in self._tree.get_children():
            self._tree.delete(row)
        for i, c in enumerate(courses):
            tag = "even" if i % 2 == 0 else "odd"
            self._tree.insert("", "end", iid=str(c["id"]),
                              values=(
                                  c.get("fullname", ""),
                                  c.get("shortname", ""),
                                  c.get("categoryname", c.get("category", "")),
                                  c.get("enrolledusercount", "?"),
                              ), tags=(tag,))

    def _filter_courses(self, *_):
        q = self._search_var.get().lower()
        self._render_courses([c for c in self._courses
                              if q in c.get("fullname", "").lower()
                              or q in c.get("shortname", "").lower()])

    def _on_double_click(self, _):
        self._select()

    def _select(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Selección", "Selecciona un curso de la lista")
            return
        try:
            pass_threshold_pct = float(self._pass_threshold_var.get().strip().replace(",", "."))
        except ValueError:
            messagebox.showerror("Selección", "Introduce un porcentaje de aprobado válido (0-100).")
            return
        if not (0 < pass_threshold_pct <= 100):
            messagebox.showerror("Selección", "Introduce un porcentaje de aprobado válido (0-100).")
            return
        course_id = int(sel[0])
        self._on_select(course_id,
                        next((c for c in self._courses if c["id"] == course_id), {}),
                        pass_threshold_pct)


# ============================================================
# Progress panel
# ============================================================

class LoadingPanel(ctk.CTkFrame):
    def __init__(self, parent, course_name: str):
        super().__init__(parent, fg_color=C["bg"], corner_radius=0)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        center = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        center.grid(row=0, column=0)

        ctk.CTkLabel(center, text=f"⚙️  {T('Analizando curso')}",
                     font=("Segoe UI", 18, "bold"), text_color=C["fg"]).pack(pady=(0, 8))
        ctk.CTkLabel(center, text=course_name,
                     text_color=C["fg_dim"], font=("Segoe UI", 13, "bold")).pack()

        self._pb = ctk.CTkProgressBar(center, width=440, mode="determinate",
                                       fg_color=C["border"], progress_color=C["accent"],
                                       height=12, corner_radius=6)
        self._pb.set(0)
        self._pb.pack(pady=28)

        self._msg = ctk.CTkLabel(center, text=T("Iniciando..."),
                                  text_color=C["fg_dim"], font=("Segoe UI", 12))
        self._msg.pack()
        ctk.CTkLabel(center,
                     text=T("Solo se consultan datos, no se modifica nada en Moodle."),
                     text_color=C["fg_dim"], font=("Segoe UI", 11)).pack(pady=(20, 0))

    def update_progress(self, msg: str, pct: int):
        self._pb.set(pct / 100)
        self._msg.configure(text=T(msg))
        self.update_idletasks()


# ============================================================
# Course dashboard
# ============================================================

class DashboardPanel(ctk.CTkFrame):
    def __init__(self, parent, analysis: Dict, client: MoodleClient,
                 on_student_select, on_back=None):
        super().__init__(parent, fg_color=C["bg"], corner_radius=0)
        self._analysis = analysis
        self._client = client
        self._on_student_select = on_student_select
        self._on_back = on_back
        self._all_students = analysis.get("students", [])
        self._filtered_students = list(self._all_students)
        self._chart_builders: Dict = {}
        self._chart_sel_buttons: Dict = {}
        self._chart_cache: Dict = {}
        self._current_chart_name: Optional[str] = None
        self._chart_frame_single: Optional[ChartFrame] = None
        self._student_row_frames: List = []
        self._selected_student_id: Optional[int] = None
        self._pass_threshold_pct = float(analysis.get("pass_threshold_pct", 50.0))
        self._report_agent = ReportAgent()
        self._current_ai_report_title = T("Informe IA")
        self._current_ai_report_markdown = ""
        self._ai_report_ready = False
        self._build()

    def _build(self):
        course = self._analysis.get("course", {})
        cm = self._analysis.get("course_metrics", {})

        # ── Header ──
        header = ctk.CTkFrame(self, fg_color=C["bg_sidebar"], corner_radius=0, height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        if self._on_back:
            ctk.CTkButton(header, text=f"← {T('Cursos')}", command=self._on_back,
                          fg_color=C["bg_card"], hover_color=C["select"],
                          text_color=C["fg"], width=100, height=34,
                          corner_radius=8, font=("Segoe UI", 12)).pack(
                side="left", padx=14, pady=9)

        ctk.CTkLabel(header, text=f"📚  {course.get('fullname', 'Curso')}",
                     font=("Segoe UI", 15, "bold"),
                     text_color=C["accent"]).pack(side="left", pady=9)

        if self._analysis.get("ml_used"):
            ctk.CTkLabel(header, text="🤖  Predicciones ML activas",
                         text_color=C["accent2"],
                         font=("Segoe UI", 11)).pack(side="right", padx=14)

        _div(self)

        # ── KPIs ──
        kpi_f = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        kpi_f.pack(fill="x", padx=14, pady=10)

        high = cm.get("at_risk_high", 0)
        med  = cm.get("at_risk_medium", 0)
        avg_sub = cm.get("avg_submission_rate")
        kpi_data = [
            ("Total Alumnos",    str(cm.get("total_students", 0)),       C["fg"],     "👥"),
            ("Riesgo Alto",      str(high),  C["high"] if high else C["low"],          "🔴"),
            ("Riesgo Medio",     str(med),   C["medium"] if med else C["low"],         "🟡"),
            ("Engagement Medio", f"{cm.get('avg_engagement', 0):.0f}/100", C["accent"],"⚡"),
            ("Nota Media",
             f"{cm.get('avg_grade_pct'):.0f}%" if cm.get("avg_grade_pct") is not None else "N/D",
             C["accent2"], "📊"),
            ("Entregas Prom.",   f"{avg_sub:.0f}%" if avg_sub is not None else "N/D",
             C["fg"] if avg_sub is not None else C["fg_dim"], "📝"),
        ]
        for i, (title, value, color, icon) in enumerate(kpi_data):
            card = MetricCard(kpi_f, title, value, color, icon)
            card.grid(row=0, column=i, padx=5, sticky="nsew")
            kpi_f.columnconfigure(i, weight=1)

        _div(self)

        # ── Cuerpo ──
        body = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        body.pack(fill="both", expand=True)

        # Student sidebar
        sidebar = ctk.CTkFrame(body, fg_color=C["bg_sidebar"], corner_radius=0, width=280)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="Alumnos",
                     font=("Segoe UI", 13, "bold"),
                     text_color=C["fg"]).pack(anchor="w", padx=12, pady=(10, 4))

        # Risk filter
        self._risk_filter = ctk.CTkSegmentedButton(
            sidebar,
            values=[T("Todos"), "🔴", "🟡", "🟢"],
            command=lambda *_: self._apply_filter(),
            fg_color=C["bg_card"],
            selected_color=C["accent"],
            selected_hover_color=C["hover"],
            unselected_color=C["bg_card"],
            unselected_hover_color=C["select"],
            text_color=C["fg"],
            font=("Segoe UI", 12),
            height=30,
        )
        self._risk_filter.set(T("Todos"))
        self._risk_filter.pack(fill="x", padx=8, pady=(0, 6))

        # Search
        self._student_search = tk.StringVar()
        self._student_search.trace("w", lambda *_: self._apply_filter())
        ctk.CTkEntry(sidebar, textvariable=self._student_search,
                     fg_color=C["bg_card"], border_color=C["border"],
                     text_color=C["fg"], placeholder_text=f"🔍  {T('Buscar alumno...')}",
                     font=("Segoe UI", 11), height=32).pack(
            fill="x", padx=8, pady=(0, 4))

        # Cabecera columnas
        col_hdr = ctk.CTkFrame(sidebar, fg_color=C["bg_card"],
                               corner_radius=0, height=26)
        col_hdr.pack(fill="x", padx=8, pady=(0, 1))
        col_hdr.pack_propagate(False)
        ctk.CTkLabel(col_hdr, text="Alumno", anchor="w",
                     font=("Segoe UI", 11, "bold"), text_color=C["fg_dim"]).pack(
            side="left", padx=10)
        ctk.CTkLabel(col_hdr, text="Nota", anchor="e",
                     font=("Segoe UI", 11, "bold"), text_color=C["fg_dim"],
                     width=44).pack(side="right", padx=4)
        ctk.CTkLabel(col_hdr, text="Eng", anchor="center",
                     font=("Segoe UI", 11, "bold"), text_color=C["fg_dim"],
                     width=32).pack(side="right")

        # Lista scrollable
        self._student_scroll = ctk.CTkScrollableFrame(
            sidebar, fg_color=C["bg_sidebar"], corner_radius=0)
        self._student_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # ── Contenido derecho ──
        right = ctk.CTkFrame(body, fg_color=C["bg"], corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        self._dash_tabs = ctk.CTkTabview(
            right,
            fg_color=C["bg_card"],
            segmented_button_fg_color=C["bg_sidebar"],
            segmented_button_selected_color=C["tab_active"],
            segmented_button_selected_hover_color=C["hover"],
            segmented_button_unselected_color=C["bg_sidebar"],
            segmented_button_unselected_hover_color=C["select"],
            text_color=C["fg"],
            command=lambda *_: self._on_outer_tab_change(),
        )
        self._dash_tabs.pack(fill="both", expand=True, padx=8, pady=8)

        self._tab_summary = T("Resumen")
        self._tab_charts = T("Gráficas")
        self._tab_recommendations = T("Recomendaciones")
        self._tab_ai_reports = T("Informes IA")
        self._dash_tabs.add(self._tab_summary)
        self._dash_tabs.add(self._tab_charts)
        self._dash_tabs.add(self._tab_recommendations)
        self._dash_tabs.add(self._tab_ai_reports)

        self._populate_students()
        self._build_overview_tab(self._dash_tabs.tab(self._tab_summary))
        self._build_charts_tab(self._dash_tabs.tab(self._tab_charts))
        self._build_recs_tab(self._dash_tabs.tab(self._tab_recommendations))
        self._build_ai_reports_tab(self._dash_tabs.tab(self._tab_ai_reports))

    # ── Outer tab change ──

    def _on_outer_tab_change(self):
        if self._dash_tabs.get() == self._tab_charts:
            self.after(120, self._load_first_chart_if_needed)

    def _load_first_chart_if_needed(self):
        """Load the first chart when the tab is opened for the first time."""
        if self._chart_builders and self._current_chart_name is None:
            first = next(iter(self._chart_sel_buttons))
            self._select_chart(first)

    def _select_chart(self, name: str):
        """Select and render the requested chart with caching."""
        # Update button visual states
        for btn_name, btn in self._chart_sel_buttons.items():
            if btn_name == name:
                btn.configure(fg_color=C["accent"], text_color="white",
                              hover_color=C["hover"])
            else:
                btn.configure(fg_color=C["bg_card"], text_color=C["fg"],
                              hover_color=C["select"])

        if name == self._current_chart_name and (
                self._chart_frame_single and self._chart_frame_single.has_figure):
            return  # ya está visible

        self._current_chart_name = name

        # Load the figure from cache or build it
        if name not in self._chart_cache:
            builder = self._chart_builders.get(name)
            if builder is None:
                return
            self._chart_cache[name] = builder()

        if self._chart_frame_single:
            self._chart_frame_single.show_figure(self._chart_cache[name])

    # Student list

    def _populate_students(self):
        for f in self._student_row_frames:
            f.destroy()
        self._student_row_frames = []

        risk_colors_map = {"alto": C["high"], "medio": C["medium"], "bajo": C["low"]}

        for s in self._filtered_students:
            m = s.get("metrics", {})
            risk = s.get("risk_level", "bajo")
            color = risk_colors_map.get(risk, C["fg"])
            grade = m.get("final_grade_pct")
            grade_str = f"{grade:.0f}%" if grade is not None else "N/D"
            eng = f"{m.get('engagement_score', 0):.0f}"

            is_sel = s["id"] == self._selected_student_id
            row_bg = C["select"] if is_sel else C["bg_card"]

            row = ctk.CTkFrame(self._student_scroll, fg_color=row_bg,
                               corner_radius=6, height=34)
            row.pack(fill="x", pady=2)
            row.pack_propagate(False)

            # Side color bar.
            bar = ctk.CTkFrame(row, fg_color=color, corner_radius=3, width=4)
            bar.pack(side="left", fill="y", padx=(4, 6), pady=4)

            name_lbl = ctk.CTkLabel(row, text=s.get("fullname", "")[:24],
                                     font=("Segoe UI", 11), text_color=C["fg"],
                                     anchor="w")
            name_lbl.pack(side="left", fill="x", expand=True)

            grade_lbl = ctk.CTkLabel(row, text=grade_str, font=("Segoe UI", 11),
                                      text_color=color, width=44, anchor="e")
            grade_lbl.pack(side="right", padx=(0, 4))

            eng_lbl = ctk.CTkLabel(row, text=eng, font=("Segoe UI", 11),
                                    text_color=C["fg_dim"], width=32, anchor="center")
            eng_lbl.pack(side="right")

            student_ref = s
            all_widgets = [row, bar, name_lbl, grade_lbl, eng_lbl]

            def _click(e, st=student_ref):
                self._on_student_click_ctk(st)

            def _enter(e, r=row, sid=s["id"]):
                if sid != self._selected_student_id:
                    r.configure(fg_color=C["select"])

            def _leave(e, r=row, sid=s["id"]):
                if sid != self._selected_student_id:
                    r.configure(fg_color=C["bg_card"])

            for w in all_widgets:
                w.bind("<Button-1>", _click)
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)

            self._student_row_frames.append(row)

    def _on_student_click_ctk(self, student):
        old_id = self._selected_student_id
        self._selected_student_id = student["id"]
        # Update row colors
        for i, s in enumerate(self._filtered_students):
            if i < len(self._student_row_frames):
                fr = self._student_row_frames[i]
                if s["id"] == student["id"]:
                    fr.configure(fg_color=C["select"])
                elif s["id"] == old_id:
                    fr.configure(fg_color=C["bg_card"])
        self._on_student_select(student)

    def _apply_filter(self):
        risk_map = {T("Todos"): "todos", "🔴": "alto", "🟡": "medio", "🟢": "bajo"}
        risk_f = risk_map.get(self._risk_filter.get(), "todos")
        q = self._student_search.get().lower()
        self._filtered_students = [
            s for s in self._all_students
            if (risk_f == "todos" or s.get("risk_level") == risk_f)
            and q in s.get("fullname", "").lower()
        ]
        self._populate_students()

    # ── Tab Resumen ──

    def _build_overview_tab(self, parent):
        cm = self._analysis.get("course_metrics", {})
        avg_completion = cm.get("avg_completion")
        avg_submission = cm.get("avg_submission_rate")
        has_completion = bool(cm.get("has_completion"))
        has_assignments = bool(cm.get("has_assignments"))
        has_forums = bool(cm.get("has_forums"))
        scroll = ctk.CTkScrollableFrame(parent, fg_color=C["bg"])
        scroll.pack(fill="both", expand=True)

        stats = [
            ("👥", "Total de alumnos",           str(cm.get("total_students", 0))),
            ("🔴", "En riesgo alto",              f"{cm.get('at_risk_high', 0)} alumnos"),
            ("🟡", "En riesgo medio",             f"{cm.get('at_risk_medium', 0)} alumnos"),
            ("⚡", "Engagement medio",            f"{cm.get('avg_engagement', 0):.1f} / 100"),
            ("😴", "Sin acceso en 7+ días",       f"{cm.get('inactive_7d', 0)} alumnos"),
        ]
        if has_completion:
            stats.append(("✅", "Completitud media", f"{avg_completion:.1f}%" if avg_completion is not None else "N/D"))
        if has_assignments:
            stats.extend([
                ("📝", "Entrega media de tareas", f"{avg_submission:.1f}%" if avg_submission is not None else "N/D"),
                ("❌", "Sin ninguna entrega", f"{cm.get('no_submissions', 0)} alumnos"),
            ])
        if has_forums:
            stats.append(("💬", "Sin participación en foros", f"{cm.get('no_forum', 0)} alumnos"))

        ctk.CTkLabel(scroll, text="Estadísticas Generales",
                     font=FONT_SUBTITLE, text_color=C["fg_dim"]).pack(
            anchor="w", padx=14, pady=(14, 6))

        for icon, label, value in stats:
            row = ctk.CTkFrame(scroll, fg_color=C["bg_card"], corner_radius=8)
            row.pack(fill="x", padx=12, pady=3)
            ctk.CTkLabel(row, text=icon, font=("Segoe UI", 15),
                         text_color=C["fg"]).pack(side="left", padx=(14, 10), pady=10)
            ctk.CTkLabel(row, text=label, text_color=C["fg"],
                         font=("Segoe UI", 12)).pack(side="left")
            ctk.CTkLabel(row, text=value, text_color=C["accent"],
                         font=("Segoe UI", 12, "bold")).pack(side="right", padx=14)

        high_risk = [s for s in self._all_students if s.get("risk_level") == "alto"]
        if high_risk:
            ctk.CTkLabel(scroll, text=f"⚠  {T('Alumnos en riesgo alto')}",
                         font=FONT_SUBTITLE, text_color=C["high"]).pack(
                anchor="w", padx=14, pady=(20, 6))
            for s in high_risk[:10]:
                m = s.get("metrics", {})
                sub_rate = m.get("submission_rate")
                card = ctk.CTkFrame(scroll, fg_color=C["bg_card"], corner_radius=8)
                card.pack(fill="x", padx=12, pady=3)
                ctk.CTkLabel(card, text=s.get("fullname", ""),
                             font=("Segoe UI", 12, "bold"),
                             text_color=C["fg"]).pack(side="left", padx=14, pady=10)
                info = (f"Eng: {m.get('engagement_score', 0):.0f}  |  "
                        f"Acceso: {m.get('last_access_str', 'N/D')}  |  "
                        f"Entregas: {sub_rate:.0f}%" if sub_rate is not None else
                        f"Eng: {m.get('engagement_score', 0):.0f}  |  "
                        f"Acceso: {m.get('last_access_str', 'N/D')}  |  "
                        "Entregas: N/D")
                ctk.CTkLabel(card, text=info, text_color=C["fg_dim"],
                             font=("Segoe UI", 11)).pack(side="left", padx=8)
                ctk.CTkButton(card, text="Ver detalle",
                              command=lambda st=s: self._on_student_select(st),
                              fg_color=C["accent"], hover_color=C["hover"],
                              text_color="white", height=28, width=90,
                              corner_radius=6,
                              font=("Segoe UI", 11)).pack(side="right", padx=10, pady=8)

    # Charts tab

    def _build_charts_tab(self, parent):
        cm = self._analysis.get("course_metrics", {})
        chart_tabs_spec = [
            # ── Fila 1 ──
            ("Dist. Riesgo",   self._chart_risk),
            ("Engagement",     self._chart_engagement),
            ("Calificaciones", self._chart_grades),
            ("Correlación",    self._chart_scatter),
            ("Mapa de Calor",  self._chart_heatmap),
            ("Top Riesgo",     self._chart_top_risk),
            ("Corr. Métricas", self._chart_correlation),
            ("Funnel",         self._chart_funnel),
        ]
        if cm.get("has_assignments"):
            chart_tabs_spec.append(("Entregas", self._chart_submissions_heatmap))
        chart_tabs_spec.append(("Top vs Bottom", self._chart_top_bottom))
        if cm.get("has_quizzes"):
            chart_tabs_spec.append(("Cuestionarios", self._chart_quiz_difficulty))
        if cm.get("has_forums"):
            chart_tabs_spec.append(("Foros", self._chart_forum_activity))
        chart_tabs_spec.extend([
            ("Box Plot", self._chart_grade_boxplot),
            ("Real vs Pred.", self._chart_predicted_vs_actual),
            ("Burbujas", self._chart_risk_bubble),
        ])
        ROW_SIZE = 8  # primera fila: 8 botones; segunda: 7

        # Selector with two rows of buttons.
        sel_outer = ctk.CTkFrame(parent, fg_color=C["bg_sidebar"], corner_radius=8)
        sel_outer.pack(fill="x", padx=4, pady=(4, 0))

        self._chart_sel_buttons = {}
        self._chart_builders    = {}
        self._chart_cache       = {}
        self._current_chart_name = None

        for row_idx, row_start in enumerate(range(0, len(chart_tabs_spec), ROW_SIZE)):
            row_items = chart_tabs_spec[row_start:row_start + ROW_SIZE]
            row_f = ctk.CTkFrame(sel_outer, fg_color="transparent")
            row_f.pack(fill="x", padx=4, pady=(3, 0 if row_idx == 0 else 3))
            for title, builder in row_items:
                btn = ctk.CTkButton(
                    row_f, text=title, width=0, height=26,
                    corner_radius=5, font=("Segoe UI", 10),
                    fg_color=C["bg_card"], text_color=C["fg"],
                    hover_color=C["select"],
                    command=lambda t=title: self._select_chart(t),
                )
                btn.pack(side="left", padx=2, pady=2)
                self._chart_sel_buttons[title] = btn
                self._chart_builders[title] = builder

        # Shared content area.
        self._chart_frame_single = ChartFrame(parent)
        self._chart_frame_single.pack(fill="both", expand=True, padx=4, pady=(4, 4))

    def _chart_risk(self):
        return charts_course.chart_risk_donut(
            self._analysis.get("course_metrics", {}), figsize=(5, 4))

    def _chart_engagement(self):
        return charts_course.chart_engagement_histogram(
            self._all_students, figsize=(8, 4.5))

    def _chart_grades(self):
        threshold = self._analysis.get("pass_threshold_pct", 50.0)
        return charts_course.chart_grade_distribution(
            self._analysis.get("course_metrics", {}),
            figsize=(8, 4.5),
            pass_threshold_pct=threshold)

    def _chart_scatter(self):
        return charts_course.chart_scatter_engagement_vs_grade(
            self._all_students, figsize=(8, 5))

    def _chart_heatmap(self):
        return charts_course.chart_activity_heatmap(
            self._all_students, figsize=(10, 6))

    def _chart_top_risk(self):
        return charts_course.chart_top_risk_bar(
            self._all_students, figsize=(8, 5))

    def _chart_correlation(self):
        return charts_course.chart_correlation_matrix(
            self._all_students, figsize=(7, 5.5))

    def _chart_funnel(self):
        return charts_course.chart_course_funnel(
            self._all_students, figsize=(8, 4.5))

    def _chart_submissions_heatmap(self):
        return charts_course.chart_submissions_heatmap(
            self._all_students, self._analysis.get("assignments", []),
            figsize=(10, 6))

    def _chart_top_bottom(self):
        return charts_course.chart_top_bottom_comparison(
            self._all_students, figsize=(8, 4.5))

    def _chart_quiz_difficulty(self):
        return charts_course.chart_quiz_difficulty(
            self._all_students, self._analysis.get("quizzes", []),
            figsize=(8, 4.5), pass_threshold_pct=self._pass_threshold_pct)

    def _chart_forum_activity(self):
        return charts_course.chart_forum_activity(
            self._all_students, self._analysis.get("forums", []),
            figsize=(8, 4.5))

    def _chart_grade_boxplot(self):
        return charts_course.chart_grade_boxplot(
            self._all_students, figsize=(10, 5), pass_threshold_pct=self._pass_threshold_pct)

    def _chart_predicted_vs_actual(self):
        return charts_course.chart_predicted_vs_actual(
            self._all_students, figsize=(8, 4.5), pass_threshold_pct=self._pass_threshold_pct)

    def _chart_risk_bubble(self):
        return charts_course.chart_risk_bubble(
            self._all_students, figsize=(8, 5), pass_threshold_pct=self._pass_threshold_pct)

    # ── Tab Recomendaciones ──

    def _build_recs_tab(self, parent):
        recs = self._analysis.get("teacher_recommendations", [])
        scroll = ctk.CTkScrollableFrame(parent, fg_color=C["bg"])
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text=T("Recomendaciones para el docente"),
                     font=FONT_TITLE, text_color=C["accent"]).pack(
            anchor="w", padx=16, pady=(14, 16))

        if not recs:
            ctk.CTkLabel(scroll, text=f"✅  {T('No hay alertas especiales. El grupo va bien.')}",
                         text_color=C["low"], font=FONT_SUBTITLE).pack(
                anchor="w", padx=16)
            return

        for rec in recs:
            card = ctk.CTkFrame(scroll, fg_color=C["bg_card"], corner_radius=10)
            card.pack(fill="x", padx=12, pady=5)
            ctk.CTkLabel(card, text="⚠", font=("Segoe UI", 16),
                         text_color=C["medium"]).pack(side="left", padx=(14, 10), pady=12)
            ctk.CTkLabel(card, text=rec, text_color=C["fg"],
                         font=("Segoe UI", 12), wraplength=560,
                         justify="left").pack(
                side="left", fill="x", expand=True, padx=(0, 14), pady=12)

    def _build_ai_reports_tab(self, parent):
        wrapper = ctk.CTkFrame(parent, fg_color=C["bg"], corner_radius=0)
        wrapper.pack(fill="both", expand=True)

        controls = ctk.CTkFrame(wrapper, fg_color=C["bg_card"], corner_radius=10)
        controls.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(controls, text="Informes con IA",
                     font=FONT_TITLE, text_color=C["accent"]).pack(
            anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            controls,
            text="Genera informes por curso o por tarea usando un proveedor compatible con OpenAI.",
            text_color=C["fg_dim"], font=("Segoe UI", 11)
        ).pack(anchor="w", padx=14, pady=(0, 10))

        btn_row = ctk.CTkFrame(controls, fg_color=C["bg_card"], corner_radius=0)
        btn_row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(
            btn_row, text="Informe del curso", command=self._generate_course_ai_report,
            fg_color=C["accent"], hover_color=C["hover"], text_color="white",
            height=34, width=150
        ).pack(side="left", padx=(0, 8))

        self._assignment_label_map = self._build_assignment_label_map()
        assignment_values = list(self._assignment_label_map.keys()) or [T("Sin tareas disponibles")]
        self._assignment_report_var = tk.StringVar(value=assignment_values[0])
        assign_menu = ctk.CTkOptionMenu(
            btn_row,
            values=assignment_values,
            variable=self._assignment_report_var,
            fg_color=C["bg_sidebar"],
            button_color=C["accent2"],
            button_hover_color=C["hover"],
            text_color=C["fg"],
            width=260,
        )
        assign_menu.pack(side="left", padx=(0, 8))
        if not self._assignment_label_map:
            assign_menu.configure(state="disabled")

        ctk.CTkButton(
            btn_row, text="Informe de la tarea", command=self._generate_assignment_ai_report,
            fg_color=C["accent2"], hover_color=C["hover"], text_color="white",
            height=34, width=160
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="Exportar PDF", command=self._export_current_ai_report_pdf,
            fg_color=C["bg"], border_width=1, border_color=C["accent"],
            hover_color=C["select"], text_color=C["accent"],
            height=34, width=130
        ).pack(side="right")

        self._ai_report_status = ctk.CTkLabel(
            controls, text="Listo para generar informes.", text_color=C["fg_dim"],
            font=("Segoe UI", 11)
        )
        self._ai_report_status.pack(anchor="w", padx=14, pady=(0, 12))

        self._ai_report_box = ReportPreview(wrapper)
        self._ai_report_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._set_report_text(
            self._ai_report_box,
            f"# {T('Informes IA')}\n\n"
            f"{T('Pulsa uno de los botones para generar el informe.')}\n\n"
            f"## {T('Ámbitos disponibles')}\n"
            f"- {T('Curso')}\n"
            f"- {T('Tarea')}"
        )

    def _build_assignment_label_map(self) -> Dict[str, int]:
        mapping = {}
        for assignment in self._analysis.get("assignments", []):
            aid = assignment.get("id")
            if not aid:
                continue
            label = f"{assignment.get('name', f'Tarea {aid}')} [{aid}]"
            mapping[label] = aid
        return mapping

    def _generate_course_ai_report(self):
        self._current_ai_report_title = f"{T('Informe del curso')} {self._analysis.get('course', {}).get('fullname', 'curso')}"
        self._run_ai_report(
            lambda: ReportAgent().generate_course_report(self._analysis),
            self._ai_report_status,
            self._ai_report_box,
        )

    def _generate_assignment_ai_report(self):
        assignment_id = self._assignment_label_map.get(self._assignment_report_var.get())
        if not assignment_id:
            self._set_report_text(self._ai_report_box, T("Sin tareas disponibles."))
            self._ai_report_status.configure(text="Sin tareas disponibles.", text_color=C["medium"])
            return

        assignment = next(
            (a for a in self._analysis.get("assignments", []) if a.get("id") == assignment_id),
            {},
        )
        self._current_ai_report_title = f"{T('Informe de la tarea')} {assignment.get('name', assignment_id)}"
        self._run_ai_report(
            lambda: ReportAgent().generate_assignment_report(self._analysis, assignment_id),
            self._ai_report_status,
            self._ai_report_box,
        )

    def _run_ai_report(self, builder, status_label, textbox):
        agent = ReportAgent()
        if not agent.is_configured():
            self._ai_report_ready = False
            self._set_report_text(textbox, agent.setup_message())
            status_label.configure(text="Falta configurar el proveedor de IA.", text_color=C["medium"])
            return

        self._ai_report_ready = False
        status_label.configure(text="Generando informe IA...", text_color=C["accent"])
        self._set_report_text(
            textbox,
            f"## {T('Generando informe IA...')}\n\n{T('Espera unos segundos.')}"
        )

        def worker():
            try:
                report = builder()
                self.after(0, lambda: self._finish_ai_report(status_label, textbox, report))
            except ReportAgentError as exc:
                self.after(0, lambda: self._fail_ai_report(status_label, textbox, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_ai_report(self, status_label, textbox, report: str):
        self._ai_report_ready = True
        status_label.configure(text="Informe IA generado.", text_color=C["low"])
        self._set_report_text(textbox, report)

    def _fail_ai_report(self, status_label, textbox, error: str):
        self._ai_report_ready = False
        status_label.configure(text="Error al generar el informe IA.", text_color=C["high"])
        self._set_report_text(textbox, T(error))

    def _export_current_ai_report_pdf(self):
        content = self._current_ai_report_markdown.strip()
        if not content or not self._ai_report_ready:
            messagebox.showinfo("Exportar PDF", "Genera primero un informe para exportarlo.")
            return

        path = filedialog.asksaveasfilename(
            title="Guardar informe en PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile="informe-curso.pdf",
        )
        if not path:
            return
        try:
            export_markdown_pdf(path, self._current_ai_report_title, content)
            self._ai_report_status.configure(text="Informe exportado a PDF.", text_color=C["low"])
        except OSError as exc:
            messagebox.showerror("Exportar PDF", f"No se pudo guardar el PDF:\n{exc}")

    def _set_report_text(self, textbox, text: str):
        self._current_ai_report_markdown = text
        textbox.render(text)
