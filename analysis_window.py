"""Reaction Analysis: build equations from favorites and compute Δ."""
import os
import csv
from collections import OrderedDict

import tkinter as tk
from tkinter import (ttk, messagebox, filedialog, simpledialog,
                     font as tkfont)

from table_grid import TableGrid
from reaction_store import get_store


# ===========================================================================
# Helpers
# ===========================================================================
def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _discover_paths(node, prefix, out):
    if isinstance(node, dict):
        for k, v in node.items():
            _discover_paths(v, prefix + [str(k)], out)
    elif isinstance(node, list):
        return
    elif _is_number(node):
        out.add("/".join(prefix))


def discover_quantities(entries):
    out = set()
    for entry in entries:
        _discover_paths(entry, [], out)

    def key(p):
        return (0 if p.startswith("thermochemistry") else 1, p)
    return sorted(out, key=key)


def get_value(entry, path):
    node = entry
    for part in path.split("/"):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return float(node) if _is_number(node) else None


def _fmt(part):
    s = part.replace("_", " ")
    return s[:1].upper() + s[1:] if s else s


def pretty_path(path):
    parts = path.split("/")
    if parts and parts[0] == "thermochemistry" and len(parts) >= 2:
        out = [f"T = {parts[1]} K"]
        out.extend(_fmt(p) for p in parts[2:])
        return "  →  ".join(out)
    return "  →  ".join(_fmt(p) for p in parts)


def short_name(key):
    base = key.split("\\")[-1] if "\\" in key else key
    base = base.split("/")[-1]
    return os.path.splitext(base)[0]


# ===========================================================================
# Auto-sized, drag-locked Treeview wrapper
# ===========================================================================
class AutoSizeTree:
    def __init__(self, tree, cell_font, header_font,
                 padding=24, min_width=50):
        self.tree = tree
        self.cell_font = cell_font
        self.header_font = header_font
        self.padding = padding
        self.min_width = min_width
        tree.bind("<ButtonPress-1>", self._on_press, add="+")
        tree.bind("<ButtonRelease-1>", self._on_release, add="+")
        tree.bind("<Motion>", self._on_motion, add="+")

    def _on_press(self, event):
        try:
            region = self.tree.identify_region(event.x, event.y)
        except tk.TclError:
            return
        if region == "separator":
            return "break"

    def _on_release(self, event):
        self.autosize()

    def _on_motion(self, event):
        try:
            self.tree.configure(cursor="arrow")
        except tk.TclError:
            pass

    def _show_list(self):
        v = self.tree.cget("show")
        if isinstance(v, (list, tuple)):
            return [str(s) for s in v]
        return str(v).split()

    def autosize(self):
        show = self._show_list()
        cols = []
        if "tree" in show:
            cols.append(("#0", "tree"))
        for c in self.tree["columns"]:
            cols.append((c, "heading"))

        for col_id, kind in cols:
            heading = str(self.tree.heading(col_id, "text"))
            w = self.header_font.measure(heading)
            for iid in self.tree.get_children(""):
                if kind == "tree":
                    text = self.tree.item(iid, "text")
                else:
                    text = self.tree.set(iid, col_id)
                w = max(w, self.cell_font.measure(str(text)))
            w = max(self.min_width, w + self.padding)
            try:
                self.tree.column(col_id, width=w, minwidth=w,
                                 stretch=False)
            except tk.TclError:
                pass

    def total_width(self):
        total = 0
        try:
            show = self._show_list()
            if "tree" in show:
                total += int(self.tree.column("#0", "width"))
            for c in self.tree["columns"]:
                total += int(self.tree.column(c, "width"))
        except tk.TclError:
            pass
        return total


# ===========================================================================
# Window
# ===========================================================================
class AnalysisWindow(tk.Toplevel):
    EDITOR_WIDTH = 780
    EDITOR_HEIGHT = 300
    SAVED_WIDTH = 780
    SAVED_HEIGHT = 300

    def __init__(self, master, data, favorites):
        super().__init__(master)
        self.title("Reaction Analysis")
        self.minsize(1100, 720)
        self.configure(bg="white")

        self.data = data
        self._favorites_set = favorites
        self.favorites = sorted(k for k in favorites if k in data.raw)
        self.store = get_store()

        self._extra_keys = set()
        self._row_values = {}

        self._settings = {}
        self._quantities_display = {}
        self._locked_quantity_path = None

        self._cell_font = tkfont.Font(family="Segoe UI", size=10)
        self._header_font = tkfont.Font(family="Segoe UI", size=10,
                                        weight="bold")

        self._saved_sort_col = "delta"
        self._saved_sort_reverse = False

        self._sync_favorites_from_reactions(silent=True)

        self._build_ui()
        self._maximize()

        self.after_idle(self._finalize_initial_layout)
        self._refresh_quantity_list()
        self._refresh_saved_reactions()
        self._update_equation_banner()

        # ----- hotkeys -----
        self.bind("<Return>", self._hotkey_return)
        self.bind("<KP_Enter>", self._hotkey_return)
        self.bind("<Escape>", lambda e: self.destroy())

        # Ctrl+S. bind_all is the most reliable way to catch the event
        # regardless of which descendant widget has focus. The handler
        # itself checks that the focus belongs to this window, so it
        # does nothing if another Toplevel is on top.
        self.bind_all("<Control-s>", self._hotkey_save, add="+")
        self.bind_all("<Control-S>", self._hotkey_save, add="+")

        # Clean up the global binding when the window closes.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(50, self.focus_force)

    # ------------------------------------------------------------------
    def _on_close(self):
        """Remove our global Ctrl+S bindings and close."""
        try:
            self.unbind_all("<Control-s>")
            self.unbind_all("<Control-S>")
        except tk.TclError:
            pass
        self.destroy()

    def _finalize_initial_layout(self):
        self._result_autosize.autosize()
        self._saved_autosize.autosize()
        self._adjust_result_width()
        self._result_grid.update()
        self._saved_grid.update()

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

    def _focus_is_inside(self):
        """Return True if the currently focused widget is inside us."""
        try:
            focused = self.focus_get()
        except tk.TclError:
            return False
        w = focused
        while w is not None:
            if w is self:
                return True
            w = getattr(w, "master", None)
        return False

    def _hotkey_return(self, event=None):
        focused = self.focus_get()
        if focused is self.saved_tree:
            self._load_selected(keep_focus=True)
            return "break"
        if focused is not None:
            cls = focused.winfo_class()
            if cls in ("TEntry", "Entry"):
                return None
        self._recalculate()
        return "break"

    def _hotkey_save(self, event=None):
        """Ctrl+S — only acts when the focus is inside this window."""
        if not self._focus_is_inside():
            return None
        try:
            self._save_current()
        except tk.TclError:
            pass
        return "break"

    # ==================================================================
    # Layout
    # ==================================================================
    def _build_ui(self):
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill=tk.BOTH, expand=True)

        outer.rowconfigure(0, weight=3)
        outer.rowconfigure(1, weight=2)
        outer.columnconfigure(0, weight=1)

        top = ttk.Frame(outer)
        top.grid(row=0, column=0, sticky="nsew")

        bottom = ttk.Frame(outer)
        bottom.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        self._build_editor(top)
        self._build_saved(bottom)

    # ---------------- Top: equation editor ----------------
    def _build_editor(self, parent):
        ttk.Label(parent, text="Reaction equation",
                  font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)

        builder = ttk.Frame(parent, width=self.EDITOR_WIDTH,
                            height=self.EDITOR_HEIGHT)
        builder.pack(anchor=tk.NW, pady=(4, 8))
        builder.pack_propagate(False)

        hdr = ttk.Frame(builder, padding=(4, 2))
        hdr.pack(fill=tk.X)
        hdr.grid_columnconfigure(0, minsize=34)
        hdr.grid_columnconfigure(1, minsize=64)
        hdr.grid_columnconfigure(2, minsize=110)
        hdr.grid_columnconfigure(3, weight=1)
        ttk.Label(hdr, text="Incl.", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w")
        ttk.Label(hdr, text="Coef", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=1, sticky="w", padx=(4, 0))
        ttk.Label(hdr, text="Side", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=2, sticky="w")
        ttk.Label(hdr, text="Log file",
                  font=("Segoe UI", 9, "bold")).grid(
            row=0, column=3, sticky="w", padx=(4, 0))

        canvas_row = ttk.Frame(builder)
        canvas_row.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_row, bg="white",
                           highlightthickness=1,
                           highlightbackground="#d0d0d0")
        vsb = ttk.Scrollbar(canvas_row, orient="vertical",
                            command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas, padding=(4, 4))
        self._rows_inner = inner
        self._rows_canvas = canvas
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(win_id, width=e.width))

        self._populate_rows()
        self._bind_wheel(canvas)

        qframe = ttk.Frame(parent)
        qframe.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(qframe, text="Quantity:").pack(side=tk.LEFT)
        self.quantity_var = tk.StringVar()
        self.quantity_cb = ttk.Combobox(qframe,
                                        textvariable=self.quantity_var,
                                        state="readonly", width=80)
        self.quantity_cb.pack(side=tk.LEFT, padx=(6, 8), fill=tk.X,
                              expand=True)
        self.quantity_cb.bind("<<ComboboxSelected>>",
                              lambda e: self._recalculate())
        ttk.Button(qframe, text="Recalculate",
                   command=self._recalculate).pack(side=tk.LEFT)

        result_row = ttk.Frame(parent)
        result_row.pack(fill=tk.BOTH, expand=True)

        rw = ttk.Frame(result_row)
        rw.pack(side=tk.LEFT, fill=tk.Y)
        rw.pack_propagate(False)
        rw.configure(width=520)
        self._result_wrap = rw

        ttk.Label(rw, text="Result",
                  font=("Segoe UI", 11, "bold")).pack(anchor=tk.W)

        table_wrap = ttk.Frame(rw)
        table_wrap.pack(fill=tk.BOTH, expand=True)

        cols = ("coef", "side", "value", "contrib")
        self.result_tree = ttk.Treeview(table_wrap, columns=cols,
                                        show="headings",
                                        selectmode="browse")
        for c, t in (("coef", "Coef"),
                     ("side", "Side"),
                     ("value", "Value (per molecule)"),
                     ("contrib", "Contribution to Δ")):
            self.result_tree.heading(c, text=t)
            self.result_tree.column(c, width=100, anchor=tk.CENTER)

        vsb2 = ttk.Scrollbar(table_wrap, orient="vertical",
                             command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=vsb2.set)
        vsb2.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.result_tree.tag_configure("reactant", background="#eaf4ff")
        self.result_tree.tag_configure("product", background="#eafdea")
        self.result_tree.tag_configure("total", background="#f0f0f0",
                                       font=("Segoe UI", 10, "bold"))
        self.result_tree.tag_configure("delta", background="#fff6d6",
                                       font=("Segoe UI", 10, "bold"))

        self._result_grid = TableGrid(self.result_tree, table_wrap)
        self._result_autosize = AutoSizeTree(
            self.result_tree, self._cell_font, self._header_font)

        banner = tk.Frame(result_row, bg="#eef6ff", bd=2, relief="groove")
        banner.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        tk.Label(banner, text="Reaction scheme",
                 font=("Segoe UI", 10, "bold"),
                 bg="#eef6ff", fg="#1a2230").pack(
            anchor=tk.W, padx=14, pady=(10, 0))

        self.equation_label = tk.Label(
            banner, text="—", bg="#eef6ff", fg="#1a2230",
            font=("Consolas", 16, "bold"),
            anchor=tk.NW, justify=tk.LEFT, wraplength=900)
        self.equation_label.pack(fill=tk.BOTH, expand=True,
                                 padx=14, pady=(6, 4))

        self.delta_label = tk.Label(
            banner, text="", bg="#eef6ff", fg="#a03000",
            font=("Consolas", 14, "bold"),
            anchor=tk.W, justify=tk.LEFT)
        self.delta_label.pack(fill=tk.X, padx=14, pady=(0, 12))

        self.summary_label = ttk.Label(parent, text="", justify=tk.LEFT,
                                       font=("Consolas", 10))
        self.summary_label.pack(anchor=tk.W, fill=tk.X, pady=(6, 0))

    def _bind_wheel(self, canvas):
        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        def _up(e):
            canvas.yview_scroll(-1, "units")
        def _down(e):
            canvas.yview_scroll(1, "units")

        def bind(w):
            w.bind("<MouseWheel>", _wheel)
            w.bind("<Button-4>", _up)
            w.bind("<Button-5>", _down)
            for c in w.winfo_children():
                bind(c)

        bind(canvas)
        bind(self._rows_inner)

    def _populate_rows(self):
        for w in self._rows_inner.winfo_children():
            w.destroy()
        self._settings.clear()

        all_keys = sorted(set(self.favorites) | self._extra_keys)

        if not all_keys:
            ttk.Label(self._rows_inner,
                      text="No favorites to analyze. Load a reaction "
                           "or add files to favorites in the main "
                           "window.",
                      foreground="#999", wraplength=700).pack(
                anchor=tk.W, pady=10)
        else:
            for key in all_keys:
                self._add_row(self._rows_inner, key)

        self._bind_wheel(self._rows_canvas)

    def _add_row(self, parent, key):
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)

        row.grid_columnconfigure(0, minsize=34)
        row.grid_columnconfigure(1, minsize=64)
        row.grid_columnconfigure(2, minsize=110)
        row.grid_columnconfigure(3, weight=1)

        include_var = tk.BooleanVar(value=False)
        coef_var = tk.IntVar(value=1)
        side_var = tk.StringVar(value="Reactant")

        ttk.Checkbutton(row, variable=include_var).grid(
            row=0, column=0, sticky="w")

        ttk.Spinbox(row, from_=1, to=999, width=5,
                    textvariable=coef_var).grid(
            row=0, column=1, padx=(4, 0), sticky="w")

        ttk.Combobox(row, textvariable=side_var,
                     values=("Reactant", "Product"),
                     state="readonly", width=10).grid(
            row=0, column=2, padx=(4, 0), sticky="w")

        missing = key not in self.data.raw
        label_text = short_name(key)
        if missing:
            label_text += "   [not in current JSON]"
        tk.Label(row, text=label_text, anchor=tk.W, bg="white",
                 fg="#a33" if missing else "#222").grid(
            row=0, column=3, sticky="w", padx=(6, 0))

        self._settings[key] = {
            "include": include_var,
            "coef": coef_var,
            "side": side_var,
        }

    # ---------------- Bottom: saved reactions ----------------
    def _build_saved(self, parent):
        ttk.Label(parent, text="Saved reactions",
                  font=("Segoe UI", 11, "bold")).pack(anchor=tk.W,
                                                      pady=(4, 4))

        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X, pady=(0, 4))

        ttk.Button(bar, text="Save current reaction  (Ctrl+S)",
                   command=self._save_current).pack(side=tk.LEFT)
        ttk.Button(bar, text="Load  (Enter)",
                   command=lambda: self._load_selected(keep_focus=True)
                   ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="Delete  (Del)",
                   command=self._delete_selected).pack(side=tk.LEFT,
                                                       padx=(6, 0))
        ttk.Button(bar, text="Clear",
                   command=self._clear_reactions).pack(side=tk.LEFT,
                                                       padx=(6, 0))
        ttk.Button(bar, text="Export to CSV…",
                   command=self._export_csv).pack(side=tk.LEFT,
                                                  padx=(6, 0))
        ttk.Button(bar, text="Load reactions from CSV…",
                   command=self._import_csv).pack(side=tk.LEFT,
                                                  padx=(6, 0))

        saved_outer = ttk.Frame(parent, width=self.SAVED_WIDTH,
                                height=self.SAVED_HEIGHT)
        saved_outer.pack(anchor=tk.NW)
        saved_outer.pack_propagate(False)

        wrap = ttk.Frame(saved_outer)
        wrap.pack(fill=tk.BOTH, expand=True)
        self._saved_wrap = wrap

        cols = ("quantity", "reactants", "products", "delta")
        self.saved_tree = ttk.Treeview(wrap, columns=cols,
                                       show="tree headings",
                                       selectmode="browse")
        self.saved_tree.heading("#0", text="Name",
                                command=lambda: self._sort_by_column("#0"))
        self.saved_tree.heading(
            "quantity", text="Quantity",
            command=lambda: self._sort_by_column("quantity"))
        self.saved_tree.heading(
            "reactants", text="Reactants",
            command=lambda: self._sort_by_column("reactants"))
        self.saved_tree.heading(
            "products", text="Products",
            command=lambda: self._sort_by_column("products"))
        self.saved_tree.heading(
            "delta", text="Δ (P − R)",
            command=lambda: self._sort_by_column("delta"))

        for c in cols:
            self.saved_tree.column(c, width=130, anchor=tk.W)
        self.saved_tree.column("#0", width=160, anchor=tk.W)

        vsb = ttk.Scrollbar(wrap, orient="vertical",
                            command=self.saved_tree.yview)
        self.saved_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.saved_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.saved_tree.tag_configure("odd", background="#f7f7f7")

        self.saved_tree.bind("<Delete>",
                             lambda e: self._delete_selected())
        self.saved_tree.bind(
            "<Double-1>",
            lambda e: self._load_selected(keep_focus=True))

        self._saved_grid = TableGrid(self.saved_tree, wrap)
        self._saved_autosize = AutoSizeTree(
            self.saved_tree, self._cell_font, self._header_font)

    # ==================================================================
    # Quantities
    # ==================================================================
    def _refresh_quantity_list(self):
        entries = [self.data.raw[k] for k in self.favorites]
        paths = discover_quantities(entries)

        self._quantities_display.clear()
        displays = []
        for p in paths:
            disp = pretty_path(p)
            if disp in self._quantities_display:
                disp = f"{disp}   ({p})"
            self._quantities_display[disp] = p
            displays.append(disp)

        if self._locked_quantity_path:
            locked_disp = pretty_path(self._locked_quantity_path)
            self.quantity_cb["values"] = [locked_disp]
            self.quantity_var.set(locked_disp)
            self.quantity_cb.config(state="disabled")
        else:
            self.quantity_cb["values"] = displays
            self.quantity_cb.config(state="readonly")
            if displays and not self.quantity_var.get():
                self.quantity_cb.current(0)

    def _lock_quantity_to(self, path):
        self._locked_quantity_path = path
        disp = pretty_path(path)
        self.quantity_cb["values"] = [disp]
        self.quantity_var.set(disp)
        self.quantity_cb.config(state="disabled")

    def _unlock_quantity(self):
        self._locked_quantity_path = None
        displays = list(self._quantities_display.keys())
        self.quantity_cb["values"] = displays
        self.quantity_cb.config(state="readonly")

    # ==================================================================
    # Calculation
    # ==================================================================
    def _compute_current(self):
        if self._locked_quantity_path:
            path = self._locked_quantity_path
            disp = self.quantity_var.get()
        else:
            disp = self.quantity_var.get()
            path = self._quantities_display.get(disp)
        if not path:
            return None

        rows = []
        reactants_sum = 0.0
        products_sum = 0.0
        missing = []
        settings_snapshot = {}

        for key in sorted(self._settings.keys()):
            s = self._settings[key]
            include = bool(s["include"].get())
            try:
                coef = int(s["coef"].get())
                if coef < 1:
                    coef = 1
                    s["coef"].set(1)
            except (tk.TclError, ValueError):
                coef = 1
                s["coef"].set(1)
            side = s["side"].get()

            snap = {"include": include, "coef": coef, "side": side}
            settings_snapshot[key] = snap

            if not include:
                continue

            value = None
            source = "json"
            if key in self.data.raw:
                value = get_value(self.data.raw[key], path)

            if value is None:
                cached = self._row_values.get(key)
                if cached and cached.get("path") == path:
                    value = cached.get("value")
                    source = "csv"

            if value is None:
                missing.append(key)
                continue

            snap["value"] = value
            snap["value_source"] = source

            if side == "Reactant":
                contrib = -coef * value
                reactants_sum += coef * value
                tag = "reactant"
            else:
                contrib = coef * value
                products_sum += coef * value
                tag = "product"

            rows.append({
                "key": key,
                "coef": coef,
                "side": side,
                "value": value,
                "contrib": contrib,
                "tag": tag,
                "source": source,
            })

        delta = products_sum - reactants_sum
        return {
            "path": path,
            "display": disp,
            "rows": rows,
            "reactants_sum": reactants_sum,
            "products_sum": products_sum,
            "delta": delta,
            "missing": missing,
            "settings": settings_snapshot,
        }

    def _equation_text(self, data):
        r_terms, p_terms = [], []
        for r in data["rows"]:
            nm = short_name(r["key"])
            term = f"{r['coef']}·{nm}" if r["coef"] > 1 else nm
            (r_terms if r["side"] == "Reactant" else p_terms).append(term)
        left = " + ".join(r_terms) or "∅"
        right = " + ".join(p_terms) or "∅"
        return f"{left}  →  {right}"

    def _update_equation_banner(self, data=None):
        if data is None:
            self.equation_label.config(text="—")
            self.delta_label.config(text="")
            return
        self.equation_label.config(text=self._equation_text(data))
        self.delta_label.config(
            text=f"Δ = {data['delta']:+.8f}   "
                 f"(Products {data['products_sum']:+.6f} − "
                 f"Reactants {data['reactants_sum']:+.6f})")

    def _adjust_result_width(self):
        total = self._result_autosize.total_width()
        if total <= 0:
            return
        self._result_wrap.configure(width=max(280, total + 22))

    def _recalculate(self):
        data = self._compute_current()
        self.result_tree.delete(*self.result_tree.get_children(""))

        if data is None:
            self.summary_label.config(text="Pick a quantity first.")
            self._update_equation_banner(None)
            self._result_autosize.autosize()
            self._adjust_result_width()
            self._result_grid.update()
            return

        for r in data["rows"]:
            value_text = f"{r['value']:.8f}"
            if r.get("source") == "csv":
                value_text += "  (csv)"
            self.result_tree.insert(
                "", "end",
                values=(r["coef"], r["side"], value_text,
                        f"{r['contrib']:+.8f}"),
                tags=(r["tag"],))

        self.result_tree.insert(
            "", "end",
            values=("", "Reactants", "",
                    f"{data['reactants_sum']:.8f}"),
            tags=("total",))
        self.result_tree.insert(
            "", "end",
            values=("", "Products", "",
                    f"{data['products_sum']:.8f}"),
            tags=("total",))
        self.result_tree.insert(
            "", "end",
            values=("", "Δ", "", f"{data['delta']:+.8f}"),
            tags=("delta",))

        self._update_equation_banner(data)

        lines = [
            f"Reactants sum:  {data['reactants_sum']:+.8f}",
            f"Products sum:   {data['products_sum']:+.8f}",
            f"Δ (products − reactants) = {data['delta']:+.8f}",
        ]
        if data["missing"]:
            lines.append(
                f"Note: {len(data['missing'])} file(s) had no value "
                f"for this quantity and were skipped.")
        if self._locked_quantity_path:
            lines.append(
                "Note: quantity locked to the one loaded from the "
                "reaction.")
        self.summary_label.config(text="\n".join(lines))

        self._result_autosize.autosize()
        self._adjust_result_width()
        self._result_grid.update()

    # ==================================================================
    # Saved reactions
    # ==================================================================
    @staticmethod
    def _reaction_signature(r):
        settings_sig = tuple(sorted(
            (k,
             int(s.get("coef", 1) or 1),
             s.get("side", "Reactant"))
            for k, s in r.get("settings", {}).items()
            if s.get("include", True)
        ))
        return (r.get("name", ""),
                r.get("quantity_path", ""),
                settings_sig)

    def _save_current(self):
        data = self._compute_current()
        if data is None:
            messagebox.showinfo("Analysis", "Pick a quantity first.",
                                parent=self)
            return

        default_name = f"Reaction {len(self.store) + 1}"
        name = simpledialog.askstring(
            "Save reaction", "Reaction name:",
            initialvalue=default_name, parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return

        new_r = {
            "name": name,
            "quantity_path": data["path"],
            "quantity_display": data["display"],
            "reactants_sum": data["reactants_sum"],
            "products_sum": data["products_sum"],
            "delta": data["delta"],
            "settings": data["settings"],
        }

        sig = self._reaction_signature(new_r)
        for existing in self.store.reactions:
            if self._reaction_signature(existing) == sig:
                if not messagebox.askyesno(
                        "Duplicate reaction",
                        "An identical reaction is already saved. "
                        "Save anyway?", parent=self):
                    return
                break

        self.store.add(new_r)
        self._refresh_saved_reactions()

    def _sort_by_column(self, col):
        if self._saved_sort_col == col:
            self._saved_sort_reverse = not self._saved_sort_reverse
        else:
            self._saved_sort_col = col
            self._saved_sort_reverse = False
        self._refresh_saved_reactions()

    def _refresh_saved_reactions(self):
        self.saved_tree.delete(*self.saved_tree.get_children(""))

        indices = list(range(len(self.store.reactions)))
        col = self._saved_sort_col

        if col:
            def key(i):
                r = self.store.reactions[i]
                if col == "#0":
                    return r.get("name", "").lower()
                if col == "quantity":
                    return r.get("quantity_display", "").lower()
                if col == "reactants":
                    return r.get("reactants_sum", 0.0)
                if col == "products":
                    return r.get("products_sum", 0.0)
                if col == "delta":
                    return r.get("delta", 0.0)
                return 0
            indices.sort(key=key, reverse=self._saved_sort_reverse)

        for display_idx, store_idx in enumerate(indices):
            r = self.store.reactions[store_idx]
            tag = "odd" if display_idx % 2 else ""
            self.saved_tree.insert(
                "", "end", iid=str(store_idx),
                text=r["name"],
                values=(r["quantity_display"],
                        f"{r['reactants_sum']:.6f}",
                        f"{r['products_sum']:.6f}",
                        f"{r['delta']:+.6f}"),
                tags=(tag,) if tag else ())

        self._saved_autosize.autosize()
        self._saved_grid.update()

    def _selected_index(self):
        sel = self.saved_tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except ValueError:
            return None

    def _delete_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        r = self.store.reactions[idx]

        children_before = list(self.saved_tree.get_children(""))
        try:
            display_pos = children_before.index(str(idx))
        except ValueError:
            display_pos = -1

        if not messagebox.askyesno("Delete reaction",
                                   f"Delete '{r['name']}'?",
                                   parent=self):
            try:
                self.saved_tree.selection_set(str(idx))
                self.saved_tree.focus(str(idx))
                self.saved_tree.focus_set()
            except tk.TclError:
                pass
            return

        self.store.remove(idx)
        self._refresh_saved_reactions()

        new_children = list(self.saved_tree.get_children(""))
        if not new_children:
            return
        if display_pos < 0:
            target = new_children[0]
        elif display_pos >= len(new_children):
            target = new_children[-1]
        else:
            target = new_children[display_pos]

        try:
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

        try:
            self.saved_tree.selection_set(target)
            self.saved_tree.focus(target)
            self.saved_tree.see(target)
            self.saved_tree.focus_set()
        except tk.TclError:
            pass

    def _clear_reactions(self):
        if not self.store.reactions:
            return
        if not messagebox.askyesno(
                "Clear reactions",
                f"Delete all {len(self.store.reactions)} saved "
                f"reactions?", parent=self):
            return
        self.store.reactions.clear()
        self._refresh_saved_reactions()
        try:
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

    def _load_selected(self, keep_focus=False):
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("Analysis", "Select a reaction first.",
                                parent=self)
            return
        r = self.store.reactions[idx]

        loaded_settings = r.get("settings", {})
        path = r.get("quantity_path", "")

        self._extra_keys = set()
        self._row_values = {}

        for key, s in loaded_settings.items():
            if key not in self.data.raw:
                self._extra_keys.add(key)
            if "value" in s and isinstance(s["value"], (int, float)):
                self._row_values[key] = {
                    "path": path,
                    "value": float(s["value"]),
                }

        self._populate_rows()

        disp = r.get("quantity_display", "")
        found = None
        if disp and disp in self._quantities_display:
            found = disp
        elif path:
            for d, p in self._quantities_display.items():
                if p == path:
                    found = d
                    break

        if found is not None:
            self._unlock_quantity()
            self.quantity_var.set(found)
        else:
            if not path:
                messagebox.showinfo(
                    "Analysis",
                    "This reaction has no stored quantity; cannot load.",
                    parent=self)
                return
            self._lock_quantity_to(path)

        for key, s in self._settings.items():
            src = loaded_settings.get(key)
            if src is None:
                s["include"].set(False)
                continue
            s["include"].set(bool(src.get("include", True)))
            try:
                s["coef"].set(int(src.get("coef", 1)))
            except (tk.TclError, ValueError):
                s["coef"].set(1)
            side = src.get("side", "Reactant")
            if side not in ("Reactant", "Product"):
                side = "Reactant"
            s["side"].set(side)

        self._recalculate()

        if keep_focus:
            try:
                self.saved_tree.focus_set()
            except tk.TclError:
                pass

    # ==================================================================
    # Favorites sync
    # ==================================================================
    def _sync_favorites_from_reactions(self, silent=False):
        added = []
        for r in self.store.reactions:
            for key in r.get("settings", {}).keys():
                if (key in self.data.raw
                        and key not in self._favorites_set):
                    self._favorites_set.add(key)
                    added.append(key)

        if added:
            self.favorites = sorted(
                k for k in self._favorites_set if k in self.data.raw)
            try:
                refresh = getattr(self.master, "_refresh_tree", None)
                if callable(refresh):
                    refresh()
            except Exception:
                pass

        if added and not silent:
            messagebox.showinfo(
                "Favorites synced",
                f"Added {len(added)} file(s) to favorites:"
                "\n" + "\n".join(short_name(k) for k in sorted(added)),
                parent=self)
        return added

    # ==================================================================
    # CSV export
    # ==================================================================
    _CSV_COLUMNS = [
        "Reaction", "Quantity", "Quantity Path", "File",
        "Coefficient", "Side", "Value", "Contribution",
        "Reactants sum", "Products sum", "Delta",
    ]

    def _export_csv(self):
        if not self.store.reactions:
            messagebox.showinfo("Export", "No saved reactions.",
                                parent=self)
            return

        path = filedialog.asksaveasfilename(
            parent=self, title="Export reactions to CSV",
            defaultextension=".csv",
            initialfile="reactions.csv",
            filetypes=[("CSV file", "*.csv"), ("All files", "*.*")])
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(self._CSV_COLUMNS)
                for r in self.store.reactions:
                    name = r["name"]
                    q = r.get("quantity_display", "")
                    qpath = r.get("quantity_path", "")
                    settings = r.get("settings", {})
                    if not settings:
                        w.writerow([name, q, qpath, "", "", "",
                                    "", "",
                                    f"{r.get('reactants_sum', 0):.8f}",
                                    f"{r.get('products_sum', 0):.8f}",
                                    f"{r.get('delta', 0):+.8f}"])
                        continue
                    for key, s in sorted(settings.items()):
                        if not s.get("include", True):
                            continue
                        try:
                            coef = int(s.get("coef", 1))
                        except (TypeError, ValueError):
                            coef = 1
                        side = s.get("side", "Reactant")

                        value = None
                        if key in self.data.raw:
                            value = get_value(self.data.raw[key], qpath)
                        if value is None and "value" in s:
                            value = s["value"]

                        if value is None:
                            w.writerow([name, q, qpath, key, coef, side,
                                        "", "",
                                        f"{r.get('reactants_sum', 0):.8f}",
                                        f"{r.get('products_sum', 0):.8f}",
                                        f"{r.get('delta', 0):+.8f}"])
                        else:
                            contrib = (-coef * value) \
                                if side == "Reactant" else (coef * value)
                            w.writerow([name, q, qpath, key, coef, side,
                                        f"{value:.8f}",
                                        f"{contrib:+.8f}",
                                        f"{r.get('reactants_sum', 0):.8f}",
                                        f"{r.get('products_sum', 0):.8f}",
                                        f"{r.get('delta', 0):+.8f}"])
        except Exception as e:
            messagebox.showerror("Export failed", str(e), parent=self)
            return
        messagebox.showinfo("Export", f"Saved to:\n{path}", parent=self)

    # ==================================================================
    # CSV import
    # ==================================================================
    def _import_csv(self):
        path = filedialog.askopenfilename(
            parent=self, title="Load reactions from CSV",
            filetypes=[("CSV file", "*.csv"), ("All files", "*.*")])
        if not path:
            return

        try:
            with open(path, "r", newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
        except Exception as e:
            messagebox.showerror("Import failed", str(e), parent=self)
            return

        if len(rows) < 2:
            messagebox.showinfo("Import",
                                "CSV file has no data rows.",
                                parent=self)
            return

        header = rows[0]
        data_rows = rows[1:]

        def col_idx(name):
            try:
                return header.index(name)
            except ValueError:
                return None

        i_reaction = col_idx("Reaction")
        i_quantity = col_idx("Quantity")
        i_qpath = col_idx("Quantity Path")
        i_file = col_idx("File")
        i_coef = col_idx("Coefficient")
        i_side = col_idx("Side")
        i_value = col_idx("Value")
        i_rs = col_idx("Reactants sum")
        i_ps = col_idx("Products sum")
        i_delta = col_idx("Delta")

        if i_reaction is None or i_file is None:
            messagebox.showerror(
                "Import failed",
                "CSV is missing required columns "
                "'Reaction' and/or 'File'.", parent=self)
            return

        groups = OrderedDict()
        for r in data_rows:
            if not r or all(not c.strip() for c in r):
                continue
            if i_reaction >= len(r):
                continue
            name = r[i_reaction].strip()
            if not name:
                continue
            groups.setdefault(name, []).append(r)

        def _to_float(row, idx, default=0.0):
            if idx is None or idx >= len(row):
                return default
            s = row[idx].strip()
            if not s:
                return default
            try:
                return float(s)
            except ValueError:
                return default

        existing_sigs = {
            self._reaction_signature(r) for r in self.store.reactions
        }

        new_reactions = []
        skipped_dups = 0
        for name, rrows in groups.items():
            first = rrows[0]
            quantity = (first[i_quantity].strip()
                        if i_quantity is not None
                        and i_quantity < len(first) else "")
            qpath = (first[i_qpath].strip()
                     if i_qpath is not None
                     and i_qpath < len(first) else "")
            rs = _to_float(first, i_rs, 0.0)
            ps = _to_float(first, i_ps, 0.0)
            delta = _to_float(first, i_delta, 0.0)

            settings = {}
            for r in rrows:
                if i_file >= len(r):
                    continue
                key = r[i_file].strip()
                if not key:
                    continue
                coef = 1
                if i_coef is not None and i_coef < len(r):
                    try:
                        coef = int(r[i_coef])
                    except (TypeError, ValueError):
                        coef = 1
                if coef < 1:
                    coef = 1
                side = "Reactant"
                if i_side is not None and i_side < len(r):
                    sv = r[i_side].strip()
                    if sv in ("Reactant", "Product"):
                        side = sv

                entry = {"include": True, "coef": coef, "side": side}

                if i_value is not None and i_value < len(r):
                    raw = r[i_value].strip().replace("(csv)", "").strip()
                    if raw:
                        try:
                            entry["value"] = float(raw)
                        except ValueError:
                            pass

                settings[key] = entry

            candidate = {
                "name": name,
                "quantity_path": qpath,
                "quantity_display": quantity
                or (pretty_path(qpath) if qpath else ""),
                "reactants_sum": rs,
                "products_sum": ps,
                "delta": delta,
                "settings": settings,
            }

            sig = self._reaction_signature(candidate)
            if sig in existing_sigs:
                skipped_dups += 1
                continue

            new_reactions.append(candidate)
            existing_sigs.add(sig)

        if not new_reactions:
            messagebox.showinfo(
                "Import",
                f"Nothing new to import from:\n{path}\n\n"
                f"{skipped_dups} duplicate reaction(s) skipped.",
                parent=self)
            return

        added = []
        for r in new_reactions:
            for key in r["settings"].keys():
                if (key in self.data.raw
                        and key not in self._favorites_set):
                    self._favorites_set.add(key)
                    added.append(key)

        if added:
            self.favorites = sorted(
                k for k in self._favorites_set if k in self.data.raw)
            self._populate_rows()
            self._refresh_quantity_list()
            try:
                refresh = getattr(self.master, "_refresh_tree", None)
                if callable(refresh):
                    refresh()
            except Exception:
                pass

        for r in new_reactions:
            self.store.add(r)
        self._refresh_saved_reactions()

        msg = (f"Loaded {len(new_reactions)} new reaction(s) "
               f"from:\n{path}")
        if skipped_dups:
            msg += f"\n\nSkipped {skipped_dups} duplicate(s)."
        if added:
            msg += (f"\n\nAdded {len(added)} .log file(s) to favorites:"
                    f"\n" + "\n".join(short_name(k) for k in sorted(added)))
        messagebox.showinfo("Import", msg, parent=self)