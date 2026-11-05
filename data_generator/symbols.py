"""IEC 60617-style symbols drawn with plain DXF lines, arcs and circles.

Our own simplified drawings of the symbol shapes, not copies of any symbol
library. Every symbol is drawn on a vertical conductor, top terminal at
``(x, y_top)``, length ``L`` downwards, and returns its extents in sheet
millimetres ``(xmin, ymin, xmax, ymax)``, which become the answer-key box.

Shapes:

- circuit breaker: a switch blade with a cross at the fixed contact
  (MCCB); the MCB adds a small overcurrent-release box on the conductor; the
  ACB adds withdrawable (draw-out) chevrons at both terminals
- switch-disconnector: a switch blade with a disconnector bar and a
  load-break circle at the fixed contact
- current transformer: a circle threaded by the conductor, with two secondary
  terminals
- earth: three falling bars
- meter: a circle with its type written inside
"""

from __future__ import annotations

from typing import Protocol

Box = tuple[float, float, float, float]


class Pen(Protocol):
    """What a symbol needs from a sheet: lines, circles and text."""

    def line(self, p1: tuple[float, float], p2: tuple[float, float], lw: int = 35) -> None: ...
    def circle(self, c: tuple[float, float], r: float, lw: int = 35) -> None: ...
    def text(self, s: str, x: float, y: float, h: float, rot: float = 0.0) -> Box: ...
    def text_width(self, s: str, h: float) -> float: ...


def _union(*boxes: Box) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _breaker_blade(pen: Pen, x: float, y_top: float, L: float, cross: bool) -> Box:
    """Conductor, open blade and fixed-contact mark common to breakers and switches."""
    contact = y_top - 0.3 * L
    pivot = y_top - 0.72 * L
    pen.line((x, y_top), (x, contact))
    pen.line((x, pivot), (x, y_top - L))
    tip = (x - 0.32 * L, contact + 0.02 * L)
    pen.line((x, pivot), tip)
    c = 0.09 * L
    if cross:
        pen.line((x - c, contact - c), (x + c, contact + c))
        pen.line((x - c, contact + c), (x + c, contact - c))
    return (tip[0], y_top - L, x + c, y_top)


def mccb(pen: Pen, x: float, y_top: float, L: float) -> Box:
    return _breaker_blade(pen, x, y_top, L, cross=True)


def mcb(pen: Pen, x: float, y_top: float, L: float) -> Box:
    box = _breaker_blade(pen, x, y_top, L, cross=True)
    # Overcurrent release: a small rectangle beside the lower conductor.
    w, h = 0.16 * L, 0.12 * L
    yb = y_top - 0.86 * L
    pen.line((x + 0.05 * L, yb), (x + 0.05 * L + w, yb))
    pen.line((x + 0.05 * L + w, yb), (x + 0.05 * L + w, yb + h))
    pen.line((x + 0.05 * L + w, yb + h), (x + 0.05 * L, yb + h))
    pen.line((x + 0.05 * L, yb + h), (x + 0.05 * L, yb))
    return _union(box, (x, yb, x + 0.05 * L + w, yb + h))


def acb(pen: Pen, x: float, y_top: float, L: float) -> Box:
    """Breaker between two draw-out chevrons."""
    k = 0.12 * L
    inner_top, inner_bottom = y_top - 1.4 * k, y_top - L + 1.4 * k
    box = _breaker_blade(pen, x, inner_top, inner_top - inner_bottom, cross=True)
    pen.line((x, y_top), (x, inner_top + 0.4 * k))
    pen.line((x, inner_bottom - 0.4 * k), (x, y_top - L))
    for yc, sign in ((inner_top + 0.4 * k, 1), (inner_bottom - 0.4 * k, -1)):
        for dy in (0.0, 0.5 * k):
            yy = yc + sign * dy
            pen.line((x - k, yy + sign * k * 0.8), (x, yy))
            pen.line((x, yy), (x + k, yy + sign * k * 0.8))
    return _union(box, (x - k, y_top - L, x + k, y_top))


def switch_disconnector(pen: Pen, x: float, y_top: float, L: float) -> Box:
    box = _breaker_blade(pen, x, y_top, L, cross=False)
    contact = y_top - 0.3 * L
    b = 0.1 * L
    pen.line((x - b, contact), (x + b, contact))  # disconnector bar
    r = 0.05 * L
    pen.circle((x + b + r, contact), r)  # load-break mark
    return _union(box, (x - b, contact - r, x + b + 2 * r, contact + r))


def current_transformer(pen: Pen, x: float, y_c: float, r: float) -> Box:
    """A CT ring centred on the conductor at ``(x, y_c)``; the conductor is drawn by the caller."""
    pen.circle((x, y_c), r)
    pen.line((x + r, y_c + 0.35 * r), (x + 2.0 * r, y_c + 0.35 * r))
    pen.line((x + r, y_c - 0.35 * r), (x + 2.0 * r, y_c - 0.35 * r))
    pen.circle((x + 2.15 * r, y_c + 0.35 * r), 0.15 * r)
    pen.circle((x + 2.15 * r, y_c - 0.35 * r), 0.15 * r)
    return (x - r, y_c - r, x + 2.3 * r, y_c + r)


def earth(pen: Pen, x: float, y_top: float, L: float) -> Box:
    """Earth: a short lead and three falling bars."""
    pen.line((x, y_top), (x, y_top - 0.45 * L))
    w = 0.32 * L
    for i, f in enumerate((1.0, 0.65, 0.3)):
        y = y_top - 0.45 * L - i * 0.16 * L
        pen.line((x - w * f, y), (x + w * f, y))
    return (x - w, y_top - 0.45 * L - 0.32 * L, x + w, y_top)


def meter(pen: Pen, x: float, y_c: float, r: float, label: str, text_h: float) -> Box:
    """A meter circle with its type (``MFM`` or ``kWh``) inside."""
    pen.circle((x, y_c), r)
    w = pen.text_width(label, text_h)
    pen.text(label, x - w / 2, y_c - text_h / 2, text_h)
    return (x - r, y_c - r, x + r, y_c + r)


BREAKERS = {"mccb": mccb, "mcb": mcb, "switch_disconnector": switch_disconnector, "acb": acb}
