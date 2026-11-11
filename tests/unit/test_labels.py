"""Plain words on normal screens: field names, sources, reading methods and enquiry titles."""

from __future__ import annotations

from datetime import date

from backend.app.labels import (
    display,
    field_label,
    method_words,
    model_run_words,
    reading_line,
    short_date,
    source_words,
    title_from_specification,
)


def test_known_fields_read_as_words() -> None:
    assert field_label("system.voltage") == "System voltage"
    assert field_label("enclosure.form") == "Form of separation"
    assert field_label("way.Q2.rating") == "Way Q2 rating"
    assert field_label("way.Q10.poles") == "Way Q10 poles"


def test_an_unknown_field_still_has_no_dots_or_underscores() -> None:
    label = field_label("busbar.short_time_rating")
    assert "." not in label and "_" not in label
    assert label == "Busbar short time rating"


def test_values_and_devices() -> None:
    assert display("mccb") == "MCCB"
    assert display(None) == "Not given"
    assert display(400, "A") == "400 A"


def test_sources() -> None:
    assert source_words("specification", 5) == "Specification, page 5"
    assert source_words("schematic", 1) == "Drawing, sheet 1"
    assert source_words("requirements", 1) == "Customer letter"


def test_methods_say_how_a_value_was_read() -> None:
    assert method_words("ocr") == "Read from the drawing picture (OCR)"
    assert "pieced together" in method_words("llm", quote_match="words_on_page")
    assert method_words("rules", agreement="agree") == "Read by the rules; the model read the same"


def test_the_reading_line_is_honest() -> None:
    assert short_date(date(2026, 11, 7)) == "7 Nov 2026"
    assert model_run_words("gemma4:e2b, 2026-11-07") == "gemma4:e2b (recorded 7 Nov 2026)"
    assert reading_line({"rules"}, []) == "Read with rules"
    assert reading_line({"rules+model", "ocr"}, ["gemma4:e2b, 2026-11-07"]) == \
        "Read with rules + OCR + gemma4:e2b (recorded 7 Nov 2026)"
    assert reading_line(set(), []) == "Nothing read yet"


def test_a_title_comes_from_the_specification_or_not_at_all() -> None:
    text = ("Technical specification for\nLow-voltage main switchboard MSB-2\n"
            "Enquiry reference: ENQ-3192\nDate: 1 Nov 2026\n")
    assert title_from_specification(text) == ("Low-voltage main switchboard MSB-2", "ENQ-3192")
    assert title_from_specification("Clause 1: General\nThe board shall ...") == (None, None)
