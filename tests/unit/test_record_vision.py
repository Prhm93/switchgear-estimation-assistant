"""Stage 4 Part B: the Colab recorder and the scorer, run here with a fake client (no model).

The fake answers with the answer key's own way values, so the scorer must give a
perfect score on what it answered; the recordings go to the test's temporary
folder and are marked fake.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from backend.app.drawing.data import evaluation_drawings
from backend.app.drawing.vision import RecordedVisionClient, VisionSheetOutput
from backend.drawings import measure_vision
from backend.record_vision import record, recording_path


class AnswerKeyVision:
    """Answers each sheet with the true ratings and poles of its ways (from the answer key)."""

    label = "answer-key fake"

    def __init__(self, samples) -> None:
        self.by_sheet = {}
        for s in samples:
            ways: dict[str, dict] = {}
            for v in s.values:
                parts = v.field.split(".")
                if parts[0] == "way" and parts[2] in ("rating", "poles"):
                    ways.setdefault(parts[1], {"way": parts[1]})["rating_a" if parts[2] == "rating" else "poles"] = v.value
            self.by_sheet[s.sheet] = VisionSheetOutput.model_validate({"ways": list(ways.values())})
        self.calls = 0

    def read(self, *, file_sha256: str, sheet: int, image: Callable[[], bytes]) -> VisionSheetOutput:
        self.calls += 1
        return self.by_sheet[sheet]


def test_record_then_score_and_a_second_run_skips_what_is_there(tmp_path: Path) -> None:
    samples = [s for s in evaluation_drawings("showcase") if s.version.value == "scanned"]
    fake = AnswerKeyVision(samples)
    made, skipped, failed = record(samples, fake, tmp_path, "showcase", model="fake-vision", fake=True)
    assert (made, skipped, failed) == (len(samples), 0, [])
    path = recording_path(tmp_path, "showcase", samples[0])
    assert path.is_relative_to(tmp_path) and path.name == f"{samples[0].path.stem}-sheet{samples[0].sheet}.json"
    assert RecordedVisionClient(tmp_path).recordings  # readable by the app's client
    assert record(samples, fake, tmp_path, "showcase", model="fake-vision", fake=True)[:2] == (0, len(samples))
    assert fake.calls == len(samples)
    table = measure_vision(samples, tmp_path)
    assert f"{len(samples)} of {len(samples)} sheets have a recording" in table
    for group in ("ratings", "poles"):  # the fake gives only true way values: none is wrong
        cells = next(line for line in table.splitlines() if line.startswith(f"| {group} |")).split("|")
        assert int(cells[2]) > 0 and cells[3].strip() == "0" and cells[5].strip() == "1.000"


def test_scoring_without_recordings_says_not_run_yet(tmp_path: Path) -> None:
    samples = [s for s in evaluation_drawings("showcase") if s.version.value == "scanned"]
    assert measure_vision(samples, tmp_path / "none").startswith("NOT RUN YET")
