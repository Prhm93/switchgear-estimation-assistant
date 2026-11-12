"""The simple flow (stage-simple): Add files, then one Review card at a time, then Make quote.

Review order: one card for the agreeing values ("Approve these N": the "Accept all" rule), one card per
real conflict (Approve or Change), then one card per file and page for the values read from a picture or
needing a closer look, each value ticked by default ("Approve N ticked"; un-ticking leaves it for later).
Every value keeps its own approved status and its own audit entry; nothing is approved without a click.

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
    m = re.search(r"(\d+) of (\d+) groups checked", html)
    assert m, "no progress line"
    return int(m.group(1)), int(m.group(2))


def card_form(html: str, action: str) -> dict[str, str]:
    form = re.search(rf'<form[^>]*action="([^"]*/review/{action})"[^>]*>(.*?)</form>', html, re.S)
    assert form, f"no {action} form"
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', form.group(2)))
    return {"url": form.group(1), **fields}


def form_lists(html: str, action: str) -> tuple[str, dict[str, list[str]]]:
    """A card form's address and every field with all its values (hidden lists and ticked boxes)."""
    form = re.search(rf'<form[^>]*action="([^"]*/review/{action})"[^>]*>(.*?)</form>', html, re.S)
    assert form, f"no {action} form"
    out: dict[str, list[str]] = {}
    for tag in re.findall(r"<input[^>]*>", form.group(2)):
        name, value = re.search(r'name="(\w+)"', tag), re.search(r'value="([^"]*)"', tag)
        if name and value and ('type="hidden"' in tag or ('type="checkbox"' in tag and " checked" in tag)):
            out.setdefault(name.group(1), []).append(value.group(1))
    return form.group(1), out


def statuses(client: TestClient, pid: int) -> dict[int, str]:
    with client.app.state.sessions() as session:
        return {r.id: r.review_status for r in session.scalars(
            select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid))}


def audited(client: TestClient, pid: int, action: str) -> list[int]:
    with client.app.state.sessions() as session:
        return [int(e.entity_id) for e in session.scalars(select(AuditEvent).where(
            AuditEvent.project_id == pid, AuditEvent.action == action))]


def finish(client: TestClient, pid: int) -> tuple[str, int]:
    """Press the one action of each card (Approve, Approve these N, Approve N ticked) until Make quote shows."""
    html, clicks = client.get(f"/enquiries/{pid}/review").text, 0
    while "Make quote" not in html and clicks < 100:
        action = next(a for a in ("agreeing", "approve", "group") if f"/review/{a}\"" in html)
        url, data = form_lists(html, action)
        html = client.post(url, data=data, headers=HX).text
        clicks += 1
    return client.get(f"/enquiries/{pid}/review").text, clicks


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

def test_review_opens_on_the_agreeing_values_and_approves_nothing_by_itself(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    done, total = progress(html)
    assert done == 0 and 2 <= total <= 8
    assert html.count('<article class="review-card') == 1
    count = int(re.search(r"(\d+) agreeing values", html).group(1))
    buttons = visible_buttons(html)
    assert f"Approve these {count}" in buttons and len(buttons) <= 4, buttons
    ask = re.search(r"<button[^>]*>\s*Ask\s*</button>", html).group(0)
    assert "disabled" in ask and "Coming soon" in html
    assert "A value is one fact read from your files" in html
    assert set(statuses(client, pid).values()) == {"extracted"}  # opening Review approves nothing
    more = re.search(r'<details class="more[^"]*".*?</details>', html, re.S).group(0)
    for href in (f"/enquiries/{pid}", f"/enquiries/{pid}/check", f"/enquiries/{pid}/files",
                 f"/enquiries/{pid}/proof", f"/enquiries/{pid}/activity", f"/enquiries/{pid}/quote"):
        assert f'href="{href}"' in more, href


def test_approve_these_n_approves_exactly_the_n_shown_each_with_its_own_audit_entry(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    count = int(re.search(r"Approve these (\d+)", html).group(1))
    url, data = form_lists(html, "agreeing")
    assert len(data["value_id"]) == count
    after = client.post(url, data=data, headers=HX).text
    approved = [i for i, s in statuses(client, pid).items() if s == "approved"]
    assert sorted(approved) == sorted(int(i) for i in data["value_id"])
    assert sorted(audited(client, pid, "approve")) == sorted(approved)  # one entry per value
    assert progress(after)[0] == 1
    with client.app.state.sessions() as session:
        for v in session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.id.in_(approved))):
            assert v.confidence == "high" and v.method not in ("ocr", "vision", "detector")
            assert v.quote_match != "words_on_page" and v.value is not None


def test_a_real_conflict_gets_its_own_card_with_approve_and_change(client: TestClient) -> None:
    pid = add_files(client)
    url, data = form_lists(client.get(f"/enquiries/{pid}/review").text, "agreeing")
    html = client.post(url, data=data, headers=HX).text
    assert card_form(html, "approve")["field"] == "way.Q2.rating"
    assert re.search(r"The specification says \d+ A; the drawing says \d+ A", html)
    assert "/review/change" in html
    form = card_form(html, "change")
    client.post(form["url"], data={**form, "value": "123", "unit": "A"}, headers=HX)
    with client.app.state.sessions() as session:
        rows = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid,
                                                               ExtractedValueRow.field == "way.Q2.rating")).all()
    edited = [r for r in rows if r.review_status == "edited"]
    assert len(edited) == 1 and edited[0].approved_value == 123


def test_showcase_from_upload_to_quote_in_ten_clicks_or_fewer(client: TestClient) -> None:
    pid = add_files(client)
    html, clicks = finish(client, pid)
    done, total = progress(html)
    assert done == total
    assert 1 + clicks + 1 <= 10, clicks  # Add files, the cards, Make quote
    assert sorted(visible_buttons(html)) == ["Ask", "Make quote"]
    quote = client.post(f"/enquiries/{pid}/review/quote", follow_redirects=True)
    assert quote.status_code == 200 and quote.url.path == f"/enquiries/{pid}/draft-quote"
    page = quote.text
    heads = re.findall(r'<th scope="col"[^>]*>(.*?)</th>', page)
    assert heads == ["Part", "Description", "Qty", "Line total"]
    assert "Draft total" in page and re.search(r"GBP [\d,]+\.\d\d", page)
    assert f'href="/enquiries/{pid}/quote"' in page and "Show workings" in page
    assert len(visible_buttons(page)) <= 1  # Ask only
    # every approved value has its own approve entry; nothing else was approved
    approved = sorted(i for i, s in statuses(client, pid).items() if s in ("approved", "edited"))
    assert sorted(set(audited(client, pid, "approve"))) == approved


def test_review_says_it_is_reading_while_files_are_read(client: TestClient) -> None:
    pid = add_files(client)
    with client.app.state.sessions() as session:
        for d in session.scalars(select(Document).where(Document.project_id == pid)):
            d.status = "reading"
        session.commit()
    html = client.get(f"/enquiries/{pid}/review").text
    assert "Reading your files" in html and 'hx-trigger="every 1s"' in html
    assert "/review/agreeing" not in html


def test_a_new_enquiry_with_no_files_still_opens_files(client: TestClient) -> None:
    response = client.post("/enquiries", data={"note": "Two panels"}, follow_redirects=False)
    assert re.fullmatch(r"/enquiries/\d+/files", response.headers["location"])
