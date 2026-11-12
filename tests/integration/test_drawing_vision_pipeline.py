"""Stage 4 Part B in the pipeline and the app, with a fake vision client (no model is called).

OCR is replaced by a stand-in where a test needs it, so these run without Tesseract.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import pipeline
from backend.app.config import Settings
from backend.app.drawing.ocr import TesseractMissing
from backend.app.drawing.vision import VisionRecording, VisionSheetOutput, VisionUnavailable
from backend.app.main import create_app
from backend.app.models import ExtractedValueRow, Project
from backend.app.reading import PageText, ReadResult
from backend.app.schemas import DocumentStatus, ExtractedValue, Method
from backend.app.storage import FileType
from data_generator.schemas import DocumentKind, DrawingVersionKind, Region, SourceRef
from data_generator.sets import DATA

SCAN = DATA / "projects" / "showcase" / "drawing" / "schematic_sheet1_scanned.png"
OUT = VisionSheetOutput.model_validate({"ways": [
    {"way": "Q1", "device": "MCCB", "rating_a": 630, "poles": 4, "breaking_ka": 50, "text": "MCCB 630A 4P 50kA"}]})


class FakeVision:
    """Stands in for a vision model: gives the same reading for every sheet, and counts its calls."""

    label = "fake-vision (fake)"

    def __init__(self, output: VisionSheetOutput = OUT, error: Exception | None = None) -> None:
        self.output, self.error, self.calls = output, error, []

    def read(self, *, file_sha256: str, sheet: int, image: Callable[[], bytes]) -> VisionSheetOutput:
        self.calls.append((file_sha256, sheet))
        if self.error:
            raise self.error
        return self.output


def no_tesseract(*args, **kwargs):
    raise TesseractMissing("Tesseract was not found: install it or set TESSERACT_CMD")


def ocr_with_q1_rating(file_type, data, name, dpi, cmd):
    """A stand-in OCR result: one rating for Q1 on sheet 1, and its text."""
    value = ExtractedValue(field="way.Q1.rating", value=630, unit="A", method=Method.OCR, confidence="medium",
                           rule="ocr.way", source=SourceRef(
                               document=DocumentKind.SCHEMATIC, file=name, page=1, source_text="MCCB 630A 4P 50kA",
                               regions=[Region(version=DrawingVersionKind.SCANNED, sheet=1, bbox=[10, 10, 50, 90])]))
    read = ReadResult(status=DocumentStatus.DONE, pages=[PageText(number=1, lines=["Q1", "MCCB 630A 4P 50kA"])],
                      note="Read by OCR (Tesseract, 300 dpi): every value needs the engineer's review.")
    return read, [value], []


def analyse(vision, monkeypatch, ocr=no_tesseract):
    monkeypatch.setattr(pipeline, "read_drawing_ocr", ocr)
    return pipeline.analyse_file(FileType.PNG, SCAN.read_bytes(), SCAN.name, drawing_reading="ocr", vision=vision)


def test_without_tesseract_the_vision_model_reads_the_picture(monkeypatch) -> None:
    vision = FakeVision()
    result = analyse(vision, monkeypatch)
    assert vision.calls == [(hashlib.sha256(SCAN.read_bytes()).hexdigest(), 1)]
    assert {v.method for v in result.values} == {Method.VISION}
    assert {v.field for v in result.values} == {"way.Q1.device", "way.Q1.rating", "way.Q1.poles",
                                                 "way.Q1.breaking_capacity"}
    assert result.read.status == DocumentStatus.DONE and "vision model" in result.read.note
    assert result.vision_run == "fake-vision (fake)"


def test_vision_fills_only_what_ocr_left_empty_and_ocr_text_raises_it_to_medium(monkeypatch) -> None:
    result = analyse(FakeVision(), monkeypatch, ocr=ocr_with_q1_rating)
    by_field = {(v.field, v.method): v for v in result.values}
    assert ("way.Q1.rating", Method.OCR) in by_field and ("way.Q1.rating", Method.VISION) not in by_field
    assert by_field[("way.Q1.poles", Method.VISION)].confidence == "medium"  # its text is in the OCR text
    assert "OCR" in result.read.note and "vision model" in result.read.note


def test_a_vision_failure_keeps_the_ocr_values_and_says_why(monkeypatch) -> None:
    result = analyse(FakeVision(error=VisionUnavailable("no vision recording matches this file's SHA-256")),
                     monkeypatch, ocr=ocr_with_q1_rating)
    assert [v.method for v in result.values] == [Method.OCR]
    assert "no vision recording matches" in result.read.note and result.vision_run is None


def test_without_a_vision_client_nothing_changes(monkeypatch) -> None:
    result = analyse(None, monkeypatch, ocr=ocr_with_q1_rating)
    assert [v.method for v in result.values] == [Method.OCR] and "vision" not in result.read.note
    blank = analyse(None, monkeypatch)
    assert blank.values == [] and blank.read.status == DocumentStatus.NOT_READ


def test_a_file_that_is_not_a_drawing_never_goes_to_the_vision_model(monkeypatch) -> None:
    vision = FakeVision()
    spec = DATA / "projects" / "showcase" / "specification.pdf"
    pipeline.analyse_file(FileType.PDF, spec.read_bytes(), spec.name, drawing_reading="ocr", vision=vision)
    assert vision.calls == []


# --- the app ------------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(pipeline, "read_drawing_ocr", no_tesseract)
    folder = tmp_path / "recorded-vision"
    folder.mkdir()
    data = SCAN.read_bytes()
    rec = VisionRecording(model="fake-vision", model_version="test", date="2026-11-12", prompt_version="vision-v1",
                          prompt="fake", input_name=f"showcase/drawing/{SCAN.name}",
                          input_sha256=hashlib.sha256(data).hexdigest(), sheet=1, output=OUT, fake=True)
    (folder / "fake.json").write_text(rec.model_dump_json(), encoding="utf-8")
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="ocr",
                        vision_mode="recorded", vision_recorded_dir=folder)
    with TestClient(create_app(settings)) as c:
        yield c


def test_the_app_stores_vision_values_for_review_and_accept_all_leaves_them(client: TestClient) -> None:
    response = client.post("/enquiries", data={"name": "Vision"}, files=[("files", (SCAN.name, SCAN.read_bytes()))],
                           follow_redirects=False)
    pid = int(response.headers["location"].split("/")[2])
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    with client.app.state.sessions() as session:
        rows = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid)).all()
        assert rows and {r.method for r in rows} == {"vision"}
        assert {r.review_status for r in rows} == {"extracted"}  # never approved in bulk
        doc = session.get(Project, pid).documents[0]
        assert "vision model" in (doc.note or "")
    assert "Read from the drawing picture by a vision model" in client.get(f"/values/{rows[0].id}/panel").text
    page = client.get(f"/enquiries/{pid}/check").text
    assert "Read from a drawing picture" in page  # grouped with the OCR values for the engineer
