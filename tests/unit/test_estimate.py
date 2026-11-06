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
