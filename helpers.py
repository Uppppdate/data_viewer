"""Small utility helpers used across the app."""
import json
import os


MIN_LEFT_PANE_HARD = 120
MIN_RIGHT_PANE_HARD = 260


# Store recent JSON paths next to the scripts.
RECENT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "recent_json.json")


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


# ---------------------------------------------------------------------------
# Recent JSON files
# ---------------------------------------------------------------------------
def load_recent_paths(max_n=5):
    """Return up to `max_n` existing recent JSON paths, newest first."""
    if not os.path.isfile(RECENT_FILE):
        return []
    try:
        with open(RECENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for p in data:
        if not isinstance(p, str):
            continue
        if not os.path.isfile(p):
            continue
        out.append(p)
        if len(out) >= max_n:
            break
    return out


def save_recent_paths(paths):
    try:
        with open(RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(list(paths)[:5], f, indent=2)
    except Exception:
        pass


def push_recent_path(path):
    """Move `path` to the top of the recent list and save."""
    path = os.path.abspath(path)
    paths = load_recent_paths()
    paths = [p for p in paths if p != path]
    paths.insert(0, path)
    save_recent_paths(paths)
    return paths