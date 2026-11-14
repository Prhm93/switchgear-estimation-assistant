"""Vision replies cut off mid-JSON keep their complete ways (like the Stage 3b recovery of language-model replies).

On the first Colab run of the fresh set, 10 of 120 sheets were lost because the
model's reply stopped part-way through the JSON. These tests use fake replies
and a fake Ollama client only: no model is needed.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from backend.app.drawing.data import evaluation_drawings
from backend.app.drawing.vision import (
    VISION_OPTIONS,
    OllamaVisionClient,
    RecordedVisionClient,
    VisionRecording,
    VisionUnavailable,
    parse_vision_reply,
)
from backend.record_vision import main as record_main
from backend.record_vision import record, recording_path

FULL = {"ways": [
    {"way": "Q1", "device": "MCCB", "rating_a": 630, "poles": 4, "breaking_ka": 50, "text": "MCCB 630A 4P 50kA"},
    {"way": "Q2", "device": "MCB", "rating_a": 32, "poles": 3, "breaking_ka": None, "text": "MCB 32A TP"},
    {"way": "Q3", "device": "MCCB", "rating_a": 250, "poles": 4, "breaking_ka": 36, "text": "MCCB 250A 4P"},
]}
TEXT = json.dumps(FULL)


def test_a_complete_reply_is_read_as_before() -> None:
    out, cut = parse_vision_reply(TEXT)
    assert not cut and [w.way for w in out.ways] == ["Q1", "Q2", "Q3"]


def test_a_reply_cut_off_mid_way_keeps_the_complete_ways_only() -> None:
    cut_text = TEXT[:TEXT.index('"Q3"') + 12]  # stops inside the third way
    with pytest.raises(json.JSONDecodeError):
        json.loads(cut_text)
    out, cut = parse_vision_reply(cut_text)
    assert cut and [w.way for w in out.ways] == ["Q1", "Q2"]
    assert out.ways[1].rating_a == 32  # kept exactly as the model wrote it, nothing repaired or guessed


def test_a_reply_cut_off_inside_a_string_keeps_what_came_before() -> None:
    cut_text = TEXT[:TEXT.index("MCB 32A") + 4]
    out, cut = parse_vision_reply(cut_text)
    assert cut and [w.way for w in out.ways] == ["Q1"]


def test_a_complete_way_that_breaks_the_schema_is_dropped_not_fixed() -> None:
    bad = dict(FULL["ways"][1], poles=7)
    cut_text = json.dumps({"ways": [FULL["ways"][0], bad, FULL["ways"][2]]})[:-20]
    out, cut = parse_vision_reply(cut_text)
    assert cut and [w.way for w in out.ways] == ["Q1"]


def test_a_reply_cut_off_before_any_complete_way_is_not_read() -> None:
    with pytest.raises(VisionUnavailable, match="cut off"):
        parse_vision_reply(TEXT[:30])
    with pytest.raises(VisionUnavailable, match="cut off"):
        parse_vision_reply("")


def test_a_complete_reply_that_breaks_the_schema_is_still_refused() -> None:
    with pytest.raises(VisionUnavailable, match="schema"):
        parse_vision_reply(json.dumps({"ways": [{"way": "Q1", "poles": 7}]}))


class FakeOllama:
    """Stands in for the ``ollama`` package: records the options and answers with a fixed text."""

    def __init__(self, reply: str) -> None:
        self.reply, self.options = reply, None
        outer = self

        class Client:
            def __init__(self, host: str, timeout: float) -> None:
                pass

            def chat(self, **kw):
                outer.options = kw["options"]
                return {"message": {"content": outer.reply}}

        self.Client = Client


def test_the_live_client_raises_the_output_limit_and_keeps_cut_off_ways(monkeypatch) -> None:
    fake = FakeOllama(TEXT[:TEXT.index('"Q3"') + 12])
    monkeypatch.setitem(sys.modules, "ollama", types.SimpleNamespace(Client=fake.Client))
    client = OllamaVisionClient("gemma4:e2b", "http://x")
    out = client.read(file_sha256="0" * 64, sheet=1, image=lambda: b"png")
    assert [w.way for w in out.ways] == ["Q1", "Q2"] and client.last_cut_off
    assert fake.options == VISION_OPTIONS
    assert VISION_OPTIONS["num_predict"] >= 4096 and VISION_OPTIONS["num_ctx"] >= 8192
    assert VISION_OPTIONS["temperature"] == 0


def test_a_cut_off_reply_is_recorded_as_such_and_replays(tmp_path: Path, monkeypatch) -> None:
    samples = [s for s in evaluation_drawings("showcase") if s.version.value == "scanned"][:1]
    fake = FakeOllama(TEXT[:TEXT.index('"Q3"') + 12])
    monkeypatch.setitem(sys.modules, "ollama", types.SimpleNamespace(Client=fake.Client))
    made, _, failed = record(samples, OllamaVisionClient("fake-vision", "http://x"), tmp_path, "showcase",
                             model="fake-vision", fake=True)
    assert (made, failed) == (1, [])
    rec = VisionRecording.model_validate_json(recording_path(tmp_path, "showcase", samples[0]).read_bytes())
    assert rec.reply == "cut off, 2 ways kept" and rec.options == VISION_OPTIONS
    assert RecordedVisionClient(tmp_path).recordings


def test_old_recordings_without_the_new_fields_still_load() -> None:
    old = {"model": "m", "model_version": None, "date": "2026-11-13", "prompt_version": "vision-v1", "prompt": "p",
           "input_name": "F01/drawing/x.png", "input_sha256": "a" * 64, "sheet": 1, "output": {"ways": []},
           "seconds": 1.0, "fake": True}
    rec = VisionRecording.model_validate(old)
    assert rec.reply == "complete" and rec.options is None


def test_the_recorder_can_be_limited_to_some_projects(tmp_path: Path, capsys) -> None:
    # Only the showcase is in this list; "--projects NONE" leaves nothing to record and says so.
    assert record_main(["--set", "showcase", "--version", "scanned", "--projects", "NONE",
                        "--out", str(tmp_path)]) == 2
    assert "no drawings" in capsys.readouterr().err
