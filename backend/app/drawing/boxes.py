"""Box scoring: IoU and one-to-one matching of predicted boxes to answer-key boxes.

How a predicted box counts as right (the same rule for every drawing method):

- it has the same class as an answer-key box that is not matched yet, and
- their intersection over union (IoU) is at least ``threshold`` (0.5 by default).

Predictions are taken in order of score, highest first, and each takes the
unmatched answer box of its class with the largest IoU. So every answer box is
matched at most once, and a duplicate prediction is a false positive. Scores
are per class: true positives, false positives, misses, precision, recall, F1
and the mean IoU of the matched pairs.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel


@dataclass(frozen=True)
class Box:
    """A box with its class, and the score of a prediction (1.0 for answer-key boxes)."""

    cls: str
    bbox: Sequence[float]
    score: float = 1.0
    ref: object = field(default=None, compare=False)  # what the box belongs to, for reports


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection over union of two ``[x0, y0, x1, y1]`` boxes (0 when they do not overlap)."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union


class BoxScore(BaseModel):
    tp: int = 0
    fp: int = 0
    fn: int = 0
    iou_sum: float = 0.0  # over the matched pairs

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        return 2 * self.tp / (2 * self.tp + self.fp + self.fn) if self.tp + self.fp + self.fn else None

    @property
    def mean_iou(self) -> float | None:
        return self.iou_sum / self.tp if self.tp else None

    def add(self, other: BoxScore) -> None:
        self.tp += other.tp
        self.fp += other.fp
        self.fn += other.fn
        self.iou_sum += other.iou_sum


def match_boxes(predicted: Iterable[Box], truth: Iterable[Box], threshold: float = 0.5) -> dict[str, BoxScore]:
    """Scores per class, one-to-one matching as described in the module docstring."""
    open_truth: dict[str, list[Box]] = {}
    for t in truth:
        open_truth.setdefault(t.cls, []).append(t)
    scores: dict[str, BoxScore] = {}
    for p in sorted(predicted, key=lambda b: b.score, reverse=True):
        s = scores.setdefault(p.cls, BoxScore())
        candidates = open_truth.get(p.cls, [])
        best = max(candidates, key=lambda t: iou(p.bbox, t.bbox), default=None)
        overlap = iou(p.bbox, best.bbox) if best is not None else 0.0
        if best is not None and overlap >= threshold:
            candidates.remove(best)
            s.tp += 1
            s.iou_sum += overlap
        else:
            s.fp += 1
    for cls, left in open_truth.items():
        if left:
            scores.setdefault(cls, BoxScore()).fn += len(left)
    return scores


def total(scores: dict[str, BoxScore]) -> BoxScore:
    out = BoxScore()
    for s in scores.values():
        out.add(s)
    return out


MISSED = "(missed)"  # predicted column: no prediction overlaps this answer box enough
NOTHING_THERE = "(nothing there)"  # truth row: the prediction overlaps no answer box enough


def confusion(predicted: Iterable[Box], truth: Iterable[Box], threshold: float = 0.5) -> dict[tuple[str, str], int]:
    """Counts of (answer class, predicted class), matching boxes by overlap **whatever their class**.

    Unlike :func:`match_boxes`, a prediction may take an answer box of another class, so the table shows
    which class each answer box was given. Predictions go highest score first; each takes the unmatched
    answer box with the largest IoU if it is at least ``threshold``. Unmatched answer boxes count under
    ``MISSED``; predictions that match nothing count in the ``NOTHING_THERE`` row.
    """
    open_truth = list(truth)
    table: dict[tuple[str, str], int] = {}
    for p in sorted(predicted, key=lambda b: b.score, reverse=True):
        best = max(open_truth, key=lambda t: iou(p.bbox, t.bbox), default=None)
        if best is not None and iou(p.bbox, best.bbox) >= threshold:
            open_truth.remove(best)
            key = (best.cls, p.cls)
        else:
            key = (NOTHING_THERE, p.cls)
        table[key] = table.get(key, 0) + 1
    for t in open_truth:
        table[(t.cls, MISSED)] = table.get((t.cls, MISSED), 0) + 1
    return table
