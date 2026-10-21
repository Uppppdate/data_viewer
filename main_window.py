"""The main application window (after a JSON has been loaded)."""
import os
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
from collections import OrderedDict

from helpers import (elide_left, MIN_LEFT_PANE_HARD,
                     MIN_RIGHT_PANE_HARD, load_recent_paths)
from plot_window import open_plot_window
from analysis_window import AnalysisWindow
from temperature_window import TemperatureWindow
from data_tabs import detect_kind, SeriesTab, NestedTab, GeneralTab
from platform_utils import make_font, font_family, IS_MAC, is_f_key


class MainWindow(ttk.Frame):
    def __init__(self, master, data, json_path,
                 on_open_json, on_parse_logs,
                 on_open_json_path=None):
        super().__init__(master)
        self.data = data
        self.current_key = None
        self._freq_data_cache = []
        self._num_col_width = None
        self._quantity_col_width = 380
        self._tree_texts = {}
        self._tree_kinds = {}
        self._header_full = "Current .log file: (none selected)"
        self._on_open_json = on_open_json
        self._on_open_json_path = on_open_json_path
        self._on_parse_logs = on_parse_logs

        self._favorites = set()
        self._thermo_open_state = None
        self._logs_open_state = False
        self._folder_open_state = {}
        self._fav_root_open = False

        self._paned_dragging = False

        self._dynamic_tabs = {}

        self._tree_font = make_font(10)
        self._header_font = make_font(10, weight="bold")
        self._title_font = make_font(12, weight="bold")
        try:
            self._tab_font = tkfont.nametofont("TkDefaultFont").copy()
        except Exception:
            self._tab_font = make_font(10)

        try:
            label_w = self._title_font.measure("Log files")
        except Exception:
            label_w = 80
        self._min_left_pane = max(label_w + 34, 280)

        self.paned = None
        self._toolbar = None
        self._right_frame = None
        self._toast = None
        self._toast_job = None

        self._freq_seps = []
        self._thermo_seps = []

        self._build_toolbar()
        self._build_main()
        self._build_status()
        self._build_toast()

        self.path_label.config(
            text=f"Current .json file: {os.path.abspath(json_path)}")
        self.status.config(text=f"Loaded entries: {len(self.data.keys())}")
        self._refresh_tree()

    # ------------------------------------------------------------------
    def set_json_path(self, path):
        self.path_label.config(
            text=f"Current .json file: {os.path.abspath(path)}")
        self.status.config(text=f"Loaded entries: {len(self.data.keys())}")
        self.current_key = None
        self._folder_open_state.clear()
        self._refresh_tree()

    # ==================================================================
    # Toolbar
    # ==================================================================
    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(side=tk.TOP, fill=tk.X)
        self._toolbar = bar

        ttk.Label(bar, text="Search:").pack(side=tk.LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_tree())
        ttk.Entry(bar, textvariable=self.search_var, width=30)\
            .pack(side=tk.LEFT)

        self._open_btn = ttk.Menubutton(bar, text="Open JSON…")
        self._open_btn.pack(side=tk.RIGHT)
        self._rebuild_recent_menu()

        ttk.Button(bar, text="Parse files",
                   command=self._on_parse_logs).pack(
            side=tk.RIGHT, padx=(0, 6))
        ttk.Button(bar, text="Analysis…",
                   command=self._open_analysis).pack(
            side=tk.RIGHT, padx=(0, 6))

    def _rebuild_recent_menu(self):
        menu = tk.Menu(self._open_btn, tearoff=0)
        menu.add_command(label="Browse…", command=self._on_open_json)
        menu.add_separator()
        paths = load_recent_paths()
        if not paths:
            menu.add_command(label="(no recent files)", state="disabled")
        else:
            for p in paths:
                label = os.path.basename(p) + "  —  " + os.path.dirname(p)
                menu.add_command(
                    label=label,
                    command=lambda pp=p: self._on_open_json_recent(pp))
        self._open_btn["menu"] = menu

    def _on_open_json_recent(self, path):
        if self._on_open_json_path:
            self._on_open_json_path(path)

    # ==================================================================
    # Main area
    # ==================================================================
    def _build_main(self):
        self.paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        self.paned.bind("<ButtonPress-1>", self._on_paned_press, add="+")
        self.paned.bind("<B1-Motion>", self._on_paned_motion, add="+")
        self.paned.bind("<ButtonRelease-1>", self._on_paned_release, add="+")
        self.paned.bind("<Configure>",
                        lambda e: self._enforce_pane_limits())

        # ---- Left panel ----
        left = ttk.Frame(self.paned)
        self.paned.add(left, weight=1)

        header_row = ttk.Frame(left)
        header_row.pack(fill=tk.X, pady=(4, 2))
        ttk.Label(header_row, text="Log files",
                  style="Title.TLabel").pack(side=tk.LEFT)

        ttk.Button(header_row, text="Collapse all", width=12,
                   command=self._collapse_all_logs).pack(side=tk.RIGHT)
        ttk.Button(header_row, text="Expand all", width=12,
                   command=self._expand_all_logs).pack(
            side=tk.RIGHT, padx=(0, 4))

        fav_row = ttk.Frame(left)
        fav_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(fav_row, text="★ Add all",
                   command=self._add_all_favorites).pack(side=tk.LEFT)
        ttk.Button(fav_row, text="☆ Clear favorites",
                   command=self._clear_favorites).pack(side=tk.LEFT,
                                                       padx=(4, 0))
        hint = "⌘F" if IS_MAC else "Ctrl+F"
        ttk.Label(fav_row, text=f"{hint}: toggle",
                  foreground="#777",
                  font=make_font(9)).pack(side=tk.RIGHT)

        tree_wrap = ttk.Frame(left)
        tree_wrap.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_wrap, show="tree", selectmode="browse")

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical",
                            command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<<TreeviewOpen>>", self._on_tree_toggle_state)
        self.tree.bind("<<TreeviewClose>>", self._on_tree_toggle_state)
        self.tree.bind("<Configure>", self._update_tree_labels)
        self.tree.bind("<Button-1>", self._on_tree_left_click, add="+")

        # ---- Right panel ----
        right = ttk.Frame(self.paned)
        self.paned.add(right, weight=3)

        self._right_frame = right
        right.bind("<Configure>", lambda e: self._update_header_display())

        self.header = ttk.Label(right, text=self._header_full,
                                style="Title.TLabel")
        self.header.pack(anchor=tk.W, padx=6, pady=(4, 4))

        self.nb = ttk.Notebook(right)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))
        self.nb.configure(takefocus=False)

        self.tab_freq = ttk.Frame(self.nb)
        self.nb.add(self.tab_freq, text="Vibrational Frequencies")
        self._build_freq_tab()

        self.tab_thermo = ttk.Frame(self.nb)
        self.nb.add(self.tab_thermo, text="Thermochemistry")
        self._build_thermo_tab()

        self.tab_general = ttk.Frame(self.nb)
        self.nb.add(self.tab_general, text="General Data")
        self._build_general_tab()

        self.after_idle(self._enforce_pane_limits)

        # Ctrl/Cmd+F — layout-independent handler.
        # Bind a single generic handler on the root; it will only act
        # when the pressed physical key is F.
        root = self.winfo_toplevel()
        root.bind_all("<Command-KeyPress>", self._on_cmd_keypress)
        root.bind_all("<Control-KeyPress>", self._on_cmd_keypress)

    # ------------------------------------------------------------------
    def _on_cmd_keypress(self, event=None):
        if event is None or not is_f_key(event):
            return None
        return self._toggle_favorite_selected(event)

    # ==================================================================
    # Sash drag
    # ==================================================================
    def _on_paned_press(self, event):
        try:
            pos = self.paned.sashpos(0)
        except tk.TclError:
            self._paned_dragging = False
            return
        self._paned_dragging = abs(event.x - pos) <= 5

    def _on_paned_motion(self, event):
        if not self._paned_dragging:
            return
        total = self.paned.winfo_width()
        if total <= 1:
            return
        min_pos = max(self._min_left_pane, MIN_LEFT_PANE_HARD)
        max_pos = int(total * 0.25)
        max_pos = min(max_pos, total - MIN_RIGHT_PANE_HARD)
        if max_pos < min_pos:
            max_pos = min_pos
        x = event.x
        if x < min_pos:
            try:
                self.paned.sashpos(0, min_pos)
            except tk.TclError:
                pass
            return "break"
        if x > max_pos:
            try:
                self.paned.sashpos(0, max_pos)
            except tk.TclError:
                pass
            return "break"

    def _on_paned_release(self, event):
        self._paned_dragging = False

    # ==================================================================
    # Expand / collapse
    # ==================================================================
    def _expand_all_logs(self):
        self._logs_open_state = True
        for iid in self.tree.get_children(""):
            if self.tree.get_children(iid):
                self.tree.item(iid, open=True)
                kind = self._tree_kinds.get(iid)
                if kind == "folder":
                    name = self._tree_texts.get(iid, "")
                    if name:
                        self._folder_open_state[name] = True
        self.after_idle(self._update_tree_labels)

    def _collapse_all_logs(self):
        self._logs_open_state = False
        for iid in self.tree.get_children(""):
            if self.tree.get_children(iid):
                self.tree.item(iid, open=False)
                kind = self._tree_kinds.get(iid)
                if kind == "folder":
                    name = self._tree_texts.get(iid, "")
                    if name:
                        self._folder_open_state[name] = False
        self.after_idle(self._update_tree_labels)

    def _on_tree_toggle_state(self, _event=None):
        for iid in self.tree.get_children(""):
            kind = self._tree_kinds.get(iid)
            if kind == "folder":
                name = self._tree_texts.get(iid, "")
                if not name:
                    continue
                try:
                    is_open = bool(self.tree.item(iid, "open"))
                except tk.TclError:
                    continue
                self._folder_open_state[name] = is_open
            elif kind == "favroot":
                try:
                    self._fav_root_open = bool(self.tree.item(iid, "open"))
                except tk.TclError:
                    pass
        self._update_tree_labels()

    def _capture_folder_states(self):
        for iid in self.tree.get_children(""):
            kind = self._tree_kinds.get(iid)
            if kind == "folder":
                name = self._tree_texts.get(iid, "")
                if not name:
                    continue
                try:
                    is_open = bool(self.tree.item(iid, "open"))
                except tk.TclError:
                    is_open = False
                self._folder_open_state[name] = is_open
            elif kind == "favroot":
                try:
                    self._fav_root_open = bool(self.tree.item(iid, "open"))
                except tk.TclError:
                    pass

    def _restore_open_states(self):
        for iid in self.tree.get_children(""):
            kind = self._tree_kinds.get(iid)
            if kind == "folder":
                name = self._tree_texts.get(iid, "")
                if not name:
                    continue
                want = self._folder_open_state.get(
                    name, self._logs_open_state)
                try:
                    self.tree.item(iid, open=want)
                except tk.TclError:
                    pass
            elif kind == "favroot":
                try:
                    self.tree.item(iid, open=self._fav_root_open)
                except tk.TclError:
                    pass

    def _recursive_set_open(self, tree, iid, open_state):
        try:
            tree.item(iid, open=open_state)
        except tk.TclError:
            return
        for child in tree.get_children(iid):
            self._recursive_set_open(tree, child, open_state)

    def _expand_all_thermo(self):
        self._thermo_open_state = True
        for iid in self.thermo_tree.get_children(""):
            self._recursive_set_open(self.thermo_tree, iid, True)

    def _collapse_all_thermo(self):
        self._thermo_open_state = False
        for iid in self.thermo_tree.get_children(""):
            self._recursive_set_open(self.thermo_tree, iid, False)

    # ==================================================================
    # Grid overlay
    # ==================================================================
    def _install_grid(self, tree, host, columns_after):
        seps = []
        for _ in columns_after:
            f = tk.Frame(host, bg="#b0b0b0", width=1, bd=0,
                         highlightthickness=0, takefocus=0)
            f.place_forget()
            seps.append(f)
        return seps

    @staticmethod
    def _show_list(tree):
        show_attr = tree.cget("show")
        if isinstance(show_attr, (list, tuple)):
            return [str(s) for s in show_attr]
        return str(show_attr).split()

    def _update_grid(self, tree, host, seps, columns_after):
        try:
            host.update_idletasks()
        except tk.TclError:
            return
        positions = []
        x = 0
        show = self._show_list(tree)
        if "tree" in show:
            w = int(tree.column("#0", "width"))
            x += w
            if "#0" in columns_after:
                positions.append((columns_after.index("#0"), x))
        for col in tree["columns"]:
            w = int(tree.column(col, "width"))
            x += w
            if col in columns_after:
                positions.append((columns_after.index(col), x))

        try:
            tx = tree.winfo_x()
            ty = tree.winfo_y()
            th = tree.winfo_height()
            tw = tree.winfo_width()
        except tk.TclError:
            return
        if tw <= 1 or th <= 1:
            return

        for idx, pos in positions:
            if idx >= len(seps):
                continue
            sep = seps[idx]
            if pos < 2 or pos > tw - 2:
                try:
                    sep.place_forget()
                except tk.TclError:
                    pass
                continue
            try:
                sep.place(in_=host, x=tx + pos - 1, y=ty, height=th)
                sep.lift()
            except tk.TclError:
                pass

    # ==================================================================
    # Favorites
    # ==================================================================
    def _key_from_iid(self, iid):
        return iid[5:] if iid.startswith("fav::") else iid

    def _prefix_for(self, iid):
        kind = self._tree_kinds.get(iid)
        if kind == "folder":
            return "📁 "
        if kind == "favroot":
            return "⭐ "
        key = self._key_from_iid(iid)
        return "★ " if key in self._favorites else "☆ "

    def _item_depth(self, iid):
        d = 0
        p = self.tree.parent(iid)
        while p:
            d += 1
            p = self.tree.parent(p)
        return d

    def _on_tree_left_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if self.tree.identify_column(event.x) != "#0":
            return
        kind = self._tree_kinds.get(iid)
        if kind not in ("file", "favfile"):
            return
        bbox = self.tree.bbox(iid, "#0")
        if not bbox:
            return
        cell_x = bbox[0]
        rel_x = event.x - cell_x
        depth = self._item_depth(iid)
        star_start = depth * 20
        star_end = star_start + 26
        if star_start - 2 <= rel_x <= star_end:
            self._toggle_favorite(iid)

    def _toggle_favorite(self, iid):
        key = self._key_from_iid(iid)
        if key in self._favorites:
            self._favorites.discard(key)
        else:
            self._favorites.add(key)

        try:
            yview = self.tree.yview()
        except tk.TclError:
            yview = (0.0, 1.0)

        self._refresh_tree()

        target = None
        if key in self.data.raw:
            target = key
        elif self.current_key and self.current_key in self.data.raw:
            target = self.current_key

        if target is not None:
            try:
                self.tree.selection_set(target)
                self.tree.focus(target)
            except tk.TclError:
                pass

        self._restore_open_states()

        try:
            self.tree.focus_set()
        except tk.TclError:
            pass

        try:
            self.tree.yview_moveto(yview[0])
        except tk.TclError:
            pass

        def _restore_scroll_late():
            try:
                self.tree.yview_moveto(yview[0])
            except tk.TclError:
                pass
        self.after_idle(_restore_scroll_late)

    def _add_all_favorites(self):
        added = 0
        for key in self.data.keys():
            if key not in self._favorites:
                self._favorites.add(key)
                added += 1
        if added:
            prev_key = self.current_key
            self._refresh_tree()
            if prev_key is not None and prev_key in self.data.raw:
                try:
                    self.tree.selection_set(prev_key)
                    self.tree.focus(prev_key)
                    self.tree.focus_set()
                except tk.TclError:
                    pass
            self._restore_open_states()

    def _clear_favorites(self):
        if not self._favorites:
            return
        self._favorites.clear()
        prev_key = self.current_key
        self._refresh_tree()
        if prev_key is not None and prev_key in self.data.raw:
            try:
                self.tree.selection_set(prev_key)
                self.tree.focus(prev_key)
                self.tree.focus_set()
            except tk.TclError:
                pass
        self._restore_open_states()

    def _is_inside_self(self, widget):
        w = widget
        while w is not None:
            if w is self:
                return True
            w = getattr(w, "master", None)
        return False

    def _toggle_favorite_selected(self, event=None):
        if event is not None and event.widget is not None:
            if not self._is_inside_self(event.widget):
                return None
            try:
                cls = event.widget.winfo_class()
            except (tk.TclError, AttributeError):
                cls = ""
            if cls in ("TEntry", "Entry", "TCombobox", "TSpinbox", "Text"):
                return None

        if not hasattr(self, "tree") or not self.tree.winfo_exists():
            return "break"

        sel = self.tree.selection()
        if not sel:
            return "break"
        iid = sel[0]
        kind = self._tree_kinds.get(iid)
        if kind not in ("file", "favfile"):
            return "break"
        self._toggle_favorite(iid)
        return "break"

    def _fav_root_iid(self):
        for iid in self.tree.get_children(""):
            if self._tree_kinds.get(iid) == "favroot":
                return iid
        return None

    # ==================================================================
    # Frequencies tab
    # ==================================================================
    def _build_freq_tab(self):
        wrap = ttk.Frame(self.tab_freq)
        wrap.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(wrap, padding=(4, 4))
        top.pack(fill=tk.X)

        self.freq_summary = ttk.Label(top, text="", style="Summary.TLabel",
                                      justify=tk.LEFT)
        self.freq_summary.pack(side=tk.LEFT, anchor=tk.W)

        self.plot_btn = ttk.Button(top, text="Plot",
                                   command=self._open_plot_window,
                                   state=tk.DISABLED)
        self.plot_btn.pack(side=tk.RIGHT)

        table = ttk.Frame(wrap)
        table.pack(fill=tk.BOTH, expand=True)

        num_w = self._header_font.measure("Number") + 16
        self._num_col_width = num_w

        freq_min = self._header_font.measure("Frequency (cm⁻¹)") + 24

        cols = ("index", "frequency")
        self.freq_tree = ttk.Treeview(table, columns=cols, show="headings",
                                      selectmode="browse")

        self.freq_tree.heading("index", text="Number",
                               command=lambda: self._sort_freq("index"))
        self.freq_tree.heading("frequency", text="Frequency (cm⁻¹)",
                               command=lambda: self._sort_freq("frequency"))

        self.freq_tree.column("index", width=num_w, minwidth=num_w,
                              anchor=tk.CENTER, stretch=False)
        self.freq_tree.column("frequency",
                              width=max(160, freq_min),
                              minwidth=freq_min,
                              anchor=tk.CENTER, stretch=True)

        self.freq_tree.bind("<ButtonPress-1>",
                            self._block_number_resize, add="+")
        self.freq_tree.bind("<B1-Motion>",
                            self._restore_number_width_soft, add="+")
        self.freq_tree.bind("<ButtonRelease-1>",
                            self._restore_number_width, add="+")

        vsb = ttk.Scrollbar(table, orient="vertical",
                            command=self.freq_tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.freq_tree.configure(yscrollcommand=vsb.set)
        self.freq_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.freq_tree.tag_configure("imag", background="#ffd6d6")
        self.freq_tree.tag_configure("zero", foreground="#999999")
        self.freq_tree.tag_configure("normal", background="#ffffff")

        self.freq_tree.bind("<Button-3>", self._on_freq_right_click)
        if IS_MAC:
            self.freq_tree.bind("<Control-Button-1>",
                                self._on_freq_right_click)

        self.freq_tree.bind(
            "<Configure>",
            lambda e: self._update_grid(self.freq_tree, table,
                                        self._freq_seps, ["index"]))

        self._freq_seps = self._install_grid(self.freq_tree, table, ["index"])
        self._freq_sort_state = {"col": None, "reverse": False}

    def _sort_freq(self, col):
        st = self._freq_sort_state
        st["reverse"] = (st["col"] == col and not st["reverse"])
        st["col"] = col
        rows = [(self.freq_tree.set(i, col), i)
                for i in self.freq_tree.get_children("")]
        if col in ("index", "frequency"):
            rows.sort(key=lambda x: float(x[0]), reverse=st["reverse"])
        else:
            rows.sort(key=lambda x: x[0].lower(), reverse=st["reverse"])
        for idx, (_, iid) in enumerate(rows):
            self.freq_tree.move(iid, "", idx)
        self.after_idle(self._update_freq_grid)

    def _update_freq_grid(self):
        self._update_grid(self.freq_tree, self.freq_tree.master,
                          self._freq_seps, ["index"])

    def _update_thermo_grid(self):
        self._update_grid(self.thermo_tree, self.thermo_tree.master,
                          self._thermo_seps, ["#0"])

    def _block_number_resize(self, event):
        try:
            region = self.freq_tree.identify_region(event.x, event.y)
            col = self.freq_tree.identify_column(event.x)
        except tk.TclError:
            return
        if region == "separator" and col in ("#1", "#2"):
            return "break"

    def _restore_number_width_soft(self, event=None):
        if not self._num_col_width:
            return
        try:
            current = int(self.freq_tree.column("index", "width"))
        except tk.TclError:
            return
        if current != self._num_col_width:
            try:
                self.freq_tree.column("index", width=self._num_col_width)
            except tk.TclError:
                pass

    def _restore_number_width(self, event=None):
        self._restore_number_width_soft(event)

    # ==================================================================
    # Thermochemistry tab
    # ==================================================================
    def _build_thermo_tab(self):
        wrap = ttk.Frame(self.tab_thermo)
        wrap.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(wrap, padding=(4, 4))
        top.pack(fill=tk.X)

        ttk.Label(top, text="Thermochemistry data",
                  style="Summary.TLabel").pack(side=tk.LEFT)

        ttk.Button(top, text="Collapse all", width=12,
                   command=self._collapse_all_thermo).pack(side=tk.RIGHT)
        ttk.Button(top, text="Expand all", width=12,
                   command=self._expand_all_thermo).pack(
            side=tk.RIGHT, padx=(0, 4))
        ttk.Button(top, text="Temperature analysis…",
                   command=self._open_temperature_analysis).pack(
            side=tk.RIGHT, padx=(0, 6))

        tree_wrap = ttk.Frame(wrap)
        tree_wrap.pack(fill=tk.BOTH, expand=True)

        val_min = self._header_font.measure("Value") + 24
        qty_min = self._header_font.measure("Quantity") + 24

        self.thermo_tree = ttk.Treeview(tree_wrap, columns=("value",),
                                        show="tree headings",
                                        selectmode="browse")
        self.thermo_tree.heading("#0", text="Quantity")
        self.thermo_tree.heading("value", text="Value")

        self.thermo_tree.column("#0",
                                width=self._quantity_col_width,
                                minwidth=qty_min,
                                anchor=tk.W, stretch=False)
        self.thermo_tree.column("value",
                                width=max(220, val_min),
                                minwidth=val_min,
                                anchor=tk.W, stretch=True)

        self.thermo_tree.bind("<ButtonPress-1>",
                              self._block_quantity_resize, add="+")
        self.thermo_tree.bind("<B1-Motion>",
                              self._restore_quantity_width_soft, add="+")
        self.thermo_tree.bind("<ButtonRelease-1>",
                              self._restore_quantity_width, add="+")

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical",
                            command=self.thermo_tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.thermo_tree.configure(yscrollcommand=vsb.set)
        self.thermo_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.thermo_tree.tag_configure(
            "temp", background="#dbe7f3", font=make_font(10, weight="bold"))
        self.thermo_tree.tag_configure(
            "cat", background="#eef3fa", font=make_font(10, weight="bold"))
        self.thermo_tree.tag_configure("odd", background="#f7f7f7")

        self.thermo_tree.bind("<Button-3>", self._on_thermo_right_click)
        if IS_MAC:
            self.thermo_tree.bind("<Control-Button-1>",
                                  self._on_thermo_right_click)

        self._thermo_seps = self._install_grid(self.thermo_tree, tree_wrap,
                                               ["#0"])
        self.thermo_tree.bind(
            "<Configure>",
            lambda e: self._update_grid(self.thermo_tree, tree_wrap,
                                        self._thermo_seps, ["#0"]))

    def _block_quantity_resize(self, event):
        try:
            region = self.thermo_tree.identify_region(event.x, event.y)
            col = self.thermo_tree.identify_column(event.x)
        except tk.TclError:
            return
        if region == "separator" and col in ("#0", "#1"):
            return "break"

    def _restore_quantity_width_soft(self, event=None):
        try:
            current = int(self.thermo_tree.column("#0", "width"))
        except tk.TclError:
            return
        if current != self._quantity_col_width:
            try:
                self.thermo_tree.column("#0", width=self._quantity_col_width)
            except tk.TclError:
                pass

    def _restore_quantity_width(self, event=None):
        self._restore_quantity_width_soft(event)
        self.after_idle(self._update_thermo_grid)

    # ==================================================================
    # General Data + dynamic tabs
    # ==================================================================
    def _build_general_tab(self):
        self.general_tab = GeneralTab(self.tab_general,
                                      on_copy=self._show_toast)
        self.general_tab.pack(fill=tk.BOTH, expand=True)

    def _clear_dynamic_tabs(self):
        for key in list(self._dynamic_tabs.keys()):
            w = self._dynamic_tabs.pop(key)
            try:
                self.nb.forget(w)
                w.destroy()
            except tk.TclError:
                pass

    def _add_dynamic_tab(self, key, widget, label):
        self.nb.add(widget, text=label)
        self._dynamic_tabs[key] = widget

    def _method_title(self, key):
        try:
            from orca_parser import METHODS_BY_KEY
        except Exception:
            METHODS_BY_KEY = {}
        m = METHODS_BY_KEY.get(key)
        if m:
            return m["name"]
        return key.replace("_", " ").title()

    # ==================================================================
    # Status bar
    # ==================================================================
    def _build_status(self):
        bar = ttk.Frame(self, padding=(0, 0))
        bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.status = ttk.Label(bar, text="Ready",
                                style="Status.TLabel",
                                anchor=tk.W, padding=(6, 2))
        self.status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.path_label = ttk.Label(bar, text="Current .json file: —",
                                    style="Status.TLabel",
                                    anchor=tk.E, padding=(6, 2))
        self.path_label.pack(side=tk.RIGHT)

    # ==================================================================
    # Toast
    # ==================================================================
    def _build_toast(self):
        self._toast = tk.Label(
            self, text="Value copied",
            bg="white", fg="#1e8449",
            font=self._tab_font,
            bd=0, highlightthickness=0,
            padx=6, pady=2)
        self._toast.place_forget()

    def _show_toast(self, text="Value copied"):
        if self._toast is None:
            return
        self._toast.config(text=text)
        self.update_idletasks()
        try:
            nb_top = self.nb.winfo_rooty() - self.winfo_rooty()
        except tk.TclError:
            nb_top = 60
        try:
            tab_h = self._tab_font.metrics("linespace") + 16
        except Exception:
            tab_h = 30
        y_bottom = nb_top + tab_h - 4
        self._toast.place(relx=1.0, x=-18, y=y_bottom, anchor="se")
        self._toast.lift()
        if self._toast_job:
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(1500, self._hide_toast)

    def _hide_toast(self):
        if self._toast is not None:
            self._toast.place_forget()
        self._toast_job = None

    # ==================================================================
    # Pane limits
    # ==================================================================
    def _enforce_pane_limits(self, event=None):
        if self.paned is None:
            return
        try:
            pos = self.paned.sashpos(0)
        except tk.TclError:
            return
        total = self.paned.winfo_width()
        if total <= 1:
            return
        min_pos = max(self._min_left_pane, MIN_LEFT_PANE_HARD)
        max_pos = int(total * 0.25)
        max_pos = min(max_pos, total - MIN_RIGHT_PANE_HARD)
        if max_pos < min_pos:
            max_pos = min_pos
        if pos < min_pos:
            self.paned.sashpos(0, min_pos)
        elif pos > max_pos:
            self.paned.sashpos(0, max_pos)

    # ==================================================================
    # Ellipsis / header
    # ==================================================================
    def _update_tree_labels(self, event=None):
        if not hasattr(self, "tree"):
            return
        width = self.tree.winfo_width()
        if width <= 1:
            return
        font_obj = self._tree_font

        def _set(iid, avail):
            prefix = self._prefix_for(iid)
            full = self._tree_texts.get(iid, "")
            prefix_w = font_obj.measure(prefix)
            avail_text = max(20, avail - prefix_w)
            self.tree.item(iid, text=prefix
                           + elide_left(full, avail_text, font_obj))

        for top_iid in self.tree.get_children(""):
            children = self.tree.get_children(top_iid)
            if children:
                _set(top_iid, max(30, width - 46))
                for child_iid in children:
                    _set(child_iid, max(30, width - 68))
            else:
                _set(top_iid, max(30, width - 46))

    def _set_header(self, text):
        self._header_full = text
        self._update_header_display()

    def _update_header_display(self, event=None):
        if self._right_frame is None:
            return
        try:
            width = self._right_frame.winfo_width()
        except tk.TclError:
            return
        if width <= 1:
            return
        avail = max(60, width - 16)
        display = elide_left(self._header_full, avail, self._tree_font)
        self.header.config(text=display)

    # ==================================================================
    # Tree
    # ==================================================================
    def _refresh_tree(self):
        if not hasattr(self, "tree"):
            return
        self._capture_folder_states()

        self.tree.delete(*self.tree.get_children(""))
        self._tree_texts.clear()
        self._tree_kinds.clear()
        query = self.search_var.get().strip().lower() \
            if hasattr(self, "search_var") else ""

        if self._favorites:
            fav_root = self.tree.insert("", "end", text="⭐ Favorites",
                                        open=self._fav_root_open)
            self._tree_texts[fav_root] = "Favorites"
            self._tree_kinds[fav_root] = "favroot"
            for key in sorted(self._favorites):
                if key not in self.data.raw:
                    continue
                name = key.split("\\")[-1] if "\\" in key else key
                fav_iid = "fav::" + key
                self.tree.insert(fav_root, "end", text="★ " + name,
                                 values=(key,), iid=fav_iid)
                self._tree_texts[fav_iid] = name
                self._tree_kinds[fav_iid] = "favfile"

        groups = OrderedDict()
        for key in self.data.keys():
            if query and query not in key.lower():
                continue
            if "\\" in key:
                grp, name = key.split("\\", 1)
            else:
                grp, name = "", key
            groups.setdefault(grp, []).append((name, key))

        for grp, items in groups.items():
            if grp:
                open_state = self._folder_open_state.get(
                    grp, self._logs_open_state)
                parent = self.tree.insert("", "end", text="📁 " + grp,
                                          open=open_state)
                self._tree_texts[parent] = grp
                self._tree_kinds[parent] = "folder"
                for name, key in items:
                    self.tree.insert(parent, "end",
                                     text="☆ " + name,
                                     values=(key,), iid=key)
                    self._tree_texts[key] = name
                    self._tree_kinds[key] = "file"
            else:
                for name, key in items:
                    self.tree.insert("", "end",
                                     text="☆ " + name,
                                     values=(key,), iid=key)
                    self._tree_texts[key] = name
                    self._tree_kinds[key] = "file"

        self.after_idle(self._update_tree_labels)

    def _on_tree_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        key = self._key_from_iid(iid)
        if key not in self.data.raw:
            return
        self.current_key = key
        self._show_entry(key)

    # ==================================================================
    # Show entry
    # ==================================================================
    def _show_entry(self, key):
        entry = self.data.get(key)
        self._set_header(f"Current .log file: {key}")

        freqs = entry.get("vibrational_frequencies", []) or []
        n_real = sum(1 for f in freqs if f.get("frequency", 0) != 0)
        n_imag = sum(1 for f in freqs if f.get("frequency", 0) < 0)
        self._freq_data_cache = freqs

        if n_imag == 0:
            neg_phrase = "Has no negative frequencies"
        elif n_imag == 1:
            neg_phrase = "Has 1 negative frequency"
        else:
            neg_phrase = f"Has {n_imag} negative frequencies"

        summary = (f"Total modes: {len(freqs)}   |   "
                   f"real: {n_real}   |   {neg_phrase}")
        self.freq_summary.config(text=summary)

        self._fill_freq(freqs)
        self.plot_btn.config(
            state=tk.NORMAL if n_real > 0 else tk.DISABLED)

        th = entry.get("thermochemistry") or {}
        self._fill_thermo(th)

        self._clear_dynamic_tabs()
        flat_groups = []

        reserved = {"vibrational_frequencies",
                    "has_negative_frequencies",
                    "thermochemistry"}

        for top_key, value in entry.items():
            if top_key in reserved:
                continue
            title = self._method_title(top_key)
            kind = detect_kind(value)

            if kind == "series" and isinstance(value, list) and value:
                tab = SeriesTab(self.nb, title, value,
                                on_copy=self._show_toast)
                self._add_dynamic_tab(top_key, tab, title)
            elif kind == "nested" and isinstance(value, dict) and value:
                tab = NestedTab(self.nb, title, value,
                                on_copy=self._show_toast)
                self._add_dynamic_tab(top_key, tab, title)
            else:
                if isinstance(value, dict):
                    flat_groups.append((title, value))
                elif value is not None:
                    flat_groups.append((title, {"value": value}))

        self.general_tab.populate(flat_groups)

    def _fill_freq(self, freqs):
        self.freq_tree.delete(*self.freq_tree.get_children(""))
        for f in freqs:
            idx = f.get("index", "")
            val = f.get("frequency", 0.0)
            if val == 0:
                tag = "zero"
            elif val < 0:
                tag = "imag"
            else:
                tag = "normal"
            self.freq_tree.insert("", "end", iid=f"f{idx}",
                                  values=(idx, f"{val:.2f}"),
                                  tags=(tag,))
        self.after_idle(self._update_freq_grid)

    def _fill_thermo(self, thermo):
        self.thermo_tree.delete(*self.thermo_tree.get_children(""))
        if not thermo:
            self.thermo_tree.insert("", "end",
                                    text="No thermochemistry data",
                                    values=("",), tags=("odd",))
            self.after_idle(self._update_thermo_grid)
            return

        open_state = (self._thermo_open_state
                      if self._thermo_open_state is not None else False)

        pretty = {
            "inner_energy": "Inner energy (a.u.)",
            "enthalpy": "Enthalpy (a.u.)",
            "entropy": "Entropy (a.u.)",
            "gibbs_free_energy": "Gibbs free energy (a.u.)",
        }

        leaf_idx = 0
        for T, block in thermo.items():
            temp_node = self.thermo_tree.insert(
                "", "end", text=f"T = {T} K",
                values=("",), tags=("temp",), open=open_state)

            for category in ("inner_energy", "enthalpy",
                             "entropy", "gibbs_free_energy"):
                cat_block = block.get(category)
                if not cat_block:
                    continue
                cat_node = self.thermo_tree.insert(
                    temp_node, "end",
                    text=pretty.get(category, category),
                    values=("",), tags=("cat",), open=open_state)

                for name, value in cat_block.items():
                    if isinstance(value, (int, float)):
                        vtext = f"{value:.8f}"
                    else:
                        vtext = str(value)
                    tag = ("odd",) if leaf_idx % 2 else ()
                    self.thermo_tree.insert(
                        cat_node, "end", text="  " + name,
                        values=(vtext,), tags=tag)
                    leaf_idx += 1
        self.after_idle(self._update_thermo_grid)

    # ==================================================================
    # Right-click copy
    # ==================================================================
    def _on_freq_right_click(self, event):
        iid = self.freq_tree.identify_row(event.y)
        col = self.freq_tree.identify_column(event.x)
        if not iid:
            return
        if col == "#1":
            value = self.freq_tree.set(iid, "index")
        elif col == "#2":
            value = self.freq_tree.set(iid, "frequency")
        else:
            return
        self._copy_to_clipboard(value)

    def _on_thermo_right_click(self, event):
        iid = self.thermo_tree.identify_row(event.y)
        if not iid:
            return
        value = self.thermo_tree.set(iid, "value")
        if not value:
            return
        self._copy_to_clipboard(value)

    def _copy_to_clipboard(self, text):
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()
        self._show_toast("Value copied")

    # ==================================================================
    # External windows
    # ==================================================================
    def _open_plot_window(self):
        if self.current_key is None:
            return
        open_plot_window(self, self.current_key, self._freq_data_cache)

    def _open_analysis(self):
        AnalysisWindow(self, self.data, self._favorites)

    def _open_temperature_analysis(self):
        TemperatureWindow(self, self.data, current_key=self.current_key)