"""ORCA .log parser core.

The parser exposes a small registry of "methods". Each method is a
function that receives the list of sections extracted from a log file
and returns a dict fragment that is deep-merged into the final data.

Built-in and user methods live in the `parser_methods/` folder next to
this file. They are imported automatically at startup — see the
`load_plugins` function at the bottom of this module and the README in
that folder for instructions.
"""
import os
import re
import sys
import json
import importlib
import pkgutil

# Ordered list of encodings to try when reading source files.
# `latin-1` is the last entry on purpose: it can decode any byte
# sequence and therefore never raises.
DEFAULT_ENCODINGS = [
    "utf-8",
    "utf-8-sig",
    "utf-16",
    "cp1251",
    "cp1252",
    "latin-1"
]


def read_text(filepath, encodings=None):
    """Read a text file, falling back through several encodings.

    Returns (text, encoding_used). Tries the list in order and uses the
    first encoding that decodes the file without errors.
    """
    if encodings is None:
        encodings = DEFAULT_ENCODINGS

    last_error = None
    for enc in encodings:
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, LookupError) as e:
            last_error = e
            continue

    # Absolute last resort — never raises.
    with open(filepath, "r", encoding="utf-8",
              errors="replace") as f:
        return f.read(), "utf-8 (errors=replace)"


def read_lines(filepath, encodings=None):
    """Same as read_text but returns a list of lines (keepends=True)."""
    text, enc = read_text(filepath, encodings=encodings)
    return text.splitlines(keepends=True), enc

# ===========================================================================
# Section splitting
# ===========================================================================
def extract_sections(lines):
    """Split raw ORCA log lines into (title, content_lines) sections.

    A header is three lines: dashed, title, dashed (dashes same length).
    """
    sections = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if re.match(r'^-+$', line) and len(line) >= 3:
            if i + 2 < len(lines):
                next_next_line = lines[i + 2].strip()
                if (re.match(r'^-+$', next_next_line)
                        and len(next_next_line) == len(line)):
                    title = lines[i + 1].strip()
                    content = []
                    j = i + 3
                    while j < len(lines):
                        if j + 2 < len(lines):
                            l1 = lines[j].strip()
                            l3 = lines[j + 2].strip()
                            if (re.match(r'^-+$', l1) and len(l1) >= 3 and
                                    re.match(r'^-+$', l3) and
                                    len(l3) == len(l1)):
                                break
                        content.append(lines[j])
                        j += 1
                    sections.append((title, content))
                    i = j
                    continue
        i += 1
    return sections


# ===========================================================================
# Reusable low-level helpers (plugins can import these)
# ===========================================================================
def extract_value_from_line(line, key, unit="Eh"):
    """Return the float that immediately precedes `unit` on a line
    containing `key`, or None."""
    if key in line:
        m = re.search(r'([-\d.]+)\s+' + re.escape(unit), line)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


def collect_thermo_sections(sections, section_title, category_key, parser):
    """Pull every `section_title` block, keyed by the enclosing T (K).

    `parser` is a callable taking the content lines of one block and
    returning a dict. The result looks like::

        {"thermochemistry": {"298.15": {category_key: {...}}}}
    """
    result = {}
    current_temp = None
    for title, content in sections:
        if title.startswith("THERMOCHEMISTRY AT"):
            m = re.search(r'THERMOCHEMISTRY AT ([\d.]+)K', title)
            if m:
                current_temp = m.group(1)
        elif title == section_title and current_temp:
            result.setdefault(current_temp, {})[category_key] = parser(content)
    if not result:
        return {}
    return {"thermochemistry": result}


# ===========================================================================
# Method registry
# ===========================================================================
# Each entry is: {"key": str, "name": str, "description": str, "func": callable}
PARSER_METHODS = []
METHODS_BY_KEY = {}


def register_method(key, name, description):
    """Decorator: register a parser method.

    Plugin modules call this to make their function appear in the UI.
    """
    def wrap(func):
        info = {
            "key": key,
            "name": name,
            "description": description,
            "func": func,
        }
        if key in METHODS_BY_KEY:
            # Overwrite (allows a user plugin to override a built-in).
            old = METHODS_BY_KEY[key]
            try:
                PARSER_METHODS.remove(old)
            except ValueError:
                pass
        PARSER_METHODS.append(info)
        METHODS_BY_KEY[key] = info
        return func
    return wrap


def default_method_keys():
    """Return every registered key (used to pre-tick the checkboxes)."""
    return [m["key"] for m in PARSER_METHODS]


# ===========================================================================
# Whole-file parsing
# ===========================================================================
def _deep_merge(target, source):
    for k, v in source.items():
        if (k in target and isinstance(target[k], dict)
                and isinstance(v, dict)):
            _deep_merge(target[k], v)
        else:
            target[k] = v

# ===========================================================================
# Log context passed to parser methods
# ===========================================================================
class LogContext(list):
    """Passed to parser methods.

    Behaves like the old list of sections — `for title, content in ctx:`
    keeps working — but also exposes `.lines`, the raw file content, for
    plugins that need to search the whole file.
    """

    def __init__(self, sections, raw_lines):
        super().__init__(sections)
        self.raw_lines = raw_lines


def parse_one_log(filepath, method_keys=None):
    """Parse a single ORCA-style text file using the given method keys."""
    if method_keys is None:
        method_keys = default_method_keys()

    lines, used_encoding = read_lines(filepath)
    if used_encoding != "utf-8":
        print(f"[orca_parser] {os.path.basename(filepath)}: "
              f"decoded as {used_encoding}")

    sections = extract_sections(lines)
    ctx = LogContext(sections, lines)

    data = {
        "vibrational_frequencies": [],
        "has_negative_frequencies": False,
        "thermochemistry": {},
    }

    for key in method_keys:
        m = METHODS_BY_KEY.get(key)
        if not m:
            continue
        try:
            fragment = m["func"](ctx)
        except Exception as e:
            print(f"[orca_parser] Method '{key}' failed on "
                  f"{os.path.basename(filepath)}: {e}")
            fragment = None
        if fragment:
            _deep_merge(data, fragment)

    return data

# ===========================================================================
# Batch parsing
# ===========================================================================
def find_files(directory, extensions=None):
    """Recursively find files with any of the given extensions.

    `extensions` is a list of strings, each beginning with a dot,
    e.g. ['.log', '.out']. Matching is case-insensitive. If the list
    is empty or None, the default is ['.log'].
    """
    if not extensions:
        extensions = [".log"]
    exts = {e.lower() for e in extensions}

    result = []
    for root, _dirs, files in os.walk(directory):
        for f in files:
            lf = f.lower()
            if any(lf.endswith(e) for e in exts):
                result.append(os.path.join(root, f))
    result.sort()
    return result


def find_log_files(directory):
    """Backward-compatible alias for find_files(directory, ['.log'])."""
    return find_files(directory, [".log"])


def parse_many(log_files, base_directory, output_path,
               method_keys=None, progress_cb=None):
    """Parse a list of .log files and write a combined JSON.

    Returns (count, errors).
    """
    result = {}
    errors = []
    total = len(log_files)

    for idx, filepath in enumerate(log_files, 1):
        try:
            data = parse_one_log(filepath, method_keys=method_keys)
            rel_path = os.path.relpath(filepath, base_directory)
            result[rel_path] = data
        except Exception as e:
            errors.append(f"{filepath}: {e}")
        if progress_cb:
            progress_cb(idx, total, filepath)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return len(result), errors


# ===========================================================================
# Plugin loading
# ===========================================================================
def load_plugins():
    """Import every module in `parser_methods/` so it can register."""
    here = os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(here, "parser_methods")
    if not os.path.isdir(folder):
        return

    # Make the script directory importable so plugins can do
    # `from orca_parser import register_method`.
    if here not in sys.path:
        sys.path.insert(0, here)

    try:
        import parser_methods  # noqa: F401
    except Exception as e:
        print(f"[orca_parser] Cannot import parser_methods package: {e}")
        return

    for _finder, name, _ispkg in pkgutil.iter_modules(
            parser_methods.__path__):
        if name.startswith("_"):
            continue
        try:
            importlib.import_module(f"parser_methods.{name}")
        except Exception as e:
            print(f"[orca_parser] Failed to load plugin "
                  f"parser_methods.{name}: {e}")


# Run at import time — must be the last statement in this module so all
# names referenced by plugins (register_method, extract_value_from_line,
# collect_thermo_sections, …) are already defined.
load_plugins()