"""Main application window and entry point class."""
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Dict, List, Any

import customtkinter as ctk

from .ui_widgets import C, FONT_TITLE, FONT_SUBTITLE, FONT_BODY, FONT_SMALL, _style_treeview
from .ui_connection import ConnectionPanel
from .ui_dashboard import CourseSelectionPanel, LoadingPanel, DashboardPanel
from .ui_student import StudentDetailPanel
from .moodle_client import MoodleClient, MoodleAPIError
from .data_collector import DataCollector
from .analyzer import CourseAnalyzer, RISK_COLORS, RISK_HIGH, RISK_MEDIUM, RISK_LOW
from . import i18n
T = i18n.translate_text


# ============================================================
# Main application
# ============================================================

class MoodleAnalyzerApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self._client: Optional[MoodleClient] = None
        self._analysis: Optional[Dict] = None
        self._selected_student: Optional[Dict] = None
        self._pass_threshold_pct = 50.0
        self._current_view = "connect"
        self._loading_course: Optional[Dict] = None
        self._current_panel = None
        _style_treeview()
        self._setup_window()
        self._show_connect()   # Paso 1: conectar a Moodle

    def _setup_window(self):
        self.root.title(T("Moodle Student Analyzer"))
        self.root.geometry("1300x800")
        self.root.minsize(960, 640)

        self._statusbar_frame = ctk.CTkFrame(
            self.root, fg_color=C["bg_sidebar"], corner_radius=0, height=28)
        self._statusbar_frame.pack(side="bottom", fill="x")
        self._statusbar_frame.pack_propagate(False)

        self._statusbar = ctk.CTkLabel(
            self._statusbar_frame, text="  Sin conexión",
            fg_color="transparent", text_color=C["fg_dim"],
            font=("Segoe UI", 11), anchor="w")
        self._statusbar.pack(side="left", fill="x", expand=True, padx=4)

        self._main = ctk.CTkFrame(self.root, fg_color=C["bg"], corner_radius=0)
        self._main.pack(fill="both", expand=True)

    def _set_status(self, msg: str, color: str = None):
        self._statusbar.configure(text=f"  {msg}", text_color=color or C["fg_dim"])

    def _on_language_changed(self, selection: str):
        code = i18n.code_from_name(selection)
        if code == i18n.get_language():
            return
        i18n.set_language(code)
        self.root.after_idle(self._refresh_language)

    def _refresh_language(self):
        self.root.title(T("Moodle Student Analyzer"))
        i18n.refresh_widget_tree(self.root)
        if self._current_view == "student_detail" and self._selected_student is not None:
            self._show_student_detail(self._selected_student)
        elif self._current_view == "dashboard" and self._analysis is not None:
            self._show_dashboard()
        elif self._current_view == "loading" and self._loading_course is not None:
            loading = LoadingPanel(self._main, self._loading_course.get("fullname", "Curso"))
            self._swap_panel(loading)
        elif self._current_view == "course_selection" and self._client is not None:
            self._show_course_selection()
        else:
            self._show_connect()

    def _swap_panel(self, new_panel):
        if self._current_panel:
            self._current_panel.destroy()
        new_panel.pack(fill="both", expand=True)
        self._current_panel = new_panel

    # Main navigation

    def _show_connect(self):
        """Show the Moodle connection screen."""
        self._current_view = "connect"
        self._swap_panel(ConnectionPanel(self._main, self._on_connected, self._on_language_changed))
        self._selected_student = None
        self._set_status("Conecta a un servidor Moodle para continuar")

    def _on_connected(self, client: MoodleClient):
        """Open course selection after the client is ready."""
        self._client = client
        self._set_status(
            f"Conectado: {client.site_name}  |  {client.user_fullname}", C["low"])
        self._show_course_selection()

    def _show_course_selection(self):
        self._current_view = "course_selection"
        self._selected_student = None
        self._swap_panel(
            CourseSelectionPanel(self._main, self._client, self._on_course_selected,
                                 on_back=self._show_connect,
                                 initial_pass_threshold_pct=self._pass_threshold_pct))
        self._set_status(
            f"Conectado: {self._client.site_name}  —  Selecciona un curso para analizar")

    def _on_course_selected(self, course_id: int, course: Dict, pass_threshold_pct: float):
        self._pass_threshold_pct = float(pass_threshold_pct)
        self._current_view = "loading"
        self._loading_course = course
        loading = LoadingPanel(self._main, course.get("fullname", f"Curso {course_id}"))
        self._swap_panel(loading)
        self._set_status(f"Analizando curso: {course.get('fullname', '')}...")
        self._run_analysis(course_id, course, loading)

    def _run_analysis(self, course_id: int, course: Dict, loading_panel: LoadingPanel):
        q: "queue.Queue[Any]" = queue.Queue()

        def collect():
            try:
                collector = DataCollector(self._client)
                collector.set_progress_callback(lambda m, p: q.put(("progress", m, p)))
                raw_data = collector.collect_course_data(course_id, course_info=course)
                result = CourseAnalyzer(self._pass_threshold_pct).analyze(raw_data)
                result["assignments"] = raw_data.get("assignments", [])
                result["quizzes"] = raw_data.get("quizzes", [])
                result["forums"] = raw_data.get("forums", [])
                result["contents"] = raw_data.get("contents", [])
                result["submissions_by_assign"] = raw_data.get("submissions_by_assign", {})
                q.put(("done", result))
            except Exception as e:
                q.put(("error", str(e)))

        threading.Thread(target=collect, daemon=True).start()

        def poll():
            try:
                while True:
                    item = q.get_nowait()
                    if item[0] == "progress":
                        loading_panel.update_progress(item[1], item[2])
                    elif item[0] == "done":
                        self._analysis = item[1]
                        self._loading_course = None
                        self._show_dashboard()
                        return
                    elif item[0] == "error":
                        self._loading_course = None
                        messagebox.showerror("Error en el análisis", item[1])
                        self._show_course_selection()
                        return
            except queue.Empty:
                pass
            self.root.after(100, poll)

        self.root.after(100, poll)

    def _show_dashboard(self):
        self._current_view = "dashboard"
        self._selected_student = None
        panel = DashboardPanel(
            self._main, self._analysis, self._client,
            self._show_student_detail,
            on_back=self._show_course_selection)
        self._swap_panel(panel)
        course_name = self._analysis.get("course", {}).get("fullname", "")
        n = len(self._analysis.get("students", []))
        ml = "ML" if self._analysis.get("ml_used") else "Heurístico"
        self._set_status(
            f"Curso: {course_name}  |  {n} alumnos  |  Predicciones: {ml}", C["fg"])

    def _show_student_detail(self, student: Dict):
        self._current_view = "student_detail"
        self._selected_student = student
        self._swap_panel(
            StudentDetailPanel(self._main, student, self._analysis, self._show_dashboard))
        self._set_status(
            f"Alumno: {student.get('fullname')}  |  "
            f"Riesgo: {T(student.get('risk_level', '?')).upper()}  |  "
            f"Engagement: {student.get('metrics', {}).get('engagement_score', 0):.0f}/100",
            C["fg"])
