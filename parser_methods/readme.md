# Parser methods

Every `.py` file in this folder is loaded automatically by
`orca_parser.load_plugins()` when the application starts. A method
appears in the **Select data to parse** dialog as soon as its file is
present, and can be selected with a checkbox before parsing.

## Adding a new method

1. Create a new file in this folder, for example `dipole_moment.py`.
2. The file must be UTF-8, plain Python 3, and must not start with `_`
   (files starting with `_` are treated as private helpers and are not
   loaded).
3. Use the `@register_method` decorator from `orca_parser`. The
   decorated function receives a list of sections from the log file and
   returns a dictionary fragment.

Minimal template:

The decorated function receives a **`LogContext`** object, which is a
subclass of `list` (so `for title, content in ctx:` keeps working). It
adds one extra attribute:

- `ctx.lines` — the full raw file content as a list of strings. Use
  this when you need to search the whole file and not just the parsed
  sections (which can miss unusual headers).

```python
from orca_parser import register_method


@register_method(
    key="my_key",                     # unique id (used internally)
    name="My Method",                 # label shown in the checkbox list
    description="Short explanation.", # grey text under the checkbox
)
def parse_my_method(sections):
    # `sections` is a list of tuples: (title, list_of_content_lines)
    result = {}
    for title, content in sections:
        if title == "THE SECTION I WANT":
            for line in content:
                ...
    return {"my_key": result}         # or {} if nothing was found
```

```python
from orca_parser import register_method
import re


@register_method(key="foo", name="Foo", description="Bar.")
def parse_foo(ctx):
    result = {}
    # Search sections first
    for title, content in ctx:
        if "MY SECTION" in title.upper():
            for line in content:
                m = re.search(r'([-\d.]+)', line)
                if m:
                    result["value"] = float(m.group(1))
    # Fallback: search raw lines
    if not result:
        for line in ctx.lines:
            if "My Section" in line:
                ...
    return {"foo": result} if result else {}
```

The returned dict is deep-merged into the per-file output, so you can
also return nested structures, e.g. `{"thermochemistry": {"298.15":
{"my_key": {...}}}}` — the existing `thermochemistry` dict will be
extended, not replaced.

## Available helpers

Import these from `orca_parser`:

- `extract_sections(lines)` — split raw lines into sections.
- `extract_value_from_line(line, key, unit="Eh")` — get the float
  before `unit` on a line containing `key`.
- `collect_thermo_sections(sections, section_title, category_key,
  parser)` — collect all blocks with `section_title`, keyed by the
  enclosing `THERMOCHEMISTRY AT xxxK` header.

## Overriding built-in methods

If your plugin registers a `key` that already exists, the new one
replaces the old one. This is useful for patching a built-in method
without editing it.

## Errors and debugging

If a plugin fails to import, the error is printed to the terminal but
the app keeps running. If a method raises during parsing, the exception
is caught and printed per-file — the rest of the file is still parsed.