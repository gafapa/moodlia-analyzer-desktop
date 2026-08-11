"""
MoodlIA Analyzer Desktop
Punto de entrada principal de la aplicación.
"""
import sys
import customtkinter as ctk
from tkinter import messagebox

from src import i18n

# Las opciones de tema DEBEN configurarse antes de crear ctk.CTk()
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")
i18n.install_runtime_translations()


def main():
    root = ctk.CTk()

    def _on_close():
        import os
        # Omitir root.destroy(): destruir el intérprete Tk antes de que el GC
        # haya terminado hace que Image.__del__ / Variable.__del__ intenten
        # llamar a Tcl ya muerto → "main thread is not in main loop".
        # os._exit(0) termina el proceso de inmediato sin ejecutar __del__.
        os._exit(0)

    root.protocol("WM_DELETE_WINDOW", _on_close)

    try:
        from src.ui import MoodleAnalyzerApp
        app = MoodleAnalyzerApp(root)
        root.mainloop()
    except ImportError as e:
        messagebox.showerror(
            "Error de dependencias",
            f"Falta alguna dependencia:\n{e}\n\nEjecuta: pip install -r requirements.txt"
        )
        sys.exit(1)
    except Exception as e:
        messagebox.showerror("Error inesperado", str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
