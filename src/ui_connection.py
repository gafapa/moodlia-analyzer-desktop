"""Connection and authentication panels: AISettingsDialog and ConnectionPanel."""
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional, Dict, List, Any

import customtkinter as ctk

from .ui_widgets import C, FONT_TITLE, FONT_SUBTITLE, FONT_BODY, FONT_SMALL, FONT_MONO, ChartFrame, MetricCard, _div, _default_ai_base_url
from .moodle_client import MoodleClient, MoodleAPIError
from .data_collector import DataCollector
from .analyzer import CourseAnalyzer, RISK_COLORS, RISK_HIGH, RISK_MEDIUM, RISK_LOW
from .report_agent import ReportAgent, ReportAgentError
from .ai_settings import load_ai_settings, save_ai_settings
from .pdf_export import export_markdown_pdf
from .report_preview import ReportPreview
from . import profiles as profile_store
from . import i18n
T = i18n.translate_text


class AISettingsDialog(ctk.CTkToplevel):
    PROVIDER_LABELS = {
        "Ollama": "ollama",
        "LM Studio": "lmstudio",
    }

    def __init__(self, parent, on_save=None):
        super().__init__(parent)
        self._on_save = on_save
        self._settings = load_ai_settings()
        self._alive = True
        self.title(T("Configurar IA local"))
        self.geometry("690x560")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        provider_label = next(
            (label for label, key in self.PROVIDER_LABELS.items()
             if key == self._settings.get("provider", "ollama")),
            "Ollama",
        )
        self._provider_var = tk.StringVar(value=provider_label)
        self._base_url_var = tk.StringVar(
            value=self._settings.get("base_url") or _default_ai_base_url(self.PROVIDER_LABELS[provider_label])
        )
        self._model_var = tk.StringVar(value=self._settings.get("model", ""))
        self._last_provider = self.PROVIDER_LABELS[provider_label]
        self._build()

    def destroy(self):
        self._alive = False
        super().destroy()

    def _safe_after(self, ms: int, callback):
        if not self._alive:
            return
        try:
            self.after(ms, callback)
        except tk.TclError:
            pass

    def _build(self):
        wrapper = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        wrapper.pack(fill="both", expand=True)

        card = ctk.CTkFrame(wrapper, fg_color=C["bg_card"], corner_radius=14)
        card.pack(fill="both", expand=True, padx=16, pady=16)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(card, text="Configuración de IA local",
                     font=FONT_TITLE, text_color=C["accent"]).grid(
            row=0, column=0, sticky="w", padx=20, pady=(18, 4))
        self._intro_hint = ctk.CTkLabel(
            card,
            text="Selecciona tu servidor local, refresca los modelos disponibles y guarda el modelo activo para los informes.",
            text_color=C["fg_dim"], font=("Segoe UI", 11), wraplength=620, justify="left"
        )
        self._intro_hint.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 14))

        form = ctk.CTkFrame(card, fg_color=C["bg_card"], corner_radius=0)
        form.grid(row=2, column=0, sticky="nsew", padx=20)
        form.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(form, text="Proveedor", text_color=C["fg"],
                     font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkOptionMenu(
            form,
            values=list(self.PROVIDER_LABELS.keys()),
            variable=self._provider_var,
            command=self._on_provider_changed,
            fg_color=C["bg_sidebar"],
            button_color=C["accent"],
            button_hover_color=C["hover"],
            text_color=C["fg"],
            width=240,
        ).grid(row=1, column=0, sticky="w", pady=(0, 14))

        self._provider_hint = ctk.CTkLabel(
            form,
            text="",
            text_color=C["fg_dim"],
            font=("Segoe UI", 11),
            justify="left",
            wraplength=620,
        )
        self._provider_hint.grid(row=2, column=0, sticky="w", pady=(0, 14))

        ctk.CTkLabel(form, text="URL base", text_color=C["fg"],
                     font=("Segoe UI", 12, "bold")).grid(
            row=3, column=0, sticky="w", pady=(0, 4))
        ctk.CTkEntry(
            form, textvariable=self._base_url_var, fg_color=C["bg"], border_color=C["border"],
            text_color=C["fg"], font=("Segoe UI", 12), width=520, height=36
        ).grid(row=4, column=0, sticky="ew", pady=(0, 6))

        self._base_url_hint = ctk.CTkLabel(
            form, text="", text_color=C["fg_dim"], font=("Segoe UI", 10)
        )
        self._base_url_hint.grid(row=5, column=0, sticky="w", pady=(0, 14))

        model_row = ctk.CTkFrame(form, fg_color=C["bg_card"], corner_radius=0)
        model_row.grid(row=6, column=0, sticky="ew")
        model_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(model_row, text="Modelo", text_color=C["fg"],
                     font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4))

        initial_values = [self._model_var.get()] if self._model_var.get() else [T("Sin modelos cargados")]
        self._model_menu = ctk.CTkOptionMenu(
            model_row,
            values=initial_values,
            variable=self._model_var,
            fg_color=C["bg_sidebar"],
            button_color=C["accent2"],
            button_hover_color=C["hover"],
            text_color=C["fg"],
            width=430,
        )
        self._model_menu.grid(row=1, column=0, sticky="ew", pady=(0, 14), padx=(0, 8))
        ctk.CTkButton(
            model_row, text="Refrescar modelos", command=self._refresh_models,
            fg_color=C["bg"], border_width=1, border_color=C["accent"],
            hover_color=C["select"], text_color=C["accent"], width=150, height=32
        ).grid(row=1, column=1, sticky="e", pady=(0, 14))

        self._local_note_hint = ctk.CTkLabel(
            form,
            text="No hace falta API key para Ollama o LM Studio en local.",
            text_color=C["accent2"], font=("Segoe UI", 11, "bold")
        )
        self._local_note_hint.grid(row=7, column=0, sticky="w", pady=(0, 6))

        self._status_lbl = ctk.CTkLabel(
            form, text="Pulsa 'Refrescar modelos' para consultar la instancia local.",
            text_color=C["fg_dim"], font=("Segoe UI", 11)
        )
        self._status_lbl.grid(row=8, column=0, sticky="w", pady=(0, 18))

        ctk.CTkFrame(card, fg_color=C["border"], height=1, corner_radius=0).grid(
            row=3, column=0, sticky="ew", padx=20, pady=(4, 12)
        )

        btn_row = ctk.CTkFrame(card, fg_color=C["bg_card"], corner_radius=0)
        btn_row.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 18))
        ctk.CTkButton(
            btn_row, text="Guardar", command=self._save,
            fg_color=C["low"], hover_color="#2ecc71", text_color="white",
            width=120, height=36
        ).pack(side="right")
        ctk.CTkButton(
            btn_row, text="Cerrar", command=self.destroy,
            fg_color=C["bg"], border_width=1, border_color=C["border"],
            hover_color=C["select"], text_color=C["fg"], width=120, height=36
        ).pack(side="right", padx=(0, 8))

        self._refresh_provider_help()

    def _on_provider_changed(self, label: str):
        provider = self.PROVIDER_LABELS[label]
        current_url = self._base_url_var.get().strip()
        previous_default = _default_ai_base_url(self._last_provider)
        if not current_url or current_url == previous_default:
            self._base_url_var.set(_default_ai_base_url(provider))
        self._last_provider = provider
        self._refresh_provider_help()
        empty_label = T("Sin modelos cargados")
        self._model_menu.configure(values=[empty_label])
        self._model_var.set(empty_label)

    def _refresh_provider_help(self):
        provider = self.PROVIDER_LABELS[self._provider_var.get()]
        if provider == "ollama":
            self._provider_hint.configure(
                text="Ollama: usa el servidor local de Ollama y detecta modelos desde `/api/tags`."
            )
            self._base_url_hint.configure(text="Recomendado: http://127.0.0.1:11434")
        else:
            self._provider_hint.configure(
                text="LM Studio: activa el servidor local OpenAI-compatible en la app y detecta modelos desde `/v1/models`."
            )
            self._base_url_hint.configure(text="Recomendado: http://127.0.0.1:1234")

    def _refresh_models(self):
        provider = self.PROVIDER_LABELS[self._provider_var.get()]
        base_url = self._base_url_var.get().strip()
        if not base_url:
            self._status_lbl.configure(text="Indica una URL base antes de refrescar modelos.", text_color=C["medium"])
            return

        self._status_lbl.configure(text="Consultando modelos...", text_color=C["accent"])

        def worker():
            try:
                agent = ReportAgent(provider=provider, base_url=base_url, model="")
                models = agent.list_available_models()
                self._safe_after(0, lambda: self._finish_refresh_models(models))
            except ReportAgentError as exc:
                self._safe_after(0, lambda: self._status_lbl.configure(text=str(exc), text_color=C["high"]))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_refresh_models(self, models: List[str]):
        values = models or [T("Sin modelos disponibles")]
        self._model_menu.configure(values=values)
        if models:
            if self._model_var.get() not in models:
                self._model_var.set(models[0])
            self._status_lbl.configure(text=f"{len(models)} modelo(s) disponibles.", text_color=C["low"])
        else:
            self._model_var.set(values[0])
            self._status_lbl.configure(text="La instancia no devolvió modelos.", text_color=C["medium"])

    def _save(self):
        provider = self.PROVIDER_LABELS[self._provider_var.get()]
        base_url = self._base_url_var.get().strip()
        model = self._model_var.get().strip()
        if not base_url:
            self._status_lbl.configure(text="La URL base es obligatoria.", text_color=C["high"])
            return
        if not model or model == T("Sin modelos cargados"):
            self._status_lbl.configure(text="Selecciona un modelo antes de guardar.", text_color=C["high"])
            return

        settings = {
            "provider": provider,
            "base_url": base_url,
            "model": model,
        }
        save_ai_settings(settings)
        self._status_lbl.configure(text="Configuración IA guardada.", text_color=C["low"])
        if self._on_save:
            self._on_save(settings)
        self.after(250, self.destroy)


# ============================================================
# Connection panel
# ============================================================

class ConnectionPanel(ctk.CTkFrame):
    def __init__(self, parent, on_connect, on_language_change=None):
        super().__init__(parent, fg_color=C["bg"], corner_radius=0)
        self._on_connect = on_connect
        self._on_language_change = on_language_change
        self._profiles: List[Dict] = profile_store.load_profiles()
        self._ai_settings = load_ai_settings()
        self._selected_idx: Optional[int] = None
        self._profile_buttons: List[ctk.CTkButton] = []
        self._language_var = tk.StringVar(value=i18n.current_language_name())
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Sidebar perfiles ──
        sidebar = ctk.CTkFrame(self, fg_color=C["bg_sidebar"], corner_radius=0, width=240)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        ctk.CTkLabel(sidebar, text="🎓 Moodle Analyzer",
                     font=("Segoe UI", 15, "bold"),
                     text_color=C["accent"]).pack(pady=(28, 4), padx=18, anchor="w")
        ctk.CTkLabel(sidebar, text="Perfiles guardados",
                     font=("Segoe UI", 11), text_color=C["fg_dim"]).pack(
            padx=18, anchor="w", pady=(0, 8))

        self._list_frame = ctk.CTkScrollableFrame(
            sidebar, fg_color=C["bg_sidebar"], corner_radius=0)
        self._list_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        btn_row = ctk.CTkFrame(sidebar, fg_color=C["bg_sidebar"], corner_radius=0)
        btn_row.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(btn_row, text="+ Nuevo", command=self._new_profile,
                      fg_color=C["bg_card"], hover_color=C["select"],
                      text_color=C["fg"], height=32, corner_radius=8,
                      font=("Segoe UI", 11)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="🗑 Borrar", command=self._delete_profile,
                      fg_color=C["bg_card"], hover_color=C["btn_danger"],
                      text_color=C["high"], height=32, corner_radius=8,
                      font=("Segoe UI", 11)).pack(side="left")

        # ── Formulario ──
        right = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        center = ctk.CTkFrame(right, fg_color=C["bg"], corner_radius=0)
        center.grid(row=0, column=0)

        header_row = ctk.CTkFrame(center, fg_color=C["bg"], corner_radius=0)
        header_row.pack(fill="x", pady=(0, 18))

        title_col = ctk.CTkFrame(header_row, fg_color=C["bg"], corner_radius=0)
        title_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title_col, text="Configuración de conexión",
                     font=("Segoe UI", 18, "bold"),
                     text_color=C["fg"]).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(title_col, text="Introduce los datos de tu instancia de Moodle",
                     text_color=C["fg_dim"], font=("Segoe UI", 12)).pack(anchor="w")

        if self._on_language_change is not None:
            ctk.CTkOptionMenu(
                header_row,
                values=list(i18n.SUPPORTED_LANGUAGES.values()),
                variable=self._language_var,
                command=self._on_language_selected,
                fg_color=C["bg_card"],
                button_color=C["accent"],
                button_hover_color=C["hover"],
                text_color=C["fg"],
                width=140,
                height=32,
            ).pack(side="right", padx=(16, 0))

        ai_row = ctk.CTkFrame(center, fg_color=C["bg"], corner_radius=0)
        ai_row.pack(fill="x", pady=(0, 16))
        ctk.CTkButton(
            ai_row, text="Configurar IA", command=self._open_ai_settings,
            fg_color=C["accent2"], hover_color=C["hover"], text_color="white",
            width=150, height=34, corner_radius=8, font=("Segoe UI", 12, "bold")
        ).pack(side="left")
        self._ai_summary_lbl = ctk.CTkLabel(
            ai_row, text="", text_color=C["fg_dim"], font=("Segoe UI", 11)
        )
        self._ai_summary_lbl.pack(side="left", padx=(12, 0))

        form = ctk.CTkFrame(center, fg_color=C["bg_card"], corner_radius=14)
        form.pack()
        form.grid_columnconfigure(0, weight=1)

        def _field(row_n, label_text):
            ctk.CTkLabel(form, text=label_text, text_color=C["fg"],
                         font=("Segoe UI", 12, "bold")).grid(
                row=row_n, column=0, sticky="w", padx=28, pady=(18, 4))

        _field(0, "Nombre del perfil")
        self._name_var = tk.StringVar()
        ctk.CTkEntry(form, textvariable=self._name_var, fg_color=C["bg"],
                     border_color=C["border"], text_color=C["fg"],
                     font=("Segoe UI", 12), width=360, height=36).grid(
            row=1, column=0, sticky="ew", padx=28, pady=(0, 4))

        _field(2, "URL de Moodle")
        self._url_var = tk.StringVar()
        ctk.CTkEntry(form, textvariable=self._url_var, fg_color=C["bg"],
                     border_color=C["border"], text_color=C["fg"],
                     font=("Segoe UI", 12), width=360, height=36,
                     placeholder_text="https://moodle.ejemplo.com").grid(
            row=3, column=0, sticky="ew", padx=28, pady=(0, 4))

        # Token header
        tok_hdr = ctk.CTkFrame(form, fg_color=C["bg_card"], corner_radius=0)
        tok_hdr.grid(row=4, column=0, sticky="ew", padx=28, pady=(10, 4))
        ctk.CTkLabel(tok_hdr, text="Token de acceso",
                     text_color=C["fg"], font=("Segoe UI", 12, "bold")).pack(side="left")
        self._show_token_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(tok_hdr, text="mostrar", variable=self._show_token_var,
                        command=self._toggle_token,
                        text_color=C["fg_dim"], font=("Segoe UI", 11),
                        checkbox_width=16, checkbox_height=16,
                        fg_color=C["accent"], hover_color=C["hover"]).pack(side="right")

        self._token_var = tk.StringVar()
        self._token_entry = ctk.CTkEntry(form, textvariable=self._token_var,
                                          fg_color=C["bg"], border_color=C["border"],
                                          text_color=C["fg"], show="•",
                                          font=("Consolas", 12), width=360, height=36)
        self._token_entry.grid(row=5, column=0, sticky="ew", padx=28, pady=(0, 6))

        ctk.CTkLabel(form,
                     text="Obtén el token en: Moodle → Preferencias → Claves de seguridad",
                     text_color=C["fg_dim"], font=("Segoe UI", 11)).grid(
            row=6, column=0, sticky="w", padx=28, pady=(0, 16))

        ctk.CTkFrame(form, fg_color=C["border"], height=1, corner_radius=0).grid(
            row=7, column=0, sticky="ew", padx=28, pady=(0, 16))

        self._username_lbl = ctk.CTkLabel(form, text="Usuario", text_color=C["fg"],
                                          font=("Segoe UI", 12, "bold"))
        self._username_lbl.grid(row=8, column=0, sticky="w", padx=28, pady=(18, 4))
        self._username_var = tk.StringVar()
        self._username_entry = ctk.CTkEntry(form, textvariable=self._username_var, fg_color=C["bg"],
                                            border_color=C["border"], text_color=C["fg"],
                                            font=("Segoe UI", 12), width=360, height=36)
        self._username_entry.grid(
            row=9, column=0, sticky="ew", padx=28, pady=(0, 4))

        self._password_header = ctk.CTkFrame(form, fg_color=C["bg_card"], corner_radius=0)
        self._password_header.grid(row=10, column=0, sticky="ew", padx=28, pady=(10, 4))
        ctk.CTkLabel(self._password_header, text="Contraseña",
                     text_color=C["fg"], font=("Segoe UI", 12, "bold")).pack(side="left")
        self._show_password_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self._password_header, text="mostrar", variable=self._show_password_var,
                        command=self._toggle_password,
                        text_color=C["fg_dim"], font=("Segoe UI", 11),
                        checkbox_width=16, checkbox_height=16,
                        fg_color=C["accent"], hover_color=C["hover"]).pack(side="right")

        self._password_var = tk.StringVar()
        self._password_entry = ctk.CTkEntry(form, textvariable=self._password_var,
                                            fg_color=C["bg"], border_color=C["border"],
                                          text_color=C["fg"], show="*",
                                            font=("Consolas", 12), width=360, height=36)
        self._password_entry.grid(row=11, column=0, sticky="ew", padx=28, pady=(0, 6))

        self._token_generation_hint = ctk.CTkLabel(
            form,
            text="Si no tienes token, deja el campo vacío y genera uno con estas credenciales usando Mobile web services.",
            text_color=C["fg_dim"], font=("Segoe UI", 11), wraplength=360, justify="left"
        )
        self._token_generation_hint.grid(row=12, column=0, sticky="w", padx=28, pady=(0, 16))

        ctk.CTkFrame(form, fg_color=C["border"], height=1, corner_radius=0).grid(
            row=13, column=0, sticky="ew", padx=28, pady=(0, 16))

        btn_f = ctk.CTkFrame(form, fg_color=C["bg_card"], corner_radius=0)
        btn_f.grid(row=14, column=0, sticky="ew", padx=28, pady=(0, 18))

        self._generate_btn = ctk.CTkButton(
            btn_f, text="Generar token", command=self._generate_token,
            fg_color=C["accent"], hover_color=C["hover"],
            text_color="white", width=150, height=38, corner_radius=8,
            font=("Segoe UI", 12, "bold"))

        self._save_btn = ctk.CTkButton(
            btn_f, text="💾 Guardar perfil", command=self._save_profile,
            fg_color=C["bg"], border_width=1, border_color=C["accent"],
            hover_color=C["select"], text_color=C["accent"],
            width=160, height=38, corner_radius=8, font=("Segoe UI", 12))
        self._save_btn.pack(side="left", padx=(0, 10))
        self._generate_btn.pack(side="left", padx=(0, 10))

        self._connect_btn = ctk.CTkButton(
            btn_f, text="▶  Conectar", command=self._connect,
            fg_color=C["low"], hover_color="#2ecc71",
            text_color="white", width=140, height=38, corner_radius=8,
            font=("Segoe UI", 12, "bold"))
        self._connect_btn.pack(side="left")

        self._status_lbl = ctk.CTkLabel(form, text="", text_color=C["medium"],
                                         font=("Segoe UI", 12))
        self._status_lbl.grid(row=15, column=0, sticky="w", padx=28, pady=(0, 10))

        self._token_generation_hint.configure(
            text="Si no tienes token, deja el campo vacío y genera uno con estas credenciales usando Mobile web services."
        )
        self._token_generation_hint.configure(
            text="Si no tienes token, deja el campo vacío y genera uno con estas credenciales usando Mobile web services."
        )
        self._token_var.trace_add("write", lambda *_: self._update_token_generation_visibility())
        self._update_token_generation_visibility()

        ctk.CTkLabel(center,
                     text="Solo se usan APIs de consulta: ningún dato se modifica en Moodle.",
                     text_color=C["fg_dim"], font=("Segoe UI", 11)).pack(
            anchor="w", pady=(12, 0))

        self._refresh_list()
        self._refresh_ai_summary()
        if self._profiles:
            self._select_profile(0)

    def _on_language_selected(self, selection: str):
        if self._on_language_change is not None:
            self._on_language_change(selection)

    # ── Perfiles ──

    def _refresh_list(self):
        for btn in self._profile_buttons:
            btn.destroy()
        self._profile_buttons = []
        sorted_p = sorted(self._profiles,
                          key=lambda p: p.get("last_used", ""), reverse=True)
        self._profiles = sorted_p
        for i, p in enumerate(sorted_p):
            btn = ctk.CTkButton(
                self._list_frame, text=f"  {p['name']}", anchor="w",
                fg_color=C["bg_sidebar"], hover_color=C["select"],
                text_color=C["fg"], height=36, corner_radius=6,
                font=("Segoe UI", 12),
                command=lambda idx=i: self._select_profile(idx))
            btn.pack(fill="x", pady=2)
            self._profile_buttons.append(btn)

    def _select_profile(self, idx: int):
        for b in self._profile_buttons:
            b.configure(fg_color=C["bg_sidebar"])
        if 0 <= idx < len(self._profile_buttons):
            self._profile_buttons[idx].configure(fg_color=C["select"])
        self._selected_idx = idx
        if 0 <= idx < len(self._profiles):
            p = self._profiles[idx]
            self._name_var.set(p.get("name", ""))
            self._url_var.set(p.get("url", ""))
            self._token_var.set(p.get("token", ""))
            self._username_var.set(p.get("username", ""))
            self._password_var.set("")
            self._status_lbl.configure(text="")

    def _new_profile(self):
        for b in self._profile_buttons:
            b.configure(fg_color=C["bg_sidebar"])
        self._selected_idx = None
        self._name_var.set("")
        self._url_var.set("https://")
        self._token_var.set("")
        self._username_var.set("")
        self._password_var.set("")
        self._status_lbl.configure(
            text="Rellena los datos y pulsa 'Guardar perfil'",
            text_color=C["medium"])

    def _save_profile(self):
        values = self._get_connection_values()
        name = values["name"]
        url = values["url"]
        token = values["token"]
        username = values["username"]
        if not name:
            self._status_lbl.configure(text="❌ El perfil necesita un nombre", text_color=C["high"])
            return
        if not url:
            self._status_lbl.configure(text="❌ La URL es obligatoria", text_color=C["high"])
            return
        if not token and not username:
            self._status_lbl.configure(text="❌ Introduce un token o un usuario", text_color=C["high"])
            return
        self._persist_profile(name, url, token, username)
        status_text = (
            f"✅ Perfil '{name}' guardado"
            if token
            else f"✅ Perfil '{name}' guardado. El token se generará al conectar"
        )
        self._status_lbl.configure(text=status_text, text_color=C["low"])

    def _delete_profile(self):
        if self._selected_idx is None or self._selected_idx >= len(self._profiles):
            messagebox.showinfo("Borrar perfil", "Selecciona un perfil de la lista")
            return
        name = self._profiles[self._selected_idx]["name"]
        if not messagebox.askyesno("Borrar perfil", f"¿Borrar el perfil '{name}'?"):
            return
        self._profiles = profile_store.delete_profile(name)
        self._selected_idx = None
        self._refresh_list()
        self._new_profile()

    def _toggle_token(self):
        self._token_entry.configure(show="" if self._show_token_var.get() else "*")

    def _toggle_password(self):
        self._password_entry.configure(show="" if self._show_password_var.get() else "*")

    def _open_ai_settings(self):
        AISettingsDialog(self.winfo_toplevel(), on_save=self._on_ai_settings_saved)

    def _on_ai_settings_saved(self, settings: Dict):
        self._ai_settings = dict(settings)
        self._refresh_ai_summary()

    def _refresh_ai_summary(self):
        provider = self._ai_settings.get("provider", "ollama")
        model = self._ai_settings.get("model") or "sin modelo"
        base_url = self._ai_settings.get("base_url") or _default_ai_base_url(provider)
        provider_label = "Ollama" if provider == "ollama" else "LM Studio"
        self._ai_summary_lbl.configure(
            text=f"IA local: {provider_label} · {model} · {base_url}"
        )

    def _update_token_generation_visibility(self):
        has_token = bool(self._token_var.get().strip())
        if has_token:
            self._generate_btn.pack_forget()
            self._username_lbl.grid_remove()
            self._username_entry.grid_remove()
            self._password_header.grid_remove()
            self._password_entry.grid_remove()
            self._token_generation_hint.grid_remove()
            return
        if not self._generate_btn.winfo_manager():
            self._generate_btn.pack(side="left", padx=(0, 10), before=self._connect_btn)
        self._username_lbl.grid()
        self._username_entry.grid()
        self._password_header.grid()
        self._password_entry.grid()
        self._token_generation_hint.grid()

    def _get_connection_values(self) -> Dict[str, str]:
        return {
            "name": self._name_var.get().strip(),
            "url": self._url_var.get().strip(),
            "token": self._token_var.get().strip(),
            "username": self._username_var.get().strip(),
            "password": self._password_var.get(),
        }

    def _persist_profile(self, name: str, url: str, token: str, username: str):
        self._profiles = profile_store.upsert_profile(name, url, token, username=username)
        self._refresh_list()
        idx = next((i for i, p in enumerate(self._profiles) if p["name"] == name), 0)
        self._select_profile(idx)

    def _set_connection_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self._connect_btn.configure(state=state)
        self._save_btn.configure(state=state)
        self._generate_btn.configure(state=state)

    def _build_client(self, url: str, token: str, username: str, password: str) -> MoodleClient:
        if token:
            return MoodleClient(url, token)
        if not username or not password:
            raise MoodleAPIError("Introduce un token o bien usuario y contraseña")
        return MoodleClient.from_credentials(
            url,
            username,
            password,
            service="moodle_mobile_app",
        )

    def _run_connection_task(self, status_text: str, worker, on_success, on_error=None):
        self._set_connection_busy(True)
        self._status_lbl.configure(text=status_text, text_color=C["medium"])
        self.update()

        def on_done(result, error):
            self._set_connection_busy(False)
            if error:
                self._status_lbl.configure(text=f"❌ {error}", text_color=C["high"])
                if on_error:
                    on_error(error)
                return
            on_success(result)

        def _run():
            try:
                result = worker()
                error = None
            except MoodleAPIError as e:
                result = None
                error = str(e)
            try:
                self.after(0, lambda: on_done(result, error))
            except tk.TclError:
                pass

        threading.Thread(target=_run, daemon=True).start()

    def _generate_token(self):
        values = self._get_connection_values()
        if not values["url"]:
            self._status_lbl.configure(text="❌ La URL es obligatoria", text_color=C["high"])
            return
        if values["token"]:
            self._status_lbl.configure(text="El perfil ya tiene un token", text_color=C["medium"])
            return
        if not values["username"] or not values["password"]:
            self._status_lbl.configure(
                text="❌ Introduce usuario y contraseña para generar el token",
                text_color=C["high"],
            )
            return

        def worker():
            return self._build_client(
                values["url"],
                "",
                values["username"],
                values["password"],
            )

        def on_success(client: MoodleClient):
            self._token_var.set(client.token)
            self._password_var.set("")
            if values["name"]:
                self._persist_profile(
                    values["name"],
                    values["url"],
                    client.token,
                    values["username"],
                )
            self._status_lbl.configure(
                text=f"✅ Token generado para: {client.site_name}",
                text_color=C["low"],
            )

        self._run_connection_task(
            "⏳ Generando token...",
            worker,
            on_success,
            on_error=lambda error: messagebox.showerror("Error al generar el token", error),
        )

    def _connect(self):
        values = self._get_connection_values()
        if not values["url"]:
            self._status_lbl.configure(text="❌ La URL es obligatoria", text_color=C["high"])
            return
        if not values["token"] and (not values["username"] or not values["password"]):
            self._status_lbl.configure(
                text="❌ Introduce un token o usuario y contraseña",
                text_color=C["high"],
            )
            return

        had_token = bool(values["token"])

        def worker():
            return self._build_client(
                values["url"],
                values["token"],
                values["username"],
                values["password"],
            )

        def on_success(client: MoodleClient):
            self._token_var.set(client.token)
            self._password_var.set("")
            if values["name"]:
                self._persist_profile(
                    values["name"],
                    values["url"],
                    client.token,
                    values["username"],
                )
            status_text = (
                f"✅ Conectado a: {client.site_name}"
                if had_token
                else f"✅ Token generado y conectado a: {client.site_name}"
            )
            self._status_lbl.configure(text=status_text, text_color=C["low"])
            self.after(400, lambda: self._on_connect(client))

        status_text = "⏳ Conectando..." if had_token else "⏳ Generando token y conectando..."
        self._run_connection_task(status_text, worker, on_success)
