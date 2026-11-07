"""The evaluation's three result columns and its cut-off counts, on FAKE recordings made by this test.

No model is called. A scripted provider answers the showcase specification
truthfully, except that its way-table reply is cut off part-way (the shape
seen in the real Stage 3 recordings). The test then checks that:

- the old parser loses that page and the new parser keeps its complete items;
- the cut-off reply is counted, and empty replies are counted among cut-offs;
- the v2 column uses only recordings made with the current prompt version,
  and a column with no recording reads NOT RUN YET.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.llm.extract import ReplyInfo, ReplyStatus
from backend.app.llm.prompt import PROMPT_VERSION
from backend import evaluate
from backend.evaluate import Column, Coverage, compare_table, has_recordings, run
from backend.record import record_file
from data_generator import sets
from data_generator.project import load_answers
from data_generator.schemas import DocumentKind
from tests.fakes import ScriptedProvider, oracle_script

SHOWCASE = sets.DATA / "projects" / "showcase"


@pytest.fixture(scope="module")
def recorded(tmp_path_factory) -> tuple[Path, int]:
    """A FAKE recording of the showcase specification whose way-table reply is cut off."""
    script = oracle_script(load_answers(SHOWCASE / "answers.json"), DocumentKind.SPECIFICATION)
    page = max(script, key=lambda p: len(script[p]))
    full = json.dumps({"values": script[page]}, indent=2)
    cut = full[:full.rindex('"quote"') + 12]
    out = tmp_path_factory.mktemp("recorded")
    record_file("showcase", SHOWCASE.name, "specification.pdf", (SHOWCASE / "specification.pdf").read_bytes(),
                ScriptedProvider(script, raw={page: cut}), out, fake=True)
    return out, len(script[page]) - 1


def _column(folder: Path, salvage: bool, prompt_version: str | None = None) -> Column:
    return Column(label="test", recorded_dir=folder, salvage=salvage, own_prompt=True, prompt_version=prompt_version)


def test_new_parser_keeps_the_complete_items_of_a_cut_off_page(recorded) -> None:
    folder, complete = recorded
    old, _, old_cov = run([SHOWCASE], False, "llm", "showcase", column=_column(folder, salvage=False))
    new, _, new_cov = run([SHOWCASE], False, "llm", "showcase", column=_column(folder, salvage=True))
    old_tp = sum(s.tp for s in old.values())
    new_tp = sum(s.tp for s in new.values())
    assert new_tp - old_tp == complete  # every complete item of the cut-off page is a true value
    assert sum(s.tp for g, s in old.items() if g.startswith("way.")) == 0
    for cov in (old_cov, new_cov):
        assert sum(r.status == ReplyStatus.CUT_OFF for r in cov.replies) == 1
        assert "1 cut off (0 of them empty)" in cov.reply_counts()
        assert "done_reason not recorded" in cov.reply_counts()  # the scripted provider gives none


def test_v2_column_uses_only_recordings_of_the_current_prompt(recorded) -> None:
    folder, _ = recorded
    _, _, current = run([SHOWCASE], False, "llm", "showcase", column=_column(folder, True, PROMPT_VERSION))
    _, _, other = run([SHOWCASE], False, "llm", "showcase", column=_column(folder, True, "llm-extract-1"))
    assert current.recorded == 1 and other.recorded == 0


def test_empty_replies_count_as_cut_off_and_show_their_done_reason() -> None:
    cov = Coverage()
    cov.replies = [ReplyInfo(page=1, status=ReplyStatus.OK, done_reason="stop"),
                   ReplyInfo(page=2, status=ReplyStatus.CUT_OFF, done_reason="length"),
                   ReplyInfo(page=3, status=ReplyStatus.EMPTY, done_reason="length")]
    assert cov.reply_counts() == ("3 replies: 2 cut off (1 of them empty), 0 invalid; done_reason: length 2, "
                                  "stop 1; done_reason of the empty replies: length 1")


def test_column_without_recordings_reads_not_run_yet(tmp_path: Path) -> None:
    grouped, _, cov = run([SHOWCASE], False, "llm", "showcase", column=_column(tmp_path, True))
    assert cov.recorded == 0
    table = compare_table([(_column(tmp_path, False), {}), (_column(tmp_path, True), None)])
    assert "NOT RUN YET" in table.splitlines()[-1]


def test_column_without_recordings_is_skipped_without_reading_any_file(recorded, tmp_path: Path, monkeypatch,
                                                                       capsys) -> None:
    folder, _ = recorded
    project = tmp_path / "projects" / "T01"
    project.mkdir(parents=True)
    (project / "answers.json").write_text("{}", encoding="utf-8")  # only its presence is checked
    assert not has_recordings(_column(tmp_path, True), [project], "test")
    assert has_recordings(_column(folder, True), [SHOWCASE], "showcase")
    assert has_recordings(_column(folder, True, PROMPT_VERSION), [SHOWCASE], "showcase")
    assert not has_recordings(_column(folder, True, "llm-extract-1"), [SHOWCASE], "showcase")

    calls = []
    monkeypatch.setattr(evaluate, "run", lambda *a, **k: calls.append(a))
    empty = tmp_path / "none"
    code = evaluate.main(["--mode", "llm", "--root", str(project.parent), "--count", "1",
                          "--recorded", str(empty), "--recorded-v1", str(empty)])
    assert code == 0 and calls == []  # nothing was read or replayed
    assert capsys.readouterr().out.count("NOT RUN YET (no recording in") == 6  # 3 columns, with and without DXF
