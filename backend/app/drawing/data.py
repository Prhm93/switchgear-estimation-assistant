"""Drawing samples for training and for testing, kept strictly apart.

- :func:`training_drawings` reads only ``data/training/`` and only answer keys
  whose purpose is ``training`` (symbol classes and boxes; no text values).
- :func:`evaluation_drawings` reads only a test set (``data/projects/test`` or
  ``data/projects/reworded``, purpose ``test``; or the showcase) and refuses
  the training folder. Each sample carries the answer key's symbols and the
  drawing values of its version and sheet, each with only that version's box.

Answer keys are read with the shared schema only (no generator code), so the
app image can use this module. The generated sets are git-ignored: build them
with ``python -m data_generator build --set training|test|reworded``.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from backend.app.paths import REPO_ROOT
from data_generator.schemas import AnswerKey, DocumentKind, DrawingVersionKind, SymbolBox, SymbolClass, TruthValue

DATA = REPO_ROOT / "data"
TRAINING_ROOT = DATA / "training"
EVALUATION_SETS = {"test": "test", "reworded": "test", "showcase": "showcase"}  # set name -> answer-key purpose


class DataMixError(ValueError):
    """Training and test data would be mixed: refused."""


class DrawingSample(BaseModel):
    """One version of one drawing sheet, with its answer-key content."""

    project_id: str
    seed: int | None
    purpose: str
    path: Path  # the image or PDF to read
    page: int | None  # PDF page, None for an image
    dpi: float | None  # render resolution of the answer key's clean coordinates
    version: DrawingVersionKind
    sheet: int
    width_px: int
    height_px: int
    symbols: list[SymbolBox]
    values: list[TruthValue]  # drawing values on this sheet, each with only this version's region


def _keys(root: Path) -> list[tuple[Path, AnswerKey]]:
    out = []
    for path in sorted(root.glob("*/answers.json")):
        out.append((path.parent, AnswerKey.model_validate_json(path.read_bytes())))
    return out


def _samples(folder: Path, key: AnswerKey) -> list[DrawingSample]:
    samples = []
    for d in key.drawings:
        values = []
        for v in key.values:
            if v.source.document != DocumentKind.SCHEMATIC or v.source.page != d.sheet:
                continue
            regions = [r for r in v.source.regions if r.version == d.version and r.sheet == d.sheet]
            if regions:
                values.append(v.model_copy(update={"source": v.source.model_copy(update={"regions": regions})}))
        samples.append(DrawingSample(project_id=key.project_id, seed=key.seed, purpose=key.purpose,
                                     path=folder / d.file, page=d.page, dpi=d.dpi, version=d.version,
                                     sheet=d.sheet, width_px=d.width_px, height_px=d.height_px,
                                     symbols=d.symbols, values=values))
    return samples


def training_drawings(root: Path = TRAINING_ROOT) -> list[DrawingSample]:
    """Every training drawing version; refuses any answer key that is not for training."""
    samples = []
    for folder, key in _keys(root):
        if key.purpose != "training":
            raise DataMixError(f"{folder} has purpose {key.purpose!r}: only training data may be trained on")
        samples += _samples(folder, key)
    return samples


def evaluation_drawings(set_name: str, root: Path | None = None) -> list[DrawingSample]:
    """Every drawing version of a test set; refuses the training folder and training answer keys."""
    if set_name not in EVALUATION_SETS:
        raise ValueError(f"unknown set {set_name!r}; choose from {sorted(EVALUATION_SETS)}")
    root = root or (DATA / "projects" / set_name)
    if root.resolve().is_relative_to(TRAINING_ROOT.resolve()):
        raise DataMixError(f"{root} is training data and is never used for testing")
    if set_name == "showcase":
        keys = [(root, AnswerKey.model_validate_json((root / "answers.json").read_bytes()))]
    else:
        keys = _keys(root)
    samples = []
    for folder, key in keys:
        if key.purpose != EVALUATION_SETS[set_name]:
            raise DataMixError(f"{folder} has purpose {key.purpose!r}, not a {set_name} project")
        samples += _samples(folder, key)
    return samples


def class_counts(samples: list[DrawingSample]) -> dict[DrawingVersionKind, Counter]:
    """Symbols per class for each drawing version."""
    counts: dict[DrawingVersionKind, Counter] = {v: Counter() for v in DrawingVersionKind}
    for s in samples:
        counts[s.version].update(sym.cls for sym in s.symbols)
    return counts


def count_table(counts: dict[DrawingVersionKind, Counter]) -> str:
    """Markdown table: one row per symbol class, one column per drawing version."""
    versions = list(DrawingVersionKind)
    lines = ["| Class | " + " | ".join(v.value for v in versions) + " |", "|---|" + "---|" * len(versions)]
    for cls in sorted(SymbolClass, key=lambda c: -counts[versions[0]][c]):
        lines.append(f"| {cls.value} | " + " | ".join(str(counts[v][cls]) for v in versions) + " |")
    lines.append("| **all** | " + " | ".join(str(sum(counts[v].values())) for v in versions) + " |")
    return "\n".join(lines)
