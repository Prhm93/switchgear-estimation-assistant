"""The quote check: a model value is kept only when its quote is on the page and holds its numbers."""

from __future__ import annotations

from backend.app.llm.quote import check_quote, locate, normalise

PAGE = """4 Electrical requirements
4.1 Rated operational voltage: 400 V
4.2 Prospective fault level: 36 kA for
1 s
Please allow for eleven (11) outgoing ways."""


def test_quote_on_the_page_passes_with_any_spacing_and_case() -> None:
    check = check_quote(36, "prospective   FAULT level: 36 kA for 1 s", PAGE)
    assert check.ok
    assert check.source_text == "Prospective fault level: 36 kA for\n1 s"  # as printed, across the line break


def test_quote_not_on_the_page_fails() -> None:
    check = check_quote(400, "Rated voltage 400 V", PAGE)
    assert not check.ok and check.reason == "quote not found on the page"


def test_number_of_the_value_must_be_in_the_quote() -> None:
    check = check_quote(415, "Rated operational voltage: 400 V", PAGE)
    assert not check.ok and "415" in check.reason


def test_number_words_count_as_numbers() -> None:
    assert check_quote(11, "allow for eleven", PAGE).ok
    assert not check_quote(12, "allow for eleven", PAGE).ok


def test_text_values_need_only_the_quote() -> None:
    assert check_quote("TN-S", "4 Electrical requirements", PAGE).ok  # no number to check


def test_empty_quote_fails() -> None:
    assert not check_quote(400, "", PAGE).ok


def test_helpers() -> None:
    assert normalise("  A\n  b\tC ") == "a b c"
    assert locate("RATED operational", PAGE) == "Rated operational"
    assert locate("not there", PAGE) is None
