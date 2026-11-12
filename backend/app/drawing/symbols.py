"""Breaker and switch symbols found on drawing pictures (Stage 4 Part C).

One interface, :class:`SymbolDetector`: a picture of one sheet goes in (greyscale, in the answer key's
coordinates), boxes with a class and a score come out. Detectors are chosen by name
(:func:`make_detector`), so a trained detector can be added later under its own name without touching
the callers. A trained detector would use torchvision (BSD-3-Clause); Ultralytics YOLO is AGPL and is
not used in this project.

The first detector, ``template``, has no learning. It matches templates by normalised cross-correlation
(NCC) at several sizes:

- One template per class (ACB, MCCB, MCB, switch-disconnector) is the average of symbol crops from the
  **training** drawings only (``data/training/``, clean versions), each resized to the same height.
  ``python -m backend.drawings templates`` rebuilds ``symbol_templates.npz``; the threshold was chosen on
  training drawings too (``python -m backend.drawings tune-symbols``). Test drawings are never used for either.
- The picture is halved, inverted (ink is bright) and correlated with each template at each size
  (FFT, numpy only). A score is the NCC of the template and the picture under it (-1 to 1).
- Local peaks above the threshold become boxes; overlapping boxes of any class keep only the best one
  (non-maximum suppression), so one symbol gets one class.

Found symbols are linked to the nearest way label (:func:`link_to_ways`) and turned into
``way.<id>.device`` values by :func:`detector_values`: method ``detector``, low confidence, always
reviewed, and only for ways whose device OCR did not read.
"""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from backend.app.drawing.reading import DetectedSymbol, TextBox
from backend.app.schemas import Confidence, ExtractedValue, Method
from data_generator.schemas import DocumentKind, DrawingVersionKind, Region, SourceRef, SymbolClass

BREAKER_CLASSES = (SymbolClass.ACB, SymbolClass.MCCB, SymbolClass.MCB, SymbolClass.SWITCH_DISCONNECTOR)
TEMPLATES = Path(__file__).with_name("symbol_templates.npz")
WORK_SCALE = 0.5  # detection runs at half the answer-key resolution
TEMPLATE_HEIGHT = 48  # stored template height, in work pixels
DEFAULT_THRESHOLD = 0.75  # chosen on 10 training projects only (F1 0.916 there; docs/stage-4.md, Part C)
NMS_IOU = 0.3
SIZE_STEP = 1.12  # one size to the next
# Sizes searched, as factors of the smallest and largest symbol seen in training. Wide on purpose: the training
# drawings draw symbols at about 0.6 times the size of the test drawings (docs/stage-4.md, Part C), and a real
# drawing's scale is not known in advance either.
SIZE_RANGE = (0.7, 2.0)
DEVICE_WORDS = {SymbolClass.ACB: "acb", SymbolClass.MCCB: "mccb", SymbolClass.MCB: "mcb",
                SymbolClass.SWITCH_DISCONNECTOR: "switch_disconnector"}


class SymbolDetector(Protocol):
    """Finds symbols on one sheet picture (greyscale Pillow image, answer-key coordinates)."""

    name: str

    def detect(self, image: Any) -> list[DetectedSymbol]: ...


# --- templates ------------------------------------------------------------------------------------------

def _resize(array: np.ndarray, height: int, width: int) -> np.ndarray:
    from PIL import Image

    img = Image.fromarray(np.clip(array * 255, 0, 255).astype(np.uint8))
    return np.asarray(img.resize((max(1, width), max(1, height)), Image.Resampling.BILINEAR), dtype=np.float32) / 255


def ink(image: Any, scale: float = WORK_SCALE) -> np.ndarray:
    """A greyscale picture as floats, halved and inverted: ink near 1, paper near 0."""
    from PIL import Image

    grey = image.convert("L")
    if scale != 1:
        grey = grey.resize((round(grey.width * scale), round(grey.height * scale)), Image.Resampling.BILINEAR)
    return 1.0 - np.asarray(grey, dtype=np.float32) / 255


def build_templates(crops: dict[SymbolClass, list[np.ndarray]]) -> dict[str, np.ndarray]:
    """One averaged template per class from work-scale ink crops, plus the size range seen per class."""
    out: dict[str, np.ndarray] = {}
    for cls, items in crops.items():
        if not items:
            continue
        aspect = float(np.median([c.shape[1] / c.shape[0] for c in items]))
        width = max(4, round(TEMPLATE_HEIGHT * aspect))
        out[cls.value] = np.mean([_resize(c, TEMPLATE_HEIGHT, width) for c in items], axis=0).astype(np.float32)
        heights = [c.shape[0] for c in items]
        out[f"{cls.value}__heights"] = np.array([min(heights), max(heights)], dtype=np.float32)
    return out


def save_templates(templates: dict[str, np.ndarray], path: Path = TEMPLATES) -> None:
    np.savez_compressed(path, **templates)


@lru_cache(maxsize=2)
def load_templates(path: Path = TEMPLATES) -> dict[str, np.ndarray]:
    with np.load(path) as data:
        return {k: data[k] for k in data.files}


# --- matching -------------------------------------------------------------------------------------------

def _window_sums(a: np.ndarray, h: int, w: int) -> np.ndarray:
    """Sum of every h x w window (valid positions only), by an integral image."""
    s = np.pad(a, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    return s[h:, w:] - s[:-h, w:] - s[h:, :-w] + s[:-h, :-w]


def ncc_map(picture: np.ndarray, template: np.ndarray, spectrum: tuple[np.ndarray, tuple[int, int]] | None = None
            ) -> np.ndarray:
    """Normalised cross-correlation of the template at every valid position of the picture."""
    h, w = template.shape
    H, W = picture.shape
    t = template - template.mean()
    norm = float(np.sqrt((t * t).sum()))
    if norm == 0 or h > H or w > W:
        return np.zeros((max(0, H - h + 1), max(0, W - w + 1)), dtype=np.float32)
    t /= norm
    if spectrum is None:
        shape = (H, W)
        spectrum = (np.fft.rfft2(picture, shape), shape)
    fpic, shape = spectrum
    corr = np.fft.irfft2(fpic * np.fft.rfft2(t[::-1, ::-1], shape), shape)[h - 1:H, w - 1:W]
    n = h * w
    s1 = _window_sums(picture, h, w)
    s2 = _window_sums(picture * picture, h, w)
    var = np.maximum(s2 - s1 * s1 / n, 0)
    out = np.zeros_like(corr, dtype=np.float32)
    ok = var > 1e-3 * n  # a blank window has no shape to match
    out[ok] = corr[ok] / np.sqrt(var[ok])
    return out


def _peaks(score: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    """Positions that are above the threshold and the largest of their 3 x 3 neighbourhood."""
    if score.size == 0:
        return np.empty(0, int), np.empty(0, int)
    padded = np.pad(score, 1, constant_values=-1)
    peak = score >= threshold
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            if dy == 1 and dx == 1:
                continue
            peak &= score >= padded[dy:dy + score.shape[0], dx:dx + score.shape[1]]
    return np.nonzero(peak)


def _nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    order = np.argsort(-scores)
    keep: list[int] = []
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    while order.size:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        w = np.clip(np.minimum(boxes[i, 2], boxes[rest, 2]) - np.maximum(boxes[i, 0], boxes[rest, 0]), 0, None)
        h = np.clip(np.minimum(boxes[i, 3], boxes[rest, 3]) - np.maximum(boxes[i, 1], boxes[rest, 1]), 0, None)
        inter = w * h
        order = rest[inter / (area[i] + area[rest] - inter) <= iou]
    return keep


class TemplateDetector:
    """The rule-based first detector (see the module notes)."""

    name = "template"

    def __init__(self, templates: dict[str, np.ndarray] | None = None, threshold: float = DEFAULT_THRESHOLD,
                 classes: tuple[SymbolClass, ...] = BREAKER_CLASSES) -> None:
        self.templates = templates if templates is not None else load_templates()
        self.threshold = threshold
        self.classes = [c for c in classes if c.value in self.templates]
        self.last_seconds: float | None = None

    def sizes(self, cls: SymbolClass) -> list[int]:
        """Template heights to try, in work pixels: SIZE_RANGE times the smallest and largest seen in training."""
        lo, hi = self.templates[f"{cls.value}__heights"]
        out, h = [], SIZE_RANGE[0] * float(lo)
        while h <= SIZE_RANGE[1] * float(hi):
            out.append(round(h))
            h *= SIZE_STEP
        return sorted(set(out))

    def candidates(self, picture: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[SymbolClass]]:
        spectrum = (np.fft.rfft2(picture), picture.shape)
        boxes, scores, classes = [], [], []
        for cls in self.classes:
            base = self.templates[cls.value]
            for height in self.sizes(cls):
                width = max(4, round(base.shape[1] * height / base.shape[0]))
                score = ncc_map(picture, _resize(base, height, width), spectrum)
                ys, xs = _peaks(score, self.threshold)
                for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
                    boxes.append((x, y, x + width, y + height))
                    scores.append(float(score[y, x]))
                    classes.append(cls)
        return np.array(boxes, dtype=np.float32).reshape(-1, 4), np.array(scores, dtype=np.float32), classes

    def select(self, found: tuple[np.ndarray, np.ndarray, list[SymbolClass]], size: tuple[int, int],
               threshold: float | None = None) -> list[DetectedSymbol]:
        """Boxes at or above the threshold after non-maximum suppression, in answer-key coordinates."""
        boxes, scores, classes = found
        keep = scores >= (self.threshold if threshold is None else threshold)
        boxes, scores = boxes[keep], scores[keep]
        classes = [c for c, k in zip(classes, keep.tolist(), strict=True) if k]
        out = []
        for i in _nms(boxes, scores, NMS_IOU) if len(scores) else []:
            x0, y0, x1, y1 = (boxes[i] / WORK_SCALE).tolist()
            out.append(DetectedSymbol(cls=classes[i], bbox=[x0, y0, min(x1, size[0]), min(y1, size[1])],
                                      score=round(min(1.0, max(0.0, float(scores[i]))), 3)))
        return out

    def detect(self, image: Any) -> list[DetectedSymbol]:
        start = time.perf_counter()
        out = self.select(self.candidates(ink(image)), (image.width, image.height))
        self.last_seconds = time.perf_counter() - start
        return out


DETECTORS = {"template": TemplateDetector}


def make_detector(name: str) -> SymbolDetector | None:
    """The detector called ``name``; None for ``off``."""
    if name == "off":
        return None
    if name not in DETECTORS:
        raise ValueError(f"unknown symbol detector {name!r}; choose from off, {', '.join(DETECTORS)}")
    return DETECTORS[name]()


# --- ways and values ------------------------------------------------------------------------------------

def link_to_ways(symbols: list[DetectedSymbol], labels: list[TextBox]) -> list[DetectedSymbol]:
    """Each symbol gets the way label nearest to it across the sheet (by centre x), when it is clearly
    nearer to that label than to the next one; vertical distance breaks ties. Labels are the OCR way labels."""
    if not labels:
        return symbols
    centres = sorted(((b.bbox[0] + b.bbox[2]) / 2, (b.bbox[1] + b.bbox[3]) / 2, b.text) for b in labels)
    gaps = [b[0] - a[0] for a, b in zip(centres, centres[1:], strict=False) if b[0] > a[0]]
    spacing = float(np.median(gaps)) if gaps else float("inf")
    out = []
    for s in symbols:
        cx, cy = (s.bbox[0] + s.bbox[2]) / 2, (s.bbox[1] + s.bbox[3]) / 2
        best = min(centres, key=lambda c: (abs(c[0] - cx), abs(c[1] - cy)))
        way = best[2] if abs(best[0] - cx) <= 0.4 * spacing else None
        out.append(s.model_copy(update={"way": way}))
    return out


def detector_values(symbols: list[DetectedSymbol], *, file: str, version: DrawingVersionKind, sheet: int,
                    filled: set[str]) -> list[ExtractedValue]:
    """``way.<id>.device`` for linked symbols whose way has no device yet: low confidence, always reviewed.

    Two symbols linked to the same way give nothing for it: the drawing is then not clear enough.
    """
    by_way: dict[str, list[DetectedSymbol]] = {}
    for s in symbols:
        if s.way and s.cls in DEVICE_WORDS:
            by_way.setdefault(s.way, []).append(s)
    out = []
    for way, found in sorted(by_way.items(), key=lambda kv: int(kv[0][1:])):
        field = f"way.{way}.device"
        if len(found) != 1 or field in filled:
            continue
        s = found[0]
        out.append(ExtractedValue(
            field=field, value=DEVICE_WORDS[s.cls], method=Method.DETECTOR, confidence=Confidence.LOW,
            rule=f"detector.{s.cls.value}",
            derivation=f"symbol found by the template detector (score {s.score:.2f}), linked to way {way}",
            source=SourceRef(document=DocumentKind.SCHEMATIC, file=file, page=sheet,
                             regions=[Region(version=version, sheet=sheet, bbox=[round(v, 1) for v in s.bbox])])))
    return out
