"""OCR lines to drawing values (backend.app.drawing.link), on hand-made OCR output: no Tesseract needed.

The sheet below is a small invented drawing in answer-key pixels: three way
labels in a row, vertical rating and description texts under them, sheet
notes, and a cable schedule.
"""

from __future__ import annotations

import pytest

from backend.app.drawing.link import digits, link_sheet, skew
from backend.app.drawing.ocr import OcrLine, OcrWord, SheetOcr, unturn
from backend.app.schemas import Confidence, DocumentKind, Method
from data_generator.schemas import DrawingVersionKind


def word(text: str, x0: float, y0: float, x1: float, y1: float, conf: float = 95.0) -> OcrWord:
    return OcrWord(text=text, bbox=[x0, y0, x1, y1], conf=conf)


def row(texts: list[str], x: float, y: float, conf: float = 95.0, step: float = 60.0) -> OcrLine:
    """An upright line: words left to right, 15 px tall."""
    return OcrLine(words=[word(t, x + i * step, y, x + i * step + 50, y + 15, conf) for i, t in enumerate(texts)])


def vertical(texts: list[str], x: float, conf: float = 95.0, top: float = 670.0) -> OcrLine:
    """A rotated line, 20 px wide, read from the bottom upwards; way texts start level at the top."""
    n = len(texts)
    return OcrLine(rotated=True, words=[word(t, x, top + (n - 1 - i) * 40, x + 20, top + (n - i) * 40, conf)
                                        for i, t in enumerate(texts)])


def sheet(lines: list[OcrLine], version: DrawingVersionKind = DrawingVersionKind.CLEAN) -> SheetOcr:
    return SheetOcr(sheet=1, version=version, width_px=2481, height_px=1754, lines=lines, seconds=1.0)


LABELS = [row(["Q1"], 400, 470), row(["Q2"], 590, 470), row(["Q3"], 780, 470)]


def values(lines: list[OcrLine], **kw):
    out, reading = link_sheet(sheet(lines, **kw), "schematic.pdf")
    return {v.field: v for v in out}, reading


def test_rotated_rating_goes_to_the_nearest_way_label_on_its_left() -> None:
    got, reading = values(LABELS + [vertical(["MCCB", "630A", "4P", "50kA"], 425),
                                    vertical(["SW-DISC", "400A", "4P"], 615),
                                    vertical(["SMALL", "POWER"], 450)])
    assert got["way.Q1.rating"].value == 630 and got["way.Q1.rating"].unit == "A"
    assert got["way.Q1.poles"].value == 4 and got["way.Q1.breaking_capacity"].value == 50
    assert got["way.Q1.device"].value == "mccb"
    assert got["way.Q2.device"].value == "switch_disconnector" and got["way.Q2.rating"].value == 400
    assert got["way.Q1.description"].value == "SMALL POWER"
    assert "way.Q3.rating" not in got  # no rating text under Q3
    assert reading.way_count == 2 and reading.ways[0].rating_a == 630


def test_a_rating_whose_label_was_not_read_is_dropped_not_given_to_the_way_before() -> None:
    labels = [LABELS[0], LABELS[2]]  # Q2 not read
    got, _ = values(labels + [vertical(["MCCB", "630A", "4P"], 425), vertical(["MCCB", "250A", "4P"], 615)])
    assert got["way.Q1.rating"].value == 630
    assert all(not f.startswith("way.Q1.") or got[f].value != 250 for f in got)
    assert "way.Q2.rating" not in got


def test_every_ocr_value_is_ocr_on_the_drawing_with_a_region_and_at_most_medium() -> None:
    got, _ = values(LABELS + [vertical(["MCCB", "630A", "4P", "50kA"], 425), row(["kWh"], 300, 340),
                              row(["DEGREE", "OF", "PROTECTION:", "IP31"], 90, 1300)])
    assert got
    for v in got.values():
        assert v.method == Method.OCR
        assert v.confidence in (Confidence.MEDIUM, Confidence.LOW)
        assert v.source.document == DocumentKind.SCHEMATIC and v.source.page == 1 and v.source.source_text
        assert len(v.source.regions) == 1
        r = v.source.regions[0]
        assert r.version == DrawingVersionKind.CLEAN and r.sheet == 1
        assert 0 <= r.bbox[0] < r.bbox[2] <= 2481 and 0 <= r.bbox[1] < r.bbox[3] <= 1754
    assert got["enclosure.ip_rating"].value == "IP31"


def test_trailing_symbol_noise_is_dropped_and_the_box_covers_the_kept_words() -> None:
    line = vertical(["MCCB", "630A", "4P", "50kA", "e%"], 425)
    got, _ = values(LABELS + [line])
    v = got["way.Q1.rating"]
    assert v.source.source_text == "MCCB 630A 4P 50kA"
    noise = line.words[-1].bbox
    assert v.source.regions[0].bbox[1] >= noise[3]  # the noise word (top of the line) is outside the box


def test_look_alike_letters_become_digits_with_low_confidence_and_a_note() -> None:
    got, _ = values(LABELS + [vertical(["MCCB", "630A", "4P", "SOkA"], 425),
                              row(["BUSBAR", "2500A", "TP&N", "5OkA", "1s"], 2100, 420)])
    v = got["way.Q1.breaking_capacity"]
    assert v.value == 50 and v.confidence == Confidence.LOW and "digits" in v.derivation
    assert got["way.Q1.rating"].confidence == Confidence.LOW  # same text, so the same caution
    assert got["system.fault_level"].value == 50 and got["system.fault_level"].confidence == Confidence.LOW
    assert got["busbar.rating"].value == 2500 and got["busbar.rating"].confidence == Confidence.MEDIUM


def test_low_tesseract_confidence_gives_low() -> None:
    got, _ = values(LABELS + [vertical(["MCCB", "630A", "4P"], 425, conf=60)])
    assert got["way.Q1.rating"].confidence == Confidence.LOW


def test_a_label_read_as_zero_is_taken_as_q_and_the_count_says_so() -> None:
    labels = [LABELS[0], row(["02"], 590, 470), LABELS[2]]
    got, _ = values(labels + [vertical(["MCCB", "630A", "4P"], 425), vertical(["MCCB", "250A", "4P"], 615)])
    assert got["way.Q2.rating"].value == 250
    count = got["ways.count"]
    assert count.value == 3 and count.confidence == Confidence.LOW and "taken as Q" in count.derivation


def test_way_count_is_counted_in_code_and_names_labels_not_read() -> None:
    labels = [LABELS[0], LABELS[2], row(["Q4"], 970, 470)]
    got, _ = values(labels + [vertical(["MCCB", "630A", "4P"], 425)])
    count = got["ways.count"]
    assert count.value == 3 and "not read: Q2" in count.derivation and count.confidence == Confidence.LOW
    full, _ = values(LABELS + [vertical(["MCCB", "630A", "4P"], 425)])
    assert full["ways.count"].value == 3 and full["ways.count"].confidence == Confidence.MEDIUM


def test_labels_without_any_rating_text_are_not_way_labels() -> None:
    got, _ = values(LABELS)  # e.g. a front view with section labels
    assert "ways.count" not in got


def test_tbc_rating_is_none_with_low_confidence() -> None:
    got, _ = values(LABELS + [vertical(["MCCB", "TBC", "4P"], 425)])
    assert got["way.Q1.rating"].value is None and got["way.Q1.rating"].confidence == Confidence.LOW


def test_cable_schedule_rows_and_lengths() -> None:
    schedule = [row(["Q1"], 670, 1380), row(["2x", "4C", "185", "mm2", "SWA"], 1150, 1380), row(["50"], 1460, 1380),
                row(["Q2"], 670, 1405), row(["AC", "240", "mm2", "SWA"], 1150, 1405), row(["24"], 1400, 1405)]
    got, _ = values(LABELS + [vertical(["MCCB", "630A", "4P"], 425)] + schedule)
    assert got["way.Q1.cable"].value == "2x 4C 185 mm2 SWA" and got["way.Q1.cable_length"].value == 50
    assert got["way.Q1.cable_length"].unit == "m"
    q2 = got["way.Q2.cable"]
    assert q2.value == "4C 240 mm2 SWA" and q2.confidence == Confidence.LOW and "read as" in q2.derivation
    assert got["way.Q2.cable_length"].value == 24
    assert got["ways.count"].value == 3  # schedule labels are not counted as diagram way labels


def test_tilted_schedule_rows_still_pair_with_their_own_cable() -> None:
    """A scan turned a little: every row falls 0.03 px per px; the cable 480 px right sits 14 px lower."""
    tilt = 0.03

    def tilted(texts: list[str], x: float, y: float) -> OcrLine:
        lefts = [x + i * 60 for i in range(len(texts))]
        return OcrLine(words=[word(t, x0, y + tilt * x0, x0 + 50, y + tilt * x0 + 15) for t, x0 in zip(texts, lefts)])

    lines = [tilted(["NOTES", "FOR", "THIS", "DRAWING", "ONLY"], 90, 1200)]
    for i, (way, cable) in enumerate([("Q1", ["4C", "95", "mm2", "SWA"]), ("Q2", ["4C", "240", "mm2", "SWA"]),
                                      ("Q3", ["4C", "35", "mm2", "SWA"])]):
        lines += [tilted([way], 670, 1380 + 25 * i), tilted(cable, 1150, 1380 + 25 * i)]
    assert skew(lines) == pytest.approx(tilt, abs=1e-6)
    got, _ = values(lines)
    assert [got[f"way.Q{n}.cable"].value for n in (1, 2, 3)] == ["4C 95 mm2 SWA", "4C 240 mm2 SWA", "4C 35 mm2 SWA"]


def test_sheet_facts_follow_the_dxf_rules() -> None:
    got, _ = values([row(["INCOMING", "SUPPLY", "400V", "3PH+N", "50Hz"], 210, 100),
                     row(["ACB", "2500A", "4P", "50kA"], 220, 220), row(["CT", "2500/5A"], 250, 300),
                     row(["MFM"], 300, 340), row(["1.", "FORM", "OF", "SEPARATION:", "FORM", "4a"], 90, 1270),
                     row(["3.", "CABLE", "ENTRY:", "BOTTOM"], 90, 1330),
                     row(["4.", "EARTHING", "SYSTEM:", "TN-C-S"], 90, 1360),
                     row(["OVERALL", "WIDTH", "3200", "mm", "-", "5", "SECTIONS"], 900, 1500)])
    assert got["system.voltage"].value == 400 and got["system.frequency"].value == 50
    assert got["incomer.device"].value == "acb" and got["incomer.rating"].value == 2500
    assert got["incomer.poles"].value == 4 and got["metering.ct_ratio"].value == "2500/5"
    assert got["metering.meter"].value == "MFM" and got["enclosure.form"].value == "4a"
    assert got["enclosure.cable_entry"].value == "bottom" and got["system.earthing"].value == "TN-C-S"
    assert got["enclosure.width"].value == 3200 and got["enclosure.sections"].value == 5


def test_digits_maps_only_look_alikes() -> None:
    assert digits("SO") == ("50", True)
    assert digits("630") == ("630", False)
    assert digits("A", {"A": "4"}) == ("4", True)


def test_unturn_maps_a_box_of_the_turned_image_back() -> None:
    """Upright image 100 wide, 40 tall; the turned image is 40 wide, 100 tall."""
    from PIL import Image

    upright = Image.new("L", (100, 40), 255)
    upright.putpixel((70, 10), 0)  # one dark pixel
    turned = upright.transpose(Image.Transpose.ROTATE_270)
    xs, ys = zip(*[(x, y) for x in range(turned.width) for y in range(turned.height) if turned.getpixel((x, y)) == 0])
    box = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
    assert unturn(box, turned.width) == [70, 10, 71, 11]


def test_reading_texts_leave_out_low_confidence_noise() -> None:
    noise = OcrLine(words=[word("~", 10, 10, 20, 20, conf=10)])
    _, reading = values(LABELS + [noise])
    assert all(t.text != "~" for t in reading.texts)
    assert reading.method == Method.OCR
