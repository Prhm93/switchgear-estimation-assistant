"""Compare a fresh showcase build with the committed one, pixel by pixel.

``python -m data_generator diagnose-showcase`` rebuilds the showcase into a
temporary folder and prints, for every degraded PNG, how many pixels differ
from the committed file and by how much, plus whether the clean 150 dpi
renders match and which numpy SIMD features the CPU uses. It changes nothing.
Used to measure the cross-CPU differences documented in ``docs/stage-1.md``.
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

from data_generator import sets
from data_generator.project import CLEAN_DPI, build_project, render_pdf_pages

SHOWCASE = sets.DATA / "projects" / "showcase"
DEGRADED = [f"drawing/schematic_sheet{s}_{v}.png" for s in (1, 2) for v in ("scanned", "photo")]


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


def pixel_sha256(img: Image.Image) -> str:
    """Hash of the decoded pixels (independent of PNG compression)."""
    return hashlib.sha256(np.asarray(img).tobytes()).hexdigest()


def clean_render_hashes(folder: Path) -> list[str]:
    return [pixel_sha256(im) for im in render_pdf_pages(folder / "drawing" / "schematic.pdf", CLEAN_DPI)]


def cpu_features() -> dict[str, object]:
    from numpy._core._multiarray_umath import __cpu_dispatch__, __cpu_features__

    return {"machine": platform.machine(), "processor": platform.processor(),
            "numpy_dispatch_available": [k for k in __cpu_dispatch__ if __cpu_features__.get(k)]}


def diagnose(reference: Path = SHOWCASE) -> dict[str, object]:
    job = sets.showcase_job()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "showcase"
        build_project(job.item_id, job.seed, job.purpose, out, list(job.plan), n_ways=job.n_ways)
        diffs = [asdict(pixel_diff(n, np.asarray(Image.open(out / n)), np.asarray(Image.open(reference / n))))
                 for n in DEGRADED]
        fresh_render = clean_render_hashes(out)
    info = json.loads((reference / "build-info.json").read_text(encoding="utf-8"))
    return {
        "cpu": cpu_features(),
        "reference_build": {k: info.get(k) for k in ("platform", "python", "numpy", "pillow", "pypdfium2")},
        "clean_render_150dpi_matches_reference": fresh_render == info.get("clean_render_sha256"),
        "degraded_png_diffs": diffs,
    }


def main() -> int:
    print(json.dumps(diagnose(), indent=2))
    return 0
