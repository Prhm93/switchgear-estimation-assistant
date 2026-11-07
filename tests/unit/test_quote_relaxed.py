"""The relaxed quote check (Stage 3c): quotes stitched from words that are all on the page.

The strict check (``check_quote``) is the fixed v2 baseline and is not changed.
The relaxed check accepts a quote that is not one continuous span only when
every word of it is on the page, it is not a placeholder, and the value's
numbers are in it. Such a value is marked ``words_on_page`` and is never
trusted more than "medium". Two extra rules apply to these rescued values only:

- a rating must not come from a number written only as kA or mm2, and must be
  a number at all (never "TBC");
- poles supported only by a cable core count ("4C") are kept with confidence
  low and a flag, for the engineer to check.
"""

from __future__ import annotations

import json

import pytest

from backend.app.llm.extract import llm_extract
from backend.app.llm.quote import QuoteCheckMode, check_quote, check_quote_relaxed
from backend.app.reading import PageText
from backend.app.schemas import Confidence, DocumentKind, QuoteMatch, ValueFlag
from tests.fakes import ScriptedProvider

DRAWING = """CABLE SCHEDULE
WAY DESCRIPTION DEVICE CABLE LEN (m)
Q1 SMALL POWER DB-L1 MCCB 2x 4C 185 mm2 SWA 50
MCCB 630A 4P 50kA
SW-DISC 400A 4P
Q2 AHU 1
MCCB 250 A 4 pole 36kA
TBC"""

TABLE_PAGE = """Outgoing ways
Way | Description | Device | Rating (A) | Poles | Breaking (kA) | Cable
Q8 | Mech services panel | MCCB | 200 | 4 | 36 | 4C 95 mm2 SWA"""


# --- the relaxed check itself ------------------------------------------------------------------------------

def test_stitched_quote_with_every_word_on_the_page_is_kept_as_words_on_page() -> None:
    check = check_quote_relaxed("way.Q1.cable", "2x 4C 185 mm2 SWA", "Q1 2x 4C 185 mm2 SWA", DRAWING)
    assert check.ok and check.match == QuoteMatch.WORDS_ON_PAGE
    assert check.source_text == "Q1 2x 4C 185 mm2 SWA"
    assert not check_quote("2x 4C 185 mm2 SWA", "Q1 2x 4C 185 mm2 SWA", DRAWING).ok  # strict: not one span


def test_quote_with_a_word_that_is_not_on_the_page_is_rejected() -> None:
    check = check_quote_relaxed("way.Q1.cable", "2x 4C 240 mm2 SWA", "Q1 2x 4C 240 mm2 SWA", DRAWING)
    assert not check.ok and check.reason == "quote not found on the page"


def test_exact_quote_is_marked_exact_and_behaves_as_the_strict_check() -> None:
    check = check_quote_relaxed("way.Q1.cable", "2x 4C 185 mm2 SWA", "2x 4C 185 mm2 SWA", DRAWING)
    strict = check_quote("2x 4C 185 mm2 SWA", "2x 4C 185 mm2 SWA", DRAWING)
    assert check.ok and strict.ok and check.match == strict.match == QuoteMatch.EXACT
    assert check.source_text == strict.source_text


@pytest.mark.parametrize("quote", ["Q 1", "4 C", "[MCCB SWA]", "N/A", "[No value found]"])
def test_short_bracketed_and_placeholder_quotes_stay_rejected(quote: str) -> None:
    """"Q 1" and "4 C" have every word on the page, but are too short to show where a value comes from."""
    check = check_quote_relaxed("way.Q1.description", "Spare", quote, DRAWING + "\n[MCCB x SWA]")
    assert not check.ok and check.reason == "quote not found on the page"


def test_the_number_check_still_applies_to_stitched_quotes() -> None:
    check = check_quote_relaxed("way.Q2.rating", 630, "Q2 MCCB 36kA", DRAWING)
    assert not check.ok and "630" in check.reason


# --- rating guard (reject-only), rescued values only --------------------------------------------------------

@pytest.mark.parametrize("value, quote", [(50, "MCCB 630A 50kA"), (185, "Q1 MCCB 185 mm2 SWA"),
                                          ("TBC", "Q2 AHU 1 TBC")])
def test_rating_guard_rejects_kiloamps_cable_sizes_and_placeholders(value, quote: str) -> None:
    check = check_quote_relaxed("way.Q1.rating", value, quote, DRAWING)
    assert not check.ok and check.reason.startswith("rating guard:")


def test_rating_guard_accepts_a_rating_in_amps() -> None:
    check = check_quote_relaxed("way.Q2.rating", 250, "Q2 MCCB 250 A", DRAWING)
    assert check.ok and check.match == QuoteMatch.WORDS_ON_PAGE


def test_rating_guard_accepts_a_bare_number_from_a_specification_table_row() -> None:
    quote = "Q8 Mech services panel MCCB 200 4 36 4C 95 mm2 SWA"  # cells re-joined without " | "
    check = check_quote_relaxed("way.Q8.rating", "200", quote, TABLE_PAGE)
    assert check.ok and check.match == QuoteMatch.WORDS_ON_PAGE


def test_rating_guard_does_not_touch_exact_quotes() -> None:
    """An exact quote is judged by the strict check alone, so the relaxed path changes nothing for it."""
    exact = check_quote_relaxed("way.Q1.rating", 185, "4C 185 mm2", DRAWING)
    assert exact.ok == check_quote(185, "4C 185 mm2", DRAWING).ok is True


# --- poles from cable cores: kept, flagged -----------------------------------------------------------------

def test_poles_supported_only_by_a_core_count_are_kept_with_a_flag() -> None:
    check = check_quote_relaxed("way.Q1.poles", 4, "Q1 MCCB 2x 4C 185 mm2 SWA", DRAWING)
    assert check.ok and ValueFlag.POLES_FROM_CABLE_CORES in check.flags


@pytest.mark.parametrize("quote", ["Q2 MCCB 250 A 4 pole", "SW-DISC 4P 400A"])
def test_poles_written_as_poles_get_no_flag(quote: str) -> None:
    check = check_quote_relaxed("way.Q2.poles", 4, quote, DRAWING)
    assert check.ok and check.flags == []


# --- through llm_extract -----------------------------------------------------------------------------------

def _extract(items: list[dict], mode: QuoteCheckMode):
    page = PageText(number=1, lines=DRAWING.splitlines())
    provider = ScriptedProvider({1: items})
    return llm_extract(DocumentKind.SCHEMATIC, [page], "drawing/schematic.dxf", provider, quote_check=mode)


ITEMS = [{"field": "way.Q1.cable", "value": "2x 4C 185 mm2 SWA", "unit": None, "quote": "Q1 2x 4C 185 mm2 SWA"},
         {"field": "way.Q1.poles", "value": 4, "unit": None, "quote": "Q1 MCCB 2x 4C 185 mm2 SWA"},
         {"field": "way.Q2.rating", "value": 250, "unit": "A", "quote": "Q2 MCCB 250 A"},
         {"field": "way.Q1.rating", "value": 185, "unit": "A", "quote": "Q1 MCCB 185 mm2"},
         {"field": "way.Q1.description", "value": "Small power", "unit": None, "quote": "SMALL POWER DB-L1"}]


def test_relaxed_extraction_marks_rescued_values_and_never_trusts_them_more_than_medium() -> None:
    result = _extract(ITEMS, QuoteCheckMode.RELAXED)
    by_field = {v.field: v for v in result.values}
    assert set(by_field) == {"way.Q1.cable", "way.Q1.poles", "way.Q2.rating", "way.Q1.description"}
    assert by_field["way.Q1.description"].quote_match == QuoteMatch.EXACT
    for f in ("way.Q1.cable", "way.Q2.rating"):
        assert by_field[f].quote_match == QuoteMatch.WORDS_ON_PAGE
        assert by_field[f].confidence == Confidence.MEDIUM
    poles = by_field["way.Q1.poles"]
    assert poles.confidence == Confidence.LOW and poles.flags == [ValueFlag.POLES_FROM_CABLE_CORES]
    assert [r.reason for r in result.rejected if r.field == "way.Q1.rating"][0].startswith("rating guard:")


def test_strict_extraction_keeps_only_exact_quotes_and_is_the_default() -> None:
    strict = _extract(ITEMS, QuoteCheckMode.STRICT)
    assert [v.field for v in strict.values] == ["way.Q1.description"]
    page = PageText(number=1, lines=DRAWING.splitlines())
    default = llm_extract(DocumentKind.SCHEMATIC, [page], "drawing/schematic.dxf", ScriptedProvider({1: ITEMS}))
    assert default.values == strict.values and default.rejected == strict.rejected
    assert {r.reason for r in strict.rejected} == {"quote not found on the page"}


def test_relaxed_values_survive_a_json_round_trip() -> None:
    value = _extract(ITEMS, QuoteCheckMode.RELAXED).values[0]
    again = type(value).model_validate(json.loads(value.model_dump_json()))
    assert again == value
