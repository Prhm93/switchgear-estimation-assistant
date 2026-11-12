"""The simple flow (stage-simple): Add files, then one Review card at a time, then Make quote.

At most four buttons are visible on the flow's screens: Add files, Approve and Change on a card, Make quote,
and Ask (disabled until the question box exists). Everything else sits behind one small "More" link.
Background reading runs inside the request in the test client, so the files are read when the redirect lands.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AuditEvent, Document, ExtractedValueRow
from data_generator.sets import DATA

SHOWCASE = DATA / "projects" / "showcase"
FILES = [("specification.pdf", (SHOWCASE / "specification.pdf").read_bytes()),
         ("requirements.docx", (SHOWCASE / "requirements.docx").read_bytes()),
         ("schematic.dxf", (SHOWCASE / "drawing" / "schematic.dxf").read_bytes())]
HX = {"HX-Request": "true", "HX-Target": "review-body"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="off")
    with TestClient(create_app(settings)) as c:
        yield c


def add_files(client: TestClient) -> int:
    response = client.post("/enquiries", data={"next": "review"}, files=[("files", f) for f in FILES],
                           follow_redirects=False)
    assert response.status_code == 303
    match = re.fullmatch(r"/enquiries/(\d+)/review", response.headers["location"])
    assert match, response.headers["location"]
    return int(match.group(1))


def without_more(html: str) -> str:
    """The page as first seen: the More menu and closed forms (Change) left out."""
    html = re.sub(r'<details class="more[^"]*".*?</details>', "", html, flags=re.S)
    return re.sub(r'(<details class="change"[^>]*>\s*<summary[^>]*>.*?</summary>).*?</details>', r"\1</details>",
                  html, flags=re.S)


def visible_buttons(html: str) -> list[str]:
    """Labels of every button-looking control: <button>, .btn links and labels, and a .btn summary."""
    main = re.search(r"<main.*?</main>", without_more(html), re.S).group(0)
    found = re.findall(r"<button[^>]*>(.*?)</button>", main, re.S)
    found += re.findall(r'<(?:a|label|summary)[^>]*class="[^"]*\bbtn\b[^"]*"[^>]*>(.*?)</(?:a|label|summary)>', main, re.S)
    return [re.sub(r"<[^>]+>", "", b).strip() for b in found]


def progress(html: str) -> tuple[int, int]:
    m = re.search(r"(\d+) of (\d+) checked", html)
    assert m, "no progress line"
    return int(m.group(1)), int(m.group(2))


def card_form(html: str, action: str) -> dict[str, str]:
    form = re.search(rf'<form[^>]*action="([^"]*/review/{action})"[^>]*>(.*?)</form>', html, re.S)
    assert form, f"no {action} form"
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', form.group(2)))
    return {"url": form.group(1), **fields}


# --- home -------------------------------------------------------------------------------------------------

def test_home_has_one_big_add_files_button_and_the_rest_behind_more(client: TestClient) -> None:
    html = client.get("/").text
    hero = re.search(r'<section class="hero".*?</section>', html, re.S).group(0)
    assert visible_buttons(f"<main>{hero}</main>") == ["Add files"]
    form = re.search(r'<form[^>]*action="/enquiries"[^>]*>(.*?)</form>', hero, re.S)
    assert form and 'enctype="multipart/form-data"' in form.group(0) and "data-autosubmit" in form.group(0)
    assert 'name="next" value="review"' in form.group(1) and 'type="file"' in form.group(1)
    more = re.search(r'<details class="more[^"]*".*?</details>', html, re.S).group(0)
    assert 'href="/enquiries"' in more and 'href="/enquiries/new"' in more and 'action="/enquiries/sample"' in more


# --- review -----------------------------------------------------------------------------------------------

def test_upload_opens_review_with_one_card_progress_and_at_most_four_buttons(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    done, total = progress(html)
    assert done == 0 and total > 10
    assert html.count('<article class="review-card"') == 1
    buttons = visible_buttons(html)
    assert len(buttons) <= 4 and {"Approve", "Change", "Ask"} <= set(buttons), buttons
    assert "Make quote" not in buttons  # only when every card is checked
    ask = re.search(r"<button[^>]*>\s*Ask\s*</button>", html).group(0)
    assert "disabled" in ask and "Coming soon" in html
    # plain words: what a value is, and what the boxes mean
    assert "A value is one fact read from your files" in html
    assert "Boxes show where each value was read." in html
    more = re.search(r'<details class="more[^"]*".*?</details>', html, re.S).group(0)
    for href in (f"/enquiries/{pid}", f"/enquiries/{pid}/check", f"/enquiries/{pid}/files",
                 f"/enquiries/{pid}/proof", f"/enquiries/{pid}/activity", f"/enquiries/{pid}/quote"):
        assert f'href="{href}"' in more, href


def test_approve_checks_one_card_and_shows_the_next(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    form = card_form(html, "approve")
    after = client.post(form["url"], data=form, headers=HX).text
    assert progress(after)[0] == 1 and card_form(after, "approve")["field"] != form["field"]
    with client.app.state.sessions() as session:
        rows = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid,
                                                               ExtractedValueRow.field == form["field"])).all()
        assert any(r.review_status == "approved" for r in rows)
        assert session.scalars(select(AuditEvent).where(AuditEvent.project_id == pid,
                                                        AuditEvent.action == "approve")).first() is not None


def test_change_approves_the_typed_value(client: TestClient) -> None:
    pid = add_files(client)
    form = card_form(client.get(f"/enquiries/{pid}/review").text, "change")
    client.post(form["url"], data={**form, "value": "123", "unit": "A"}, headers=HX)
    with client.app.state.sessions() as session:
        rows = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid,
                                                               ExtractedValueRow.field == form["field"])).all()
    edited = [r for r in rows if r.review_status == "edited"]
    assert len(edited) == 1 and edited[0].approved_value == 123


def test_the_planted_disagreement_shows_both_files_on_its_card(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    assert card_form(html, "approve")["field"] == "way.Q2.rating"  # disagreements come first
    assert re.search(r"The specification says \d+ A; the drawing says \d+ A", html)


def test_when_all_are_checked_make_quote_leads_to_a_short_quote(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    for _ in range(200):
        if "Make quote" in html:
            break
        form = card_form(html, "approve") if "/review/approve" in html else None
        if form is None:  # a card with no value to approve (TBC): type one
            form = card_form(html, "change")
            html = client.post(form["url"], data={**form, "value": "1"}, headers=HX).text
        else:
            html = client.post(form["url"], data=form, headers=HX).text
    html = client.get(f"/enquiries/{pid}/review").text
    done, total = progress(html)
    assert done == total
    assert sorted(visible_buttons(html)) == ["Ask", "Make quote"]
    quote = client.post(f"/enquiries/{pid}/review/quote", follow_redirects=True)
    assert quote.status_code == 200 and quote.url.path == f"/enquiries/{pid}/draft-quote"
    page = quote.text
    heads = re.findall(r'<th scope="col"[^>]*>(.*?)</th>', page)
    assert heads == ["Part", "Description", "Qty", "Line total"]
    assert "Draft total" in page and re.search(r"GBP [\d,]+\.\d\d", page)
    assert f'href="/enquiries/{pid}/quote"' in page and "Show workings" in page
    assert len(visible_buttons(page)) <= 1  # Ask only


def test_review_says_it_is_reading_while_files_are_read(client: TestClient) -> None:
    pid = add_files(client)
    with client.app.state.sessions() as session:
        for d in session.scalars(select(Document).where(Document.project_id == pid)):
            d.status = "reading"
        session.commit()
    html = client.get(f"/enquiries/{pid}/review").text
    assert "Reading your files" in html and 'hx-trigger="every 1s"' in html
    assert "/review/approve" not in html


def test_a_new_enquiry_with_no_files_still_opens_files(client: TestClient) -> None:
    response = client.post("/enquiries", data={"note": "Two panels"}, follow_redirects=False)
    assert re.fullmatch(r"/enquiries/\d+/files", response.headers["location"])
