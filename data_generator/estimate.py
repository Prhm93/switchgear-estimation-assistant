"""The correct draft estimate for a design: catalogue codes and quantities.

Built from the intended design, using only parts that exist in the catalogue
(:func:`catalogue.match_part` raises rather than guesses). Prices are not
part of the answer key; they come from the catalogue.

A line is *blocked* by a planted problem when one of the fields the problem
affects is in the line's ``basis``. A problem affects its own field and every
derived field that changes with it in the documents it alters: for example a
way's rating changed on the drawing can change the number of sections and
the board width the drawing states (:func:`affected_fields`). A correct system
must not finalise a blocked line until the engineer resolves the problem.
"""

from __future__ import annotations

from collections import OrderedDict

from data_generator import catalogue as cat
from data_generator.design import BoardDesign, Device
from data_generator.schemas import EstimateLine, PlantedProblem


# Fields a document states from values derived from the ways, not given directly.
DERIVED_FIELDS = {
    "enclosure.sections": lambda d: d.sections,
    "enclosure.width": lambda d: d.width_mm,
}


def affected_fields(design: BoardDesign, problem_field: str | None, altered: list[BoardDesign]) -> set[str]:
    """The problem's field plus every derived field that differs from the design in an altered document."""
    fields = {problem_field} if problem_field else set()
    for view in altered:
        fields |= {f for f, get in DERIVED_FIELDS.items() if get(view) != get(design)}
    return fields


def estimate_lines(design: BoardDesign, parts: list[cat.Part], problems: list[PlantedProblem],
                   affected: dict[str, set[str]] | None = None) -> list[EstimateLine]:
    """``affected`` maps a problem id to the fields it affects; by default just the problem's field."""
    d = design
    groups: OrderedDict[str, dict] = OrderedDict()

    def add(part: cat.Part, qty: float, basis: list[str]) -> None:
        g = groups.setdefault(part.code, {"part": part, "qty": 0.0, "basis": []})
        g["qty"] += qty
        for b in basis:
            if b not in g["basis"]:
                g["basis"].append(b)

    add(cat.match_part(parts, cat.Category.ACB, rating_a=d.incomer_rating_a, poles=d.incomer_poles,
                       min_breaking_ka=d.fault_level_ka),
        1, ["incomer.rating", "incomer.poles", "system.fault_level"])
    add(cat.match_part(parts, cat.Category.CT, rating_a=d.incomer_rating_a), 3,
        ["incomer.rating", "metering.ct_ratio"])
    add(cat.match_part(parts, cat.Category.METER, size=d.meter), 1, ["metering.meter"])
    for w in d.ways:
        basis = [f"way.{w.id}.device", f"way.{w.id}.rating", f"way.{w.id}.poles", "ways.count"]
        if w.device == Device.MCCB:
            part = cat.match_part(parts, cat.Category.MCCB, rating_a=w.rating_a, poles=w.poles,
                                  min_breaking_ka=max(d.fault_level_ka, w.breaking_ka or 0))
            basis += [f"way.{w.id}.breaking_capacity", "system.fault_level"]
        elif w.device == Device.MCB:
            part = cat.match_part(parts, cat.Category.MCB, rating_a=w.rating_a, poles=w.poles)
            basis += [f"way.{w.id}.breaking_capacity", "system.fault_level"]
        else:
            part = cat.match_part(parts, cat.Category.SWITCH_DISCONNECTOR, rating_a=w.rating_a, poles=w.poles)
        add(part, 1, basis)
    sections_basis = ["enclosure.sections", "ways.count"]
    add(cat.match_part(parts, cat.Category.BUSBAR, rating_a=d.busbar_rating_a), d.width_mm / 1000,
        ["busbar.rating", *sections_basis])
    add(cat.match_part(parts, cat.Category.SECTION, ip_rating=d.ip_rating, width_mm=cat.INCOMER_SECTION_WIDTH_MM),
        1, ["enclosure.ip_rating"])
    add(cat.match_part(parts, cat.Category.SECTION, ip_rating=d.ip_rating, width_mm=cat.OUTGOING_SECTION_WIDTH_MM),
        d.outgoing_sections, ["enclosure.ip_rating", *sections_basis])
    if d.form in cat.FORMS_WITH_KIT:
        add(cat.match_part(parts, cat.Category.FORM_KIT, size=d.form), d.sections,
            ["enclosure.form", *sections_basis])
    for w in d.ways:
        add(cat.match_part(parts, cat.Category.GLAND, size=w.gland), w.glands,
            [f"way.{w.id}.cable", "enclosure.cable_entry", "ways.count"])

    lines = []
    for code, g in groups.items():
        blocked = [p.id for p in problems
                   if (affected or {}).get(p.id, {p.field} if p.field else set()) & set(g["basis"])]
        lines.append(EstimateLine(code=code, description=g["part"].description, quantity=round(g["qty"], 3),
                                  unit=g["part"].unit, basis=g["basis"], blocked_by=blocked))
    return lines
