"""Drawing reading by OCR on the committed showcase drawings, in the pipeline and in the app.

These tests need the Tesseract program. On a laptop without it they skip
with a clear message; in CI (``REQUIRE_TESSERACT=1``) a missing Tesseract fails
the build instead, so the OCR tests always run there.

The tests that need no Tesseract are at the end: with drawing reading off,
nothing changes from Stage 3; with it on but Tesseract missing, the drawing
stays "not read yet" with a note.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import services
from backend.app.config import Settings
from backend.app.drawing.boxes import iou
from backend.app.drawing.data import evaluation_drawings
from backend.app.drawing.ocr import tesseract_version
from backend.app.evaluation import score, total
from backend.app.main import create_app
from backend.app.models import Document, ExtractedValueRow
from backend.app.pipeline import analyse_file
from backend.app.schemas import Confidence, DocumentKind, DocumentStatus, Method
from backend.app.storage import FileType
from data_generator.schemas import DrawingVersionKind
from data_generator.sets import DATA

SHOWCASE = DATA / "projects" / "showcase"
PDF = (SHOWCASE / "drawing" / "schematic.pdf").read_bytes()
SCAN = (SHOWCASE / "drawing" / "schematic_sheet1_scanned.png").read_bytes()


@pytest.fixture(scope="module")
def tesseract() -> str:
    version = tesseract_version()
    if version is None:
        message = "Tesseract not found: install it (docs/stage-4.md) or set TESSERACT_CMD"
        if os.environ.get("REQUIRE_TESSERACT") == "1":
            pytest.fail(message + " (REQUIRE_TESSERACT=1: OCR tests must run here)")
        pytest.skip(message)
    return version


def _truth(version: DrawingVersionKind, sheet: int = 1):
    return next(s for s in evaluation_drawings("showcase") if s.version == version and s.sheet == sheet)


def test_clean_pdf_values_are_right_and_their_boxes_sit_on_the_answer_key_boxes(tesseract: str) -> None:
    analysis = analyse_file(FileType.PDF, PDF, "schematic.pdf", drawing_reading="ocr", ocr_dpi=300)
    assert analysis.kind == DocumentKind.SCHEMATIC and analysis.read.status == DocumentStatus.DONE
    assert "OCR" in analysis.read.note and [d.sheet for d in analysis.drawings] == [1, 2]
    truth = _truth(DrawingVersionKind.CLEAN)
    sheet1 = [v for v in analysis.values if v.source.page == 1]
    s = total(score(sheet1, truth.values))
    assert s.tp >= 30 and s.precision >= 0.9, s  # showcase measured at 49 right, 0 wrong (docs/stage-4.md)
    by_field = {t.field: t for t in truth.values}
    for v in sheet1:
        t = by_field.get(v.field)
        if t is not None and t.value == v.value and v.field.endswith(".rating"):
            assert iou(v.source.regions[0].bbox, t.source.regions[0].bbox) >= 0.5, (v.field, v.source.regions)


def test_every_ocr_value_is_ocr_medium_at_most_with_a_region(tesseract: str) -> None:
    analysis = analyse_file(FileType.PNG, SCAN, "schematic_sheet1_scanned.png", drawing_reading="ocr")
    assert analysis.values and analysis.llm is None
    for v in analysis.values:
        assert v.method == Method.OCR and v.confidence in (Confidence.MEDIUM, Confidence.LOW)
        assert v.review_status == "extracted" and v.source.document == DocumentKind.SCHEMATIC
        assert v.source.regions and v.source.regions[0].version == DrawingVersionKind.SCANNED
    reading = analysis.drawings[0]
    assert reading.method == Method.OCR and reading.version == DrawingVersionKind.SCANNED and reading.texts
    assert reading.way_count == len({v.field.split(".")[1] for v in analysis.values if v.field.startswith("way.")
                                     and v.field.endswith(".device")})


def test_150_and_300_dpi_give_boxes_in_the_same_coordinates(tesseract: str) -> None:
    low = analyse_file(FileType.PDF, PDF, "schematic.pdf", drawing_reading="ocr", ocr_dpi=150)
    high = analyse_file(FileType.PDF, PDF, "schematic.pdf", drawing_reading="ocr", ocr_dpi=300)
    a = {v.field: v for v in low.values if v.field.endswith(".rating")}
    b = {v.field: v for v in high.values if v.field.endswith(".rating")}
    shared = a.keys() & b.keys()
    assert shared
    for f in shared:
        assert iou(a[f].source.regions[0].bbox, b[f].source.regions[0].bbox) >= 0.5, f


# --- in the app (the default setting is ocr) ------------------------------------------------------

@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test")
    with TestClient(create_app(settings)) as c:
        yield c


def _upload(client: TestClient) -> int:
    response = client.post("/projects", data={"name": "OCR", "reference": "ENQ-4A"}, follow_redirects=False)
    pid = int(response.headers["location"].split("/")[2])
    files = [("files", ("specification.pdf", (SHOWCASE / "specification.pdf").read_bytes())),
             ("files", ("schematic_sheet1_scanned.png", SCAN))]
    client.post(f"/projects/{pid}/documents", files=files, follow_redirects=False)
    return pid


def _ocr_rows(client: TestClient, pid: int) -> list[ExtractedValueRow]:
    with client.app.state.sessions() as session:
        return list(session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid,
                                                                    ExtractedValueRow.method == "ocr")))


def test_the_app_reads_a_scanned_drawing_by_default(client: TestClient, tesseract: str) -> None:
    assert Settings().drawing_reading == "ocr"
    pid = _upload(client)
    with client.app.state.sessions() as session:
        doc = session.scalars(select(Document).where(Document.project_id == pid,
                                                     Document.original_name == "schematic_sheet1_scanned.png")).one()
        assert doc.status == "done" and "OCR" in doc.note
    rows = _ocr_rows(client, pid)
    assert rows and all(r.confidence in ("medium", "low") and r.regions for r in rows)
    assert all(r.regions[0]["version"] == "scanned" and r.page == 1 for r in rows)


def test_approve_all_leaves_ocr_values_and_they_never_reach_the_estimate_unapproved(
        client: TestClient, tesseract: str) -> None:
    pid = _upload(client)
    rows = _ocr_rows(client, pid)
    with client.app.state.sessions() as session:  # even at high confidence, OCR values are approved one by one
        for r in rows:
            session.get(ExtractedValueRow, r.id).confidence = "high"
        session.commit()
    client.post(f"/projects/{pid}/review/approve-agreed")
    assert all(r.review_status == "extracted" for r in _ocr_rows(client, pid))
    client.post(f"/projects/{pid}/estimate")
    with client.app.state.sessions() as session:
        est = services.latest_estimate(session, pid)
        used = {i for ln in est.lines for i in ln.value_ids}
    assert not used & {r.id for r in rows}


# --- no Tesseract needed ----------------------------------------------------------------------------

def test_with_drawing_reading_off_drawings_stay_not_read_as_in_stage_3() -> None:
    for file_type, data, name in ((FileType.PDF, PDF, "schematic.pdf"),
                                  (FileType.PNG, SCAN, "schematic_sheet1_scanned.png")):
        analysis = analyse_file(file_type, data, name)  # the pipeline default is off
        assert analysis.read.status == DocumentStatus.NOT_READ and analysis.values == [] and not analysis.drawings
        off = analyse_file(file_type, data, name, drawing_reading="off")
        assert off.model_dump() == analysis.model_dump()


def test_ocr_on_without_tesseract_keeps_the_drawing_not_read_with_a_note(tmp_path: Path) -> None:
    analysis = analyse_file(FileType.PNG, SCAN, "schematic_sheet1_scanned.png", drawing_reading="ocr",
                            tesseract_cmd=str(tmp_path / "no-tesseract.exe"))
    assert analysis.read.status == DocumentStatus.NOT_READ and analysis.values == []
    assert "Tesseract was not found" in analysis.read.note


def test_text_documents_are_never_ocr_read() -> None:
    spec = (SHOWCASE / "specification.pdf").read_bytes()
    on = analyse_file(FileType.PDF, spec, "specification.pdf", drawing_reading="ocr")
    off = analyse_file(FileType.PDF, spec, "specification.pdf")
    assert on.model_dump() == off.model_dump()
