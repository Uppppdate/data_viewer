from orca_parser import register_method, extract_value_from_line, \
    collect_thermo_sections


def _parse(content):
    for line in content:
        val = extract_value_from_line(line, "Total Enthalpy")
        if val is not None:
            return {"Total Enthalpy": val}
    return {}


@register_method(
    key="enthalpy",
    name="Enthalpy",
    description="Total Enthalpy (a.u.).",
)
def parse_enthalpy(sections):
    return collect_thermo_sections(sections, "ENTHALPY",
                                   "enthalpy", _parse)