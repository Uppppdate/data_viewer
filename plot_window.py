"""Plot windows for the app: specific (frequencies) and generic (series)."""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ===========================================================================
# Common helpers
# ===========================================================================
def _short_name(key):
    return os.path.basename(key.replace("\\", "/"))


def _try_import_mpl():
    try:
        import matplotlib
        try:
            matplotlib.use("TkAgg", force=True)
        except Exception:
            pass
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        return Figure, FigureCanvasTkAgg, None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"


def _decorate_axes(ax):
    ax.axhline(0, color="#222", linewidth=0.9)
    for sp in ax.spines.values():
        sp.set_visible(True)
        sp.set_linewidth(1.2)
        sp.set_color("#333")
    ax.tick_params(direction="out", length=5, width=1.0, colors="#222")
    ax.grid(True, alpha=0.25, linestyle="--", linewidth=0.6)


def _draw_bar_plot(fig, xs, ys, x_label, y_label, title):
    ax = fig.add_subplot(111)
    colors = ["#d62728" if y < 0 else "#1f77b4" for y in ys]
    ax.bar(xs, ys, color=colors, width=0.85,
           edgecolor="#20304a", linewidth=0.4)
    _decorate_axes(ax)
    ax.set_xlabel(x_label, color="#222")
    ax.set_ylabel(y_label, color="#222")
    ax.set_title(title, color="#111")
    fig.tight_layout(pad=1.4)


def _attach_mpl_canvas(win, top, fig, FigureCanvasTkAgg, default_name):
    def save_plot():
        path = filedialog.asksaveasfilename(
            parent=win, title="Save plot",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG image", "*.png"),
                       ("PDF document", "*.pdf"),
                       ("SVG image", "*.svg"),
                       ("All files", "*.*")])
        if not path:
            return
        try:
            fig.savefig(path, dpi=200, bbox_inches="tight",
                        facecolor=fig.get_facecolor())
        except Exception as e:
            messagebox.showerror("Save failed", str(e), parent=win)
            return
        messagebox.showinfo("Saved", f"Plot saved to:\n{path}", parent=win)

    ttk.Button(top, text="Save plot…", command=save_plot).pack(side=tk.RIGHT)

    canvas = FigureCanvasTkAgg(fig, master=win)
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    canvas.draw()


def _fallback_canvas(win, xs, ys, x_label, y_label, err):
    msg = "matplotlib not available — drawing on plain canvas."
    if err:
        msg += f"  ({err})"
    ttk.Label(win, text=msg, foreground="#a00").pack(
        side=tk.TOP, anchor=tk.W, padx=10)

    cv = tk.Canvas(win, bg="white", highlightthickness=1,
                   highlightbackground="#8a8a8a")
    cv.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    def redraw(_e=None):
        _render_canvas(cv, xs, ys, x_label, y_label)
    cv.bind("<Configure>", redraw)
    win.update_idletasks()
    redraw()


def _render_canvas(cv, xs, ys, x_label, y_label):
    cv.delete("all")
    W = cv.winfo_width() or 800
    H = cv.winfo_height() or 500
    pad = 52

    ymin, ymax = min(ys), max(ys)
    if ymin == ymax:
        ymin, ymax = ymin - 1, ymax + 1
    xmin, xmax = min(xs), max(xs)
    if xmin == xmax:
        xmin, xmax = xmin - 1, xmax + 1

    def X(x):
        return pad + (x - xmin) / max(1, (xmax - xmin)) * (W - 2 * pad)

    def Y(y):
        return H - pad - (y - ymin) / (ymax - ymin) * (H - 2 * pad)

    cv.create_rectangle(pad, pad, W - pad, H - pad,
                        outline="#333", width=1.2)
    cv.create_line(pad, Y(0), W - pad, Y(0), fill="#222", width=0.9)
    cv.create_text(pad - 8, Y(0), text="0", anchor=tk.E, fill="#333")

    bw = max(2, (W - 2 * pad) / max(1, len(xs)) * 0.8)
    for x, y in zip(xs, ys):
        color = "#d62728" if y < 0 else "#1f77b4"
        cv.create_rectangle(X(x) - bw / 2, Y(0),
                            X(x) + bw / 2, Y(y),
                            fill=color, outline="#20304a", width=0.4)

    cv.create_text(W / 2, H - 22, text=x_label, fill="#333")
    cv.create_text(18, H / 2, text=y_label, angle=90, fill="#333")


# ===========================================================================
# Public API
# ===========================================================================
def open_series_plot(parent, title, xs, ys, x_label, y_label):
    """Generic bar plot for arbitrary x/y numeric data."""
    if not xs or not ys:
        return
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("900x600")
    win.transient(parent)
    win.configure(bg="white")

    top = ttk.Frame(win, padding=(10, 6))
    top.pack(side=tk.TOP, fill=tk.X)
    ttk.Label(top, text=title,
              font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

    Figure, Canvas, err = _try_import_mpl()
    if Figure is not None:
        fig = Figure(figsize=(8.0, 5.2), dpi=100, facecolor="white")
        fig.patch.set_edgecolor("#8a8a8a")
        fig.patch.set_linewidth(1.2)
        _draw_bar_plot(fig, xs, ys, x_label, y_label, title)
        base = title.replace(" ", "_").replace("\\", "_").replace("/", "_")
        _attach_mpl_canvas(win, top, fig, Canvas, f"{base}.png")
    else:
        _fallback_canvas(win, xs, ys, x_label, y_label, err)


def open_plot_window(parent, key, freq_data):
    """Specialized plot for the built-in Vibrational Frequencies tab."""
    real = [(f.get("index", i), f.get("frequency", 0.0))
            for i, f in enumerate(freq_data)
            if f.get("frequency", 0.0) != 0]
    if not real:
        messagebox.showinfo("Plot", "No non-zero frequencies to plot.")
        return

    xs = [p[0] for p in real]
    ys = [p[1] for p in real]
    short = _short_name(key)
    open_series_plot(parent, f"Vibrational Frequencies — {short}",
                     xs, ys, "Mode index", "Frequency (cm⁻¹)")

def open_line_plot(parent, title, xs, ys, x_label, y_label):
    """Line plot with markers for (x, y) sequences (e.g. property vs T)."""
    if not xs or not ys:
        return

    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("900x600")
    win.transient(parent)
    win.configure(bg="white")

    top = ttk.Frame(win, padding=(10, 6))
    top.pack(side=tk.TOP, fill=tk.X)
    ttk.Label(top, text=title,
              font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

    Figure, Canvas, err = _try_import_mpl()
    if Figure is not None:
        fig = Figure(figsize=(8.0, 5.2), dpi=100, facecolor="white")
        fig.patch.set_edgecolor("#8a8a8a")
        fig.patch.set_linewidth(1.2)

        ax = fig.add_subplot(111)
        ax.plot(xs, ys, "-o", color="#1f77b4",
                markersize=6, linewidth=1.6,
                markerfacecolor="#1f77b4",
                markeredgecolor="#20304a")
        for sp in ax.spines.values():
            sp.set_visible(True)
            sp.set_linewidth(1.2)
            sp.set_color("#333")
        ax.tick_params(direction="out", length=5, width=1.0,
                       colors="#222")
        ax.grid(True, alpha=0.25, linestyle="--", linewidth=0.6)
        ax.set_xlabel(x_label, color="#222")
        ax.set_ylabel(y_label, color="#222")
        ax.set_title(title, color="#111")
        fig.tight_layout(pad=1.4)

        base = "".join(
            c if (c.isalnum() or c in "-_.") else "_"
            for c in title)
        _attach_mpl_canvas(win, top, fig, Canvas, f"{base}.png")
    else:
        _fallback_line_canvas(win, xs, ys, x_label, y_label, err)


def _fallback_line_canvas(win, xs, ys, x_label, y_label, err):
    msg = "matplotlib not available — drawing on plain canvas."
    if err:
        msg += f"  ({err})"
    ttk.Label(win, text=msg, foreground="#a00").pack(
        side=tk.TOP, anchor=tk.W, padx=10)

    cv = tk.Canvas(win, bg="white", highlightthickness=1,
                   highlightbackground="#8a8a8a")
    cv.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

    def redraw(_e=None):
        _render_line_canvas(cv, xs, ys, x_label, y_label)
    cv.bind("<Configure>", redraw)
    win.update_idletasks()
    redraw()


def _render_line_canvas(cv, xs, ys, x_label, y_label):
    cv.delete("all")
    W = cv.winfo_width() or 800
    H = cv.winfo_height() or 500
    pad = 60

    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmin == xmax:
        xmin, xmax = xmin - 1, xmax + 1
    if ymin == ymax:
        ymin, ymax = ymin - 1, ymax + 1

    def X(x):
        return pad + (x - xmin) / (xmax - xmin) * (W - 2 * pad)

    def Y(y):
        return H - pad - (y - ymin) / (ymax - ymin) * (H - 2 * pad)

    cv.create_rectangle(pad, pad, W - pad, H - pad,
                        outline="#333", width=1.2)

    pts = [(X(x), Y(y)) for x, y in zip(xs, ys)]
    for i in range(len(pts) - 1):
        cv.create_line(*pts[i], *pts[i + 1],
                       fill="#1f77b4", width=1.8)
    for x, y in pts:
        cv.create_oval(x - 3, y - 3, x + 3, y + 3,
                       fill="#1f77b4", outline="#20304a")

    cv.create_text(W / 2, H - 22, text=x_label, fill="#333")
    cv.create_text(18, H / 2, text=y_label, angle=90, fill="#333")