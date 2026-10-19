"""Generic data-display tabs for arbitrary parser methods.

Rules:
    * list of dicts          -> SeriesTab   (table + Plot button)
    * dict of dicts          -> NestedTab   (tree, like Thermochemistry)
    * flat dict / scalar     -> pushed into the General Data tab
"""
import tkinter as tk
from tkinter import ttk

from plot_window import open_series_plot


def detect_kind(value):
    """Return 'series' | 'nested' | 'flat' for a top-level method value."""
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            return "series"
        return "flat"
    if isinstance(value, dict):
        for v in value.values():
            if isinstance(v, dict):
                return "nested"
        return "flat"
    return "flat"


# ===========================================================================
class SeriesTab(ttk.Frame):
    """List-of-dicts data with a Plot button."""

    def __init__(self, master, title, series):
        super().__init__(master)
        self.title = title
        self.series = series

        top = ttk.Frame(self, padding=(4, 4))
        top.pack(fill=tk.X)

        ttk.Label(top, text=f"{len(series)} point(s)",
                  style="Summary.TLabel").pack(side=tk.LEFT)

        self.plot_btn = ttk.Button(top, text="Plot",
                                   command=self._on_plot)
        self.plot_btn.pack(side=tk.RIGHT)
        self._update_plot_button_state()

        table = ttk.Frame(self)
        table.pack(fill=tk.BOTH, expand=True)

        cols = list(series[0].keys()) if series else []
        self.tree = ttk.Treeview(table, columns=cols, show="headings",
                                 selectmode="browse")
        for c in cols:
            self.tree.heading(c, text=c.replace("_", " ").title())
            self.tree.column(c, width=160, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(table, orient="vertical",
                            command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.tag_configure("odd", background="#f7f7f7")
        self.tree.tag_configure("neg", background="#ffd6d6")

        for i, row in enumerate(series):
            values = []
            has_neg = False
            for c in cols:
                v = row.get(c, "")
                if isinstance(v, float):
                    if v < 0:
                        has_neg = True
                    values.append(f"{v:.4f}")
                else:
                    values.append(str(v))
            tag = "neg" if has_neg else ("odd" if i % 2 else "")
            self.tree.insert("", "end", values=values,
                             tags=(tag,) if tag else ())

    # ------------------------------------------------------------------
    def _update_plot_button_state(self):
        self.plot_btn.config(
            state=tk.NORMAL if len(self.series) > 1 else tk.DISABLED)

    def _pick_columns(self):
        """Guess x/y columns from the keys."""
        if not self.series:
            return None, None
        cols = list(self.series[0].keys())
        if not cols:
            return None, None
        x_col = None
        y_col = None
        for c in cols:
            lc = c.lower()
            if x_col is None and lc in ("index", "x", "i", "n"):
                x_col = c
            if y_col is None and lc in ("frequency", "value", "y",
                                        "energy", "magnitude"):
                y_col = c
        if x_col is None:
            x_col = cols[0]
        if y_col is None or y_col == x_col:
            for c in cols:
                if c != x_col:
                    y_col = c
                    break
        return x_col, y_col

    def _on_plot(self):
        x_col, y_col = self._pick_columns()
        if not x_col or not y_col:
            return
        xs, ys = [], []
        for r in self.series:
            try:
                xs.append(float(r[x_col]))
                ys.append(float(r[y_col]))
            except (TypeError, ValueError, KeyError):
                continue
        if not xs:
            return
        open_series_plot(self, self.title, xs, ys,
                         x_col.replace("_", " ").title(),
                         y_col.replace("_", " ").title())


# ===========================================================================
class NestedTab(ttk.Frame):
    """dict-of-dicts data shown as a tree (like Thermochemistry)."""

    def __init__(self, master, title, data):
        super().__init__(master)
        self.title = title

        top = ttk.Frame(self, padding=(4, 4))
        top.pack(fill=tk.X)

        ttk.Label(top, text=title, style="Summary.TLabel").pack(side=tk.LEFT)
        ttk.Button(top, text="Collapse all", width=12,
                   command=self._collapse_all).pack(side=tk.RIGHT)
        ttk.Button(top, text="Expand all", width=12,
                   command=self._expand_all).pack(side=tk.RIGHT, padx=(0, 4))

        wrap = ttk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(wrap, columns=("value",),
                                 show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Item")
        self.tree.heading("value", text="Value")
        self.tree.column("#0", width=420, anchor=tk.W)
        self.tree.column("value", width=240, anchor=tk.W)

        vsb = ttk.Scrollbar(wrap, orient="vertical",
                            command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.tag_configure("cat", background="#eef3fa",
                                font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("odd", background="#f7f7f7")

        leaf_idx = 0
        for k, v in data.items():
            self._populate("", k, v, is_root=True)
        # Note: recursion is inside _populate below, leaf_idx handled there.

        self._leaf_idx = 0   # reset for consistency

    def _populate(self, parent, key, value, is_root=False):
        if isinstance(value, dict):
            node = self.tree.insert(
                parent, "end", text=str(key), values=("",),
                tags=("cat",), open=False)
            for k, v in value.items():
                self._populate(node, k, v)
        else:
            if isinstance(value, float):
                vtext = f"{value:.8f}"
            elif isinstance(value, (list, tuple)):
                vtext = ", ".join(str(x) for x in value)
            else:
                vtext = str(value)
            tag = "odd" if self._leaf_idx % 2 else ""
            self.tree.insert(parent, "end", text="  " + str(key),
                             values=(vtext,), tags=(tag,) if tag else ())
            self._leaf_idx += 1

    def _expand_all(self):
        for iid in self.tree.get_children(""):
            self._recursive_set(iid, True)

    def _collapse_all(self):
        for iid in self.tree.get_children(""):
            self._recursive_set(iid, False)

    def _recursive_set(self, iid, state):
        try:
            self.tree.item(iid, open=state)
        except tk.TclError:
            return
        for c in self.tree.get_children(iid):
            self._recursive_set(c, state)


# ===========================================================================
class GeneralTab(ttk.Frame):
    """Aggregates flat key->value data from all flat methods."""

    def __init__(self, master):
        super().__init__(master)

        wrap = ttk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(wrap, columns=("value",),
                                 show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Quantity")
        self.tree.heading("value", text="Value")
        self.tree.column("#0", width=420, anchor=tk.W)
        self.tree.column("value", width=260, anchor=tk.W)

        vsb = ttk.Scrollbar(wrap, orient="vertical",
                            command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.tag_configure("group", background="#eef3fa",
                                font=("Segoe UI", 10, "bold"))
        self.tree.tag_configure("odd", background="#f7f7f7")

    def populate(self, groups):
        """groups is a list of (title, flat_dict)."""
        self.tree.delete(*self.tree.get_children(""))
        if not groups:
            self.tree.insert("", "end",
                             text="No general data available",
                             values=("",), tags=("odd",))
            return

        leaf_idx = 0
        for title, data in groups:
            group_node = self.tree.insert(
                "", "end", text=title, values=("",),
                tags=("group",), open=True)
            for k, v in data.items():
                if isinstance(v, float):
                    vtext = f"{v:.8f}"
                elif isinstance(v, (list, tuple)):
                    vtext = ", ".join(str(x) for x in v)
                elif isinstance(v, dict):
                    vtext = "{ ... }"
                else:
                    vtext = str(v)
                tag = "odd" if leaf_idx % 2 else ""
                self.tree.insert(group_node, "end",
                                 text="  " + str(k),
                                 values=(vtext,),
                                 tags=(tag,) if tag else ())
                leaf_idx += 1