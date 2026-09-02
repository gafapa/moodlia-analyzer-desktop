"""Render Markdown reports as an executive-summary preview."""
import customtkinter as ctk

from .report_formatting import parse_markdown, semantic_section_key, strip_inline_markdown


SECTION_STYLES = {
    "summary": {"fg": "#ecfeff", "border": "#14b8a6", "title": "#115e59"},
    "findings": {"fg": "#fff7ed", "border": "#f59e0b", "title": "#9a3412"},
    "risks": {"fg": "#fef2f2", "border": "#ef4444", "title": "#991b1b"},
    "actions": {"fg": "#f0fdf4", "border": "#22c55e", "title": "#166534"},
    "default": {"fg": "#f8fafc", "border": "#cbd5e1", "title": "#0f172a"},
}


class ReportPreview(ctk.CTkScrollableFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="#f8fafc", corner_radius=10, **kwargs)
        self._widgets = []

    def render(self, markdown: str):
        for widget in self._widgets:
            widget.destroy()
        self._widgets = []

        title = None
        current_section = None
        current_body = None

        for block in parse_markdown(markdown):
            if block.kind == "blank":
                continue

            text = strip_inline_markdown(block.text)
            if block.kind == "heading1":
                title = ctk.CTkLabel(
                    self, text=text, text_color="#0f172a",
                    font=("Segoe UI", 22, "bold"), anchor="w", justify="left"
                )
                title.pack(fill="x", padx=18, pady=(16, 8))
                self._widgets.append(title)
                current_section = None
                current_body = None
                continue

            if block.kind == "heading2":
                section_key = semantic_section_key(text)
                style = SECTION_STYLES[section_key]
                current_section = ctk.CTkFrame(
                    self, fg_color=style["fg"], corner_radius=12,
                    border_width=1, border_color=style["border"]
                )
                current_section.pack(fill="x", padx=14, pady=8)
                current_body = ctk.CTkFrame(current_section, fg_color="transparent", corner_radius=0)
                ctk.CTkLabel(
                    current_section, text=text, text_color=style["title"],
                    font=("Segoe UI", 15, "bold"), anchor="w", justify="left"
                ).pack(fill="x", padx=16, pady=(14, 6))
                current_body.pack(fill="x", padx=16, pady=(0, 14))
                self._widgets.append(current_section)
                continue

            container = current_body or self
            padx = 0 if current_body else 18

            if block.kind == "heading3":
                widget = ctk.CTkLabel(
                    container, text=text, text_color="#334155",
                    font=("Segoe UI", 12, "bold"), anchor="w", justify="left"
                )
                widget.pack(fill="x", padx=padx, pady=(4, 2))
            elif block.kind == "bullet":
                row = ctk.CTkFrame(container, fg_color="transparent", corner_radius=0)
                row.pack(fill="x", padx=padx, pady=2)
                ctk.CTkLabel(
                    row, text="•", width=16, text_color="#2563eb",
                    font=("Segoe UI", 12, "bold")
                ).pack(side="left", anchor="n")
                ctk.CTkLabel(
                    row, text=text, text_color="#1e293b",
                    font=("Segoe UI", 11), anchor="w", justify="left",
                    wraplength=760
                ).pack(side="left", fill="x", expand=True)
                self._widgets.append(row)
                continue
            else:
                widget = ctk.CTkLabel(
                    container, text=text, text_color="#334155",
                    font=("Segoe UI", 11), anchor="w", justify="left",
                    wraplength=760
                )
                widget.pack(fill="x", padx=padx, pady=2)

            self._widgets.append(widget)
