from orca_parser import register_method, extract_value_from_line, \
    collect_thermo_sections


def _parse(content):
    for line in content:
        val = extract_value_from_line(line,
                                      "Final Gibbs free energy")
        if val is not None:
            return {"Final Gibbs free energy": val}
    return {}


@register_method(
    key="gibbs_free_energy",
    name="Gibbs Free Energy",
    description="Final Gibbs free energy (a.u.).",
)
def parse_gibbs_free_energy(sections):
    return collect_thermo_sections(sections, "GIBBS FREE ENERGY",
                                   "gibbs_free_energy", _parse)