"""The held-out reworded test set (Stage 3).

The same kinds of facts and planted problems as the test set, written in other
words. These checks build a few reworded projects on the fly (low dpi) and read
them back with independent tools, as tests/integration/test_generator.py does
for the original set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from data_generator import sets
from data_generator.planted import TEST_PLAN
from data_generator.project import build_project
from data_generator.schemas import AnswerKey, DocumentKind, ProblemKind
from tests.integration.test_generator import _norm, dxf_texts, letter_paragraphs, spec_pages

# R01 (a rating conflict), R08 (the hidden instruction line), R12 (a rating stated as TBC).
SUBSET = [1, 8, 12]


@pytest.fixture(scope="module")
def reworded(tmp_path_factory) -> dict[str, tuple[Path, AnswerKey]]:
    root = tmp_path_factory.mktemp("reworded")
    out = {}
    for i in SUBSET:
        job = sets.reworded_jobs(root)[i - 1]
        key = build_project(job.item_id, job.seed, job.purpose, job.out, list(job.plan), dpi=60.0, reword=True)
        out[job.item_id] = (job.out, key)
    return out


@pytest.fixture(scope="module")
def original(tmp_path_factory) -> dict[str, tuple[Path, AnswerKey]]:
    """The same seeds in the original wording, to show the wording is what changed."""
    root = tmp_path_factory.mktemp("original-wording")
    out = {}
    for i in SUBSET:
        job = sets.reworded_jobs(root)[i - 1]
        out[job.item_id] = (job.out, build_project(job.item_id, job.seed, job.purpose, job.out, list(job.plan),
                                                   dpi=60.0))
    return out


def test_seeds_are_2001_to_2020_and_never_shared_with_other_sets() -> None:
    jobs = sets.reworded_jobs()
    assert [j.seed for j in jobs] == list(range(2001, 2021))
    assert [j.item_id for j in jobs] == [f"R{i:02d}" for i in range(1, 21)]
    others = {j.seed for j in sets.testset_jobs()} | {j.seed for j in sets.training_jobs()} | {sets.SHOWCASE_SEED}
    assert not others & {j.seed for j in jobs}
    assert [list(j.plan) for j in jobs] == [TEST_PLAN[i] for i in range(1, 21)]
    assert all(j.reword for j in jobs)


def test_every_source_text_is_where_the_key_says(reworded) -> None:
    for pid, (folder, key) in reworded.items():
        pages, letter, texts = spec_pages(folder), "\n".join(letter_paragraphs(folder)), dxf_texts(folder)
        for v in key.values:
            src = v.source
            if src.document == DocumentKind.SPECIFICATION:
                assert _norm(src.source_text) in pages[src.page - 1], (pid, v.field, src.source_text)
            elif src.document == DocumentKind.REQUIREMENTS:
                assert src.source_text in letter, (pid, v.field)
            elif src.source_text is not None:
                assert src.source_text in texts[src.page], (pid, v.field, src.source_text)


def test_the_same_facts_are_stated_in_other_words(reworded, original) -> None:
    for pid in reworded:
        new, old = reworded[pid][1], original[pid][1]
        assert {(v.field, str(v.value), v.unit) for v in new.values} == {(v.field, str(v.value), v.unit)
                                                                         for v in old.values}, pid
        old_texts = {v.source.source_text for v in old.values if v.source.source_text}
        new_texts = [v.source.source_text for v in new.values if v.source.source_text]
        changed = sum(1 for t in new_texts if t not in old_texts)
        assert changed / len(new_texts) > 0.5, (pid, changed, len(new_texts))  # most sources are new wording
        assert [line.code for line in new.estimate] == [line.code for line in old.estimate]


def test_planted_problems_are_kept(reworded) -> None:
    kinds = {pid: [p.kind for p in key.planted] for pid, (_, key) in reworded.items()}
    assert kinds["R01"] == [ProblemKind.RATING_CONFLICT]
    assert kinds["R08"] == [ProblemKind.PROMPT_INJECTION]
    assert kinds["R12"] == [ProblemKind.MISSING_VALUE]
    folder, key = reworded["R08"]
    src = key.planted[0].sources[0]
    assert _norm(src.source_text) in spec_pages(folder)[src.page - 1]
