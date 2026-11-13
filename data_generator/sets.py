"""The fixed data sets: showcase, test and training, with their seeds and folders.

Seeds of the three sets never overlap (checked by the tests), so no training
drawing can be a copy of a test drawing.
"""

from __future__ import annotations

import json
import platform
import random
import zlib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from data_generator.design import random_design
from data_generator.planted import SHOWCASE_PLAN, TEST_PLAN, Plan, apply_plan
from data_generator.project import build_project, build_training_drawing, seed_for

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"

SHOWCASE_ID, SHOWCASE_SEED, SHOWCASE_WAYS = "SHOWCASE", 63, 8
TEST_COUNT, TEST_SEED_BASE = 20, 1000
# Held-out reworded set (Stage 3): seeds 2001 to 2020, fixed; the same planted-problem plans as T01 to T20.
REWORDED_COUNT, REWORDED_SEED_BASE = 20, 2000
TRAINING_COUNT, TRAINING_SEED_BASE = 300, 900_000
# Fresh held-out set (Stage 7): seeds 3001 to 3020, made once and frozen (FROZEN.sha256); never used for tuning.
# The same planted-problem plans as T01 to T20; even-numbered projects use the reworded wording.
FRESH_COUNT, FRESH_SEED_BASE = 20, 3000


@dataclass(frozen=True)
class Job:
    kind: str  # "project" or "training"
    item_id: str
    seed: int
    out: Path
    purpose: str = "test"
    plan: tuple = ()
    n_ways: int | None = None
    reword: bool = False


def testset_id(i: int) -> str:
    return f"T{i:02d}"


def showcase_job(root: Path = DATA) -> Job:
    return Job("project", SHOWCASE_ID, SHOWCASE_SEED, root / "projects" / "showcase", "showcase",
               tuple(SHOWCASE_PLAN), SHOWCASE_WAYS)


def testset_jobs(root: Path = DATA, count: int = TEST_COUNT) -> list[Job]:
    return [Job("project", testset_id(i), TEST_SEED_BASE + i, root / "projects" / "test" / testset_id(i), "test",
                tuple(TEST_PLAN[i])) for i in range(1, count + 1)]


def reworded_id(i: int) -> str:
    return f"R{i:02d}"


def reworded_jobs(root: Path = DATA, count: int = REWORDED_COUNT) -> list[Job]:
    """The reworded set: same kinds of facts and problems as the test set, in other words."""
    return [Job("project", reworded_id(i), REWORDED_SEED_BASE + i, root / "projects" / "reworded" / reworded_id(i),
                "test", tuple(TEST_PLAN[i]), reword=True) for i in range(1, count + 1)]


def fresh_id(i: int) -> str:
    return f"F{i:02d}"


def fresh_jobs(root: Path = DATA, count: int = FRESH_COUNT) -> list[Job]:
    """The fresh held-out set (Stage 7): new seeds, the test set's plans, every other project reworded."""
    return [Job("project", fresh_id(i), FRESH_SEED_BASE + i, root / "projects" / "fresh" / fresh_id(i), "test",
                tuple(TEST_PLAN[i]), reword=i % 2 == 0) for i in range(1, count + 1)]


def frozen_manifest(folder: Path) -> str:
    """One line per file, ``sha256  relative/path``, sorted, then the hash of those lines (the set's hash).

    ``build-info.json`` and the manifest itself are left out (they describe the build, not the data).
    """
    import hashlib

    lines = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if rel in ("build-info.json", "FROZEN.sha256"):
            continue
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}")
    body = "\n".join(lines) + "\n"
    return body + f"set  {hashlib.sha256(body.encode('utf-8')).hexdigest()}\n"


def check_frozen(folder: Path) -> str | None:
    """None when the folder matches its FROZEN.sha256, else what differs (first line only)."""
    manifest = folder / "FROZEN.sha256"
    if not manifest.exists():
        return f"{manifest} is missing"
    want = manifest.read_text(encoding="utf-8")
    have = frozen_manifest(folder)
    if want == have:
        return None
    w, h = set(want.splitlines()), set(have.splitlines())
    diff = sorted((w - h) | (h - w))
    return f"{len(diff)} manifest lines differ, for example: {diff[0]}"


def training_jobs(root: Path = DATA, count: int = TRAINING_COUNT) -> list[Job]:
    return [Job("training", f"TR{i:04d}", TRAINING_SEED_BASE + i, root / "training" / f"TR{i:04d}")
            for i in range(1, count + 1)]


def run_job(job: Job) -> str:
    if job.kind == "project":
        build_project(job.item_id, job.seed, job.purpose, job.out, list(job.plan), n_ways=job.n_ways,
                      reword=job.reword)
    else:
        build_training_drawing(job.item_id, job.seed, job.out)
    return job.item_id


def run_jobs(jobs: list[Job], workers: int = 1) -> list[str]:
    """Build every job; with ``workers > 1`` in separate processes. Output does not depend on ``workers``."""
    if workers <= 1:
        return [run_job(j) for j in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_job, jobs))


def planted_for(i: int) -> list:
    """The planted problems of test project ``i``, without rendering any file."""
    plan: Plan = TEST_PLAN[i]
    seed = TEST_SEED_BASE + i
    design = random_design(seed_for(seed, "design"), testset_id(i))
    return apply_plan(design, plan, random.Random(seed_for(seed, "planted"))).problems


def planted_markdown() -> str:
    """The text of ``data/projects/test/PLANTED.md``."""
    lines = [
        "# Planted problems in the test set",
        "",
        "Generated by `python -m data_generator planted` from `data_generator/planted.py`. Do not edit by hand.",
        "The test projects themselves are rebuilt with `python -m data_generator build --set test`.",
        "Each problem's sources (document, page, text, drawing regions) are in the project's `answers.json`.",
        "",
        "| Project | Seed | Problem | Field | What was planted |",
        "|---|---|---|---|---|",
    ]
    counts: dict[str, int] = {}
    for i in range(1, TEST_COUNT + 1):
        problems = planted_for(i)
        if not problems:
            lines.append(f"| {testset_id(i)} | {TEST_SEED_BASE + i} | none (control) | | |")
        for p in problems:
            counts[p.kind.value] = counts.get(p.kind.value, 0) + 1
            lines.append(f"| {testset_id(i)} | {TEST_SEED_BASE + i} | {p.kind.value} | {p.field or ''} | "
                         f"{p.description} |")
    lines += ["", "## Totals", "", "| Problem | Count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(counts.items())]
    controls = sum(1 for i in range(1, TEST_COUNT + 1) if not TEST_PLAN[i])
    lines += [f"| none (control projects) | {controls} |", ""]
    return "\n".join(lines)


def numpy_cpu_dispatch() -> list[str]:
    """The numpy SIMD dispatch targets this CPU supports, e.g. ``["X86_V3"]`` or ``["X86_V3", "X86_V4", ...]``."""
    from numpy._core._multiarray_umath import __cpu_dispatch__, __cpu_features__

    return [k for k in __cpu_dispatch__ if __cpu_features__.get(k)]


def build_info() -> dict[str, object]:
    """The environment a set was built in.

    Same seed gives byte-identical files in the same environment. Across
    environments the content is identical but deflate-compressed bytes (PDF
    streams, DOCX, PNG) depend on the zlib build: Python 3.14 on Windows and
    its Pillow wheel use zlib-ng, Python 3.12 on Linux uses zlib. A few pixel
    values of the scanned and photo PNGs also depend on the platform and CPU
    (see docs/stage-1.md), so the numpy CPU dispatch targets are recorded too.
    """
    from importlib.metadata import version

    from PIL import features

    info = {"python": platform.python_version(), "platform": platform.system(),
            "python_zlib": zlib.ZLIB_VERSION, "pillow_zlib": str(features.version("zlib"))}
    for lib in ("ezdxf", "matplotlib", "reportlab", "python-docx", "pypdfium2", "pillow", "numpy"):
        info[lib] = version(lib)
    info["numpy_cpu_dispatch"] = numpy_cpu_dispatch()
    return info


def write_build_info(folder: Path, extra: dict | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps({**build_info(), **(extra or {})}, indent=2, sort_keys=True) + "\n"
    (folder / "build-info.json").write_bytes(text.encode("utf-8"))
