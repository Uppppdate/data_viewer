"""Cross-platform helpers: fonts, modifiers, maximize, wheel deltas."""
import sys
import tkinter as tk
from tkinter import font as tkfont


IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")


# ---------------- Fonts ----------------
_FONT_CANDIDATES = (
    ["SF Pro Text", "Helvetica Neue", "Helvetica", "Arial"]
    if IS_MAC else
    ["Segoe UI", "Helvetica", "Arial"]
)


def font_family():
    try:
        available = set(tkfont.families())
    except Exception:
        return "Helvetica"
    for family in _FONT_CANDIDATES:
        if family in available:
            return family
    return "Helvetica"


def make_font(size=10, weight="normal", slant="roman"):
    return tkfont.Font(family=font_family(), size=size,
                       weight=weight, slant=slant)


def default_ui_size():
    return 13 if IS_MAC else 10


# ---------------- Keyboard ----------------
MODIFIERS = ("Command", "Control") if IS_MAC else ("Control",)


def modifier_event(key):
    events = []
    for mod in MODIFIERS:
        events.append(f"<{mod}-{key.lower()}>")
        events.append(f"<{mod}-{key.upper()}>")
    return events


# --- Layout-independent physical-key detection ---------------------------
def _keysym_lower(event):
    try:
        return (event.keysym or "").lower()
    except AttributeError:
        return ""


def is_f_key(event):
    """True if the event corresponds to the physical F key.

    Works for English, Russian (ЙЦУКЕН: 'а' on F), phonetic, and any
    other layout, thanks to the hardware keycode check on macOS.
    """
    if _keysym_lower(event) in ("f", "cyrillic_a", "cyrillic_ef"):
        return True
    kc = getattr(event, "keycode", None)
    if IS_MAC and kc == 3:          # physical F on macOS
        return True
    if IS_WINDOWS and kc in (ord("f"), ord("F")):
        return True
    return False


def is_s_key(event):
    """True if the event corresponds to the physical S key."""
    if _keysym_lower(event) in ("s", "cyrillic_yeru", "cyrillic_ysl"):
        return True
    kc = getattr(event, "keycode", None)
    if IS_MAC and kc == 1:          # physical S on macOS
        return True
    if IS_WINDOWS and kc in (ord("s"), ord("S")):
        return True
    return False


# ---------------- Maximize ----------------
def maximize(window):
    window.update_idletasks()
    if IS_MAC:
        try:
            window.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            window.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass
        sw = window.winfo_screenwidth()
        sh = window.winfo_screenheight()
        window.geometry(f"{sw}x{sh - 60}+0+28")
    else:
        try:
            window.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            window.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass
        sw = window.winfo_screenwidth()
        sh = window.winfo_screenheight()
        window.geometry(f"{sw}x{sh}+0+0")


# ---------------- Mouse wheel ----------------
def wheel_units(delta):
    if IS_MAC:
        return -int(delta)
    return int(-delta / 120)