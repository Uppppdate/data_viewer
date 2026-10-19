"""Small utility helpers used across the app."""
import os


# Fallback pixel limits for the panes if font measurement ever fails
MIN_LEFT_PANE_HARD = 120
MIN_RIGHT_PANE_HARD = 260


def elide_left(text, max_px, font_obj):
    """Return `text` truncated from the left with '…' if too wide."""
    if not text:
        return text
    if font_obj.measure(text) <= max_px:
        return text
    ell = "…"
    if font_obj.measure(ell) >= max_px:
        return ell
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        if font_obj.measure(ell + text[mid:]) <= max_px:
            hi = mid
        else:
            lo = mid + 1
    return ell + text[lo:]


def next_available_path(path):
    """Return a path that does not exist yet.

    If `path` exists, appends `_2`, `_3`, … before the extension.

        data.json  →  data_2.json  →  data_3.json  →  …
    """
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while True:
        candidate = f"{base}_{i}{ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1