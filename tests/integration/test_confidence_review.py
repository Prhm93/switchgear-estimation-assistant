"""Stage 6 in the app: confidence decides conflicts, bulk acceptance, ticks and the order of the review queue.

Two model readings that differ are a weak difference (each value checked on its own, unticked, with the reason),
not a conflict card; a model value that agrees with another file is high but is still ticked by a person and
never accepted in bulk; the page cards go riskiest first; and two different values can never both be approved
for one item.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import enquiry, pipeline, services
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Document, ExtractedValueRow, Project
from tests.integration.test_proof_boxes import SCAN, SPEC, ocr_stand_in


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(pipeline, "read_drawing_ocr", ocr_stand_in)
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="ocr",
                        symbol_detector="off")
    with TestClient(create_app(settings)) as c:
        yield c


def setup(client: TestClient) -> tuple[int, dict[str, int]]:
    """Showcase specification and scanned drawing (OCR stand-in), plus model readings of the meter field."""
    response = client.post("/enquiries", data={"name": "Confidence"},
                           files=[("files", (SCAN.name, SCAN.read_bytes())), ("files", (SPEC.name, SPEC.read_bytes()))],
                           follow_redirects=False)
    pid = int(response.headers["location"].split("/")[2])
    with client.app.state.sessions() as session:
        docs = {d.kind: d for d in session.scalars(select(Document).where(Document.project_id == pid))}
        for r in session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid,
                                                                 ExtractedValueRow.field == "metering.meter")):
            session.delete(r)

        def model(field: str, value, unit, doc: Document, text: str) -> ExtractedValueRow:
            row = ExtractedValueRow(project_id=pid, document_id=doc.id, field=field, value=value, unit=unit,
                                    source_document=doc.kind, source_file=doc.original_name, page=1,
                                    source_text=text, regions=[], method="llm", confidence="medium",
                                    agreement="llm_only", quote_match="exact", flags=[])
            session.add(row)
            return row

        a = model("metering.meter", "multifunction", None, docs["specification"], "multifunction meter")
        b = model("metering.meter", "kwh", None, docs["schematic"], "kWh meter")
        session.flush()
        spec_voltage = session.scalars(select(ExtractedValueRow).where(
            ExtractedValueRow.project_id == pid, ExtractedValueRow.field == "system.voltage",
            ExtractedValueRow.method == "rules")).first()
        agreeing = model("system.voltage", spec_voltage.value, spec_voltage.unit, docs["schematic"], "400V")
        session.commit()
        return pid, {"a": a.id, "b": b.id, "agreeing": agreeing.id}


def test_two_model_readings_that_differ_are_checked_one_by_one_not_a_conflict(client: TestClient) -> None:
    pid, ids = setup(client)
    with client.app.state.sessions() as session:
        project = session.get(Project, pid)
        found = enquiry.decisions(project)
        g = found.groups["metering.meter"]
        assert g["weak"] and not g["conflict"]
        assert {v.id for v in found.reasons["weak"]} >= {ids["a"], ids["b"]}
        assert "metering.meter" not in found.between_files  # the gated cross-check does not flag it
        plan = enquiry.review_plan(project)
    assert not any(c.kind == "conflict" and c.field == "metering.meter" for c in plan)
    html = client.get(f"/enquiries/{pid}/review").text
    for _ in range(10):  # walk the cards until the model readings show
        if f'value="{ids["a"]}"' in html:
            break
        url, data = _first_form(html)
        html = client.post(url, data=data, headers={"HX-Request": "true", "HX-Target": "review-body"}).text
    box = re.search(rf'<input type="checkbox" name="value_id" value="{ids["a"]}"([^>]*)>', html)
    assert box and " checked" not in box.group(1)  # a model value is ticked by a person
    assert "gives a different value" in html


def test_a_model_value_that_agrees_is_high_but_never_accepted_in_bulk(client: TestClient) -> None:
    pid, ids = setup(client)
    with client.app.state.sessions() as session:
        project = session.get(Project, pid)
        groups = enquiry.review_groups(project)
        assert enquiry.assessment(next(v for v in project.values if v.id == ids["agreeing"]), groups).level == "high"
        bulk = {v.id for v in enquiry.bulk_acceptable(groups)}
        assert ids["agreeing"] not in bulk and all(v.method == "rules" for v in enquiry.bulk_acceptable(groups))
        agreeing_card = next((c for c in enquiry.review_plan(project) if c.kind == "agreeing"), None)
        assert agreeing_card is None or ids["agreeing"] not in {v.id for v in agreeing_card.values}
        services.accept_all(session, project)
        assert session.get(ExtractedValueRow, ids["agreeing"]).review_status == "extracted"


def test_page_cards_go_riskiest_first(client: TestClient) -> None:
    pid, _ = setup(client)
    with client.app.state.sessions() as session:
        project = session.get(Project, pid)
        groups = enquiry.review_groups(project)
        pages = [c for c in enquiry.review_plan(project) if c.kind == "page"]
        top = [max(enquiry.risk(v, groups) for v in c.values) for c in pages]
        assert top == sorted(top, reverse=True) and len(pages) >= 2
        for c in pages:
            inside = [enquiry.risk(v, groups) for v in c.values]
            assert inside == sorted(inside, reverse=True)


def test_two_different_values_can_never_both_be_approved_for_one_item(client: TestClient) -> None:
    pid, ids = setup(client)
    with client.app.state.sessions() as session:
        services.review_value(session, ids["a"], "approve")
        with pytest.raises(services.ReviewError, match="already approved"):
            services.review_value(session, ids["b"], "approve")
        assert session.get(ExtractedValueRow, ids["b"]).review_status == "extracted"


def _first_form(html: str) -> tuple[str, dict[str, list[str]]]:
    from tests.integration.test_simple_flow import form_lists

    action = next(a for a in ("agreeing", "approve", "group") if f'/review/{a}"' in html)
    return form_lists(html, action)


def test_the_value_panel_shows_the_level_and_why(client: TestClient) -> None:
    pid, ids = setup(client)
    panel = client.get(f"/values/{ids['a']}/panel", headers={"HX-Request": "true"}).text
    assert 'data-confidence="low"' in panel
    assert "Read by a model, with an exact quote" in panel and "gives a different value" in panel
    agreeing = client.get(f"/values/{ids['agreeing']}/panel", headers={"HX-Request": "true"}).text
    assert 'data-confidence="high"' in agreeing and "agrees" in agreeing
