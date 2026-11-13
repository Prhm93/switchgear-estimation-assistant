"""The fixed data sets: PLANTED.md in sync, seeds apart, git-ignore rules in place."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from data_generator import sets
from data_generator.planted import TEST_PLAN
from data_generator.schemas import ProblemKind

REPO = Path(__file__).resolve().parents[2]
PLANTED_MD = REPO / "data" / "projects" / "test" / "PLANTED.md"


def test_committed_planted_md_is_up_to_date():
    assert PLANTED_MD.read_bytes() == sets.planted_markdown().encode("utf-8"), (
        "PLANTED.md is out of date: run python -m data_generator planted")


def test_plan_has_every_problem_type_and_exactly_one_ambiguous_unit_and_one_injection():
    kinds = [k for plan in TEST_PLAN.values() for k, _ in plan]
    assert set(kinds) == set(ProblemKind)
    assert kinds.count(ProblemKind.AMBIGUOUS_UNIT) == 1
    assert kinds.count(ProblemKind.PROMPT_INJECTION) == 1
    assert sorted(TEST_PLAN) == list(range(1, sets.TEST_COUNT + 1))
    assert any(not plan for plan in TEST_PLAN.values()), "keep some control projects with no problem"


def test_planted_problems_are_found_for_every_test_project():
    for i in range(1, sets.TEST_COUNT + 1):
        assert [p.kind for p in sets.planted_for(i)] == [k for k, _ in TEST_PLAN[i]]


def test_training_and_test_never_share_a_seed_or_a_folder():
    test_seeds = {j.seed for j in sets.testset_jobs()}
    training_seeds = {j.seed for j in sets.training_jobs()}
    assert len(test_seeds) == sets.TEST_COUNT and len(training_seeds) == sets.TRAINING_COUNT
    assert not test_seeds & training_seeds
    assert sets.SHOWCASE_SEED not in test_seeds | training_seeds
    test_dirs = {j.out.parent for j in sets.testset_jobs()}
    training_dirs = {j.out.parent for j in sets.training_jobs()}
    assert test_dirs == {sets.DATA / "projects" / "test"} and training_dirs == {sets.DATA / "training"}


@pytest.mark.skipif(shutil.which("git") is None or not (REPO / ".git").exists(), reason="needs a git checkout")
@pytest.mark.parametrize(
    "path, ignored",
    [
        ("data/projects/test/T01/answers.json", True),
        ("data/projects/test/PLANTED.md", False),
        ("data/training/TR0001/photo.png", True),
        ("data/external/my-drawings/answers.json", True),
        ("data/external/denylist.txt", True),
        ("data/external/SOURCES.template.md", False),
        ("data/projects/showcase/answers.json", False),
        ("data/catalogue/catalogue.csv", False),
    ],
)
def test_git_ignore_rules(path, ignored):
    result = subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=REPO)
    assert (result.returncode == 0) == ignored, path


def test_the_fresh_set_has_its_own_seeds_and_folder_and_mixes_wordings():
    fresh = sets.fresh_jobs()
    seeds = {j.seed for j in fresh}
    others = ({j.seed for j in sets.testset_jobs()} | {j.seed for j in sets.reworded_jobs()}
              | {j.seed for j in sets.training_jobs()} | {sets.SHOWCASE_SEED})
    assert len(seeds) == sets.FRESH_COUNT and not seeds & others
    assert [j.item_id for j in fresh[:2]] == ["F01", "F02"] and all(j.out.parent.name == "fresh" for j in fresh)
    assert [j.reword for j in fresh[:4]] == [False, True, False, True]
    assert all(j.purpose == "test" for j in fresh)


def test_the_frozen_manifest_notices_any_change(tmp_path):
    (tmp_path / "F01").mkdir()
    (tmp_path / "F01" / "answers.json").write_text("{}", encoding="utf-8")
    (tmp_path / "build-info.json").write_text("{}", encoding="utf-8")
    (tmp_path / "FROZEN.sha256").write_text(sets.frozen_manifest(tmp_path), encoding="utf-8")
    assert sets.check_frozen(tmp_path) is None
    assert "build-info" not in (tmp_path / "FROZEN.sha256").read_text(encoding="utf-8")
    (tmp_path / "F01" / "answers.json").write_text('{"x": 1}', encoding="utf-8")
    assert "differ" in sets.check_frozen(tmp_path)
