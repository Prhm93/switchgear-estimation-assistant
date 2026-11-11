"""The button bar under the tabs on Check: Decisions, Items and Report, with live counts.

Each view is kept in the address (``?view=...``), so Back and links work; HTMX swaps the view in place.
Export is offered only when something is approved, and refused otherwise.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import enquiry, services
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Project
from backend.app.web import VIEWS, _items
from data_generator.sets import DATA

SHOWCASE = DATA / "projects" / "showcase"
FILES = [("specification.pdf", (SHOWCASE / "specification.pdf").read_bytes()),
         ("requirements.docx", (SHOWCASE / "requirements.docx").read_bytes()),
         ("schematic.dxf", (SHOWCASE / "drawing" / "schematic.dxf").read_bytes())]
HX = {"HX-Request": "true", "HX-Target": "check-body"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="off")
    with TestClient(create_app(settings)) as c:
        yield c


def new_enquiry(client: TestClient, files=FILES) -> int:
    response = client.post("/enquiries", data={"name": "Views"}, files=[("files", f) for f in files],
                           follow_redirects=False)
    return int(response.headers["location"].split("/")[2])


def bar(html: str) -> dict[str, str | None]:
    """The buttons of the bar: label -> count shown (None when it has no count)."""
    nav = re.search(r'<nav id="views".*?</nav>', html, re.S).group(0)
    found = re.findall(r'<a class="view-btn[^"]*"[^>]*>\s*([A-Za-z]+)\s*(?:<span class="view-btn__count[^>]*>(\d+)</span>)?',
                       nav)
    return {label: count or None for label, count in found}


def current(html: str) -> str:
    nav = re.search(r'<nav id="views".*?</nav>', html, re.S).group(0)
    return re.search(r'aria-current="page"[^>]*>\s*([A-Za-z]+)', nav).group(1)


def expected_counts(client: TestClient, pid: int) -> tuple[int, int]:
    with client.app.state.sessions() as session:
        project = session.get(Project, pid)
        found = enquiry.decisions(project)
        return found.cards, len(_items_for(client, session, project))


def _items_for(client: TestClient, session, project):
    class Req:  # the route helper needs only the app state
        app = client.app
    return _items(Req, session, project)


def test_the_bar_has_one_entry_per_view_and_adding_one_is_one_line() -> None:
    assert [key for key, _label, _count in VIEWS][:3] == ["decisions", "items", "report"]


def test_decisions_is_the_default_and_the_counts_come_from_the_database(client: TestClient) -> None:
    pid = new_enquiry(client)
    page = client.get(f"/enquiries/{pid}/check").text
    decisions, items = expected_counts(client, pid)
    assert bar(page) == {"Decisions": str(decisions), "Items": str(items), "Report": None}
    assert current(page) == "Decisions"
    assert "Needs your decision" not in page and 'id="summary"' not in page  # replaced by the bar
    assert 'class="link-accept"' in page and "Accept all" in page  # a small link inside Decisions
    # Live: after "Accept all" the count follows the database.
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    after = client.get(f"/enquiries/{pid}/check").text
    decisions_after, _ = expected_counts(client, pid)
    assert decisions_after < decisions and bar(after)["Decisions"] == str(decisions_after)


def test_each_view_has_its_own_address_and_swaps_in_place(client: TestClient) -> None:
    pid = new_enquiry(client)
    page = client.get(f"/enquiries/{pid}/check?view=items").text
    assert current(page) == "Items" and 'class="item-list"' in page and "<!DOCTYPE html>" in page
    assert re.search(rf'href="/enquiries/{pid}/check\?view=report"[^>]*hx-push-url="true"', page)
    part = client.get(f"/enquiries/{pid}/check?view=report", headers=HX)
    assert part.status_code == 200 and "<!DOCTYPE html>" not in part.text and current(part.text) == "Report"
    assert current(client.get(f"/enquiries/{pid}/check?view=nonsense").text) == "Decisions"


def test_items_and_report_never_repeat_the_quote(client: TestClient) -> None:
    pid = new_enquiry(client)
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    for view in ("items", "report"):
        html = client.get(f"/enquiries/{pid}/check?view={view}").text
        body = html.split('<nav id="views"', 1)[1]
        assert "GBP" not in body and "Draft total" not in body, view  # prices live on the Quote tab only
    report = client.get(f"/enquiries/{pid}/check?view=report").text
    assert "How this was read" in report and "Read with rules" in report


def test_export_is_disabled_and_refused_while_nothing_is_approved(client: TestClient) -> None:
    pid = new_enquiry(client)
    with client.app.state.sessions() as session:
        services.build_estimate(session, pid, client.app.state.settings)  # a quote exists, nothing approved
    for url in (f"/enquiries/{pid}/quote", f"/enquiries/{pid}/check?view=report"):
        html = client.get(url).text
        assert re.search(r'<button[^>]*disabled[^>]*>[^<]*(?:<svg.*?</svg>)?\s*Export Word report', html, re.S), url
        assert "Approve at least one value to export" in html
    assert client.get(f"/enquiries/{pid}/quote/report.docx").status_code == 409
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    html = client.get(f"/enquiries/{pid}/quote").text
    assert f'href="/enquiries/{pid}/quote/report.docx"' in html
    assert client.get(f"/enquiries/{pid}/quote/report.docx").status_code == 200


def test_a_conflict_side_lists_each_source_once(client: TestClient) -> None:
    pid = new_enquiry(client)
    page = client.get(f"/enquiries/{pid}/check").text
    for side in re.findall(r'<div class="pair__side">(.*?)</form>', page, re.S):
        sources = re.findall(r'class="pair__src"[^>]*>([^<]+)</a>', side)
        assert len(sources) == len(set(sources)), sources
    assert "Drawing (CAD), sheet 1" in page
