"""1-px column separators drawn over a ttk.Treeview.

ttk.Treeview has no built-in grid lines. This helper overlays thin
tk.Frame widgets on the boundary between columns, giving the appearance
of a fully gridded table. It correctly handles both Python <3.12 and
3.14 (where cget("show") returns a tuple instead of a string).
"""
import tkinter as tk


def _show_list(tree):
    v = tree.cget("show")
    if isinstance(v, (list, tuple)):
        return [str(s) for s in v]
    return str(v).split()


class TableGrid:
    def __init__(self, tree, host):
        """Create one separator per column boundary (all but the last).

        `tree` — the Treeview.
        `host` — the frame that directly contains the tree; the
                 separators will be placed inside it.
        """
        self.tree = tree
        self.host = host
        self.seps = []

        cols = []
        if "tree" in _show_list(tree):
            cols.append("#0")
        cols.extend(list(tree["columns"]))
        # No separator is needed on the right edge of the last column.
        self.columns = cols[:-1] if cols else []

        for _ in self.columns:
            f = tk.Frame(host, bg="#b0b0b0", width=1, bd=0,
                         highlightthickness=0, takefocus=0)
            f.place_forget()
            self.seps.append(f)

        tree.bind("<Configure>", lambda e: self.update(), add="+")
        host.bind("<Configure>", lambda e: self.update(), add="+")

    def update(self):
        if not self.columns:
            return
        try:
            self.host.update_idletasks()
            tx = self.tree.winfo_x()
            ty = self.tree.winfo_y()
            th = self.tree.winfo_height()
            tw = self.tree.winfo_width()
        except tk.TclError:
            return
        if tw <= 1 or th <= 1:
            return

        x = 0
        edges = []
        for col in self.columns:
            try:
                w = int(self.tree.column(col, "width"))
            except tk.TclError:
                w = 0
            x += w
            edges.append(x)

        for sep, pos in zip(self.seps, edges):
            if pos < 2 or pos > tw - 2:
                try:
                    sep.place_forget()
                except tk.TclError:
                    pass
                continue
            try:
                sep.place(in_=self.host, x=tx + pos - 1, y=ty, height=th)
                sep.lift()
            except tk.TclError:
                pass