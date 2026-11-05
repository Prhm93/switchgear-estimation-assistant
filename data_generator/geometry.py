"""Plane geometry for drawings: millimetre to pixel mapping and homographies.

One 3x3 homography moves both an image and its boxes, so a warped image and
its boxes always agree. Pillow's ``Image.transform`` wants the *inverse*
mapping (output pixel to input pixel); :func:`pil_perspective_coeffs` gives it
from the same matrix that :func:`transform_box` uses.

Pixel coordinates are continuous: the pixel at column ``i`` covers
``[i, i + 1)``, the image spans ``[0, width] x [0, height]``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

MM_PER_INCH = 25.4

Matrix = np.ndarray  # 3x3 float64


def mm_to_px(x_mm: float, y_mm: float, page_height_mm: float, dpi: float) -> tuple[float, float]:
    """DXF millimetres (origin bottom-left, y up) to page pixels (origin top-left, y down)."""
    s = dpi / MM_PER_INCH
    return x_mm * s, (page_height_mm - y_mm) * s


def mm_box_to_px(box_mm: Sequence[float], page_height_mm: float, dpi: float) -> list[float]:
    """``[xmin, ymin, xmax, ymax]`` in DXF millimetres to a pixel box ``[x0, y0, x1, y1]``."""
    x0, y_top = mm_to_px(box_mm[0], box_mm[3], page_height_mm, dpi)
    x1, y_bottom = mm_to_px(box_mm[2], box_mm[1], page_height_mm, dpi)
    return [x0, y_top, x1, y_bottom]


def homography_from_points(src: Sequence[Sequence[float]], dst: Sequence[Sequence[float]]) -> Matrix:
    """The homography that maps four ``src`` points onto four ``dst`` points."""
    rows = []
    rhs = []
    for (x, y), (u, v) in zip(src, dst, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs += [u, v]
    h = np.linalg.solve(np.array(rows, dtype=np.float64), np.array(rhs, dtype=np.float64))
    return np.append(h, 1.0).reshape(3, 3)


def rotation_about(cx: float, cy: float, degrees: float, dx: float = 0.0, dy: float = 0.0) -> Matrix:
    """Rotate by ``degrees`` (counter-clockwise on screen) about ``(cx, cy)``, then shift."""
    a = math.radians(-degrees)  # y points down, so screen-CCW is a negative angle
    c, s = math.cos(a), math.sin(a)
    to_origin = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1]], dtype=np.float64)
    rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)
    back = np.array([[1, 0, cx + dx], [0, 1, cy + dy], [0, 0, 1]], dtype=np.float64)
    return back @ rot @ to_origin


def scale(sx: float, sy: float | None = None) -> Matrix:
    """A scaling matrix."""
    return np.diag([sx, sx if sy is None else sy, 1.0])


def apply(h: Matrix, points: Sequence[Sequence[float]]) -> np.ndarray:
    """Map points ``[[x, y], ...]`` through ``h``."""
    p = np.asarray(points, dtype=np.float64)
    ph = np.hstack([p, np.ones((len(p), 1))]) @ h.T
    return ph[:, :2] / ph[:, 2:3]


def transform_box(h: Matrix, box: Sequence[float]) -> list[float]:
    """The axis-aligned box around the four mapped corners of ``box``."""
    x0, y0, x1, y1 = box
    pts = apply(h, [[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    return [float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())]


def clip_box(box: Sequence[float], width: int, height: int) -> list[float]:
    """Clip a box to the image ``[0, width] x [0, height]``."""
    x0, y0, x1, y1 = box
    return [max(0.0, x0), max(0.0, y0), min(float(width), x1), min(float(height), y1)]


def round_box(box: Sequence[float]) -> list[float]:
    """Round to 0.01 px so the JSON is short and stable."""
    return [round(float(v), 2) for v in box]


def pil_perspective_coeffs(h: Matrix) -> tuple[float, ...]:
    """The 8 coefficients Pillow's ``Image.PERSPECTIVE`` needs for forward mapping ``h``.

    Pillow maps each output pixel back to the input, so it needs ``inv(h)``,
    normalised so the last entry is 1.
    """
    inv = np.linalg.inv(h)
    inv = inv / inv[2, 2]
    return tuple(float(v) for v in inv.flatten()[:8])


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    """Intersection over union of two boxes."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0
