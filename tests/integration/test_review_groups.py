"""Review groups for values read from a picture: one card per file and page; a person ticks each value.

Stage 6: values read from a picture or by a model start unticked (never pre-ticked, never accepted in bulk).

OCR is replaced by Part D's stand-in (three values on sheet 1 of the scanned showcase drawing: a rating and a
device with boxes, a voltage without), so this runs without Tesseract. "Approve N ticked" approves exactly the
ticked values, each with its own approved status and audit entry; an un-ticked value is left for later (one
audit entry) and stays unapproved, so it is never priced.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import pipeline
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AuditEvent, ExtractedValueRow
from tests.integration.test_proof_boxes import SCAN, SPEC, ocr_stand_in
from tests.integration.test_simple_flow import HX, form_lists, progress, visible_buttons


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(pipeline, "read_drawing_ocr", ocr_stand_in)
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="ocr",
                        symbol_detector="off")
    with TestClient(create_app(settings)) as c:
        yield c


def add(client: TestClient, *paths: Path) -> int:
    response = client.post("/enquiries", data={"next": "review"},
                           files=[("files", (p.name, p.read_bytes())) for p in paths], follow_redirects=False)
    return int(response.headers["location"].split("/")[2])


def rows(client: TestClient, pid: int) -> dict[str, ExtractedValueRow]:
    with client.app.state.sessions() as session:
        return {r.field: r for r in session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid))}


def events(client: TestClient, pid: int, action: str) -> list[int]:
    with client.app.state.sessions() as session:
        return sorted(int(e.entity_id) for e in session.scalars(select(AuditEvent).where(
            AuditEvent.project_id == pid, AuditEvent.action == action)))


def test_picture_values_of_one_sheet_are_one_card_unticked_with_their_boxes(client: TestClient) -> None:
    pid = add(client, SCAN)
    html = client.get(f"/enquiries/{pid}/review").text
    assert progress(html) == (0, 1)
    card = re.search(r'<article class="review-card review-card--group".*?</article>', html, re.S).group(0)
    assert SCAN.name in card and "sheet 1" in card
    boxes = re.findall(r'<input type="checkbox" name="value_id" value="(\d+)"([^>]*)>', card)
    by_field = rows(client, pid)
    assert sorted(int(i) for i, _ in boxes) == sorted(v.id for v in by_field.values())
    assert not any(" checked" in attrs for _, attrs in boxes)  # Stage 6: a person ticks each picture value
    assert card.count('<svg class="crop') == 2  # the rating and the device have boxes; the voltage shows its text
    assert "400V 50Hz" in card and "Boxes show where each value was read." in card
    assert "Approve 0 ticked" in visible_buttons(html)
    assert "Read from a drawing picture" in card  # each value says why it is here
    assert {v.review_status for v in by_field.values()} == {"extracted"}  # nothing approved without a click


def test_untick_leaves_a_value_for_later_and_approves_only_the_ticked(client: TestClient) -> None:
    pid = add(client, SCAN)
    url, data = form_lists(client.get(f"/enquiries/{pid}/review").text, "group")
    by_field = rows(client, pid)
    later = by_field["system.voltage"].id
    assert "value_id" not in data  # nothing ticked by default
    data["value_id"] = [str(v.id) for f, v in by_field.items() if v.id != later]  # the engineer ticks two
    after = client.post(url, data=data, headers=HX).text
    now = rows(client, pid)
    assert now["system.voltage"].review_status == "extracted" and now["system.voltage"].approved_value is None
    approved = sorted(v.id for v in now.values() if v.review_status == "approved")
    assert approved == sorted(int(i) for i in data["value_id"]) and len(approved) == 2
    assert events(client, pid, "approve") == approved  # one audit entry per approved value
    assert events(client, pid, "review_later") == [later]
    assert progress(after) == (1, 1) and "1 value left for later" in after
    assert "Make quote" in after


def test_ids_outside_the_card_are_never_approved(client: TestClient) -> None:
    pid = add(client, SCAN)
    url, data = form_lists(client.get(f"/enquiries/{pid}/review").text, "group")
    client.post(url, data={**data, "value_id": ["999999"]}, headers=HX)
    assert {v.review_status for v in rows(client, pid).values()} == {"extracted"}
    assert events(client, pid, "approve") == []


def test_each_group_holds_one_file_and_page(client: TestClient) -> None:
    pid = add(client, SCAN, SPEC)
    html, seen = client.get(f"/enquiries/{pid}/review").text, []
    for _ in range(40):
        if "Make quote" in html:
            break
        action = next(a for a in ("agreeing", "approve", "group") if f'/review/{a}"' in html)
        if action == "group":
            card = re.search(r'<article class="review-card review-card--group"[^>]*data-doc="(\d+)" data-page="(\d+)"'
                             r'(.*?)</article>', html, re.S)
            items = re.findall(r'<li class="group-value" data-doc="(\d+)" data-page="(\d+)"', card.group(3))
            assert items and set(items) == {(card.group(1), card.group(2))}
            seen.append((card.group(1), card.group(2)))
        url, data = form_lists(html, action)
        html = client.post(url, data=data, headers=HX).text
    assert "Make quote" in html
    assert len(seen) == len(set(seen)) >= 1  # one card per file and page
