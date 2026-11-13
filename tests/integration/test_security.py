"""Stage 8: hostile input in every field the engineer types or uploads is stored as data and shown escaped.

Covers the enquiry name and note, a file's name, a typed value and unit, a rejection reason and a rename; SQL
text in those fields; a path in a file name; and wrong-type, oversized and empty uploads through the web form.
(Document text with HTML is covered by test_web_flow; the question box by test_ask.)
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app import services
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AuditEvent, Document, ExtractedValueRow, Project
from data_generator.sets import DATA

SPEC = DATA / "projects" / "showcase" / "specification.pdf"
XSS = '<script>alert("x")</script><img src=x onerror=alert(1)>'
SQL = "x'); DROP TABLE projects; --"
HTML_PAGES = ("", "/files", "/check", "/check/values", "/review", "/activity", "/quote")


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="off",
                        max_upload_mb=1)
    with TestClient(create_app(settings)) as c:
        yield c


def raw_markup(html: str) -> list[str]:
    return [m for m in ("<script>alert", "<img src=x", "onerror=alert(1)>") if m in html]


def new(client: TestClient, name: str, note: str = "", files=None) -> int:
    response = client.post("/enquiries", data={"name": name, "note": note}, files=files or [], follow_redirects=False)
    assert response.status_code == 303, response.text[:300]
    return int(response.headers["location"].split("/")[2])


def test_script_in_name_note_file_name_value_and_reason_is_escaped_everywhere(client: TestClient) -> None:
    pid = new(client, XSS, XSS, [("files", (f"{XSS}.pdf", SPEC.read_bytes()))])
    with client.app.state.sessions() as session:
        assert session.get(Project, pid).name == XSS  # stored exactly as typed
        doc = session.scalars(select(Document).where(Document.project_id == pid)).one()
        # the name is cut to its last part (after any "/"), kept only as data, and never used as a path
        assert doc.original_name.endswith("onerror=alert(1)>.pdf") and "/" not in doc.original_name
        assert re.fullmatch(r"[0-9a-f]{32}\.pdf", doc.storage_key)
        rows = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid)).all()
        services.review_value(session, rows[0].id, "edit", "999", XSS, reason=XSS)
        services.review_value(session, rows[1].id, "reject", reason=XSS)
    for page in ("/enquiries", *(f"/enquiries/{pid}{p}" for p in HTML_PAGES)):
        html = client.get(page).text
        assert raw_markup(html) == [], page
    assert "&lt;script&gt;" in client.get(f"/enquiries/{pid}/activity").text


def test_rename_with_markup_is_escaped(client: TestClient) -> None:
    pid = new(client, "Plain")
    client.post(f"/enquiries/{pid}/rename", data={"name": XSS})
    assert raw_markup(client.get("/enquiries").text) == []
    assert raw_markup(client.get(f"/enquiries/{pid}").text) == []


def test_sql_text_is_stored_as_data_and_every_table_is_still_there(client: TestClient) -> None:
    pid = new(client, SQL, SQL, [("files", (f"{SQL}.pdf", SPEC.read_bytes()))])
    client.post(f"/enquiries/{pid}/rename", data={"name": SQL + " 2"})
    with client.app.state.sessions() as session:
        assert session.get(Project, pid).name == SQL + " 2"
        assert session.scalar(select(func.count()).select_from(Project)) == 1
        assert session.scalar(select(func.count()).select_from(AuditEvent)) > 0
    assert client.get("/enquiries").status_code == 200 and SQL.replace("'", "&#39;") in client.get("/enquiries").text


def test_a_path_in_a_file_name_never_reaches_the_storage_folder(client: TestClient, tmp_path: Path) -> None:
    pid = new(client, "Paths", files=[("files", ("../../../evil.pdf", SPEC.read_bytes())),
                                      ("files", ("..\\..\\evil2.pdf", SPEC.read_bytes()))])
    storage = tmp_path / "storage"
    assert not any(p.name.startswith("evil") for p in tmp_path.parent.rglob("evil*.pdf"))
    assert all(re.fullmatch(r"[0-9a-f]{32}\.pdf", p.name) for p in storage.rglob("*") if p.is_file())
    with client.app.state.sessions() as session:
        names = {d.original_name for d in session.scalars(select(Document).where(Document.project_id == pid))}
    assert names == {"evil.pdf", "evil2.pdf"}  # the path is dropped; the name is kept only as data


@pytest.mark.parametrize("name, data, why", [
    ("tool.exe", b"MZ\x90\x00", "not accepted"),
    ("fake.pdf", b"PK\x03\x04 not a pdf", "does not match"),
    ("empty.pdf", b"", "empty"),
    ("big.pdf", b"%PDF-1.4\n" + b"0" * 1_100_000, "limit"),
])
def test_wrong_type_empty_and_oversized_uploads_are_refused_with_a_reason(client: TestClient, name, data, why) -> None:
    pid = new(client, "Uploads")
    response = client.post(f"/enquiries/{pid}/documents", files=[("files", (name, data))])
    assert why in response.text
    with client.app.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Document).where(Document.project_id == pid)) == 0


def test_every_decision_on_a_value_is_in_the_audit_log_with_its_actor(client: TestClient) -> None:
    pid = new(client, "Audit", files=[("files", ("spec.pdf", SPEC.read_bytes()))])
    with client.app.state.sessions() as session:
        rows = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid)
                               .order_by(ExtractedValueRow.id)).all()[:3]
        services.review_value(session, rows[0].id, "approve", actor="engineer-a")
        services.review_value(session, rows[1].id, "edit", "999", "A", reason="typed", actor="engineer-b")
        services.review_value(session, rows[2].id, "reject", reason="not this one", actor="engineer-c")
        events = {e.entity_id: e for e in session.scalars(select(AuditEvent).where(
            AuditEvent.project_id == pid, AuditEvent.entity == "extracted_value"))}
    assert [(events[str(r.id)].action, events[str(r.id)].actor) for r in rows] == [
        ("approve", "engineer-a"), ("edit", "engineer-b"), ("reject", "engineer-c")]
    assert events[str(rows[1].id)].detail["field"] == rows[1].field


@pytest.fixture(scope="module")
def injected_spec(tmp_path_factory) -> bytes:
    """Test project T08: its specification hides a white 1 pt instruction line in the general notes."""
    from data_generator import sets
    from data_generator.project import build_project

    job = sets.testset_jobs(tmp_path_factory.mktemp("t08"))[7]
    build_project(job.item_id, job.seed, job.purpose, job.out, list(job.plan), dpi=60.0)
    return (job.out / "specification.pdf").read_bytes()


def test_a_hidden_instruction_in_a_pdf_reached_through_the_question_box_is_flagged_not_obeyed(
        client: TestClient, injected_spec: bytes) -> None:
    from backend.app.models import AskQuestion

    pid = new(client, "Injected", files=[("files", ("specification.pdf", injected_spec))])
    with client.app.state.sessions() as session:
        before = {v.id: v.review_status for v in session.get(Project, pid).values}
    html = client.post(f"/enquiries/{pid}/ask",
                       data={"question": "What does the note to automated review tools say about the estimate total?"}).text
    box = re.search(r'<aside class="ask".*?</aside>', html, re.S).group(0)
    assert "ignore all previous instructions" in box  # shown as data, with its source
    assert "looks like an instruction" in box and "was not followed" in box
    with client.app.state.sessions() as session:
        assert {v.id: v.review_status for v in session.get(Project, pid).values} == before  # nothing approved
        assert session.scalars(select(AskQuestion)).one().numbers["flagged_instruction"] is True
