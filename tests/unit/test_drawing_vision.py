"""Stage 4 Part B: a vision model reads drawing pictures where OCR cannot.

Everything here runs against fake clients and fake recordings written into the
test's own temporary folder (clearly marked ``fake``), so no model is needed.
Real recordings live in the git-ignored ``data/recorded-vision/`` and are never
committed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.drawing.vision import (
    RecordedVisionClient,
    VisionRecording,
    VisionSheetOutput,
    VisionUnavailable,
    device_word,
    make_vision_client,
    vision_values,
)
from backend.app.labels import method_words
from backend.app.paths import REPO_ROOT
from backend.app.schemas import Confidence, Method
from data_generator.schemas import DrawingVersionKind

OUTPUT = {"ways": [
    {"way": "Q1", "device": "MCCB", "rating_a": 630, "poles": 4, "breaking_ka": 50, "text": "MCCB 630A 4P 50kA"},
    {"way": "Q2", "device": "moulded case circuit breaker", "rating_a": 250, "poles": 3, "breaking_ka": None,
     "text": "250A TP"},
]}


def output() -> VisionSheetOutput:
    return VisionSheetOutput.model_validate(OUTPUT)


def values(**kw):
    defaults = {"file": "schematic_sheet1_scanned.png", "version": DrawingVersionKind.SCANNED, "sheet": 1,
                "ocr_text": "", "filled": set()}
    return vision_values(output(), **{**defaults, **kw})


# --- the model's answer --------------------------------------------------------------------------------

def test_the_model_answer_is_checked_before_use() -> None:
    with pytest.raises(ValidationError):
        VisionSheetOutput.model_validate({"ways": [{"way": "Way 1", "rating_a": 630}]})
    with pytest.raises(ValidationError):
        VisionSheetOutput.model_validate({"ways": [{"way": "Q1", "poles": 7}]})
    with pytest.raises(ValidationError):
        VisionSheetOutput.model_validate({"ways": [{"way": "Q1", "rating_a": -5}]})
    with pytest.raises(ValidationError):  # nothing the schema does not name
        VisionSheetOutput.model_validate({"ways": [], "total_ways": 9})


def test_device_words_are_plain_names() -> None:
    assert device_word("MCCB") == "mccb" and device_word("Air circuit breaker") == "acb"
    assert device_word("switch-disconnector") == "switch_disconnector" and device_word("MCB") == "mcb"
    assert device_word("fuse") is None and device_word(None) is None


# --- values: read from a picture, never above medium, always reviewed --------------------------------------

def test_vision_values_are_marked_read_from_a_picture_and_need_review() -> None:
    out = values()
    fields = {v.field: v for v in out}
    assert fields["way.Q1.rating"].value == 630 and fields["way.Q1.rating"].unit == "A"
    assert fields["way.Q1.breaking_capacity"].unit == "kA" and fields["way.Q2.device"].value == "mccb"
    assert "way.Q2.breaking_capacity" not in fields  # the model gave none: nothing is made up
    assert all(v.method == Method.VISION for v in out)
    assert all(v.confidence == Confidence.LOW for v in out)  # nothing in the OCR text backs them
    assert all(v.review_status.value == "extracted" for v in out)
    assert all(v.source.page == 1 and v.source.source_text for v in out)
    assert method_words("vision") == "Read from the drawing picture by a vision model"


def test_a_value_whose_text_ocr_also_read_is_medium_never_high() -> None:
    out = values(ocr_text="Q1 MCCB 630A 4P 50kA  Q2 SMALL POWER")
    q1 = [v for v in out if v.field.startswith("way.Q1.")]
    q2 = [v for v in out if v.field.startswith("way.Q2.")]
    assert {v.confidence for v in q1} == {Confidence.MEDIUM}
    assert {v.confidence for v in q2} == {Confidence.LOW}


def test_vision_only_fills_what_ocr_left_empty() -> None:
    out = values(filled={"way.Q1.rating", "way.Q1.poles"})
    fields = {v.field for v in out}
    assert "way.Q1.rating" not in fields and "way.Q1.poles" not in fields
    assert "way.Q1.breaking_capacity" in fields and "way.Q2.rating" in fields


# --- recordings: matched by the SHA-256 of the file, refused otherwise ----------------------------------

def write_recording(folder: Path, data: bytes, sheet: int = 1, **extra) -> Path:
    rec = VisionRecording(model="fake-vision", model_version="test", date="2026-11-12", prompt_version="vision-v1",
                          prompt="fake prompt", input_name="T01/drawing/schematic_sheet1_scanned.png",
                          input_sha256=hashlib.sha256(data).hexdigest(), sheet=sheet, output=output(), fake=True,
                          **extra)
    path = folder / f"fake-{sheet}.json"
    path.write_text(rec.model_dump_json(indent=1), encoding="utf-8")
    return path


def test_a_recording_is_replayed_only_for_the_same_file(tmp_path: Path) -> None:
    data = b"the picture bytes"
    write_recording(tmp_path, data)
    client = RecordedVisionClient(tmp_path)
    got = client.read(file_sha256=hashlib.sha256(data).hexdigest(), sheet=1, image=lambda: b"")
    assert got == output() and client.label == "fake-vision, 2026-11-12 (recorded, fake)"
    with pytest.raises(VisionUnavailable, match="SHA-256"):
        client.read(file_sha256=hashlib.sha256(b"another file").hexdigest(), sheet=1, image=lambda: b"")
    with pytest.raises(VisionUnavailable, match="sheet 2"):
        client.read(file_sha256=hashlib.sha256(data).hexdigest(), sheet=2, image=lambda: b"")


def test_a_recorded_client_never_renders_the_picture(tmp_path: Path) -> None:
    data = b"bytes"
    write_recording(tmp_path, data)

    def boom() -> bytes:
        raise AssertionError("a recording needs no picture")

    RecordedVisionClient(tmp_path).read(file_sha256=hashlib.sha256(data).hexdigest(), sheet=1, image=boom)


def test_a_broken_recording_is_refused_with_its_name(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text(json.dumps({"model": "x"}), encoding="utf-8")
    with pytest.raises(VisionUnavailable, match="bad.json"):
        RecordedVisionClient(tmp_path)


def test_vision_is_off_by_default_and_its_folder_is_never_committed() -> None:
    from backend.app.config import Settings

    settings = Settings()
    assert settings.vision_mode == "off"
    assert make_vision_client(settings) is None
    assert settings.vision_recorded_dir == REPO_ROOT / "data" / "recorded-vision"
    assert "data/recorded-vision/" in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_recorded_mode_without_recordings_gives_no_client_and_says_why(tmp_path: Path) -> None:
    from backend.app.config import Settings

    settings = Settings(vision_mode="recorded", vision_recorded_dir=tmp_path / "missing")
    with pytest.raises(VisionUnavailable, match="no vision recordings"):
        make_vision_client(settings)
