"""Catalogue matcher: exact, substitute (needs review) and unmatched; never a guess."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.catalogue import load_catalogue, match
from backend.app.schemas import MatchStatus, Requirement
from data_generator.sets import DATA

ITEMS = load_catalogue(DATA / "catalogue" / "catalogue.csv")
PRICES = {i.code: i.unit_price_gbp for i in ITEMS}


def req(category, **kw):
    return Requirement(key="k", category=category, description="test", quantity=1, **kw)


def test_the_committed_catalogue_loads_with_prices():
    assert len(ITEMS) == 64 and all(i.unit_price_gbp > 0 for i in ITEMS)
    assert PRICES["PRT-0102"] == Decimal("4929.36")  # read from the CSV, two decimals, not a float


@pytest.mark.parametrize("category, kw, code", [
    ("mccb", {"rating_a": 250, "poles": 4, "min_breaking_ka": 36}, "PRT-0212"),
    ("mccb", {"rating_a": 250, "poles": 4, "min_breaking_ka": 50}, "PRT-0215"),
    ("mcb", {"rating_a": 20, "poles": 3, "min_breaking_ka": 10}, "PRT-0302"),
    ("switch_disconnector", {"rating_a": 250, "poles": 4}, "PRT-0402"),
    ("current_transformer", {"rating_a": 1250, "size": "1250/5"}, "PRT-0503"),
    ("meter", {"size": "kWh"}, "PRT-0602"),
    ("enclosure_section", {"ip_rating": "ip54", "width_mm": 600}, "PRT-0806"),
    ("form_kit", {"size": "4a"}, "PRT-0902"),
    ("cable_gland", {"size": "M40"}, "PRT-1004"),
])
def test_exact_matches(category, kw, code):
    result = match(req(category, **kw), ITEMS)
    assert (result.status, result.code) == (MatchStatus.EXACT, code)


def test_breaking_capacity_is_a_minimum_and_the_lowest_enough_wins():
    result = match(req("acb", rating_a=1250, poles=4, min_breaking_ka=36), ITEMS)
    assert (result.status, result.code) == (MatchStatus.EXACT, "PRT-0103")
    assert "50 kA is the lowest breaking capacity of at least 36 kA" in result.reason


def test_a_missing_rating_gives_the_next_higher_rating_as_a_substitute_with_the_reason():
    result = match(req("mccb", rating_a=225, poles=4, min_breaking_ka=36), ITEMS)
    assert (result.status, result.code) == (MatchStatus.SUBSTITUTE, "PRT-0212")
    assert result.reason.startswith("250 A chosen, 225 A requested")


def test_a_higher_breaking_capacity_can_force_a_substitute():
    result = match(req("mccb", rating_a=100, poles=4, min_breaking_ka=50), ITEMS)  # no 100 A at 50 kA
    assert (result.status, result.code) == (MatchStatus.SUBSTITUTE, "PRT-0215")
    assert result.reason.startswith("250 A chosen, 100 A requested")


def test_a_substitute_is_never_a_lower_rating():
    result = match(req("mcb", rating_a=80, poles=3, min_breaking_ka=10), ITEMS)  # MCBs stop at 63 A
    assert result.status == MatchStatus.UNMATCHED and result.code is None


@pytest.mark.parametrize("category, kw", [
    ("mcb", {"rating_a": 20, "poles": 4}),  # no 4-pole MCBs
    ("mccb", {"rating_a": 800, "poles": 4, "min_breaking_ka": 36}),  # MCCBs stop at 630 A
    ("enclosure_section", {"ip_rating": "IP65", "width_mm": 600}),
    ("meter", {"size": "power quality analyser"}),
    ("transformer", {"rating_a": 1000}),
])
def test_no_safe_part_is_unmatched_and_has_no_code(category, kw):
    result = match(req(category, **kw), ITEMS)
    assert result.status == MatchStatus.UNMATCHED and result.code is None and result.reason
