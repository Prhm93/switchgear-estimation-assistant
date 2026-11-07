"""Replies that stop part-way: every complete item is kept, the rest of the page is not lost.

The reply shapes below are copied from real Stage 3 recordings of gemma4:e2b
(the way-table page of test project T01, and the endings seen across the test
and reworded sets): a reply cut inside a quote, after an opening brace, after
a comma, after a key, and an empty reply. No model is called; the end-to-end
test uses the scripted FAKE provider on the committed showcase specification.
"""

from __future__ import annotations

import json

import pytest

from backend.app.llm.extract import ReplyStatus, parse_reply, salvage_items
from backend.app.pipeline import analyse_file
from backend.app.storage import FileType
from data_generator import sets
from data_generator.project import load_answers
from data_generator.schemas import DocumentKind
from tests.fakes import ScriptedProvider, oracle_script

# The start of T01's page 4 reply as recorded, two complete items, then cut inside the third item's quote.
HEAD = """{
  "values": [
    {
      "field": "ways.count",
      "value": "6",
      "quote": "6 Outgoing ways"
    },
    {
      "field": "way.Q1.rating",
      "value": "630",
      "quote": "Q1 | Small power DB-L1 | MCCB | 630 | 4 | 50 | 2x 4C 185 mm2 SWA"
    },
"""
CUT_IN_QUOTE = HEAD + """    {
      "field": "way.Q4.rating",
      "value": "630",
      "quote": "Q4"""
CUT_AFTER_BRACE = HEAD + "    {\n"
CUT_AFTER_ITEM = HEAD.rstrip().rstrip(",") + "\n"
CUT_AFTER_KEY = HEAD + '    {\n      "field": "way.Q4.description",\n      "value":'


@pytest.mark.parametrize("reply", [CUT_IN_QUOTE, CUT_AFTER_BRACE, CUT_AFTER_ITEM, CUT_AFTER_KEY])
def test_cut_off_reply_keeps_every_complete_item(reply: str) -> None:
    items, status, reason = parse_reply(reply)
    assert status == ReplyStatus.CUT_OFF
    assert [i["field"] for i in items] == ["ways.count", "way.Q1.rating"]
    assert reason == "reply cut off, 2 items kept"


def test_old_parser_loses_the_whole_page() -> None:
    items, status, reason = parse_reply(CUT_IN_QUOTE, salvage=False)
    assert items == [] and status == ReplyStatus.CUT_OFF
    assert reason.startswith("reply is not valid JSON (Unterminated string")


def test_empty_reply_is_counted_as_empty() -> None:
    assert parse_reply("") == ([], ReplyStatus.EMPTY, "reply is empty")
    assert parse_reply("  \n") == ([], ReplyStatus.EMPTY, "reply is empty")


def test_valid_replies_are_unchanged() -> None:
    assert parse_reply("{}") == ([], ReplyStatus.OK, None)
    items, status, reason = parse_reply(HEAD.rstrip().rstrip(",") + "\n  ]\n}")
    assert len(items) == 2 and status == ReplyStatus.OK and reason is None


def test_malformed_but_not_cut_off_is_invalid() -> None:
    reply = '{"values": [{"field": "system.voltage", "value": 400, "quote": "400 V"} {"field": "x"}]}'
    items, status, reason = parse_reply(reply)
    assert status == ReplyStatus.INVALID
    # Both items are complete JSON objects, so both go on to the checks; the second then fails the schema.
    assert len(items) == 2 and reason.startswith("reply is not valid JSON") and reason.endswith("2 items kept")


def test_salvage_never_repairs_an_incomplete_item() -> None:
    assert salvage_items('{"values": [{"field": "a", "value": 1, "quote": "1"}, {"field": "b", "va') == [
        {"field": "a", "value": 1, "quote": "1"}]
    assert salvage_items('{"other": [') == []
    assert salvage_items("{") == []


def test_cut_off_page_keeps_its_checked_values_end_to_end() -> None:
    """A FAKE model answers the showcase way-table page truthfully, but its reply is cut off."""
    showcase = sets.DATA / "projects" / "showcase"
    spec = (showcase / "specification.pdf").read_bytes()
    script = oracle_script(load_answers(showcase / "answers.json"), DocumentKind.SPECIFICATION)
    page = max(script, key=lambda p: len(script[p]))  # the way-table page
    full = json.dumps({"values": script[page]}, indent=2)
    last = full.rindex('"quote"')
    cut = full[:last + 12]  # inside the last item's quote
    result = analyse_file(FileType.PDF, spec, "specification.pdf", ScriptedProvider(script, raw={page: cut}))
    kept_on_page = [v for v in result.llm.values if v.source.page == page]
    assert len(kept_on_page) == len(script[page]) - 1  # all but the incomplete last item
    page_rejections = [r for r in result.llm.rejected if r.page == page]
    assert [r.reason for r in page_rejections] == [f"reply cut off, {len(script[page]) - 1} items kept"]
    info = next(r for r in result.llm.replies if r.page == page)
    assert info.status == ReplyStatus.CUT_OFF and info.items_kept == len(script[page]) - 1
