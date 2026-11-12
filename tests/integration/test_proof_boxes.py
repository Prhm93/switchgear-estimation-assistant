"""Stage 4 Part D: found items as boxes on the drawing in the proof viewer, linked to their values.

OCR is replaced by a stand-in that gives two values with boxes and one without, so this runs without
Tesseract; the detector is off here (it has its own tests).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from backend.app import pipeline
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Document, ExtractedValueRow
from backend.app.reading import PageText, ReadResult
from backend.app.schemas import DocumentStatus, ExtractedValue, Method
from data_generator.schemas import DocumentKind, DrawingVersionKind, Region, SourceRef
from data_generator.sets import DATA

SCAN = DATA / "projects" / "showcase" / "drawing" / "schematic_sheet1_scanned.png"
SPEC = DATA / "projects" / "showcase" / "specification.pdf"


def value(field, v, unit, confidence, text, bbox=None, method=Method.OCR):
    regions = [Region(version=DrawingVersionKind.SCANNED, sheet=1, bbox=bbox)] if bbox else []
    return ExtractedValue(field=field, value=v, unit=unit, method=method, confidence=confidence, rule="test",
                          source=SourceRef(document=DocumentKind.SCHEMATIC, file=SCAN.name, page=1,
                                           source_text=text, regions=regions))


def ocr_stand_in(file_type, data, name, dpi, cmd):
    values = [value("way.Q1.rating", 630, "A", "medium", "MCCB 630A <b>", [100, 200, 180, 260]),
              value("way.Q2.device", "mccb", None, "low", None, [300, 200, 340, 300], Method.DETECTOR),
              value("system.voltage", 400, "V", "medium", "400V 50Hz")]
    values[1].derivation = "symbol found by the template detector (score 0.82), linked to way Q2"
    read = ReadResult(status=DocumentStatus.DONE, pages=[PageText(number=1, lines=["MCCB 630A <b>", "400V 50Hz"])],
                      note="Read by OCR (Tesseract, 300 dpi): every value needs the engineer's review.")
    return read, values, []


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(pipeline, "read_drawing_ocr", ocr_stand_in)
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="ocr",
                        symbol_detector="off")
    with TestClient(create_app(settings)) as c:
        yield c


def upload(client: TestClient) -> tuple[int, int, dict[str, int]]:
    response = client.post("/enquiries", data={"name": "Boxes"},
                           files=[("files", (SCAN.name, SCAN.read_bytes())), ("files", (SPEC.name, SPEC.read_bytes()))],
                           follow_redirects=False)
    pid = int(response.headers["location"].split("/")[2])
    with client.app.state.sessions() as session:
        doc = session.scalars(select(Document).where(Document.project_id == pid,
                                                     Document.original_name == SCAN.name)).one()
        ids = {r.field: r.id for r in session.scalars(select(ExtractedValueRow).where(
            ExtractedValueRow.document_id == doc.id))}
        return pid, doc.id, ids


def test_the_drawing_sheet_shows_a_box_for_each_value_with_a_region(client: TestClient) -> None:
    pid, doc_id, ids = upload(client)
    html = client.get(f"/enquiries/{pid}/proof?doc={doc_id}&page=1").text
    width, height = Image.open(SCAN).size
    figure = re.search(r'<figure class="sheet".*?</figure>', html, re.S).group(0)
    assert f'<img class="sheet__img" src="/documents/{doc_id}/sheets/1.png"' in figure
    assert f'viewBox="0 0 {width} {height}"' in figure
    boxes = re.findall(r'<a class="sheet__box sheet__box--(\w+)" id="box-(\d+)" href="([^"]+)"', figure)
    assert sorted((tone, int(i)) for tone, i, _ in boxes) == sorted(
        [("picture", ids["way.Q1.rating"]), ("symbol", ids["way.Q2.device"])])  # the voltage has no box
    assert all(href == f"#v-{i}" for _, i, href in boxes)  # a box opens the value it supports
    rect = re.search(rf'id="box-{ids["way.Q1.rating"]}".*?<rect x="100(\.0)?" y="200(\.0)?" width="80(\.0)?" '
                     rf'height="60(\.0)?"', figure, re.S)
    assert rect, "the box is drawn where the value was read"
    assert "&lt;b&gt;" in figure and "<b>" not in figure  # read text is escaped in the box title
    symbol = re.search(rf'id="box-{ids["way.Q2.device"]}".*?</a>', figure, re.S).group(0)
    assert re.search(r'<text[^>]*class="sheet__label"[^>]*>MCCB 0\.82</text>', symbol)  # symbol boxes are labelled
    legend = re.search(r'<figcaption.*?</figcaption>', figure, re.S).group(0)
    for words in ("Read by rules", "Read from a picture, needs review", "Symbol found",
                  "Boxes show where each value was read."):
        assert words in legend, words
    line = re.search(rf'<div class="value-line" id="v-{ids["way.Q1.rating"]}">.*?</div>', html, re.S).group(0)
    assert f'href="#box-{ids["way.Q1.rating"]}"' in line and "Show on the drawing" in line
    voltage = re.search(rf'<div class="value-line" id="v-{ids["system.voltage"]}">.*?</div>', html, re.S).group(0)
    assert "#box-" not in voltage


def test_the_sheet_picture_is_served_and_other_files_have_no_boxes(client: TestClient) -> None:
    pid, doc_id, _ = upload(client)
    response = client.get(f"/documents/{doc_id}/sheets/1.png")
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert client.get(f"/documents/{doc_id}/sheets/9.png").status_code == 404
    with client.app.state.sessions() as session:
        spec_id = session.scalars(select(Document.id).where(Document.project_id == pid,
                                                            Document.original_name == SPEC.name)).one()
    assert '<figure class="sheet"' not in client.get(f"/enquiries/{pid}/proof?doc={spec_id}").text
    assert client.get(f"/documents/{spec_id}/sheets/1.png").status_code == 404
    assert client.get("/documents/99999/sheets/1.png").status_code == 404


def test_boxes_are_thin_see_through_outlines_coloured_by_how_the_value_was_read() -> None:
    css = (Path(__file__).parents[2] / "frontend" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    base = re.search(r"\.sheet__box rect\s*\{([^}]*)\}", css).group(1)
    assert "stroke-width: 2;" in base and "fill: currentColor" in base and "fill-opacity: 0.15" in base
    sheet_rules = " ".join(line for line in css.splitlines() if ".sheet__box" in line)
    for rule in re.findall(r"fill-opacity:\s*([\d.]+)", sheet_rules):
        assert float(rule) <= 0.3, "a box never hides the text under it"
    for kind in ("rules", "picture", "symbol"):
        rule = re.search(rf"\.sheet__box--{kind}\s*\{{([^}}]*)\}}", css)
        assert rule and "var(--" in rule.group(1) and "#" not in rule.group(1)
