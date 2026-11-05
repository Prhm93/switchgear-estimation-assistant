"""Compare a fresh showcase build with the committed one, pixel by pixel.

``python -m data_generator diagnose-showcase`` rebuilds the showcase into a
temporary folder and prints, for every degraded PNG, how many pixels differ
from the committed file and by how much, plus whether the clean 150 dpi
renders match, which degrade step first gives different pixels, and which
numpy SIMD features the CPU uses. It changes nothing. Used to measure the
cross-CPU differences documented in ``docs/stage-1.md``.

It also holds the cross-CPU acceptance rule used by the showcase test
(:func:`cross_cpu_check`): on a machine with other CPU features than the build
machine, a degraded PNG may differ from the committed one in at most
:data:`SHARE_LIMIT` of its values.
"""

from __future__ import annotations

import hashlib
import json
import platform
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from data_generator import degrade, sets
from data_generator.project import CLEAN_DPI, build_project, render_pdf_pages

SHOWCASE = sets.DATA / "projects" / "showcase"
DEGRADED = [f"drawing/schematic_sheet{s}_{v}.png" for s in (1, 2) for v in ("scanned", "photo")]

# Cross-CPU acceptance rule; the measurements behind these numbers are in docs/stage-1.md.
SHARE_LIMIT = 0.005  # at most 0.5 % of values may differ: about 3x the 0.154 % maximum measured on CI (run #7)


@dataclass
class PixelDiff:
    name: str
    shape: tuple[int, ...]
    values: int  # number of pixel values (pixels x channels)
    differing: int
    share: float  # differing / values
    max_abs: int
    histogram: dict[int, int]  # absolute difference -> count, for differences > 0


def pixel_diff(name: str, a: np.ndarray, b: np.ndarray) -> PixelDiff:
    """Differences between two images of the same shape."""
    if a.shape != b.shape:
        raise ValueError(f"{name}: shapes differ {a.shape} vs {b.shape}")
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    nz = d[d > 0]
    hist = {int(k): int(v) for k, v in zip(*np.unique(nz, return_counts=True))} if nz.size else {}
    return PixelDiff(name, tuple(a.shape), int(d.size), int(nz.size), float(nz.size / d.size),
                     int(d.max()), hist)


def pixel_sha256(img) -> str:
    """Hash of the decoded pixels (independent of PNG compression); takes an image or an array."""
    return hashlib.sha256(np.ascontiguousarray(np.asarray(img)).tobytes()).hexdigest()


@dataclass
class CrossCpuCheck:
    share: float  # share of values that differ at all

    @property
    def passed(self) -> bool:
        return self.share <= SHARE_LIMIT


def cross_cpu_check(rebuilt: np.ndarray, reference: np.ndarray) -> CrossCpuCheck:
    """Apply the cross-CPU acceptance rule to one degraded image (see the module docstring)."""
    if rebuilt.shape != reference.shape:
        raise ValueError(f"shapes differ {rebuilt.shape} vs {reference.shape}")
    d = rebuilt.astype(np.int16) != reference.astype(np.int16)
    return CrossCpuCheck(float(np.count_nonzero(d) / d.size))


def clean_render_hashes(folder: Path) -> list[str]:
    return [pixel_sha256(im) for im in render_pdf_pages(folder / "drawing" / "schematic.pdf", CLEAN_DPI)]

def cpu_features() -> dict[str, object]:
    return {"machine": platform.machine(), "processor": platform.processor(),
            "numpy_dispatch_available": sets.numpy_cpu_dispatch()}


def traced_showcase_build(out: Path) -> dict[str, dict[str, str]]:
    """Build the showcase into ``out``; return, per degraded PNG, the pixel hash after each degrade step.

    The build order is fixed (sheet 1 scanned, sheet 1 photo, sheet 2 scanned,
    sheet 2 photo) and every degrade call starts with the "marked" step.
    """
    calls: list[dict[str, str]] = []

    def record(step: str, pixels: np.ndarray) -> None:
        if step == "marked":
            calls.append({})
        calls[-1][step] = pixel_sha256(pixels)

    job = sets.showcase_job()
    degrade.TRACE = record
    try:
        build_project(job.item_id, job.seed, job.purpose, out, list(job.plan), n_ways=job.n_ways)
    finally:
        degrade.TRACE = None
    if len(calls) != len(DEGRADED):
        raise RuntimeError(f"expected {len(DEGRADED)} degrade calls, got {len(calls)}")
    return dict(zip(DEGRADED, calls))


def diagnose(reference: Path = SHOWCASE) -> dict[str, object]:
    info = json.loads((reference / "build-info.json").read_text(encoding="utf-8"))
    ref_steps = info.get("degraded_step_sha256", {})
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "showcase"
        steps = traced_showcase_build(out)
        diffs = []
        for n in DEGRADED:
            a, b = np.asarray(Image.open(out / n)), np.asarray(Image.open(reference / n))
            check = cross_cpu_check(a, b)
            diffs.append({**asdict(pixel_diff(n, a, b)),
                          "cross_cpu_check": {**asdict(check), "passed": check.passed},
                          "steps_matching_reference": {k: v == ref_steps.get(n, {}).get(k)
                                                       for k, v in steps[n].items()}})
        fresh_render = clean_render_hashes(out)
    return {
        "cpu": cpu_features(),
        "reference_build": {k: info.get(k) for k in ("platform", "python", "numpy", "pillow", "pypdfium2",
                                                     "numpy_cpu_dispatch")},
        "clean_render_150dpi_matches_reference": fresh_render == info.get("clean_render_sha256"),
        "degraded_png_diffs": diffs,
    }


def main() -> int:
    print(json.dumps(diagnose(), indent=2))
    return 0
