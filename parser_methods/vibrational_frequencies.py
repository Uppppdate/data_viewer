import re
from orca_parser import register_method


def _parse_frequencies(content):
    freqs = []
    has_negative = False
    pattern = r'\s*(\d+):\s+([-\d.]+)\s+cm\*\*-1'
    for line in content:
        m = re.match(pattern, line)
        if m:
            idx = int(m.group(1))
            freq = float(m.group(2))
            freqs.append({"index": idx, "frequency": freq})
            if freq < 0:
                has_negative = True
    return freqs, has_negative


@register_method(
    key="vibrational_frequencies",
    name="Vibrational Frequencies",
    description="Mode index and frequency (cm⁻¹) from the "
                "VIBRATIONAL FREQUENCIES section, plus a flag for "
                "negative modes.",
)
def parse_vibrational_frequencies(sections):
    for title, content in sections:
        if title == "VIBRATIONAL FREQUENCIES":
            freqs, has_neg = _parse_frequencies(content)
            return {
                "vibrational_frequencies": freqs,
                "has_negative_frequencies": has_neg,
            }
    return {}