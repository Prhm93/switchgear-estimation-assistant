"""Stage 4 Part C on real (synthetic) drawings and in the pipeline.

The showcase is not in the training set, so this is a small held-out check of the committed templates.
"""

from __future__ import annotations

from backend.app import pipeline
from backend.app.drawing.boxes import Box, match_boxes, total
from backend.app.drawing.data import evaluation_drawings
from backend.app.drawing.reading import DetectedSymbol, DrawingReading, TextBox
from backend.app.drawing.symbols import BREAKER_CLASSES, TemplateDetector
from backend.app.reading import PageText, ReadResult
from backend.app.schemas import DocumentStatus, Method
from backend.app.storage import FileType
from backend.drawings import _sheet
from data_generator.schemas import DrawingVersionKind, SymbolClass
from data_generator.sets import DATA

KEEP = {c.value for c in BREAKER_CLASSES}


def test_the_showcase_clean_drawing_breakers_are_found() -> None:
    sample = next(s for s in evaluation_drawings("showcase") if s.version.value == "clean"
                  and any(t.cls.value in KEEP for t in s.symbols))
    found = TemplateDetector().detect(_sheet(sample))
    pred = [Box(f.cls.value, f.bbox, f.score) for f in found]
    truth = [Box(t.cls.value, t.bbox) for t in sample.symbols if t.cls.value in KEEP]
    score = total(match_boxes(pred, truth))
    assert score.recall >= 0.8 and score.precision >= 0.8, score


SCAN = DATA / "projects" / "showcase" / "drawing" / "schematic_sheet1_scanned.png"


class OneSymbol:
    """Stands in for a detector: one MCCB under the Q2 label."""

    name = "fake"

    def detect(self, image):
        return [DetectedSymbol(cls=SymbolClass.MCCB, bbox=[190, 300, 210, 380], score=0.8),
                DetectedSymbol(cls=SymbolClass.ACB, bbox=[90, 300, 110, 380], score=0.8)]


def ocr_with_labels(file_type, data, name, dpi, cmd):
    from backend.app.schemas import ExtractedValue
    from data_generator.schemas import DocumentKind, Region, SourceRef

    reading = DrawingReading(file=name, version=DrawingVersionKind.SCANNED, sheet=1, method=Method.OCR,
                             width_px=1000, height_px=800,
                             labels=[TextBox(text="Q1", bbox=[90, 400, 110, 420]),
                                     TextBox(text="Q2", bbox=[190, 400, 210, 420])])
    q1 = ExtractedValue(field="way.Q1.device", value="mccb", method=Method.OCR, confidence="medium", rule="ocr.way",
                        source=SourceRef(document=DocumentKind.SCHEMATIC, file=name, page=1, source_text="MCCB 630A",
                                         regions=[Region(version=DrawingVersionKind.SCANNED, sheet=1,
                                                         bbox=[90, 200, 110, 290])]))
    read = ReadResult(status=DocumentStatus.DONE, pages=[PageText(number=1, lines=["Q1", "Q2"])],
                      note="Read by OCR (Tesseract, 300 dpi): every value needs the engineer's review.")
    return read, [q1], [reading]


def test_the_pipeline_adds_detector_devices_only_for_ways_ocr_did_not_read(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "read_drawing_ocr", ocr_with_labels)
    result = pipeline.analyse_file(FileType.PNG, SCAN.read_bytes(), SCAN.name, drawing_reading="ocr",
                                   detector=OneSymbol())
    devices = sorted((v.field, v.value, v.method) for v in result.values if v.field.endswith(".device"))
    assert devices == [("way.Q1.device", "mccb", Method.OCR), ("way.Q2.device", "mccb", Method.DETECTOR)]
    assert result.drawings[0].symbols and {s.way for s in result.drawings[0].symbols} == {"Q1", "Q2"}
    assert "symbol detector" in result.read.note


def test_without_a_detector_nothing_changes(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "read_drawing_ocr", ocr_with_labels)
    result = pipeline.analyse_file(FileType.PNG, SCAN.read_bytes(), SCAN.name, drawing_reading="ocr")
    assert [v.method for v in result.values] == [Method.OCR] and "symbol detector" not in result.read.note
