"""The ORCA Data Processor — application root."""
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from helpers import next_available_path
from orca_data import OrcaData
from welcome_screen import WelcomeScreen
from main_window import MainWindow
from parse_dialog import ParseProgressDialog, MethodSelectionDialog
from orca_parser import find_files, parse_many, PARSER_METHODS


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")


class OrcaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("The ORCA Data Processor")
        self.minsize(940, 580)

        self.configure(bg="white")
        os.makedirs(DATA_DIR, exist_ok=True)

        self.data = OrcaData()
        self._welcome = None
        self._main = None

        self._build_style()
        self._show_welcome()

    # ------------------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # ---- White backgrounds everywhere ----
        self.configure(bg="white")
        style.configure(".", background="white", foreground="#222")
        style.configure("TFrame", background="white")
        style.configure("TLabel", background="white")
        style.configure("TLabelframe", background="white")
        style.configure("TLabelframe.Label", background="white")
        style.configure("TNotebook", background="white", borderwidth=0)
        style.configure("TNotebook.Tab",
                        background="white",
                        focuscolor="white",     # hides the dotted focus ring
                        padding=(14, 6))
        style.map("TNotebook.Tab",
                  background=[("selected", "white"),
                              ("active", "white")],
                  focuscolor=[("focus", "white")])

        style.configure("Treeview",
                        rowheight=22, font=("Segoe UI", 10),
                        background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        style.configure("Summary.TLabel",
                        font=("Segoe UI", 10), foreground="#333",
                        background="white")
        style.configure("Title.TLabel",
                        font=("Segoe UI", 12, "bold"),
                        background="white")
        style.configure("Status.TLabel",
                        background="white", foreground="#333")

    # ------------------------------------------------------------------
    def _show_welcome(self):
        self.resizable(True, True)
        self._maximize()

        self._welcome = WelcomeScreen(
            self,
            on_select_json=self._welcome_select_json,
            on_parse_logs=self._parse_logs)
        self._welcome.pack(fill=tk.BOTH, expand=True)

        self.lift()
        self.focus_force()

    def _show_main(self, json_path):
        if self._welcome is not None:
            self._welcome.destroy()
            self._welcome = None

        if self._main is not None:
            self._main.destroy()
            self._main = None

        self.resizable(True, True)
        self._maximize()

        self._main = MainWindow(
            self,
            data=self.data,
            json_path=json_path,
            on_open_json=self._main_open_json,
            on_parse_logs=self._parse_logs)
        self._main.pack(fill=tk.BOTH, expand=True)

        self.lift()
        self.focus_force()

    def _maximize(self):
        self.update_idletasks()
        try:
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            self.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

    # ------------------------------------------------------------------
    def _welcome_select_json(self):
        path = filedialog.askopenfilename(
            title="Select JSON file",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self._load_json_into_main(path)

    def _main_open_json(self):
        path = filedialog.askopenfilename(
            title="Select JSON file",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        self._load_json_into_main(path)

    def _load_json_into_main(self, path):
        try:
            self.data.load(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read JSON:\n{e}")
            return
        self._show_main(path)

    # ------------------------------------------------------------------
    # Parsing (background thread + queue polled from the main thread)
    # ------------------------------------------------------------------
    def _parse_logs(self):
        directory = filedialog.askdirectory(
            title="Select directory containing files to parse")
        if not directory:
            return

        # ---- Extension + method selection ---------------------------
        sel = MethodSelectionDialog(self, PARSER_METHODS,
                                    default_extension=".log")
        self.wait_window(sel)
        if sel.result is None:      # cancelled
            return
        method_keys = sel.result
        if not method_keys:
            messagebox.showwarning(
                "Nothing selected",
                "Please select at least one data type to parse.")
            return
        extensions = sel.extensions or [".log"]

        # ---- Find matching files ------------------------------------
        files = find_files(directory, extensions)
        if not files:
            messagebox.showwarning(
                "No files found",
                f"No files with extension(s) "
                f"{', '.join(extensions)} were found in:\n{directory}")
            return

        # ---- Output path --------------------------------------------
        os.makedirs(DATA_DIR, exist_ok=True)
        target = os.path.join(DATA_DIR, "data.json")
        output_path = next_available_path(target)

        # ---- Run in a background thread -----------------------------
        dlg = ParseProgressDialog(self, len(files))
        events = queue.Queue()
        result = {}

        def progress_cb(idx, total, filepath):
            events.put(("progress", idx, total, filepath))

        def worker():
            try:
                count, errors = parse_many(
                    files, directory, output_path,
                    method_keys=method_keys,
                    progress_cb=progress_cb)
                result["count"] = count
                result["errors"] = errors
            except Exception as e:
                result["exc"] = e
            events.put(("done", None, None, None))

        def poll():
            try:
                while True:
                    kind, idx, total, fp = events.get_nowait()
                    if kind == "progress":
                        dlg.update_progress(idx, total, fp)
                    elif kind == "done":
                        dlg.finish()
                        self._on_parse_done(result, output_path)
                        return
            except queue.Empty:
                pass
            self.after(40, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.after(40, poll)

    def _on_parse_done(self, result, output_path):
        if "exc" in result:
            messagebox.showerror(
                "Parse error", f"Failed to parse:\n{result['exc']}")
            return

        count = result.get("count", 0)
        errors = result.get("errors", [])

        if errors:
            messagebox.showwarning(
                "Some files failed",
                f"{len(errors)} file(s) could not be parsed.\n"
                "First error:\n\n" + errors[0][:500])

        if count == 0:
            messagebox.showwarning(
                "Nothing parsed",
                "No .log files could be parsed successfully.")
            return

        if messagebox.askyesno(
                "Parsing complete",
                f"Parsed {count} .log file(s).\n"
                f"Saved to:\n{output_path}\n\n"
                "Load the results now?"):
            self._load_json_into_main(output_path)