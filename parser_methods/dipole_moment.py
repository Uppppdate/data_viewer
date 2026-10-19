"""Dipole moment parser — robust against ORCA format variations."""
import re
from orca_parser import register_method


_FLOAT_RE = re.compile(r'[-\d]+\.[-\d]+(?:[eE][-+]?\d+)?')


def _last_float(line):
    """Return the last float-like token on a line, or None."""
    nums = _FLOAT_RE.findall(line)
    if not nums:
        return None
    try:
        return float(nums[-1])
    except ValueError:
        return None


def _scan_block(content, out):
    """Extract dipole data from one DIPOLE section."""
    for line in content:
        low = line.lower()
        if "magnitude" in low:
            val = _last_float(line)
            if val is None:
                continue
            if "debye" in low:
                out.setdefault("magnitude_debye", val)
            elif "a.u." in low or "(au)" in low or "(a.u)" in low:
                out.setdefault("magnitude_au", val)
            else:
                # unknown unit — keep as generic
                out.setdefault("magnitude", val)
        elif "total dipole moment" in low:
            nums = _FLOAT_RE.findall(line)
            if len(nums) >= 3:
                try:
                    out.setdefault("total_x_au", float(nums[-3]))
                    out.setdefault("total_y_au", float(nums[-2]))
                    out.setdefault("total_z_au", float(nums[-1]))
                except ValueError:
                    pass


def _scan_raw_lines(raw_lines, out):
    """Fallback — scan the whole file, not just the extracted section.

    Handles the case where extract_sections() did not pick up the block
    for some reason (unusual separators, extra spaces, etc.).
    """
    in_dipole = False
    for line in raw_lines:
        stripped = line.strip()
        up = stripped.upper()
        # Enter the block on a line that is exactly a DIPOLE MOMENT header
        if up in ("DIPOLE MOMENT", "DIPOLE MOMENT (DEBYE)",
                  "DIPOLE MOMENT (A.U.)", "DIPOLE MOMENT (AU)"):
            in_dipole = True
            continue
        if not in_dipole:
            continue
        # Stop when we hit the next section-looking header
        if stripped.startswith("---") and "DIPOLE" not in up:
            # leave the section only after we have consumed the closing dashes
            continue
        low = stripped.lower()
        if "magnitude" in low:
            val = _last_float(stripped)
            if val is None:
                continue
            if "debye" in low:
                out.setdefault("magnitude_debye", val)
            elif "a.u." in low or "(au)" in low or "(a.u)" in low:
                out.setdefault("magnitude_au", val)
        elif "total dipole moment" in low:
            nums = _FLOAT_RE.findall(stripped)
            if len(nums) >= 3:
                try:
                    out.setdefault("total_x_au", float(nums[-3]))
                    out.setdefault("total_y_au", float(nums[-2]))
                    out.setdefault("total_z_au", float(nums[-1]))
                except ValueError:
                    pass
        # Stop scanning once we have both magnitudes
        if "magnitude_debye" in out and "magnitude_au" in out:
            break


@register_method(
    key="dipole_moment",
    name="Dipole Moment",
    description="Total dipole moment magnitude in a.u. and Debye, plus "
                "the X/Y/Z components if the format provides them.",
)
def parse_dipole_moment(ctx):
    result = {}

    # 1) Try extracted sections with a case-insensitive DIPOLE match
    for title, content in ctx:
        if "DIPOLE" in title.upper():
            _scan_block(content, result)
            if result:
                break

    # 2) Fallback — scan the raw file if the sections did not yield data
    if not result:
        _scan_raw_lines(ctx.raw_lines, result)

    if not result:
        # Debug aid: log that the method ran but found nothing
        # (harmless; remove if it gets noisy).
        # print("[dipole] no dipole moment found in this file")
        return {}

    return {"dipole_moment": result}