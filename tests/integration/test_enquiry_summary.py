"""V4 of the visual pass: the start page, the enquiry Summary page and the plain-language fixes.

- Start: "Drop the customer's files, or describe it"; files, a typed note, or both may start an enquiry.
  A note alone is saved (table enquiry_notes, migration 0006) and the enquiry opens on Files with a
  prompt to add the files.
- Summary (/enquiries/<id>): six tiles worked out from the enquiry, and an Ask column that is a quiet
  empty state until the Ask panel is built (UX-3): no input, no sample replies.
- Check: the views are "To check" and "Parts list", with one line saying what a value is. Quote: a plain
  line when nothing is approved yet.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import enquiry
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app import services
from backend.app.models import AuditEvent, Document, EnquiryNote, Project
from data_generator.sets import DATA

SHOWCASE = DATA / "projects" / "showcase"
FILES = [("specification.pdf", (SHOWCASE / "specification.pdf").read_bytes()),
         ("requirements.docx", (SHOWCASE / "requirements.docx").read_bytes()),
         ("schematic.dxf", (SHOWCASE / "drawing" / "schematic.dxf").read_bytes())]
VALUE_LINE = "A value is one fact read from your files. Approve it and it can be priced."
QUOTE_EMPTY = "Nothing is approved yet. Go to Check and approve values."


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="off")
    with TestClient(create_app(settings)) as c:
        yield c


def text_of(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def created_id(response) -> int:
    return int(re.match(r"^/enquiries/(\d+)/", response.headers["location"]).group(1))


def with_files(client: TestClient) -> int:
    response = client.post("/enquiries", data={"name": "Summary"}, files=[("files", f) for f in FILES],
                           follow_redirects=False)
    return created_id(response)


# --- start page ------------------------------------------------------------------------------------------

def test_the_start_page_takes_files_or_a_typed_note(client: TestClient) -> None:
    html = client.get("/enquiries/new").text
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S).group(1)
    assert text_of(h1) == "Drop the customer's files, or describe it" and 'class="accent"' in h1
    form = re.search(r'<form class="start-form".*?</form>', html, re.S).group(0)
    assert 'action="/enquiries"' in form and 'enctype="multipart/form-data"' in form
    assert 'type="file" name="files" multiple' in form
    assert re.search(r'<textarea[^>]+name="note"', form) and "Or describe the enquiry in a sentence" in form
    assert 'name="name"' in form  # the optional name stays
    assert re.search(r'<button class="btn btn--primary[^"]*" type="submit">\s*Start', form)
    chips = re.search(r'<div class="start-chips".*?</div>', html, re.S).group(0)
    assert 'action="/enquiries/sample"' in chips and 'href="/enquiries"' in chips


def test_the_start_page_drawing_is_a_quiet_watermark_with_its_own_ids(client: TestClient) -> None:
    html = client.get("/enquiries/new").text
    mark = re.search(r'<div class="watermark" aria-hidden="true">.*?</svg>', html, re.S).group(0)
    assert 'id="start-bk-title"' in mark
    ids = Counter(re.findall(r'\sid="([^"]+)"', html))
    assert not [i for i, n in ids.items() if n > 1]


def test_a_typed_note_alone_starts_an_enquiry_and_opens_files_with_a_prompt(client: TestClient) -> None:
    note = "Main switchboard, 1250 A incomer, four outgoing ways, form 4b. Drawing to follow."
    response = client.post("/enquiries", data={"note": note}, follow_redirects=False)
    assert response.status_code == 303
    pid = created_id(response)
    assert response.headers["location"] == f"/enquiries/{pid}/files"
    page = client.get(response.headers["location"]).text
    assert note in page and "Add the customer's files to read this enquiry." in page
    with client.app.state.sessions() as session:
        rows = session.scalars(select(EnquiryNote).where(EnquiryNote.project_id == pid)).all()
        assert [r.text for r in rows] == [note]
        assert session.scalar(select(AuditEvent).where(AuditEvent.project_id == pid,
                                                       AuditEvent.action == "note")) is not None


def test_a_note_with_files_is_kept_too(client: TestClient) -> None:
    response = client.post("/enquiries", data={"note": "Urgent, quote by Friday."},
                           files=[("files", FILES[0])], follow_redirects=False)
    pid = created_id(response)
    with client.app.state.sessions() as session:
        assert [n.text for n in session.get(Project, pid).notes] == ["Urgent, quote by Friday."]


def test_white_space_is_not_a_note(client: TestClient) -> None:
    pid = created_id(client.post("/enquiries", data={"note": "   \n "}, follow_redirects=False))
    with client.app.state.sessions() as session:
        assert session.get(Project, pid).notes == []


# --- summary page ----------------------------------------------------------------------------------------

def test_an_enquiry_without_files_opens_on_files(client: TestClient) -> None:
    pid = created_id(client.post("/enquiries", data={"note": "Board for site B."}, follow_redirects=False))
    response = client.get(f"/enquiries/{pid}", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"/enquiries/{pid}/files"


def test_the_summary_has_six_tiles_and_a_quiet_ask_column(client: TestClient) -> None:
    pid = with_files(client)
    response = client.get(f"/enquiries/{pid}", follow_redirects=False)
    assert response.status_code == 200
    html = response.text
    tiles = re.findall(r'<a class="tile[^"]*" href="([^"]+)"[^>]*>\s*<span class="tile__label">([^<]+)</span>', html)
    assert [label for _, label in tiles] == ["What is quoted", "Parts found", "Drawing attached",
                                              "Do they agree?", "Estimated cost", "Required, not found"]
    # Changed on purpose (brief, step 7): a tile opens its detail below, kept in the address.
    assert [href for href, _ in tiles] == [f"/enquiries/{pid}?tile={k}" for k in
                                           ("quoted", "parts", "drawing", "agree", "cost", "missing")]
    assert "Waiting for approvals" in html  # nothing approved yet
    assert "From the app&#39;s list of required fields, not from the specification." in html
    ask = re.search(r'<aside class="ask".*?</aside>', html, re.S).group(0)
    assert "Nothing asked yet." in ask
    # Changed on purpose (Stage 9): the quiet column became the question box: one input, one button.
    assert len(re.findall(r"<input", ask)) == 1 and len(re.findall(r"<button", ask)) == 1


def test_the_steps_start_with_the_summary(client: TestClient) -> None:
    pid = with_files(client)
    steps = re.search(r'<nav id="steps".*?</nav>', client.get(f"/enquiries/{pid}/check").text, re.S).group(0)
    labels = [text_of(a) for a in re.findall(r"<a class=\"step[^>]*>(.*?)</a>", steps, re.S)]
    assert labels[0] == "Summary" and [re.sub(r"\s*\d+$", "", s) for s in labels[1:]] == ["1 Files", "2 Check", "3 Quote"]
    summary = client.get(f"/enquiries/{pid}").text
    assert re.search(rf'<a class="step" href="/enquiries/{pid}" aria-current="page"', summary)


# --- plain-language fixes --------------------------------------------------------------------------------

def test_check_views_are_to_check_and_parts_list_with_one_line_on_values(client: TestClient) -> None:
    pid = with_files(client)
    html = client.get(f"/enquiries/{pid}/check").text
    nav = re.search(r'<nav id="views".*?</nav>', html, re.S).group(0)
    names = [re.sub(r"\s*\d+$", "", text_of(a)) for a in re.findall(r'<a class="view-btn.*?</a>', nav, re.S)]
    assert names == ["To check", "Parts list", "Report"]
    assert "Decisions" not in nav and "Items" not in nav
    after = html[html.index('<nav id="views"'):]
    assert re.search(r'</nav>\s*<p class="value-note[^"]*">' + re.escape(VALUE_LINE) + "</p>", after)


def test_quote_says_go_to_check_while_nothing_is_approved(client: TestClient) -> None:
    pid = with_files(client)
    html = client.get(f"/enquiries/{pid}/quote").text
    assert QUOTE_EMPTY in text_of(html)
    assert f'href="/enquiries/{pid}/check"' in html


# --- one count, one definition ---------------------------------------------------------------------------

def test_check_counts_decisions_only_and_shows_the_accept_all_line_apart(client: TestClient) -> None:
    pid = with_files(client)
    html = client.get(f"/enquiries/{pid}/check").text
    with client.app.state.sessions() as session:
        found = enquiry.decisions(session.get(Project, pid))
        assert found.acceptable, "the showcase must have agreeing values for this test"
        expected = len(found.conflicts) + sum(len(v) for v in found.reasons.values())
    nav = re.search(r'<nav id="views".*?</nav>', html, re.S).group(0)
    assert re.search(rf">\s*To check\s*<span class=\"view-btn__count mono\">{expected}</span>", nav)
    steps = re.search(r'<nav id="steps".*?</nav>', html, re.S).group(0)
    assert f'aria-label="{expected} waiting for you">{expected}</span>' in steps
    decisions = re.search(r'<section class="section-block" aria-label="Decisions">.*?</section>', html, re.S)
    accept = re.search(r'<section class="accept-block" aria-labelledby="accept-title">.*?</section>', html, re.S)
    assert accept and f"Accept all {len(found.acceptable)} agreeing values" in accept.group(0)
    assert "Accept all" not in (decisions.group(0) if decisions else "")
    assert "Not counted as decisions" in accept.group(0)


def test_summary_and_check_use_one_definition_of_disagree(client: TestClient) -> None:
    pid = with_files(client)
    check = client.get(f"/enquiries/{pid}/check").text
    shown_on_check = len(re.findall(r'<article class="decision decision--conflict"', check))
    with client.app.state.sessions() as session:
        assert enquiry.decisions(session.get(Project, pid)).disagree == shown_on_check
    summary = client.get(f"/enquiries/{pid}").text
    agree = re.search(r'data-tile="agree">.*?</a>', summary, re.S).group(0)
    if shown_on_check:
        assert f"Not yet: {shown_on_check} disagree" in agree
    else:
        assert ">Yes<" in agree


# --- the tile detail panel and the buttons (brief, steps 6 and 7) ----------------------------------------

KEYS = ("quoted", "parts", "drawing", "agree", "cost", "missing")


def detail(html: str) -> re.Match:
    return re.search(r'<section id="tile-detail" class="tile-detail" data-open="(\w+)"[^>]*>(.*?)</section>', html, re.S)


def test_a_tile_opens_its_detail_below_and_keeps_it_in_the_address(client: TestClient) -> None:
    pid = with_files(client)
    html = client.get(f"/enquiries/{pid}").text
    assert detail(html).group(1) == "agree"  # the agreement opens first
    for key in KEYS:
        tag = re.search(rf'<a class="tile[^"]*"[^>]*data-tile="{key}">', html).group(0)
        assert f'hx-get="/enquiries/{pid}/tiles/{key}"' in tag and f'hx-push-url="/enquiries/{pid}?tile={key}"' in tag
        assert ('aria-current="true"' in tag) == (key == "agree")
    page = client.get(f"/enquiries/{pid}?tile=parts").text
    assert detail(page).group(1) == "parts"
    assert re.search(r'<a class="tile[^"]*"[^>]*aria-current="true"[^>]*data-tile="parts">', page)
    part = client.get(f"/enquiries/{pid}/tiles/parts", headers={"HX-Request": "true"}).text
    assert "<html" not in part and 'id="summary-report"' in part and detail(part).group(1) == "parts"
    assert client.get(f"/enquiries/{pid}/tiles/nothing").status_code == 404
    assert detail(client.get(f"/enquiries/{pid}?tile=nothing").text).group(1) == "agree"


def test_every_tile_detail_shows_real_rows(client: TestClient) -> None:
    pid = with_files(client)
    with client.app.state.sessions() as session:
        project = session.get(Project, pid)
        found = enquiry.decisions(project)
        first_way = next(f for f in found.groups if f.startswith("way."))
    parts = detail(client.get(f"/enquiries/{pid}?tile=parts").text).group(2)
    assert f'href="/enquiries/{pid}/check?view=items"' in parts and "<li" in parts
    drawing = detail(client.get(f"/enquiries/{pid}?tile=drawing").text).group(2)
    assert "Drawing (CAD)" in drawing and "schematic.dxf" in drawing
    quoted = detail(client.get(f"/enquiries/{pid}?tile=quoted").text).group(2)
    assert "System voltage" in quoted and "Incomer rating" in quoted
    missing = detail(client.get(f"/enquiries/{pid}?tile=missing").text).group(2)
    assert "From the app&#39;s list of required fields, not from the specification." in missing
    cost = detail(client.get(f"/enquiries/{pid}?tile=cost").text).group(2)
    assert "Waiting for approvals" in cost and f'href="/enquiries/{pid}/check"' in cost
    assert first_way  # the showcase has outgoing ways


def test_conflicts_on_the_summary_use_the_existing_decision_action(client: TestClient) -> None:
    pid = with_files(client)
    with client.app.state.sessions() as session:
        conflicts = enquiry.decisions(session.get(Project, pid)).conflicts
        assert conflicts, "the showcase must have a planted conflict for this test"
        field, keep = conflicts[0]["field"], conflicts[0]["sides"][0][0].id
    agree = detail(client.get(f"/enquiries/{pid}").text).group(2)
    form = re.search(rf'<form method="post" action="/enquiries/{pid}/fields/use">.*?</form>', agree, re.S).group(0)
    assert 'name="back" value="summary"' in form and "Use this" in form
    response = client.post(f"/enquiries/{pid}/fields/use", data={"field": field, "value_id": keep, "back": "summary"},
                           follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == f"/enquiries/{pid}?tile=agree"
    with client.app.state.sessions() as session:
        assert field not in {g["field"] for g in enquiry.decisions(session.get(Project, pid)).conflicts}
    # Without "back" the action still returns to Check, as before.
    response = client.post(f"/enquiries/{pid}/fields/use", data={"field": field, "value_id": keep},
                           follow_redirects=False)
    assert response.headers["location"].startswith(f"/enquiries/{pid}/check")


def test_report_is_off_until_something_is_approved_and_the_other_buttons_open_existing_pages(client: TestClient) -> None:
    pid = with_files(client)
    html = client.get(f"/enquiries/{pid}").text
    bar = re.search(r'<nav class="summary__actions"[^>]*>.*?</nav>', html, re.S).group(0)
    assert re.search(r'<button class="btn[^"]*" type="button" disabled[^>]*>[^<]*(<svg.*?</svg>)?\s*Report', bar, re.S)
    assert "report.docx" not in bar
    assert f'href="/enquiries/{pid}/check"' in bar and "View all values" in bar
    with client.app.state.sessions() as session:
        drawing = session.scalars(select(Document).where(Document.project_id == pid,
                                                         Document.kind == "schematic")).first()
    assert f'href="/enquiries/{pid}/proof?doc={drawing.id}"' in bar and "View drawing" in bar
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    bar = re.search(r'<nav class="summary__actions"[^>]*>.*?</nav>', client.get(f"/enquiries/{pid}").text, re.S).group(0)
    assert f'href="/enquiries/{pid}/quote/report.docx"' in bar


def test_the_cost_tile_never_shows_a_price_built_from_unapproved_values(client: TestClient) -> None:
    pid = with_files(client)
    with client.app.state.sessions() as session:
        services.build_estimate(session, pid, client.app.state.settings)  # a quote exists, nothing approved
    tile = re.search(r'data-tile="cost">.*?</a>', client.get(f"/enquiries/{pid}").text, re.S).group(0)
    assert "Waiting for approvals" in tile and "GBP" not in tile
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    with client.app.state.sessions() as session:
        estimate = services.latest_estimate(session, pid)
        assert estimate.lines  # built from the approved values only (services.build_estimate)
        total = f"{estimate.currency} {estimate.total:,.2f}"
    tile = re.search(r'data-tile="cost">.*?</a>', client.get(f"/enquiries/{pid}").text, re.S).group(0)
    assert total in tile and "Draft, from" in tile
