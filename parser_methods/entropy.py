from orca_parser import register_method, extract_value_from_line, \
    collect_thermo_sections


_KEYS = [
    "Electronic entropy",
    "Vibrational entropy",
    "Rotational entropy",
    "Translational entropy",
    "Final entropy term",
]


def _parse(content):
    result = {}
    for line in content:
        for key in _KEYS:
            val = extract_value_from_line(line, key)
            if val is not None:
                result[key] = val
                break
    return result


@register_method(
    key="entropy",
    name="Entropy",
    description="Electronic / vibrational / rotational / translational "
                "terms and the final entropy term (a.u.).",
)
def parse_entropy(sections):
    return collect_thermo_sections(sections, "ENTROPY",
                                   "entropy", _parse)