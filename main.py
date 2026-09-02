"""Main entry point for MoodlIA Analyzer Desktop."""
import sys
import customtkinter as ctk
from tkinter import messagebox

from src import i18n

# Theme options must be configured before creating the CTk root.
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")
i18n.install_runtime_translations()


def main():
    root = ctk.CTk()

    def _on_close():
        import os
        # Skip root.destroy(): destroying the Tk interpreter before garbage collection
        # can leave Image.__del__ or Variable.__del__ calling a dead Tcl interpreter,
        # which raises "main thread is not in main loop".
        # os._exit(0) terminates the process immediately without running __del__.
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
