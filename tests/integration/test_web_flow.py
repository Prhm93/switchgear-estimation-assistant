"""The showcase from upload to exported report, through the web screens, in rules mode.

Each test gets its own SQLite file database (migrated by the app on start-up,
as in Docker) and its own storage folder. Uploads run their background
processing inside the request, as FastAPI's TestClient does, so statuses are
final when the upload call returns. The PostgreSQL variant runs on the tests'
own database (the ``pg_url`` fixture), never on the app's.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections.abc import Iterator
from pathlib import Path

import docx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import services
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AuditEvent, Document, ExtractedValueRow, Match, Project
from backend.app.storage import KEY_PATTERN
from data_generator.project import load_answers
from data_generator.sets import DATA

SHOWCASE = DATA / "projects" / "showcase"
KEY = load_answers(SHOWCASE / "answers.json")
SHOWCASE_FILES = ["specification.pdf", "requirements.docx", "drawing/schematic.pdf",
                  "drawing/schematic_sheet1_scanned.png", "drawing/schematic.dxf"]
HTML = {"accept": "text/html"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    # The Stage 2 rules-mode flow: drawings without a text layer stay "not read yet" (no OCR).
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="off")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def sessions(client: TestClient):
    return client.app.state.sessions


def new_project(client: TestClient, name: str = "Showcase") -> int:
    response = client.post("/enquiries", data={"name": name, "reference": "ENQ-TEST"}, follow_redirects=False)
    assert response.status_code == 303
    return int(re.match(r"^/enquiries/(\d+)/files$", response.headers["location"]).group(1))


def upload(client: TestClient, project_id: int, files: list[tuple[str, bytes]], htmx: bool = False):
    headers = {"HX-Request": "true"} if htmx else {}
    return client.post(f"/enquiries/{project_id}/documents", headers=headers, follow_redirects=False,
                       files=[("files", (name, data)) for name, data in files])


def accept_all(client: TestClient, project_id: int):
    """ "Accept all" with its confirmation: approves the agreeing high-confidence values, then rebuilds the quote."""
    return client.post(f"/enquiries/{project_id}/check/accept-all", data={"confirm": "yes"}, follow_redirects=False)


def upload_showcase(client: TestClient, project_id: int) -> None:
    response = upload(client, project_id, [(Path(n).name, (SHOWCASE / n).read_bytes()) for n in SHOWCASE_FILES])
    assert response.status_code == 303


def values(client: TestClient, project_id: int, **where) -> list[ExtractedValueRow]:
    with sessions(client)() as session:
        rows = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == project_id))
        return [r for r in rows if all(getattr(r, k) == v for k, v in where.items())]


def audit_actions(client: TestClient, project_id: int) -> list[str]:
    with sessions(client)() as session:
        return [e.action for e in session.scalars(select(AuditEvent).where(AuditEvent.project_id == project_id))]


def latest(client: TestClient, project_id: int):
    with sessions(client)() as session:
        est = services.latest_estimate(session, project_id)
        return est, list(est.lines) if est else []


# --- the whole flow ---------------------------------------------------------------------------------

def test_showcase_upload_to_docx(client: TestClient) -> None:
    showcase_flow(client)


@pytest.mark.database
def test_showcase_upload_to_docx_on_postgres(tmp_path: Path, pg_url: str) -> None:
    """The same flow on PostgreSQL (Docker locally, the pgvector service in CI), in the tests' own database."""
    settings = Settings(database_url=pg_url, storage_dir=tmp_path / "storage", environment="test",
                        drawing_reading="off")
    with TestClient(create_app(settings)) as pg_client:
        showcase_flow(pg_client)


def showcase_flow(client: TestClient) -> None:
    pid = new_project(client)
    upload_showcase(client, pid)

    with sessions(client)() as session:
        docs = {d.original_name: d for d in session.scalars(select(Document).where(Document.project_id == pid))}
    assert {n: (d.kind, d.status) for n, d in docs.items()} == {
        "specification.pdf": ("specification", "done"),
        "requirements.docx": ("requirements", "done"),
        "schematic.pdf": ("schematic", "not_read"),  # no text layer: marked, not guessed
        "schematic_sheet1_scanned.png": ("schematic", "not_read"),
        "schematic.dxf": ("schematic", "done"),
    }
    # The hash is of the bytes exactly as uploaded.
    assert docs["specification.pdf"].sha256 == hashlib.sha256((SHOWCASE / "specification.pdf").read_bytes()).hexdigest()

    for screen in ("files", "proof", "check", "quote", "activity"):
        assert client.get(f"/enquiries/{pid}/{screen}", headers=HTML).status_code == 200
    with sessions(client)() as session:
        count = len(session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid)).all())
    listing = client.get("/enquiries").text
    assert "Showcase" in listing and "Needs you (" in listing
    check = client.get(f"/enquiries/{pid}/check").text
    assert count > 0 and re.search(r'>\s*To check\s*<span class="view-btn__count mono">\d+</span>', check)  # renamed in V4
    assert "The documents disagree" in check and "was not read" in check
    assert 'id="f-way.Q2.rating"' in check and 'class="link-accept"' in check  # the conflict waits; the rest in one step

    # Approve everything that agrees; the planted Q2 conflict (250 A spec, 200 A drawing) stays open.
    assert accept_all(client, pid).status_code == 303
    q2 = {v.source_document: v for v in values(client, pid, field="way.Q2.rating")}
    assert {d: v.review_status for d, v in q2.items()} == {"specification": "extracted", "schematic": "extracted"}

    est, lines = latest(client, pid)  # rebuilt by the accept step itself
    assert [p["field"] for p in est.problems] == ["way.Q2.rating"]  # the conflict blocks its line only
    assert len(lines) == len(KEY.estimate) - 1

    # Resolve it as an engineer would: reject the drawing value with a reason, approve the specification.
    client.post(f"/values/{q2['schematic'].id}/reject", data={"reason": "drawing superseded by spec rev B"})
    client.post(f"/values/{q2['specification'].id}/approve")
    est, lines = latest(client, pid)  # rebuilt after each decision
    assert not est.problems and not est.unmatched and not est.pending
    assert sorted((ln.code, float(ln.quantity)) for ln in lines) == sorted((e.code, e.quantity) for e in KEY.estimate)
    assert all(ln.value_ids for ln in lines)  # every line links to the approved values it came from

    page = client.get(f"/enquiries/{pid}/quote").text
    assert services.money(est.total) in page and "out of date" not in page

    response = client.get(f"/enquiries/{pid}/estimates/{est.id}/report.docx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    report = docx.Document(io.BytesIO(response.content))
    text = "\n".join([p.text for p in report.paragraphs]
                     + [c.text for t in report.tables for r in t.rows for c in r.cells])
    assert "Draft estimate" in text and "Showcase" in text
    assert services.money(est.total) in text
    for ln in lines:
        assert ln.code in text
    assert 'way.Q2.rating = 250 A (specification.pdf, page 5, "' in text  # the Q2 line keeps its source

    actions = audit_actions(client, pid)
    for action in ("upload", "extract", "approve", "approve_agreed", "reject", "estimate", "export"):
        assert action in actions, f"no {action} event in the audit log"
    assert actions.count("upload") == len(SHOWCASE_FILES)
    activity = client.get(f"/enquiries/{pid}/activity").text
    assert "Exported the report (DOCX)" in activity and "drawing superseded by spec rev B" in activity
    # Stage 6: the letter's medium values agree with the specification, so they rise to high and went with
    # "Accept all"; after the export nothing waits and the enquiry is "Quoted"
    assert "Quoted" in client.get("/enquiries").text


def test_nothing_approved_means_an_empty_estimate(client: TestClient) -> None:
    pid = new_project(client)
    upload_showcase(client, pid)
    est, lines = latest(client, pid)  # built when the files were read
    assert lines == [] and est.total == 0
    kinds = {p["field"]: p["kind"] for p in est.problems}
    assert kinds.pop("way.Q2.rating") == "conflict"  # the documents disagree; reported as such even unreviewed
    assert set(kinds.values()) == {"missing"}


def test_an_unapproved_value_cannot_reach_the_estimate(client: TestClient) -> None:
    pid = new_project(client)
    upload_showcase(client, pid)
    accept_all(client, pid)
    for v in values(client, pid, field="incomer.rating"):  # un-approve the incomer by rejecting it everywhere
        client.post(f"/values/{v.id}/reject", data={"reason": "test"})
    client.post(f"/enquiries/{pid}/quote")
    est, lines = latest(client, pid)
    assert all("incomer.rating" not in ln.basis for ln in lines)
    assert "incomer.rating" in {p["field"] for p in est.problems}
    rejected = {v.id for v in values(client, pid, field="incomer.rating")}
    assert not rejected & {i for ln in lines for i in ln.value_ids}


def test_a_substitute_is_priced_only_after_approval(client: TestClient) -> None:
    pid = new_project(client)
    upload_showcase(client, pid)
    accept_all(client, pid)
    q2 = {v.source_document: v for v in values(client, pid, field="way.Q2.rating")}
    client.post(f"/values/{q2['schematic'].id}/reject", data={"reason": "superseded"})
    client.post(f"/values/{q2['specification'].id}/approve")
    # The engineer types a rating the catalogue does not stock: the next size up is a substitute.
    q1 = values(client, pid, field="way.Q1.rating", source_document="specification")[0]
    for drawn in values(client, pid, field="way.Q1.rating", source_document="schematic"):
        client.post(f"/values/{drawn.id}/reject", data={"reason": "customer change"})
    asked = int(q1.value) - 5
    client.post(f"/values/{q1.id}/edit", data={"value": str(asked), "unit": "A", "reason": "customer change"})
    client.post(f"/enquiries/{pid}/quote")
    est, lines = latest(client, pid)
    assert [p["key"] for p in est.pending] == ["way.Q1"]
    reason = est.pending[0]["reason"]
    chosen = re.match(rf"^(\d+) A chosen, {asked} A requested: ", reason)
    assert chosen and asked < int(chosen.group(1)) <= int(q1.value)  # the next stocked size up
    assert all("way.Q1.rating" not in ln.basis for ln in lines)  # not priced yet
    page = client.get(f"/enquiries/{pid}/quote").text
    assert "Substitute, needs review" in page and reason in page

    response = client.post(f"/matches/{est.pending[0]['match_id']}/approve", follow_redirects=False)
    assert response.status_code == 303
    est, lines = latest(client, pid)
    assert not est.pending
    q1_lines = [ln for ln in lines if "way.Q1.rating" in ln.basis]
    assert len(q1_lines) == 1 and q1_lines[0].substitute_reasons == [reason]
    assert "substitute_approve" in audit_actions(client, pid)


def test_a_changed_requirement_needs_its_substitute_approved_again(client: TestClient) -> None:
    pid = new_project(client)
    upload_showcase(client, pid)
    accept_all(client, pid)
    q1 = values(client, pid, field="way.Q1.rating", source_document="specification")[0]
    for drawn in values(client, pid, field="way.Q1.rating", source_document="schematic"):
        client.post(f"/values/{drawn.id}/reject", data={"reason": "customer change"})
    client.post(f"/values/{q1.id}/edit", data={"value": str(int(q1.value) - 5), "unit": "A"})
    client.post(f"/enquiries/{pid}/quote")
    est, _ = latest(client, pid)
    client.post(f"/matches/{est.pending[0]['match_id']}/approve")
    client.post(f"/values/{q1.id}/edit", data={"value": str(int(q1.value) - 10), "unit": "A"})
    client.post(f"/enquiries/{pid}/quote")
    est, _ = latest(client, pid)
    assert [p["key"] for p in est.pending] == ["way.Q1"]
    with sessions(client)() as session:
        assert session.get(Match, est.pending[0]["match_id"]).review_status == "pending"


# --- review actions -----------------------------------------------------------------------------------

def test_review_actions_through_htmx_return_the_check_block(client: TestClient) -> None:
    pid = new_project(client)
    upload_showcase(client, pid)
    v = values(client, pid, field="system.voltage", source_document="specification")[0]
    response = client.post(f"/values/{v.id}/approve", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert '<div id="check-body"' in response.text and "<html" not in response.text
    assert 'id="steps"' in response.text and 'hx-swap-oob="true"' in response.text  # the tab count follows
    assert values(client, pid, id=v.id)[0].review_status == "approved"

    # A refused decision comes back in the proof panel with the reason, and nothing changes.
    response = client.post(f"/values/{v.id}/reject", headers={"HX-Request": "true"}, data={"reason": ""})
    assert "Give a reason for rejecting." in response.text and response.headers["HX-Retarget"] == "#panel"
    assert values(client, pid, id=v.id)[0].review_status == "approved"


def test_an_edit_keeps_the_extracted_value_and_its_source(client: TestClient) -> None:
    pid = new_project(client)
    upload_showcase(client, pid)
    v = values(client, pid, field="enclosure.ip_rating", source_document="specification")[0]
    client.post(f"/values/{v.id}/edit", data={"value": "IP55", "unit": "", "reason": "customer email"})
    row = values(client, pid, id=v.id)[0]
    assert (row.review_status, row.approved_value, row.value) == ("edited", "IP55", v.value)
    assert row.source_text == v.source_text and row.page == v.page


def test_new_enquiry_is_one_screen_and_the_name_is_optional(client: TestClient) -> None:
    form = client.get("/enquiries/new")
    assert form.status_code == 200 and 'name="name"' in form.text and 'name="files"' in form.text
    assert "stored but not read: drawing reading is off" in form.text  # said before the upload (here OCR is off)
    # No name, files in the same step: it is named from the specification's title and goes on to Check.
    spec = (SHOWCASE / "specification.pdf").read_bytes()
    response = client.post("/enquiries", data={"name": "  "}, files=[("files", ("specification.pdf", spec))],
                           follow_redirects=False)
    assert response.status_code == 303
    pid = int(re.match(r"^/enquiries/(\d+)/files\?go=1$", response.headers["location"]).group(1))
    forward = client.get(response.headers["location"], follow_redirects=False)
    assert forward.status_code == 303 and forward.headers["location"] == f"/enquiries/{pid}/check"
    with sessions(client)() as session:
        project = session.get(Project, pid)
        assert (project.name, project.reference) == ("Low-voltage main switchboard MSB-2", "ENQ-3192")
    # A typed name is kept, and markup in it is shown escaped.
    response = client.post("/enquiries", data={"name": "<b>Board</b>"}, follow_redirects=True)
    assert "&lt;b&gt;Board&lt;/b&gt;" in response.text and "<b>Board</b>" not in response.text


def test_the_file_lines_poll_while_reading_and_then_move_on_to_check(client: TestClient) -> None:
    pid = new_project(client)
    spec = (SHOWCASE / "specification.pdf").read_bytes()
    # Through HTMX the upload answers with the file lines: still queued, asking for themselves again.
    response = upload(client, pid, [("specification.pdf", spec)], htmx=True)
    assert response.status_code == 200 and f'hx-get="/enquiries/{pid}/documents?go=1"' in response.text
    assert "waiting to be read" in response.text
    # Reading has finished by now: the next poll sends the browser on to Check.
    poll = client.get(f"/enquiries/{pid}/documents?go=1", headers={"HX-Request": "true"})
    assert poll.status_code == 204 and poll.headers["HX-Redirect"] == f"/enquiries/{pid}/check"
    lines = client.get(f"/enquiries/{pid}/files").text
    assert "Specification · 8 pages · read" in lines and "hx-trigger" not in lines


# --- uploads ---------------------------------------------------------------------------------------

def test_a_path_in_the_filename_cannot_escape_storage(client: TestClient, tmp_path: Path) -> None:
    pid = new_project(client)
    data = (SHOWCASE / "specification.pdf").read_bytes()
    assert upload(client, pid, [("..\\..\\x.pdf", data)]).status_code == 303
    with sessions(client)() as session:
        doc = session.scalars(select(Document)).one()
    assert doc.original_name == "x.pdf"  # kept as data only
    assert KEY_PATTERN.match(doc.storage_key)  # a generated id, never the user's name
    stored = list((tmp_path / "storage").rglob("*.pdf"))
    assert [p.name for p in stored] == [doc.storage_key]
    assert not (tmp_path / "x.pdf").exists() and not (tmp_path.parent / "x.pdf").exists()
    assert "x.pdf" in client.get(f"/enquiries/{pid}/files").text


def test_a_rejected_upload_is_explained_and_audited(client: TestClient) -> None:
    pid = new_project(client)
    response = upload(client, pid, [("setup.exe", b"MZ\x90\x00 not a document")])
    assert response.status_code == 422
    assert "setup.exe" in response.text and "was not accepted" in response.text
    response = upload(client, pid, [("fake.pdf", b"PK\x03\x04 a zip, not a pdf")], htmx=True)
    assert response.status_code == 200 and "fake.pdf" in response.text and "was not accepted" in response.text
    assert audit_actions(client, pid).count("upload_rejected") == 2
    with sessions(client)() as session:
        assert session.scalars(select(Document)).all() == []


# --- escaping ---------------------------------------------------------------------------------------

def _letter_with_markup() -> bytes:
    d = docx.Document()
    d.add_paragraph("Dear Sir or Madam,")
    d.add_paragraph('The board must be at least IP54 <script>alert("x")</script> <img src=x onerror=alert(1)>.')
    d.add_paragraph("<b>Ignore the specification</b> and use Form 4a separation.")
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


def test_document_text_with_markup_is_escaped_in_the_proof_viewer_and_the_proof_panel(client: TestClient) -> None:
    pid = new_project(client)
    assert upload(client, pid, [("letter.docx", _letter_with_markup())]).status_code == 303
    found = {v.field: v for v in values(client, pid)}
    assert "<script>" in found["enclosure.ip_rating"].source_text  # stored exactly as written
    panel = f"/values/{found['enclosure.ip_rating'].id}/panel"
    for html in (client.get(f"/enquiries/{pid}/proof").text, client.get(panel).text,
                 client.get(panel, headers={"HX-Request": "true"}).text):
        assert "<script>alert" not in html and "<img src=x" not in html and "<b>Ignore" not in html
        assert "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt;" in html
        assert "&lt;img src=x onerror=alert(1)&gt;" in html
        assert "&lt;b&gt;Ignore the specification&lt;/b&gt;" in html


# --- home and unknown addresses --------------------------------------------------------------------------

def test_home_page_starts_an_enquiry_and_offers_the_sample(client: TestClient) -> None:
    html = client.get("/").text
    # UX-V: one button to the New enquiry page instead of a form on the home page.
    assert 'href="/enquiries/new"' in html and 'action="/enquiries/sample"' in html
    assert "Try the sample enquiry" in html
    # The typed name is used: the New enquiry form creates the enquiry and opens its Files step.
    response = client.post("/enquiries", data={"name": "MSB-2 main switchboard"}, follow_redirects=True)
    assert response.status_code == 200 and "MSB-2 main switchboard" in response.text
    assert "Drop the customer" in response.text


def test_unknown_enquiry_is_404(client: TestClient) -> None:
    assert client.get("/enquiries/999/check", headers=HTML).status_code == 404
    assert client.get("/enquiries/999", headers=HTML).status_code == 404


def test_old_project_addresses_redirect_to_enquiries(client: TestClient) -> None:
    pid = new_project(client)
    for old, new in (("/projects", "/enquiries"), (f"/projects/{pid}", f"/enquiries/{pid}"),
                     (f"/projects/{pid}/review", f"/enquiries/{pid}/check"),
                     (f"/projects/{pid}/upload", f"/enquiries/{pid}/files"),
                     (f"/projects/{pid}/analysis?doc=3", f"/enquiries/{pid}/proof?doc=3"),
                     (f"/projects/{pid}/estimate", f"/enquiries/{pid}/quote"),
                     (f"/projects/{pid}/audit", f"/enquiries/{pid}/activity")):
        response = client.get(old, follow_redirects=False)
        assert response.status_code == 308 and response.headers["location"] == new, old


# --- without a database --------------------------------------------------------------------------------

def test_screens_explain_a_missing_database(tmp_path: Path) -> None:
    settings = Settings(database_url=None, storage_dir=tmp_path / "storage", environment="test")
    with TestClient(create_app(settings)) as c:
        page = c.get("/enquiries", headers=HTML)
        assert page.status_code == 503 and "DATABASE_URL" in page.text and "System status" in page.text
        assert c.get("/enquiries").json() == {"detail": "The database is not configured (DATABASE_URL)."}
        assert c.get("/health").status_code == 200
        assert c.get("/").status_code == 200  # the home page needs no database
