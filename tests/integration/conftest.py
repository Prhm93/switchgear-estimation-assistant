"""Fixtures that build small synthetic sets on the fly (nothing is read from data/projects/test/).

Projects are built at 100 dpi to keep the suite fast; the generator code path
is the same as at the 150 dpi used for the real sets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data_generator import sets
from data_generator.project import build_project, build_training_drawing, load_answers
from data_generator.schemas import AnswerKey

TEST_DPI = 100.0
# One test project per planted-problem type, plus the controls are covered by T04 being absent:
# 1 way rating, 2 extra way, 3 missing value, 5 incomer rating, 7 missing way, 8 prompt injection,
# 9 rating + missing, 11 ambiguous unit, 12 TBC, 14 poles, 17 breaking capacity, 19 busbar, 20 control.
RENDERED = [1, 2, 3, 5, 7, 8, 9, 11, 12, 14, 17, 19, 20]
TWICE = [2, 8]  # built twice for the byte-identity test
TRAINING_TWICE = [1, 2]


def _build_test(i: int, root: Path) -> tuple[Path, AnswerKey]:
    job = sets.testset_jobs(root)[i - 1]
    build_project(job.item_id, job.seed, job.purpose, job.out, list(job.plan), dpi=TEST_DPI)
    return job.out, load_answers(job.out / "answers.json")


@pytest.fixture(scope="session")
def built(tmp_path_factory) -> dict[str, tuple[Path, AnswerKey]]:
    """Rendered test projects, keyed by id ("T01", ...)."""
    root = tmp_path_factory.mktemp("set_a")
    return {sets.testset_id(i): _build_test(i, root) for i in RENDERED}


@pytest.fixture(scope="session")
def built_again(tmp_path_factory, built) -> dict[str, Path]:
    """A second build of a few projects into a different folder."""
    root = tmp_path_factory.mktemp("set_b")
    return {sets.testset_id(i): _build_test(i, root)[0] for i in TWICE}


@pytest.fixture(scope="session")
def training_pairs(tmp_path_factory) -> list[tuple[Path, Path]]:
    """Training drawings built twice, as (first, second) folders."""
    a, b = tmp_path_factory.mktemp("train_a"), tmp_path_factory.mktemp("train_b")
    pairs = []
    for job in sets.training_jobs(a, max(TRAINING_TWICE)):
        if int(job.item_id[2:]) in TRAINING_TWICE:
            build_training_drawing(job.item_id, job.seed, job.out)
            other = b / job.item_id
            build_training_drawing(job.item_id, job.seed, other)
            pairs.append((job.out, other))
    return pairs
