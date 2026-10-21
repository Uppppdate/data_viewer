"""Single Point Energy from ORCA output.

Format recognised:

    -------------------------   --------------------
    FINAL SINGLE POINT ENERGY       -78.122618850681
    -------------------------   --------------------
"""
import re
from orca_parser import register_method


_PATTERN = re.compile(
    r'FINAL\s+SINGLE\s+POINT\s+ENERGY\s+([-+]?\d+\.\d+)',
    re.IGNORECASE,
)


def _scan(lines):
    for line in lines:
        m = _PATTERN.search(line)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


@register_method(
    key="single_point_energy",
    name="Single Point Energy",
    description="Final single point energy (Eh) from the "
                "'FINAL SINGLE POINT ENERGY' line.",
)
def parse_single_point_energy(ctx):
    # Scan parsed sections first (faster)
    for _title, content in ctx:
        value = _scan(content)
        if value is not None:
            return {"single_point_energy": {
                "final_single_point_energy_eh": value,
            }}

    # Fallback: scan raw lines
    raw = getattr(ctx, "raw_lines", None) or []
    value = _scan(raw)
    if value is not None:
        return {"single_point_energy": {
            "final_single_point_energy_eh": value,
        }}
    return {}