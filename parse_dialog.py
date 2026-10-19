"""Modal dialogs for the parse workflow."""
import os
import tkinter as tk
from tkinter import ttk, messagebox


# ===========================================================================
# Method selection + extension chooser
# ===========================================================================
class MethodSelectionDialog(tk.Toplevel):
    """Lets the user choose file extension(s) and parser methods.

    After the dialog closes, `self.result` is either None (cancelled)
    or a list of selected method keys, and `self.extensions` is a list
    of lowercase extensions (each beginning with a dot).
    """

    def __init__(self, master, methods, default_extension=".log"):
        super().__init__(master)
        self.title("Parse files")
        self.geometry("640x640")
        self.transient(master)
        self.configure(bg="white")
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.result = None
        self.extensions = None
        self._vars = {}

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        # ----- Extension row -----
        ext_frame = ttk.Frame(outer)
        ext_frame.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(ext_frame, text="File extension(s):",
                  font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

        self.ext_var = tk.StringVar(value=default_extension)
        entry = ttk.Entry(ext_frame, textvariable=self.ext_var, width=24)
        entry.pack(side=tk.LEFT, padx=(8, 8))

        ttk.Label(ext_frame,
                  text="comma-separated, e.g.  .log,.out,.txt",
                  foreground="#777").pack(side=tk.LEFT)

        # ----- Methods -----
        ttk.Label(outer, text="Choose the data to extract:",
                  font=("Segoe UI", 10, "bold")).pack(anchor=tk.W,
                                                      pady=(0, 6))

        wrap = ttk.Frame(outer)
        wrap.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(wrap, bg="white", highlightthickness=0)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(inner_id, width=e.width))

        for m in methods:
            var = tk.BooleanVar(value=True)
            self._vars[m["key"]] = var

            row = ttk.Frame(inner, padding=(0, 2))
            row.pack(fill=tk.X, pady=(0, 8))

            ttk.Checkbutton(row, text=m["name"], variable=var).pack(
                anchor=tk.W)

            desc = m.get("description", "")
            if desc:
                tk.Label(row, text=desc, bg="white", fg="#555",
                         font=("Segoe UI", 9), wraplength=520,
                         justify=tk.LEFT).pack(anchor=tk.W, padx=(22, 0))

        # ----- Bottom buttons -----
        btns = ttk.Frame(outer)
        btns.pack(fill=tk.X, pady=(12, 0))

        ttk.Button(btns, text="Select all",
                   command=self._select_all).pack(side=tk.LEFT)
        ttk.Button(btns, text="Deselect all",
                   command=self._deselect_all).pack(side=tk.LEFT,
                                                    padx=(6, 0))
        ttk.Button(btns, text="Cancel",
                   command=self._cancel).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Parse",
                   command=self._ok).pack(side=tk.RIGHT, padx=(0, 6))

        self.update_idletasks()
        self._center(master)
        self.grab_set()
        self.lift()
        self.focus_force()
        entry.focus_set()

    # ------------------------------------------------------------------
    def _center(self, master):
        try:
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width()
            mh = master.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            x = mx + (mw - w) // 2
            y = my + (mh - h) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    @staticmethod
    def _parse_extensions(raw):
        parts = [p.strip() for p in raw.replace(";", ",").split(",")]
        exts = []
        for p in parts:
            if not p:
                continue
            if not p.startswith("."):
                p = "." + p
            exts.append(p.lower())
        return exts

    def _select_all(self):
        for v in self._vars.values():
            v.set(True)

    def _deselect_all(self):
        for v in self._vars.values():
            v.set(False)

    def _ok(self):
        exts = self._parse_extensions(self.ext_var.get())
        if not exts:
            messagebox.showwarning(
                "Invalid extension",
                "Please enter at least one file extension, e.g. .log",
                parent=self)
            return
        self.extensions = exts
        self.result = [k for k, v in self._vars.items() if v.get()]
        self._close()

    def _cancel(self):
        self.result = None
        self.extensions = None
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


# ===========================================================================
# Progress
# ===========================================================================
class ParseProgressDialog(tk.Toplevel):
    """A small modal window with a progress bar and a file list."""

    def __init__(self, master, total_files):
        super().__init__(master)
        self.title("Parsing files…")
        self.geometry("680x460")
        self.transient(master)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self.total = total_files
        self.current = 0

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        self.header = ttk.Label(
            frame,
            text=f"Found {total_files} file(s). Parsing…",
            font=("Segoe UI", 10, "bold"))
        self.header.pack(anchor=tk.W, pady=(0, 8))

        self.progress = ttk.Progressbar(
            frame, mode="determinate",
            maximum=max(1, total_files))
        self.progress.pack(fill=tk.X, pady=(0, 10))

        self.status = ttk.Label(frame, text="", foreground="#333")
        self.status.pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(frame, text="Processed files:").pack(anchor=tk.W)

        list_wrap = ttk.Frame(frame)
        list_wrap.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self.listbox = tk.Listbox(list_wrap, activestyle="none",
                                  font=("Consolas", 9))
        vsb = ttk.Scrollbar(list_wrap, orient="vertical",
                            command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.update_idletasks()
        self._center(master)
        self.grab_set()
        self.lift()
        self.focus_force()

    def _center(self, master):
        try:
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width()
            mh = master.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            x = mx + (mw - w) // 2
            y = my + (mh - h) // 2
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    def update_progress(self, idx, total, filepath):
        self.current = idx
        self.progress["value"] = idx
        name = os.path.basename(filepath)
        self.status.config(text=f"[{idx}/{total}] {name}")
        self.listbox.insert(tk.END, filepath)
        self.listbox.see(tk.END)
        self.update_idletasks()

    def finish(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()