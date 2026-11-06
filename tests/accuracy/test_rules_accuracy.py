"""Rules-mode accuracy on a small subset of the test projects, built on the fly.

CI runs this subset only. The full baseline on all 20 test projects comes
from ``python -m backend.evaluate`` and is reported in docs/stage-2.md.

The subset is T01 (a rating conflict) and T08 (the hidden instruction line).
The thresholds sit just below the full-set result so that a broken rule
fails here; they are not the reported numbers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.evaluation import total
from backend.evaluate import run
from data_generator import sets
from data_generator.project import build_project

SUBSET = [1, 8]


@pytest.fixture(scope="module")
def folders(tmp_path_factory) -> list[Path]:
    root = tmp_path_factory.mktemp("accuracy")
    out = []
    for i in SUBSET:
        job = sets.testset_jobs(root)[i - 1]
        build_project(job.item_id, job.seed, job.purpose, job.out, list(job.plan), dpi=100.0)
        out.append(job.out)
    return out


def test_rules_with_the_dxf_find_every_value_without_false_ones(folders: list[Path]) -> None:
    t = total(run(folders, with_dxf=True)[0])
    assert t.precision >= 0.99 and t.recall >= 0.99, t


def test_rules_without_the_dxf_read_only_the_documents(folders: list[Path]) -> None:
    grouped, _ = run(folders, with_dxf=False)
    t = total(grouped)
    assert t.precision >= 0.99, t
    assert 0.3 < t.recall < 0.7, t  # no drawing values: the drawing PDF has no text layer and PNGs need OCR
    assert all(s.tp == 0 for g, s in grouped.items() if g.startswith("way.") and g.endswith(".cable_length"))
