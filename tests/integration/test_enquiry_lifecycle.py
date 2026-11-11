"""The enquiry life cycle on the new screens: rename, archive, delete, read again, the sample enquiry,
"Accept all" and the quote that rebuilds itself.

Each test has its own SQLite database and storage folder; drawing reading is off unless a test needs
it, so no Tesseract is required. Recordings used here are fake ones made by the test, never the
saved runs in data/recorded/.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app import enquiry, services
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AuditEvent, Document, Estimate, ExtractedValueRow, Project
from backend.app.services import SAMPLE_FILES
from backend.record import record_file
from data_generator import sets
from data_generator.project import load_answers
from data_generator.schemas import DocumentKind
from tests.fakes import FAKE_MODEL, ScriptedProvider, oracle_script

SHOWCASE = sets.DATA / "projects" / "showcase"
SPEC = (SHOWCASE / "specification.pdf").read_bytes()
LETTER = (SHOWCASE / "requirements.docx").read_bytes()
DXF = (SHOWCASE / "drawing" / "schematic.dxf").read_bytes()
MACHINE_WORDS = re.compile(r"\b(?:way\.Q\d+\.|system\.|enclosure\.|incomer\.|spec\.table|[0-9a-f]{64})")


def make_client(tmp_path: Path, **extra) -> TestClient:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test",
                        **{"drawing_reading": "off", **extra})
    return TestClient(create_app(settings))


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path) as c:
        yield c


def new_enquiry(client: TestClient, files: list[tuple[str, bytes]], name: str = "Board A") -> int:
    response = client.post("/enquiries", data={"name": name}, files=[("files", f) for f in files],
                           follow_redirects=False)
    assert response.status_code == 303
    return int(response.headers["location"].split("/")[2])


def actions(client: TestClient, project_id: int | None = None) -> list[AuditEvent]:
    with client.app.state.sessions() as session:
        rows = session.scalars(select(AuditEvent).order_by(AuditEvent.id))
        return [e for e in rows if project_id is None or e.project_id == project_id]


def count(client: TestClient, model, **where) -> int:
    with client.app.state.sessions() as session:
        query = select(func.count()).select_from(model)
        for key, value in where.items():
            query = query.where(getattr(model, key) == value)
        return session.scalar(query) or 0


# --- rename, archive, delete ----------------------------------------------------------------------

def test_an_enquiry_can_be_renamed_and_the_change_is_audited(client: TestClient) -> None:
    pid = new_enquiry(client, [])
    assert "Board A" in client.get(f"/enquiries/{pid}/rename").text
    assert client.post(f"/enquiries/{pid}/rename", data={"name": "  "}).status_code == 422
    client.post(f"/enquiries/{pid}/rename", data={"name": "Board B", "reference": "ENQ-9"})
    with client.app.state.sessions() as session:
        assert session.get(Project, pid).name == "Board B"
    event = [e for e in actions(client, pid) if e.action == "rename"][-1]
    assert event.detail["old_name"] == "Board A" and event.detail["name"] == "Board B"
    assert "Board B" in client.get("/enquiries").text


def test_archive_needs_a_confirmation_hides_the_enquiry_and_can_be_undone(client: TestClient) -> None:
    pid = new_enquiry(client, [])
    page = client.get(f"/enquiries/{pid}/archive").text
    assert "Archive this enquiry?" in page and 'name="confirm" value="yes"' in page
    client.post(f"/enquiries/{pid}/archive")  # no confirmation: nothing happens
    with client.app.state.sessions() as session:
        assert session.get(Project, pid).archived_at is None
    client.post(f"/enquiries/{pid}/archive", data={"confirm": "yes"})
    assert "Board A" not in client.get("/enquiries").text
    assert "Board A" in client.get("/enquiries?show=archived").text
    client.post(f"/enquiries/{pid}/unarchive")
    assert "Board A" in client.get("/enquiries").text
    assert [e.action for e in actions(client, pid)][-2:] == ["archive", "unarchive"]


def test_delete_needs_a_confirmation_and_keeps_an_audit_entry(client: TestClient) -> None:
    pid = new_enquiry(client, [("specification.pdf", SPEC)])
    values = count(client, ExtractedValueRow, project_id=pid)
    assert values > 0
    page = client.get(f"/enquiries/{pid}/delete").text
    assert "Delete this enquiry?" in page and "cannot be undone" in page and f"{values} values" in page
    response = client.post(f"/enquiries/{pid}/delete")  # no confirmation: the confirm page again
    assert response.status_code == 200 and count(client, Project, id=pid) == 1
    client.post(f"/enquiries/{pid}/delete", data={"confirm": "yes"})
    assert count(client, Project, id=pid) == 0
    assert count(client, ExtractedValueRow, project_id=pid) == 0 and count(client, Document, project_id=pid) == 0
    deleted = [e for e in actions(client) if e.action == "delete"]
    assert len(deleted) == 1 and deleted[0].entity_id == str(pid) and deleted[0].detail["name"] == "Board A"
    assert deleted[0].detail["values"] == values
    # The enquiry's earlier activity is kept, no longer tied to it.
    assert any(e.action == "upload" and e.project_id is None for e in actions(client))
    assert not list((client.app.state.settings.storage_dir).rglob("*.pdf"))
    assert client.get(f"/enquiries/{pid}/check").status_code == 404


# --- files: delete one, read one again -----------------------------------------------------------------

def test_a_file_is_deleted_only_after_confirmation_and_the_quote_follows(client: TestClient) -> None:
    pid = new_enquiry(client, [("specification.pdf", SPEC), ("requirements.docx", LETTER)])
    with client.app.state.sessions() as session:
        letter = session.scalars(select(Document).where(Document.original_name == "requirements.docx")).one()
        letter_id = letter.id
    assert "Delete requirements.docx?" in client.get(f"/documents/{letter_id}/delete").text
    client.post(f"/documents/{letter_id}/delete")
    assert count(client, Document, id=letter_id) == 1
    client.post(f"/documents/{letter_id}/delete", data={"confirm": "yes"})
    assert count(client, Document, id=letter_id) == 0
    assert count(client, ExtractedValueRow, document_id=letter_id) == 0
    event = [e for e in actions(client, pid) if e.action == "document_delete"][-1]
    assert event.detail["name"] == "requirements.docx" and event.detail["values"] > 0


def test_read_again_replaces_the_values_and_is_audited(client: TestClient) -> None:
    pid = new_enquiry(client, [("specification.pdf", SPEC)])
    with client.app.state.sessions() as session:
        doc_id = session.scalars(select(Document)).one().id
        first = session.scalars(select(ExtractedValueRow)).first()
    client.post(f"/values/{first.id}/approve")
    assert count(client, ExtractedValueRow, document_id=doc_id, review_status="approved") == 1
    page = client.get(f"/documents/{doc_id}/read-again").text
    assert "Read specification.pdf again?" in page and "Your 1 decision" in page
    before = count(client, ExtractedValueRow, document_id=doc_id)
    client.post(f"/documents/{doc_id}/read-again")  # no confirmation: nothing changes
    assert count(client, ExtractedValueRow, id=first.id) == 1
    client.post(f"/documents/{doc_id}/read-again", data={"confirm": "yes"})
    with client.app.state.sessions() as session:
        doc = session.get(Document, doc_id)
        assert doc.status == "done" and doc.read_method == "rules"
        rows = list(session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.document_id == doc_id)))
    assert len(rows) == before and all(r.review_status == "extracted" for r in rows)  # the decision is gone
    trail = [e.action for e in actions(client, pid)]
    assert "read_again" in trail and trail.index("read_again") < len(trail) - 1  # read after the reset


# --- Check, Accept all and the quote -------------------------------------------------------------------

def test_check_does_not_render_a_form_per_value(client: TestClient) -> None:
    pid = new_enquiry(client, [("specification.pdf", SPEC), ("requirements.docx", LETTER),
                               ("schematic.dxf", DXF)])
    page = client.get(f"/enquiries/{pid}/check").text
    values = count(client, ExtractedValueRow, project_id=pid)
    assert page.count("<form") < values / 3, (page.count("<form"), values)
    assert "Show all values" in page and "Items the customer wants" in page
    # One count everywhere: the summary sentence says the number on the Check tab.
    tab = re.search(r'step__count--needs mono" aria-label="(\d+) waiting', page).group(1)
    assert f"<strong>{tab}</strong> need" in page
    assert "/check/values" in page  # the full list is loaded only when opened


def test_normal_screens_show_plain_labels_not_machine_names(client: TestClient) -> None:
    pid = new_enquiry(client, [("specification.pdf", SPEC), ("requirements.docx", LETTER),
                               ("schematic.dxf", DXF)])
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    for url in (f"/enquiries/{pid}/check", f"/enquiries/{pid}/quote", f"/enquiries/{pid}/files",
                "/enquiries", f"/enquiries/{pid}/activity"):
        html = re.sub(r'<details class="tech">.*?</details>', " ", client.get(url).text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", html)  # what is on the screen; machine names only under "Details"
        assert not MACHINE_WORDS.search(text), (url, MACHINE_WORDS.search(text).group(0))
    assert "System voltage" in client.get(f"/enquiries/{pid}/check/values").text


def test_accept_all_shows_the_count_needs_a_confirmation_and_leaves_doubtful_values(
        client: TestClient) -> None:
    pid = new_enquiry(client, [("specification.pdf", SPEC), ("requirements.docx", LETTER),
                               ("schematic.dxf", DXF)])
    with client.app.state.sessions() as session:
        project = session.get(Project, pid)
        expected = {v.id for v in enquiry.bulk_acceptable(enquiry.review_groups(project))}
        found = enquiry.decisions(project)
        conflicted = {v.id for g in found.conflicts for side in g["sides"] for v in side}
    assert expected and conflicted
    page = client.get(f"/enquiries/{pid}/check/accept-all").text
    assert f"Approve {len(expected)} values" in page or f"{len(expected)} values" in page
    client.post(f"/enquiries/{pid}/check/accept-all")  # without the confirmation nothing is approved
    assert count(client, ExtractedValueRow, project_id=pid, review_status="approved") == 0
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    with client.app.state.sessions() as session:
        approved = list(session.scalars(select(ExtractedValueRow).where(
            ExtractedValueRow.project_id == pid, ExtractedValueRow.review_status == "approved")))
    assert {v.id for v in approved} == expected and not expected & conflicted
    assert all(v.confidence == "high" and v.method != "ocr" and v.quote_match != "words_on_page"
               for v in approved)
    approvals = [e for e in actions(client, pid) if e.action == "approve"]
    assert sorted(int(e.entity_id) for e in approvals) == sorted(expected)  # one audit entry per value
    assert all(e.actor for e in approvals)  # each with the actor
    summary = [e for e in actions(client, pid) if e.action == "approve_agreed"]
    assert len(summary) == 1 and summary[0].detail["approved"] == len(expected)


def test_the_quote_rebuilds_after_every_decision(client: TestClient) -> None:
    pid = new_enquiry(client, [("specification.pdf", SPEC), ("requirements.docx", LETTER),
                               ("schematic.dxf", DXF)])
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    with client.app.state.sessions() as session:
        first = services.latest_estimate(session, pid)
        assert first is not None
        open_value = session.scalars(select(ExtractedValueRow).where(
            ExtractedValueRow.project_id == pid, ExtractedValueRow.review_status == "extracted",
            ExtractedValueRow.value.is_not(None))).first()
    client.post(f"/values/{open_value.id}/approve")
    with client.app.state.sessions() as session:
        latest = services.latest_estimate(session, pid)
        assert latest.id != first.id
        assert not enquiry.quote_out_of_date(session, pid, latest)
    page = client.get(f"/enquiries/{pid}/quote").text
    assert "out of date" not in page.lower()
    assert count(client, Estimate, project_id=pid) >= 2


# --- the sample enquiry ---------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fake_recordings(tmp_path_factory) -> Path:
    """A fake recording (made here, labelled fake) for the showcase specification's exact bytes."""
    out = tmp_path_factory.mktemp("recorded")
    script = oracle_script(load_answers(SHOWCASE / "answers.json"), DocumentKind.SPECIFICATION)
    record_file("showcase", "SHOWCASE", "specification.pdf", SPEC, ScriptedProvider(script), out, fake=True)
    return out


def _sample(client: TestClient) -> int:
    response = client.post("/enquiries/sample", follow_redirects=False)
    assert response.status_code == 303
    return int(response.headers["location"].split("/")[2])


def test_the_sample_uses_a_recording_whose_hash_matches_and_says_so(tmp_path: Path, fake_recordings: Path) -> None:
    with make_client(tmp_path, recorded_dir=fake_recordings) as c:  # MODEL_MODE stays "rules"
        pid = _sample(c)
        with c.app.state.sessions() as session:
            project = session.get(Project, pid)
            assert project.is_sample and project.name.startswith("Sample enquiry")
            docs = {d.original_name: d for d in project.documents}
        assert set(docs) == {Path(n).name for n in SAMPLE_FILES}
        assert "(fake test recording)" in docs["specification.pdf"].model_run
        assert docs["requirements.docx"].model_run is None  # no recording for these bytes
        page = c.get(f"/enquiries/{pid}/check").text
        assert f"Read with rules + {FAKE_MODEL} (recorded " in page
        # A normal upload of the very same file follows MODEL_MODE (rules): no recording.
        other = new_enquiry(c, [("specification.pdf", SPEC)])
        with c.app.state.sessions() as session:
            doc = session.scalars(select(Document).where(Document.project_id == other)).one()
            assert doc.model_run is None
        assert "<span>Read with rules</span>" in c.get(f"/enquiries/{other}/check").text


def test_the_sample_without_a_matching_recording_is_read_by_the_rules(tmp_path: Path,
                                                                     fake_recordings: Path) -> None:
    sample = tmp_path / "sample"
    for name in SAMPLE_FILES:
        (sample / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SHOWCASE / name, sample / name)
    (sample / "specification.pdf").write_bytes(SPEC + b"\n% one changed byte\n")  # another SHA-256
    with make_client(tmp_path, recorded_dir=fake_recordings, sample_dir=sample) as c:
        pid = _sample(c)
        with c.app.state.sessions() as session:
            spec = session.scalars(select(Document).where(Document.project_id == pid,
                                                          Document.original_name == "specification.pdf")).one()
            assert spec.status == "done" and spec.model_run is None
            assert "No recorded model run matches" in spec.note
        page = c.get(f"/enquiries/{pid}/check").text
        assert "<span>Read with rules</span>" in page and "(recorded " not in page


def test_the_enquiries_list_offers_the_sample_when_empty(client: TestClient) -> None:
    page = client.get("/enquiries").text
    assert "Try the sample enquiry" in page and 'action="/enquiries/sample"' in page
    pid = new_enquiry(client, [("specification.pdf", SPEC)])
    page = client.get("/enquiries").text
    assert "Board A" in page and "Needs you (" in page and f"/enquiries/{pid}" in page
