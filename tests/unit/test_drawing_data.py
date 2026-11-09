"""Drawing data loaders (Stage 4): training drawings and test drawings never mix.

Training samples come only from data/training/ (answer keys with purpose
"training"); test samples only from the test and reworded projects (purpose
"test"). The generated sets are git-ignored, so tests on the full sets skip
when they are not built; the mixing rules are checked on small files made here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.drawing.data import (TRAINING_ROOT, DataMixError, class_counts, count_table, evaluation_drawings,
                                      training_drawings)
from data_generator.schemas import DrawingVersionKind, SymbolClass
from data_generator.sets import DATA

SHOWCASE_KEY = DATA / "projects" / "showcase" / "answers.json"


def _project(root: Path, pid: str, purpose: str) -> Path:
    """A one-project folder with the showcase's drawings but the given id and purpose."""
    key = json.loads(SHOWCASE_KEY.read_text(encoding="utf-8"))
    key.update(project_id=pid, purpose=purpose)
    folder = root / pid
    folder.mkdir(parents=True)
    (folder / "answers.json").write_text(json.dumps(key), encoding="utf-8")
    return folder


def test_training_loader_refuses_a_project_that_is_not_training(tmp_path: Path) -> None:
    _project(tmp_path, "TR0001", "test")
    with pytest.raises(DataMixError):
        training_drawings(tmp_path)


def test_test_loader_refuses_training_data(tmp_path: Path) -> None:
    _project(tmp_path, "T01", "training")
    with pytest.raises(DataMixError):
        evaluation_drawings("test", tmp_path)
    with pytest.raises(DataMixError):
        evaluation_drawings("test", TRAINING_ROOT)  # never read the training folder as a test set


def test_test_samples_carry_symbols_and_the_truth_values_of_their_version(tmp_path: Path) -> None:
    _project(tmp_path, "T01", "test")
    samples = evaluation_drawings("test", tmp_path)
    assert {(s.version, s.sheet) for s in samples} == {(v, n) for v in DrawingVersionKind for n in (1, 2)}
    sheet1 = [s for s in samples if s.sheet == 1]
    assert all(len(s.symbols) == 13 for s in sheet1)
    for s in sheet1:
        assert s.values and all(r.version == s.version and r.sheet == 1
                                for v in s.values for r in v.source.regions)
    clean = next(s for s in samples if s.version == DrawingVersionKind.CLEAN and s.sheet == 1)
    assert clean.path.name == "schematic.pdf" and clean.page == 1 and clean.dpi == 150.0


def test_class_count_table_lists_every_class_per_version(tmp_path: Path) -> None:
    _project(tmp_path, "T01", "test")
    counts = class_counts(evaluation_drawings("test", tmp_path))
    assert counts[DrawingVersionKind.PHOTO][SymbolClass.MCCB] == 4
    table = count_table(counts)
    assert "| mcb | 3 | 3 | 3 |" in table and table.splitlines()[0].startswith("| Class | clean | scanned | photo |")


def test_full_training_set_counts() -> None:
    if not (TRAINING_ROOT / "TR0300" / "answers.json").exists():
        pytest.skip("data/training is not built (git-ignored): python -m data_generator build --set training")
    samples = training_drawings()
    assert len(samples) == 900
    counts = class_counts(samples)
    for version in DrawingVersionKind:
        assert sum(counts[version].values()) == 4015
        assert counts[version][SymbolClass.MCB] == 138 and counts[version][SymbolClass.MCCB] == 1893


def test_full_sets_never_share_a_project_or_a_seed() -> None:
    if not (TRAINING_ROOT / "TR0300" / "answers.json").exists() or not (DATA / "projects" / "test" / "T20").exists():
        pytest.skip("training or test set not built (git-ignored)")
    train = training_drawings()
    tests = evaluation_drawings("test") + evaluation_drawings("reworded")
    assert not {s.project_id for s in train} & {s.project_id for s in tests}
    assert not {s.seed for s in train} & {s.seed for s in tests}
    assert not {s.path.resolve() for s in train} & {s.path.resolve() for s in tests}
