"""The strict quote check is the fixed v2 baseline, checked on the real v2 recordings.

The recordings (data/recorded/, prompt llm-extract-2) are git-ignored, so these
tests skip when they are missing (as in CI). The fingerprints below were taken
from the v2 code on main (ac4582b) before the relaxed check existed: a SHA-256
over the sorted kept values and over the sorted rejections of project T01.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backend.app.llm.prompt import PROMPT_TEMPLATE, PROMPT_VERSION, SYSTEM_PROMPT
from backend.app.llm.quote import QuoteCheckMode
from backend.app.pipeline import analyse_file
from backend.app.recordings import recording_path
from backend.app.storage import EXTENSIONS
from backend.record import READ_FILES, set_folders
from data_generator.sets import DATA
from estimation_assistant.providers import load_recording, make_provider

RECORDED = DATA / "recorded"
T01 = DATA / "projects" / "test" / "T01"
# file -> (kept values, their SHA-256, rejections, their SHA-256), from the v2 code before Stage 3c.
V2_T01 = {
    "specification.pdf": (69, "bd0bcde42b9c59eb2015bae70eb46b848d529afcc5017eac5f7b77a9e7c0d4e3",
                          0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    "requirements.docx": (8, "87412d8999803259e675ebefaad32c3e04078a15a8625bd26577ee03130c4c23",
                          0, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    "drawing/schematic.dxf": (61, "9e19f6ea99cdd0018a215c414da4bf66fd58c900625134c3aa6e4bd8ff59523b",
                              28, "f3b1a12975af6d75dcb298ccd305e113a9d46786e317790004ee1703de880a71"),
}


def _needs(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"{path} is missing (v2 recordings and the test set are git-ignored)")


def _digest(rows: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(rows)).encode()).hexdigest()


@pytest.mark.parametrize("file", READ_FILES)
def test_strict_check_gives_exactly_the_v2_values_on_t01(file: str) -> None:
    _needs(recording_path(RECORDED, "test", "T01", file))
    _needs(T01 / file)
    data = (T01 / file).read_bytes()
    rec = load_recording(recording_path(RECORDED, "test", "T01", file), data)
    a = analyse_file(EXTENSIONS[Path(file).suffix.lower()], data, file, make_provider("recorded", recording=rec),
                     quote_check=QuoteCheckMode.STRICT)
    kept = [json.dumps([v.field, v.value, v.unit, v.source.page, v.source.source_text, v.confidence.value],
                       default=str) for v in a.llm.values]
    rejected = [json.dumps([r.page, r.field, r.reason], default=str) for r in a.llm.rejected]
    assert (len(kept), _digest(kept), len(rejected), _digest(rejected)) == V2_T01[file]


def test_every_v2_recording_still_passes_the_sha256_and_prompt_checks() -> None:
    _needs(RECORDED / "test")
    checked = 0
    for set_name, project, folder in set_folders(["showcase", "test", "reworded"]):
        for file in READ_FILES:
            path = recording_path(RECORDED, set_name, project, file)
            if not path.exists() or not (folder / file).exists():
                continue
            rec = load_recording(path, (folder / file).read_bytes())  # raises on other bytes
            assert rec.prompt_version == PROMPT_VERSION
            assert rec.system_prompt == SYSTEM_PROMPT and rec.prompt_template == PROMPT_TEMPLATE
            checked += 1
    assert checked == 123
