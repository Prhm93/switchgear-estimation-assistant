"""Estimate rules: approved values only, conflicts and missing values block, substitutes need approval."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.catalogue import load_catalogue
from backend.app.estimate import ApprovedValue, build, gland_for, load_rules
from backend.app.paths import REPO_ROOT
from backend.app.schemas import MatchStatus
from data_generator.project import load_answers
from data_generator.sets import DATA

ITEMS = load_catalogue(DATA / "catalogue" / "catalogue.csv")
PRICE = {i.code: i for i in ITEMS}
RULES = load_rules(REPO_ROOT / "config" / "estimate.toml")
KEY = load_answers(DATA / "projects" / "showcase" / "answers.json")


def approved_from_key(skip=lambda v: False) -> list[ApprovedValue]:
    out = []
    for i, v in enumerate(KEY.values):
        if not skip(v):
            out.append(ApprovedValue(value_id=i, field=v.field, value=v.value, unit=v.unit,
                                     source=f"{v.source.document.value} p{v.source.page}"))
    return out


def resolved_showcase() -> list[ApprovedValue]:
    """Every answer-key value approved, with the planted conflict resolved by keeping the specification's 250 A."""
    return approved_from_key(skip=lambda v: v.field == "way.Q2.rating" and v.source.document.value == "schematic")


def test_showcase_estimate_equals_the_answer_key_lines():
    draft = build(resolved_showcase(), ITEMS, RULES)
    assert not draft.problems and not draft.unmatched and not draft.substitutes_to_review
    got = {ln.code: float(ln.quantity) for ln in draft.lines}
    want = {e.code: e.quantity for e in KEY.estimate}
    assert got == want


def test_totals_are_catalogue_prices_times_quantities_plus_labour_and_margin():
    draft = build(resolved_showcase(), ITEMS, RULES)
    materials = sum(PRICE[ln.code].unit_price_gbp * ln.quantity for ln in draft.lines)
    hours = sum(PRICE[ln.code].labour_hours * ln.quantity for ln in draft.lines)
    assert draft.totals.materials == materials.quantize(Decimal("0.01"))
    assert draft.totals.labour == (hours * Decimal("48.00")).quantize(Decimal("0.01"))
    subtotal = draft.totals.materials + draft.totals.labour
    assert draft.totals.margin == (subtotal * Decimal("0.18")).quantize(Decimal("0.01"))
    assert draft.totals.total == subtotal + draft.totals.margin
    assert all(ln.unit_price == PRICE[ln.code].unit_price_gbp for ln in draft.lines)


def test_unapproved_values_never_reach_the_estimate():
    """Nothing approved: no line, no price, everything listed as missing."""
    draft = build([], ITEMS, RULES)
    assert draft.lines == [] and draft.totals.total == 0
    assert {p.field for p in draft.problems} >= {"incomer.rating", "incomer.device", "metering.meter"}


def test_a_conflict_blocks_only_the_lines_that_need_it():
    draft = build(approved_from_key(), ITEMS, RULES)  # both Q2 ratings approved: 250 A and 200 A
    conflict = next(p for p in draft.problems if p.field == "way.Q2.rating")
    assert conflict.kind == "conflict" and conflict.lines == ["way.Q2"]
    assert "250 A (specification p5)" in conflict.message and "200 A (schematic p1)" in conflict.message
    assert "PRT-0212" not in {ln.code for ln in draft.lines}  # the 250 A MCCB line is not built
    assert "PRT-0103" in {ln.code for ln in draft.lines}  # the incomer is unaffected


def test_a_fault_level_without_its_unit_is_not_assumed_to_be_ka():
    values = [v if v.field != "system.fault_level" else v.model_copy(update={"unit": None})
              for v in resolved_showcase()]
    draft = build(values, ITEMS, RULES)
    problem = next(p for p in draft.problems if p.field == "system.fault_level")
    assert "not assumed" in problem.message and "incomer" in problem.lines
    assert "PRT-0103" not in {ln.code for ln in draft.lines}


def test_a_tbc_rating_is_missing_information():
    values = [v if v.field != "way.Q3.rating" else v.model_copy(update={"value": None, "unit": None})
              for v in resolved_showcase()]
    draft = build(values, ITEMS, RULES)
    assert any(p.field == "way.Q3.rating" and p.kind == "missing" for p in draft.problems)


def test_a_substitute_reaches_the_estimate_only_after_approval():
    values = [v if not (v.field == "way.Q2.rating") else v.model_copy(update={"value": 225})
              for v in resolved_showcase()]
    draft = build(values, ITEMS, RULES)
    sub = next(d for d in draft.decisions if d.requirement.key == "way.Q2")
    assert sub.match.status == MatchStatus.SUBSTITUTE and not sub.approved
    assert sub.match.reason.startswith("250 A chosen, 225 A requested")
    assert [d.requirement.key for d in draft.substitutes_to_review] == ["way.Q2"]
    assert "PRT-0212" not in {ln.code for ln in draft.lines}

    approved = build(values, ITEMS, RULES, approved_substitutes={("way.Q2", sub.match.code)})
    line = next(ln for ln in approved.lines if ln.code == "PRT-0212")
    assert line.substitute_reasons == [sub.match.reason]
    assert approved.totals.total > draft.totals.total


def test_unmatched_items_are_listed_and_not_priced():
    values = [v if v.field != "way.Q1.rating" else v.model_copy(update={"value": 80})  # no 80 A MCB
              for v in resolved_showcase()]
    draft = build(values, ITEMS, RULES)
    assert [d.requirement.key for d in draft.unmatched] == ["way.Q1"]
    assert all("way.Q1" not in ln.requirement_keys for ln in draft.lines)


@pytest.mark.parametrize("cable, gland", [("4C 4 mm2 SWA", ("M20", 1)), ("4C 16 mm2 SWA", ("M25", 1)),
                                          ("4C 120 mm2 SWA", ("M40", 1)), ("4C 240 mm2 SWA", ("M50", 1)),
                                          ("2x 4C 185 mm2 SWA", ("M63", 2)), ("fibre optic", None)])
def test_gland_sizing(cable, gland):
    assert gland_for(cable, RULES) == gland


LAYOUT_LINES = {"section.incomer", "section.outgoing", "busbar", "form_kit"}
HELD_LINES = LAYOUT_LINES - {"section.incomer"}  # the incomer section is one section whatever the layout


def _with(values: list[ApprovedValue], field: str, value, unit: str | None, source: str) -> list[ApprovedValue]:
    return values + [ApprovedValue(value_id=900, field=field, value=value, unit=unit, source=source)]


def _layout_built(draft) -> set[str]:
    return {k for ln in draft.lines for k in ln.requirement_keys} & LAYOUT_LINES


def test_a_rating_conflict_that_changes_the_section_count_holds_back_the_stated_sections():
    """630 A takes two units, 400 A one: the drawing's stated sections and width may follow the wrong one."""
    values = [v if v.field != "way.Q2.rating" else v.model_copy(update={"value": 630}) for v in resolved_showcase()]
    draft = build(_with(values, "way.Q2.rating", 400, "A", "schematic sheet 1"), ITEMS, RULES)
    assert _layout_built(draft) == LAYOUT_LINES - HELD_LINES
    held = next(p for p in draft.problems if p.field == "enclosure.sections")
    assert held.kind == "conflict" and "way.Q2.rating" in held.message
    assert set(held.lines) >= {"sections", "busbar", "form_kit"}
    assert "PRT-0103" in {ln.code for ln in draft.lines}  # the incomer is unaffected


def test_a_rating_conflict_that_keeps_the_section_count_does_not_hold_back_the_sections():
    """The showcase's 250 A against 200 A: one unit either way, so the stated layout stands."""
    draft = build(approved_from_key(), ITEMS, RULES)
    assert _layout_built(draft) == LAYOUT_LINES
    assert "enclosure.sections" not in {p.field for p in draft.problems}


def test_a_conflicting_number_of_ways_holds_back_the_stated_sections():
    draft = build(_with(resolved_showcase(), "ways.count", 9, None, "schematic sheet 1"), ITEMS, RULES)
    assert _layout_built(draft) == LAYOUT_LINES - HELD_LINES
    assert "ways.count" in next(p for p in draft.problems if p.field == "enclosure.sections").message


def test_an_open_conflict_between_unapproved_values_still_holds_back_the_stated_layout():
    """Neither Q2 rating is approved yet: the drawing's sections may follow the wrong one, so they wait."""
    values = [v for v in resolved_showcase() if v.field != "way.Q2.rating"]
    disputed = [ApprovedValue(value_id=901, field="way.Q2.rating", value=630, unit="A", source="specification p5"),
                ApprovedValue(value_id=902, field="way.Q2.rating", value=400, unit="A", source="schematic sheet 1")]
    draft = build(values, ITEMS, RULES, open_values=disputed)
    assert _layout_built(draft) == LAYOUT_LINES - HELD_LINES
    q2 = next(p for p in draft.problems if p.field == "way.Q2.rating")
    assert q2.kind == "conflict" and "resolve" in q2.message
    assert not {901, 902} & {i for ln in draft.lines for i in getattr(ln, "value_ids", [])}
    assert all("way.Q2.rating" not in ln.basis for ln in draft.lines)  # open values are never priced


def test_glands_wait_for_the_cable_entry():
    """The gland plate is at the top or the bottom: without the cable entry no gland is priced."""
    draft = build([v for v in resolved_showcase() if v.field != "enclosure.cable_entry"], ITEMS, RULES)
    assert not any(k.startswith("gland.") for ln in draft.lines for k in ln.requirement_keys)
    entry = next(p for p in draft.problems if p.field == "enclosure.cable_entry")
    assert entry.kind == "missing" and all(line.startswith("gland.") for line in entry.lines)
    full = build(resolved_showcase(), ITEMS, RULES)
    assert all("enclosure.cable_entry" in ln.basis for ln in full.lines if ln.code.startswith("PRT-10"))


def test_a_breaking_capacity_conflict_blocks_an_mccb_way():
    """The MCCB must break max(fault level, its own kA): with the kA in dispute the part cannot be chosen."""
    mccb = next(v for v in resolved_showcase() if v.field.endswith(".device") and v.value == "mccb")
    way = mccb.field.rsplit(".", 1)[0]
    draft = build(_with(resolved_showcase(), f"{way}.breaking_capacity", 99, "kA", "schematic sheet 1"), ITEMS, RULES)
    assert all(f"{way}.rating" not in ln.basis for ln in draft.lines)
    problem = next(p for p in draft.problems if p.field == f"{way}.breaking_capacity")
    assert problem.kind == "conflict" and way in problem.lines


def test_an_mccb_way_without_its_own_breaking_capacity_uses_the_fault_level():
    mccb = next(v for v in resolved_showcase() if v.field.endswith(".device") and v.value == "mccb")
    way = mccb.field.rsplit(".", 1)[0]
    draft = build([v for v in resolved_showcase() if v.field != f"{way}.breaking_capacity"], ITEMS, RULES)
    assert any(f"{way}.rating" in ln.basis for ln in draft.lines)
