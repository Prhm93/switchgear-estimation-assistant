"""Rescued (words_on_page) values in the app: stored, marked, never approved in bulk, never estimated unapproved.

A FAKE recording of the showcase specification (made by this test, labelled
fake) holds one value whose quote is two words of the page in the wrong order:
every word is on the page, but not as one span. With the default setting
(relaxed) it is stored as ``words_on_page``; with QUOTE_CHECK=strict it is
rejected exactly as in v2.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app import services
from backend.app.config import Settings
from backend.app.llm.quote import normalise
from backend.app.main import create_app
from backend.app.models import ExtractedValueRow
from backend.app.pipeline import analyse_file
from backend.app.storage import FileType
from backend.record import record_file
from data_generator import sets
from tests.fakes import ScriptedProvider

SHOWCASE = sets.DATA / "projects" / "showcase"
SPEC = (SHOWCASE / "specification.pdf").read_bytes()
FIELDS = ["system.earthing", "metering.meter", "enclosure.cable_entry", "enclosure.form"]


def _stitched_item() -> tuple[int, dict]:
    """A field the rules do not report on some page, with a quote of two page words in reverse order."""
    rules = analyse_file(FileType.PDF, SPEC, "specification.pdf")
    taken = {(v.field, v.source.page) for v in rules.values}
    for page in rules.read.pages:
        words = [w for w in page.text.split() if w.isalpha() and len(w) > 4]
        pairs = [(a, b) for a, b in zip(words, words[1:]) if a.lower() != b.lower()]
        for field in FIELDS:
            if (field, page.number) in taken or not pairs:
                continue
            a, b = pairs[0]
            quote = f"{b} {a}"
            if normalise(quote) not in normalise(page.text):
                return page.number, {"field": field, "value": "Stitched test value", "unit": None, "quote": quote}
    raise AssertionError("no page and field to plant the stitched quote on")


@pytest.fixture(scope="module")
def planted(tmp_path_factory) -> tuple[Path, dict]:
    page, item = _stitched_item()
    out = tmp_path_factory.mktemp("recorded-3c")
    record_file("showcase", "SHOWCASE", "specification.pdf", SPEC, ScriptedProvider({page: [item]}), out, fake=True)
    return out, item


def _client(tmp_path: Path, recorded: Path, **extra) -> TestClient:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", model_mode="recorded",
                        recorded_dir=recorded, **extra)
    return TestClient(create_app(settings))


def _upload(client: TestClient) -> int:
    response = client.post("/enquiries", data={"name": "Relaxed"}, follow_redirects=False)
    pid = int(response.headers["location"].split("/")[2])
    client.post(f"/enquiries/{pid}/documents", files=[("files", ("specification.pdf", SPEC))], follow_redirects=False)
    return pid


def _rows(client: TestClient, pid: int, field: str) -> list[ExtractedValueRow]:
    with client.app.state.sessions() as session:
        return list(session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid,
                                                                    ExtractedValueRow.field == field)))


@pytest.fixture
def client(tmp_path: Path, planted) -> Iterator[TestClient]:
    with _client(tmp_path, planted[0]) as c:
        yield c


def test_relaxed_is_the_default_and_the_rescued_value_is_stored_and_marked(client: TestClient, planted) -> None:
    _, item = planted
    assert Settings().quote_check == "relaxed"
    pid = _upload(client)
    rows = [r for r in _rows(client, pid, item["field"]) if r.method == "llm"]
    assert len(rows) == 1
    row = rows[0]
    assert row.quote_match == "words_on_page" and row.confidence == "medium" and row.review_status == "extracted"
    page = client.get(f"/enquiries/{pid}/check").text
    assert item["value"].upper() in page  # under "Needs your decision" (here a conflict with the rules value)
    assert "Quote pieced together" in page
    assert "Quote pieced together" in client.get(f"/values/{row.id}/panel").text


def test_approve_all_never_approves_a_rescued_value(client: TestClient, planted) -> None:
    _, item = planted
    pid = _upload(client)
    row = next(r for r in _rows(client, pid, item["field"]) if r.method == "llm")
    with client.app.state.sessions() as session:  # even at high confidence it must be left for the engineer
        session.get(ExtractedValueRow, row.id).confidence = "high"
        session.commit()
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    with client.app.state.sessions() as session:
        assert session.get(ExtractedValueRow, row.id).review_status == "extracted"
        approved = session.scalars(select(ExtractedValueRow).where(ExtractedValueRow.project_id == pid,
                                                                   ExtractedValueRow.review_status == "approved"))
        assert all(r.quote_match != "words_on_page" for r in approved)


def test_an_unapproved_rescued_value_cannot_reach_the_estimate(client: TestClient, planted) -> None:
    _, item = planted
    pid = _upload(client)
    client.post(f"/enquiries/{pid}/check/accept-all", data={"confirm": "yes"})
    client.post(f"/enquiries/{pid}/quote")
    with client.app.state.sessions() as session:
        est = services.latest_estimate(session, pid)
        used = {i for ln in est.lines for i in ln.value_ids}
        rescued = {r.id for r in session.scalars(select(ExtractedValueRow).where(
            ExtractedValueRow.project_id == pid, ExtractedValueRow.quote_match == "words_on_page"))}
    assert rescued and not rescued & used


def test_strict_setting_rejects_the_stitched_quote_as_in_v2(tmp_path: Path, planted) -> None:
    _, item = planted
    with _client(tmp_path, planted[0], quote_check="strict") as c:
        pid = _upload(c)
        assert [r for r in _rows(c, pid, item["field"]) if r.method == "llm"] == []
        with c.app.state.sessions() as session:
            assert not list(session.scalars(select(ExtractedValueRow).where(
                ExtractedValueRow.project_id == pid, ExtractedValueRow.quote_match == "words_on_page")))
