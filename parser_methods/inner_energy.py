from orca_parser import register_method, extract_value_from_line, \
    collect_thermo_sections


_KEYS = [
    "Electronic energy",
    "Zero point energy",
    "Thermal vibrational correction",
    "Thermal rotational correction",
    "Thermal translational correction",
    "Total thermal energy",
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
    key="inner_energy",
    name="Inner Energy",
    description="Electronic, zero-point and thermal corrections, plus "
                "total thermal energy (a.u.).",
)
def parse_inner_energy(sections):
    return collect_thermo_sections(sections, "INNER ENERGY",
                                   "inner_energy", _parse)