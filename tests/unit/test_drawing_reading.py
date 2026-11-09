"""DrawingReading (Stage 4): the typed reading of one drawing image, whatever method made it.

Counts are always computed in code from the listed items (never taken from a
method's own count), boxes must have size and lie inside the image, and way
references use the answer key's form (Q1, Q2, ...).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.drawing.reading import DetectedSymbol, DrawingReading, TextBox, WayReading
from backend.app.schemas import Method
from data_generator.schemas import DrawingVersionKind, SymbolClass


def _reading(**extra) -> DrawingReading:
    base = dict(file="drawing/schematic_sheet1_scanned.png", version=DrawingVersionKind.SCANNED, sheet=1,
                method=Method.OCR, width_px=2481, height_px=1754)
    return DrawingReading(**(base | extra))


def test_a_reading_holds_texts_symbols_and_ways() -> None:
    reading = _reading(
        texts=[TextBox(text="MCCB 250A 4P 36kA", bbox=[100, 200, 300, 220], confidence=91.0)],
        symbols=[DetectedSymbol(cls=SymbolClass.MCCB, bbox=[110, 230, 150, 300], score=0.9, way="Q1"),
                 DetectedSymbol(cls=SymbolClass.MCCB, bbox=[210, 230, 250, 300], score=0.8, way="Q2"),
                 DetectedSymbol(cls=SymbolClass.ACB, bbox=[10, 30, 50, 100], score=0.7)],
        ways=[WayReading(way="Q1", rating_a=250, poles=4, breaking_ka=36, device="mccb"),
              WayReading(way="Q2", rating_a=125)])
    assert reading.way_count == 2
    assert reading.symbol_counts() == {SymbolClass.MCCB: 2, SymbolClass.ACB: 1}
    assert DrawingReading.model_validate_json(reading.model_dump_json()) == reading


def test_counts_are_summed_in_code_and_duplicate_ways_count_once() -> None:
    reading = _reading(ways=[WayReading(way="Q1"), WayReading(way="Q1", rating_a=100), WayReading(way="Q3")])
    assert reading.way_count == 2
    with pytest.raises(ValidationError):
        _reading(way_count=7)  # a method cannot supply its own count


@pytest.mark.parametrize("box", [[10, 10, 10, 20], [10, 20, 30, 5], [-1, 0, 10, 10], [0, 0, 3000, 10]])
def test_boxes_must_have_size_and_lie_inside_the_image(box: list[float]) -> None:
    with pytest.raises(ValidationError):
        _reading(texts=[TextBox(text="Q1", bbox=box)])


@pytest.mark.parametrize("way", ["Q0", "q1", "Way 1", "Q100"])
def test_way_references_use_the_answer_key_form(way: str) -> None:
    with pytest.raises(ValidationError):
        WayReading(way=way)


def test_only_drawing_methods_can_make_a_reading() -> None:
    with pytest.raises(ValidationError):
        _reading(method=Method.LLM)
