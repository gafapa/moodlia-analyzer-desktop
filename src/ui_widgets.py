"""Shared UI constants, helpers and reusable widget classes."""
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Dict, List, Any

import customtkinter as ctk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from . import i18n
T = i18n.translate_text

# ============================================================
# Paleta y fuentes
# ============================================================

C = {
    "bg":         "#f0f4f8",
    "bg_card":    "#ffffff",
    "bg_sidebar": "#e2e8f0",
    "fg":         "#1e293b",
    "fg_dim":     "#64748b",
    "accent":     "#2563eb",   # botones: azul oscuro + texto blanco
    "accent2":    "#0891b2",
    "tab_active": "#60a5fa",   # tabs seleccionados: azul medio + texto oscuro ✓
    "border":     "#cbd5e1",
    "high":       "#dc2626",
    "medium":     "#d97706",
    "low":        "#16a34a",
    "select":     "#dbeafe",   # filas/hover seleccionado: azul pálido
    "hover":      "#3b82f6",   # hover general: azul medio
    "btn_danger": "#b91c1c",
}

FONT_TITLE    = ("Segoe UI", 18, "bold")
FONT_SUBTITLE = ("Segoe UI", 14, "bold")
FONT_BODY     = ("Segoe UI", 13)
FONT_SMALL    = ("Segoe UI", 12)
FONT_MONO     = ("Consolas", 12)


def _style_treeview():
    """Dark-style ttk.Treeview (no CTk equivalent)."""
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Treeview",
                    background=C["bg_card"], foreground=C["fg"],
                    fieldbackground=C["bg_card"], rowheight=32,
                    font=("Segoe UI", 12), borderwidth=0)
    style.configure("Treeview.Heading",
                    background=C["bg_sidebar"], foreground=C["fg"],
                    font=("Segoe UI", 12, "bold"), relief="flat")
    style.map("Treeview",
              background=[("selected", C["select"])],
              foreground=[("selected", C["fg"])])
    style.configure("Vertical.TScrollbar",
                    background=C["bg_card"], troughcolor=C["bg_sidebar"],
                    arrowcolor=C["fg_dim"], bordercolor=C["border"],
                    width=8)


# ============================================================
# Widgets reutilizables
# ============================================================

class MetricCard(ctk.CTkFrame):
    def __init__(self, parent, title: str, value: str,
                 color: str = None, icon: str = ""):
        super().__init__(parent, fg_color=C["bg_card"], corner_radius=10,
                         border_width=1, border_color=C["border"])
        if color is None:
            color = C["fg"]
        text = f"{icon}  {title}" if icon else title
        ctk.CTkLabel(self, text=text, text_color=C["fg_dim"],
                     font=("Segoe UI", 11)).pack(anchor="w", padx=12, pady=(10, 2))
        self._val = ctk.CTkLabel(self, text=value, text_color=color,
                                 font=("Segoe UI", 24, "bold"))
        self._val.pack(anchor="w", padx=12, pady=(0, 10))

    def update(self, value: str, color: str = None):
        self._val.configure(text=value)
        if color:
            self._val.configure(text_color=color)


class ChartFrame(ctk.CTkFrame):
    """Embebe una figura matplotlib con toolbar interactiva."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=C["bg_card"], corner_radius=8, **kwargs)
        # Do not use "_canvas" because it is an internal CTkFrame attribute.
        self._mpl_canvas = None
        self._mpl_toolbar = None

    def show_figure(self, fig, show_toolbar: bool = False):
        i18n.translate_figure(fig)
        if self._mpl_canvas:
            self._mpl_canvas.get_tk_widget().destroy()
        if self._mpl_toolbar:
            self._mpl_toolbar.destroy()
        self._mpl_toolbar = None

        self._mpl_canvas = FigureCanvasTkAgg(fig, master=self)
        # Remove from pyplot's figure manager so it doesn't count against the
        # "max open figures" limit; the canvas holds its own reference.
        plt.close(fig)
        widget = self._mpl_canvas.get_tk_widget()
        widget.configure(bg=C["bg_card"])
        widget.pack(fill="both", expand=True)

        if show_toolbar:
            tb_frame = tk.Frame(self, bg=C["bg_card"])
            tb_frame.pack(fill="x")
            self._mpl_toolbar = NavigationToolbar2Tk(self._mpl_canvas, tb_frame)
            self._mpl_toolbar.config(background=C["bg_card"])
            for btn in self._mpl_toolbar.winfo_children():
                try:
                    btn.config(background=C["bg_card"], foreground=C["fg"])
                except tk.TclError:
                    pass
            self._mpl_toolbar.update()

        self._mpl_canvas.draw()

    def clear(self):
        if self._mpl_canvas:
            self._mpl_canvas.get_tk_widget().destroy()
            self._mpl_canvas = None
        if self._mpl_toolbar:
            self._mpl_toolbar.destroy()
            self._mpl_toolbar = None

    @property
    def has_figure(self) -> bool:
        return self._mpl_canvas is not None


def _div(parent, color=None, height=1):
    """Línea separadora."""
    ctk.CTkFrame(parent, fg_color=color or C["border"],
                 height=height, corner_radius=0).pack(fill="x")


def _default_ai_base_url(provider: str) -> str:
    return "http://127.0.0.1:11434" if provider == "ollama" else "http://127.0.0.1:1234"
