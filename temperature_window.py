"""Compare a thermochemistry quantity across temperatures.

Pick any .log/.out entry from the current JSON, choose a numeric path
inside its `thermochemistry` block, and get a table + plot of that
value versus temperature.
"""
import tkinter as tk
from tkinter import ttk, messagebox

from plot_window import open_line_plot


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _collect_paths(node, prefix, out):
    if isinstance(node, dict):
        for k, v in node.items():
            _collect_paths(v, prefix + [str(k)], out)
    elif isinstance(node, list):
        return
    elif _is_number(node):
        out.add("/".join(prefix))


def _get_at(node, path):
    cur = node
    for part in path.split("/"):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return float(cur) if _is_number(cur) else None


def _pretty(path):
    parts = path.split("/")
    out = []
    for p in parts:
        s = p.replace("_", " ")
        out.append(s[:1].upper() + s[1:] if s else s)
    return "  →  ".join(out)


class TemperatureWindow(tk.Toplevel):
    def __init__(self, master, data, current_key=None):
        super().__init__(master)
        self.title("Temperature analysis")
        self.geometry("980x640")
        self.minsize(760, 500)
        self.transient(master)
        self.configure(bg="white")

        self.data = data
        self._paths_by_display = {}
        self._current_key = current_key

        self._build_ui()
        self._refresh_file_list()
        self._refresh_quantity_list()
        self._refresh_table()

    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        row1 = ttk.Frame(outer)
        row1.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(row1, text="Log file:").pack(side=tk.LEFT)
        self.file_var = tk.StringVar()
        self.file_cb = ttk.Combobox(row1, textvariable=self.file_var,
                                    state="readonly")
        self.file_cb.pack(side=tk.LEFT, padx=(6, 0),
                          fill=tk.X, expand=True)
        self.file_cb.bind("<<ComboboxSelected>>",
                          lambda e: self._on_file_change())

        row2 = ttk.Frame(outer)
        row2.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row2, text="Quantity: ").pack(side=tk.LEFT)
        self.qty_var = tk.StringVar()
        self.qty_cb = ttk.Combobox(row2, textvariable=self.qty_var,
                                   state="readonly")
        self.qty_cb.pack(side=tk.LEFT, padx=(6, 0),
                         fill=tk.X, expand=True)
        self.qty_cb.bind("<<ComboboxSelected>>",
                         lambda e: self._refresh_table())

        ttk.Button(row2, text="Plot vs T",
                   command=self._plot).pack(side=tk.RIGHT, padx=(8, 0))

        # Table
        wrap = ttk.Frame(outer)
        wrap.pack(fill=tk.BOTH, expand=True)

        cols = ("temperature", "value", "delta")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                 selectmode="browse")
        self.tree.heading("temperature", text="Temperature (K)")
        self.tree.heading("value", text="Value")
        self.tree.heading("delta", text="Δ vs first T")
        self.tree.column("temperature", width=160, anchor=tk.CENTER)
        self.tree.column("value", width=220, anchor=tk.E)
        self.tree.column("delta", width=200, anchor=tk.E)

        vsb = ttk.Scrollbar(wrap, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.tag_configure("odd", background="#f7f7f7")

        self.status = ttk.Label(outer, text="", foreground="#555")
        self.status.pack(anchor=tk.W, pady=(6, 0))

    # ------------------------------------------------------------------
    def _refresh_file_list(self):
        keys = sorted(self.data.keys())
        self.file_cb["values"] = keys
        if not keys:
            return
        if self._current_key and self._current_key in keys:
            self.file_var.set(self._current_key)
        else:
            self.file_cb.current(0)

    def _on_file_change(self):
        self._refresh_quantity_list()
        self._refresh_table()

    def _refresh_quantity_list(self):
        key = self.file_var.get()
        entry = self.data.get(key) if key else {}
        th = entry.get("thermochemistry") or {}

        paths = set()
        for _temp, block in th.items():
            _collect_paths(block, [], paths)

        self._paths_by_display.clear()
        displays = []
        for p in sorted(paths):
            d = _pretty(p)
            if d in self._paths_by_display:
                d = f"{d}   ({p})"
            self._paths_by_display[d] = p
            displays.append(d)

        self.qty_cb["values"] = displays
        if displays:
            self.qty_cb.current(0)
        else:
            self.qty_var.set("")

    # ------------------------------------------------------------------
    def _collect(self):
        key = self.file_var.get()
        entry = self.data.get(key) if key else {}
        th = entry.get("thermochemistry") or {}
        path = self._paths_by_display.get(self.qty_var.get())
        if not path:
            return []

        rows = []
        for temp_str, block in th.items():
            try:
                temp = float(temp_str)
            except ValueError:
                continue
            val = _get_at(block, path)
            if val is None:
                continue
            rows.append((temp, val))
        rows.sort(key=lambda x: x[0])
        return rows

    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children(""))
        rows = self._collect()

        if not rows:
            self.status.config(text="No data for this selection.")
            return

        base = rows[0][1]
        for i, (t, v) in enumerate(rows):
            tag = "odd" if i % 2 else ""
            self.tree.insert("", "end",
                             values=(f"{t:g}",
                                     f"{v:.8f}",
                                     f"{v - base:+.8f}"),
                             tags=(tag,) if tag else ())

        self.status.config(
            text=f"{len(rows)} temperature point(s). "
                 f"Min = {min(v for _, v in rows):.6f}, "
                 f"Max = {max(v for _, v in rows):.6f}.")

    # ------------------------------------------------------------------
    def _plot(self):
        rows = self._collect()
        if len(rows) < 2:
            messagebox.showinfo(
                "Plot",
                "Need at least two temperatures to draw a dependency.",
                parent=self)
            return

        xs = [t for t, _ in rows]
        ys = [v for _, v in rows]
        key = self.file_var.get()
        base = key.split("\\")[-1] if "\\" in key else key
        title = f"{base} — {self.qty_var.get()}"
        open_line_plot(self, title, xs, ys, "Temperature (K)",
                       self.qty_var.get())