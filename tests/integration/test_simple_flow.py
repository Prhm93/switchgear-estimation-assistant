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

from backend.app.confidence import assess
from backend.app.config import Settings
from backend.app.crosscheck import seen_from_rows
from backend.app.main import create_app
from backend.app.models import AuditEvent, Document, Estimate, ExtractedValueRow
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
    """The page as first seen: the small-screen menu, hidden controls and closed forms (Change) left out."""
    html = re.sub(r'<details class="nav-menu[^"]*".*?</details>', "", html, flags=re.S)
    html = re.sub(r'<button[^>]*\shidden[^>]*>.*?</button>', "", html, flags=re.S)
    return re.sub(r'(<details class="change[^"]*"[^>]*>\s*<summary[^>]*>.*?</summary>).*?</details>', r"\1</details>",
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
    """A card form's address and every field with all its values (hidden lists and ticked boxes), including
    inputs placed outside the form with form="<its id>"."""
    form = re.search(rf'<form([^>]*)action="([^"]*/review/{action})"([^>]*)>(.*?)</form>', html, re.S)
    assert form, f"no {action} form"
    form_id = re.search(r'id="([^"]+)"', form.group(1) + form.group(3))
    tags = re.findall(r"<input[^>]*>", form.group(4))
    if form_id:
        tags += [t for t in re.findall(r"<input[^>]*>", html) if f'form="{form_id.group(1)}"' in t]
    out: dict[str, list[str]] = {}
    for tag in tags:
        name, value = re.search(r'name="(\w+)"', tag), re.search(r'value="([^"]*)"', tag)
        if name and value and ('type="hidden"' in tag or ('type="checkbox"' in tag and " checked" in tag)):
            out.setdefault(name.group(1), []).append(value.group(1))
    return form.group(2), out


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
        action = next(a for a in ("agreeing", "approve", "group") if f'/review/{a}"' in html)
        url, data = form_lists(html, action)
        html = client.post(url, data=data, headers=HX).text
        clicks += 1
    return client.get(f"/enquiries/{pid}/review").text, clicks


# --- home -------------------------------------------------------------------------------------------------

NAV = {"How it works": "/#how", "Safety": "/#safety", "Measured": "/#accuracy", "Enquiries": "/enquiries"}


def test_home_has_one_big_add_files_button_that_lists_files_before_reading(client: TestClient) -> None:
    html = client.get("/").text
    hero = re.search(r'<section class="hero".*?</section>', html, re.S).group(0)
    assert visible_buttons(f"<main>{hero}</main>") == ["Add files"]  # "Read these files" shows once files are chosen
    form = re.search(r'<form[^>]*action="/enquiries"[^>]*>(.*?)</form>', hero, re.S)
    assert form and 'enctype="multipart/form-data"' in form.group(0)
    assert "data-autosubmit" not in hero  # choosing files no longer sends them
    assert 'name="next" value="review"' in form.group(1) and 'type="file"' in form.group(1)
    assert "data-file-list" in form.group(1)
    read = re.search(r'<button[^>]*type="submit"[^>]*>\s*Read these files\s*</button>', form.group(1))
    assert read and " hidden" in read.group(0) and "data-read" in read.group(0)
    js = (Path(__file__).parents[2] / "frontend" / "static" / "js" / "upload.js").read_text(encoding="utf-8")
    assert "DataTransfer" in js and "data-remove" in js and "Add more" in js and "data-autosubmit" not in js
    assert "Remove" in js  # each listed file has a remove link


@pytest.mark.parametrize("path", ["/", "/enquiries", "REVIEW"])
def test_the_top_bar_shows_plain_links_and_the_theme_switch_and_no_more_menu(client: TestClient, path: str) -> None:
    if path == "REVIEW":
        path = f"/enquiries/{add_files(client)}/review"
    html = client.get(path).text
    bar = re.search(r'<header class="(?:topbar|site-header)">.*?</header>', html, re.S).group(0)
    inline = re.search(r'<div class="nav-links">.*?</div>', bar, re.S).group(0)
    for label, href in NAV.items():
        assert re.search(rf'<a[^>]*href="{re.escape(href)}"[^>]*>{label}</a>', inline), label
    small = re.search(r'<details class="nav-menu">.*?</details>', bar, re.S).group(0)  # one menu under 700 px
    assert all(f'href="{href}"' in small for href in NAV.values())
    assert 'class="more' not in html and ">More<" not in html
    assert "data-theme-toggle" in bar


def test_the_links_collapse_into_one_menu_under_700px() -> None:
    css = (Path(__file__).parents[2] / "frontend" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\.nav-menu\s*\{\s*display: none;", css)
    blocks = re.findall(r"@media \(max-width: 700px\) \{(.*?)\n\}", css, re.S)
    assert any(".nav-links { display: none; }" in b and ".nav-menu { display: block; }" in b for b in blocks)


# --- review -----------------------------------------------------------------------------------------------

APPROVE_LINE = ("Approve means: I checked this against the file and it is right. "
                "Only approved values are used in the quote.")


def ticks(html: str) -> list[str]:
    return re.findall(r'<input type="checkbox" name="value_id" value="(\d+)"[^>]*\schecked', html)


def counts(html: str) -> tuple[int, int, int]:
    m = re.search(r"(\d+) approved, (\d+) changed, (\d+) still to check", html)
    assert m, "no counts line"
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def test_review_opens_on_the_agreeing_values_and_approves_nothing_by_itself(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    done, total = progress(html)
    assert done == 0 and 2 <= total <= 8
    assert html.count('<article class="review-card') == 1
    count = int(re.search(r"(\d+) agreeing values", html).group(1))
    assert APPROVE_LINE in html
    assert len(ticks(html)) == count  # every listed value has a tick, all ticked
    assert counts(html) == (0, 0, count)
    buttons = visible_buttons(html)
    assert f"Yes, these are right ({count} ticked)" in buttons and "Check one by one" in buttons
    assert len(buttons) <= 4, buttons
    assert re.search(r'<button[^>]*type="submit"[^>]*>Yes, these are right \(<span data-ticked>\d+</span> ticked\)', html)
    ask = re.search(r"<button[^>]*>\s*Ask\s*</button>", html).group(0)
    assert "disabled" in ask and "Coming soon" in html
    assert "A value is one fact read from your files" in html
    assert set(statuses(client, pid).values()) == {"extracted"}  # opening Review approves nothing
    assert f'href="/enquiries/{pid}"' in html  # the enquiry's other screens, from one plain link


def test_the_ticked_count_is_the_approved_count_each_with_its_own_audit_entry(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    url, data = form_lists(html, "agreeing")
    assert len(data["value_id"]) == int(re.search(r"Yes, these are right \((\d+) ticked\)",
                                                  re.sub(r"<[^>]+>", "", html)).group(1))
    after = client.post(url, data=data, headers=HX).text
    approved = [i for i, s in statuses(client, pid).items() if s == "approved"]
    assert sorted(approved) == sorted(int(i) for i in data["value_id"])
    assert sorted(audited(client, pid, "approve")) == sorted(approved)  # one entry per value
    assert progress(after)[0] == 1
    with client.app.state.sessions() as session:  # Stage 6: high as assessed (agreement may raise it), rules only
        rows = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid)).all()
        levels = assess(seen_from_rows(rows, as_read=True))
        for v in (r for r in rows if r.id in approved):
            assert levels[v.id].level == "high" and v.method == "rules"
            assert v.quote_match != "words_on_page" and v.value is not None


def test_an_unticked_value_stays_to_check_is_never_priced_and_the_counts_add_up(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    url, data = form_lists(html, "agreeing")
    listed = len(data["value_id"])
    with client.app.state.sessions() as session:  # untick a value the quote needs: a busbar or way rating
        rows = {int(i): session.get(ExtractedValueRow, int(i)) for i in data["value_id"]}
        left = next(i for i, r in rows.items() if r.field.endswith(".rating"))
    data["value_id"] = [i for i in data["value_id"] if int(i) != left]
    client.post(url, data=data, headers=HX)
    assert statuses(client, pid)[left] == "extracted" and audited(client, pid, "review_later") == [left]
    page = client.get(f"/enquiries/{pid}/review").text
    approved, changed, still = counts(page)
    assert (approved, changed, still) == (listed - 1, 0, 1) and approved + changed + still == listed
    finish(client, pid)
    client.post(f"/enquiries/{pid}/review/quote")
    with client.app.state.sessions() as session:
        est = session.scalars(select(Estimate).where(Estimate.project_id == pid).order_by(Estimate.id.desc())).first()
        used = {i for ln in est.lines for i in ln.value_ids}
    assert left not in used  # unapproved: never priced
    assert statuses(client, pid)[left] == "extracted"


def test_change_stores_the_engineers_value_keeps_the_original_and_audits_it(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review").text
    change = re.search(r'<details class="change-inline"[^>]*>\s*<summary[^>]*>Change</summary>(.*?)</details>', html, re.S)
    assert change, "every listed value has a Change link"
    url = re.search(r'action="([^"]*/review/one/change)"', change.group(1)).group(1)
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"', change.group(1)))
    prefilled = re.search(r'name="value" value="([^"]*)"', change.group(1)).group(1)
    vid = int(fields["value_id"])
    with client.app.state.sessions() as session:
        original = session.get(ExtractedValueRow, vid).value
    assert str(original) == prefilled  # the box opens with the value read
    after = client.post(url, data={**fields, "value": "999", "unit": ""}, headers=HX).text
    with client.app.state.sessions() as session:
        row = session.get(ExtractedValueRow, vid)
        assert row.review_status == "edited" and row.approved_value == 999 and row.value == original
    assert audited(client, pid, "edit") == [vid]
    assert "changed by engineer" in after
    approved, changed, still = counts(after)
    assert changed == 1 and approved + changed + still == len(ticks(html))


def test_check_one_by_one_shows_single_cards_with_approve_and_change(client: TestClient) -> None:
    pid = add_files(client)
    html = client.get(f"/enquiries/{pid}/review?one=1").text
    assert html.count('<article class="review-card') == 1
    assert {"Approve", "Change"} <= set(visible_buttons(html))
    fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)"',
                             re.search(r'<form[^>]*action="[^"]*/review/one/approve"[^>]*>(.*?)</form>', html, re.S).group(1)))
    after = client.post(f"/enquiries/{pid}/review/one/approve", data=fields, headers=HX).text
    assert statuses(client, pid)[int(fields["value_id"])] == "approved"
    assert audited(client, pid, "approve") == [int(fields["value_id"])]
    assert "/review/one/approve" in after and fields["value_id"] not in re.findall(r'name="value_id" value="(\d+)"', after)


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


def test_the_home_sketch_is_pinned_and_opens_and_closes_with_the_scroll() -> None:
    static = Path(__file__).parents[2] / "frontend" / "static"
    css = (static / "css" / "app.css").read_text(encoding="utf-8")
    block = re.search(r"@media \(min-width: 901px\) and \(prefers-reduced-motion: no-preference\) \{(.*?)\n\}", css, re.S)
    assert block, "only on wide screens with motion allowed"
    assert "position: sticky" in block.group(1) and ".hero__art" in block.group(1)
    assert "overflow: clip" in block.group(1)  # overflow: hidden would stop the pin
    js = (static / "js" / "home.js").read_text(encoding="utf-8")
    assert "Math.sin(Math.PI * p)" in js and "v <= 1.05" not in js  # closed at both ends of the pinned scroll
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in js  # reduced motion: the still drawing
