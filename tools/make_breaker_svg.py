"""Draw the illustrative air circuit breaker as a pencil-style SVG: frontend/static/img/breaker.svg.

An invented, generic breaker, not any real product: a withdrawable four-pole air circuit breaker built
from boxes, prisms and short cylinders in rough, illustrative proportions (units are arbitrary, nothing
is to scale). One fixed three-quarter view from the front right, projected with simple orthographic
maths. Hidden edges are removed back to front: every visible face is filled with the paper colour, so a
nearer face covers what lies behind it (the painter's method). The pencil look is geometry only, no SVG
filter: each edge is drawn twice with small offsets and a gentle bend, ends overshoot by 1 to 3 px, and
width and opacity vary; shaded faces get thin 45 degree hatching; a few faint construction lines.

Each part is one SVG group with an id (``bk-<part>``) and a 3D explode vector, given to the page as its
projection (``--dx`` and ``--dy`` in user units, scaled by ``--explode`` from 0 to 1 in CSS). Leader
lines end on anchor points defined in 3D on each part, so a leader follows its part when it moves.

Standard library only, fixed random seed: the output is byte-identical on every run.

    python tools/make_breaker_svg.py           # writes frontend/static/img/breaker.svg
    python tools/make_breaker_svg.py --check   # exit 1 if the committed file is out of date
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "frontend" / "static" / "img" / "breaker.svg"
SEED = 6021
WIDTH, HEIGHT = 820, 600
AZIMUTH, ELEVATION = math.radians(36), math.radians(24)

Vec = tuple[float, float, float]
Pt = tuple[float, float]

# --- projection --------------------------------------------------------------------------------------

_CAM: Vec = (math.sin(AZIMUTH) * math.cos(ELEVATION), math.sin(ELEVATION), math.cos(AZIMUTH) * math.cos(ELEVATION))
_RIGHT: Vec = (math.cos(AZIMUTH), 0.0, -math.sin(AZIMUTH))
_UP: Vec = (-math.sin(AZIMUTH) * math.sin(ELEVATION), math.cos(ELEVATION), -math.cos(AZIMUTH) * math.sin(ELEVATION))


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def project(p: Vec) -> Pt:
    """Model space (x right, y up, z towards the front) to screen units before scaling (y down)."""
    return (dot(p, _RIGHT), -dot(p, _UP))


def depth(p: Vec) -> float:
    """Larger is nearer the viewer."""
    return dot(p, _CAM)


# --- geometry ----------------------------------------------------------------------------------------

@dataclass
class Face:
    points: list[Vec]
    hatch: bool = False        # a shaded face: thin 45 degree hatching
    flat: bool = False         # a detail drawn on a surface (window, panel): never culled by its solid
    css: str = ""              # an extra class, e.g. the trip marker
    layer: int = 0             # drawing layer within a part: details on a surface come after the surface
    order: float = 0.0         # depth of the whole solid, so that a solid's faces stay together


@dataclass
class Part:
    key: str
    label: str
    explode: Vec = (0.0, 0.0, 0.0)
    anchor: Vec = (0.0, 0.0, 0.0)
    side: str = "right"        # label column
    faces: list[Face] = field(default_factory=list)
    marks: list[list[Vec]] = field(default_factory=list)   # stroke-only polylines on surfaces
    group: str = ""            # svg id; defaults to bk-<key>

    def solid(self, faces: list[Face], layer: int = 0) -> None:
        """Add one solid (or one surface detail); its faces are drawn together, far solids first."""
        middle = centroid([p for f in faces for p in f.points]) if faces else (0.0, 0.0, 0.0)
        for f in faces:
            f.layer, f.order = layer, depth(middle)
        self.faces.extend(faces)


def newell(points: list[Vec]) -> Vec:
    nx = ny = nz = 0.0
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return (nx, ny, nz)


def centroid(points: list[Vec]) -> Vec:
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n, sum(p[2] for p in points) / n)


def outward(faces: list[list[Vec]]) -> list[tuple[list[Vec], Vec]]:
    """Each face of a convex solid with its normal pointing out of the solid."""
    middle = centroid([p for f in faces for p in f])
    out = []
    for f in faces:
        n = newell(f)
        if dot(n, sub(centroid(f), middle)) < 0:
            f, n = list(reversed(f)), (-n[0], -n[1], -n[2])
        out.append((f, n))
    return out


def visible(faces: list[list[Vec]], shade: str = "") -> list[Face]:
    """The faces of a convex solid that face the viewer. ``shade`` names normals to hatch: 'x', '-y'."""
    kept = []
    for f, n in outward(faces):
        if dot(n, _CAM) <= 1e-9:
            continue
        length = math.sqrt(dot(n, n)) or 1.0
        unit = (n[0] / length, n[1] / length, n[2] / length)
        hatch = ("x" in shade and unit[0] > 0.9) or ("-y" in shade and unit[1] < -0.9)
        kept.append(Face(f, hatch=hatch))
    return kept


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, shade: str = "x") -> list[Face]:
    c = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    p = lambda i, j, k: c[i * 4 + j * 2 + k]  # noqa: E731
    faces = [[p(0, 0, 0), p(0, 1, 0), p(0, 1, 1), p(0, 0, 1)], [p(1, 0, 0), p(1, 0, 1), p(1, 1, 1), p(1, 1, 0)],
             [p(0, 0, 0), p(0, 0, 1), p(1, 0, 1), p(1, 0, 0)], [p(0, 1, 0), p(1, 1, 0), p(1, 1, 1), p(0, 1, 1)],
             [p(0, 0, 0), p(1, 0, 0), p(1, 1, 0), p(0, 1, 0)], [p(0, 0, 1), p(0, 1, 1), p(1, 1, 1), p(1, 0, 1)]]
    return visible(faces, shade)


def prism_x(profile: list[tuple[float, float]], x0: float, x1: float, shade: str = "x") -> list[Face]:
    """A convex (y, z) profile extruded along x."""
    a = [(x0, y, z) for y, z in profile]
    b = [(x1, y, z) for y, z in profile]
    sides = [[a[i], a[(i + 1) % len(a)], b[(i + 1) % len(b)], b[i]] for i in range(len(a))]
    return visible([a, b] + sides, shade)


def cylinder_z(cx: float, cy: float, r: float, z0: float, z1: float, n: int = 10, shade: str = "") -> list[Face]:
    ring = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    a = [(x, y, z0) for x, y in ring]
    b = [(x, y, z1) for x, y in ring]
    sides = [[a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]] for i in range(n)]
    return visible([a, b] + sides, shade)


def circle_z(cx: float, cy: float, r: float, z: float, n: int = 14) -> list[Vec]:
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n), z) for i in range(n)]
    return pts + [pts[0]]


def panel_z(x0: float, x1: float, y0: float, y1: float, z: float, css: str = "") -> Face:
    """A flat rectangle on a front-facing surface (a window or a recess)."""
    return Face([(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)], flat=True, css=css)


# --- the invented breaker ----------------------------------------------------------------------------

POLES = [8.25, 22.75, 37.25, 51.75]   # pole centres along x
FRONT = 43.0                           # front face of the fascia plate


def model() -> list[Part]:
    """The parts, in drawing order (back to front for this view)."""
    rails = Part("slide-rails", "Slide rails (cradle)", anchor=(65.5, -1.5, 55.0), side="right")
    for x0, x1 in ((-8.0, -3.0), (63.0, 68.0)):
        rails.solid(box(x0, x1, -5.0, -1.5, -14.0, 62.0, shade="x"))
        rails.solid(box(x0 + 1.5, x1 - 1.5, -1.5, 2.5, -14.0, 30.0, shade="x"))   # flange towards the body
    rails.marks += [[(65.5, -1.5, z), (65.5, -1.5, z + 3.0)] for z in (36.0, 44.0, 52.0)]  # stop notches

    terminals = Part("rear-terminals", "Rear terminals", anchor=(POLES[-1], 33.6, -17.0), side="right")
    for x in POLES:
        terminals.solid(box(x - 1.6, x + 1.6, 30.4, 33.6, -21.0, -9.0, shade="x"))
        terminals.marks.append(circle_z(x, 32.0, 0.8, -21.0, n=8))           # bolt hole at the end

    isolating = Part("isolating-contacts", "Isolating contacts", anchor=(POLES[-1] + 3.2, 12.0, -5.0), side="right")
    for x in POLES:
        for y in (32.0, 12.0):
            isolating.solid(cylinder_z(x, y, 3.3, -9.0, 0.0, n=8))
            isolating.marks += [circle_z(x, y, 3.35, z, n=8) for z in (-3.0, -6.0)]  # finger rings

    frame = Part("frame", "Breaker body", anchor=(60.0, 30.0, 40.0), side="right")
    frame.solid(box(0.0, 60.0, 0.0, 46.0, 0.0, 1.2))      # back wall
    frame.solid(box(0.0, 1.2, 0.0, 46.0, 0.0, 40.0))      # left wall
    frame.solid(box(0.0, 60.0, 0.0, 1.2, 0.0, 40.0))      # base
    for x in (15.5, 30.0, 44.5):                           # phase barriers between the poles
        frame.solid(box(x - 0.4, x + 0.4, 1.2, 40.0, 1.2, 26.0, shade="x"))

    fixed = Part("fixed-contacts", "Fixed contacts", anchor=(POLES[-1] + 2.0, 34.0, 6.0), side="right")
    moving = Part("moving-contacts", "Moving contacts", anchor=(POLES[-1] + 1.6, 24.0, 12.5), side="right")
    arcing = Part("arcing-contacts", "Arcing contacts", anchor=(POLES[-1] + 1.4, 41.0, 9.0), side="right")
    for x in POLES:
        for y0 in (29.5, 10.0):
            fixed.solid(box(x - 2.0, x + 2.0, y0, y0 + 4.5, 1.2, 9.0))
        moving.solid(prism_x([(13.0, 14.5), (15.5, 18.5), (32.5, 11.5), (30.5, 9.0)], x - 1.6, x + 1.6))
        moving.solid(cylinder_z(x, 15.0, 1.4, 14.0, 22.0, n=8))           # pivot pin towards the mechanism
        arcing.solid(prism_x([(34.0, 5.0), (34.0, 8.5), (45.5, 11.5), (46.5, 8.0)], x - 1.4, x + 1.4))

    frame_front = Part("frame", "Breaker body", group="bk-frame-front")
    frame_front.solid(box(58.8, 60.0, 0.0, 46.0, 0.0, 1.2))     # right posts and rails of the open side
    frame_front.solid(box(58.8, 60.0, 0.0, 46.0, 38.8, 40.0))
    frame_front.solid(box(58.8, 60.0, 44.8, 46.0, 0.0, 40.0))
    frame_front.solid(box(58.8, 60.0, 0.0, 1.2, 0.0, 40.0))
    frame_front.solid(box(0.0, 60.0, 44.8, 46.0, 38.8, 40.0))

    chutes = Part("arc-chutes", "Arc chutes", explode=(0.0, 17.0, 0.0), anchor=(POLES[0] - 6.0, 56.0, 18.0),
                  side="left")
    for x in POLES:
        x0, x1, y0, y1, z0, z1 = x - 6.0, x + 6.0, 46.0, 58.0, 5.0, 30.0
        chutes.solid(box(x0, x1, y0, y1, z0, z1, shade="x"))
        plates = 14
        for i in range(1, plates + 1):                     # thin vertical splitter plates
            px = x0 + (x1 - x0) * i / (plates + 1)
            chutes.marks.append([(px, y1, z0 + 1.0), (px, y1, z1 - 1.0)])          # seen on the top
            chutes.marks.append([(px, y0 + 1.0, z1), (px, y1 - 0.6, z1)])          # seen at the front
        chutes.marks.append([(x1, y0 + 2.0, z0 + 2.0), (x1, y1 - 2.0, z0 + 2.0)])  # side plate rivet line

    aux = Part("auxiliary-switches", "Auxiliary switches", anchor=(5.0, 51.5, 36.0), side="left")
    aux.solid(box(3.0, 31.0, 46.0, 49.0, 32.0, 39.0))
    for i in range(6):
        x = 5.0 + i * 4.3
        aux.solid(box(x, x + 2.6, 49.0, 51.5, 34.0, 37.0))

    plate = Part("front-plate", "Front plate", explode=(0.0, 0.0, 18.0), anchor=(-3.0, 40.0, FRONT), side="left")
    plate.solid(box(-3.0, 63.0, 0.0, 48.0, 40.0, FRONT, shade="x"))
    z = FRONT + 0.01
    for panel in (panel_z(19.0, 30.0, 37.0, 43.0, z),           # spring-charged window
                  panel_z(32.5, 37.5, 37.0, 43.0, z),           # trip indicator
                  panel_z(40.0, 56.0, 37.0, 43.0, z),           # operations counter
                  panel_z(35.0, 57.0, 15.5, 32.0, z),           # trip unit
                  panel_z(36.0, 57.0, 3.0, 11.0, z)):           # charging handle recess
        plate.solid([panel], layer=1)
    plate.solid([panel_z(37.5, 54.5, 24.5, 30.0, z + 0.01)], layer=2)          # trip unit display window
    plate.solid([panel_z(33.3, 36.7, 38.0, 42.0, z + 0.02, css="trip-marker")], layer=2)
    plate.solid(cylinder_z(10.0, 32.0, 3.4, FRONT, FRONT + 1.6, n=14), layer=3)  # ON push button
    plate.solid(cylinder_z(10.0, 22.0, 3.4, FRONT, FRONT + 1.6, n=14), layer=3)  # OFF push button
    plate.solid(box(42.0, 51.0, 5.0, 9.0, FRONT, FRONT + 3.2), layer=3)           # charging handle
    zb = FRONT + 1.61
    plate.marks += [
        [(10.0, 30.6, zb), (10.0, 33.4, zb)],                                    # "I" on the ON button
        circle_z(10.0, 22.0, 1.3, zb, n=10),                                      # "O" on the OFF button
        [(43.0, 7.0, FRONT + 3.21), (50.0, 7.0, FRONT + 3.21)],                  # grip line
        [(23.5, 38.5, z), (23.5, 41.5, z), (26.5, 41.5, z)],                     # spring symbol
    ]
    plate.marks += [[(x, 37.6, z), (x, 42.4, z)] for x in (44.0, 48.0, 52.0)]   # counter digit cells
    plate.marks += [circle_z(x, 19.5, 0.9, z, n=8) for x in (40.0, 44.0, 48.0)]   # trip unit keys

    indicator = Part("position-indicator", "Position indicator", explode=(0.0, 0.0, 18.0),
                     anchor=(4.0, 7.0, FRONT + 0.4), side="left")
    zi = FRONT + 0.02
    indicator.solid([panel_z(4.0, 16.0, 4.0, 10.0, zi)])
    indicator.marks += [[(x, 4.8, zi), (x, 6.2, zi)] for x in (6.5, 10.0, 13.5)]   # disconnected, test, connected
    indicator.marks.append([(12.4, 8.9, zi), (13.5, 7.0, zi), (14.6, 8.9, zi), (12.4, 8.9, zi)])  # pointer

    return [rails, terminals, isolating, frame, fixed, moving, arcing, frame_front, chutes, aux, plate, indicator]


# --- pencil rendering --------------------------------------------------------------------------------

class Pencil:
    """Turns projected edges into wobbly double strokes. All randomness comes from one seeded generator."""

    def __init__(self, scale: float, offset: Pt) -> None:
        self.rng = random.Random(SEED)
        self.scale, self.offset = scale, offset

    def screen(self, p: Vec) -> Pt:
        x, y = project(p)
        return (x * self.scale + self.offset[0], y * self.scale + self.offset[1])

    def jitter(self, amount: float) -> float:
        return self.rng.uniform(-amount, amount)

    def stroke(self, a: Pt, b: Pt, overshoot: bool = True, wobble: float = 0.6) -> str:
        """One pencil pass along a to b: offset by up to 0.6 px, a gentle bend, ends overshooting 1 to 3 px."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        o1 = self.rng.uniform(1.0, 3.0) if overshoot and length > 6 else 0.0
        o2 = self.rng.uniform(1.0, 3.0) if overshoot and length > 6 else 0.0
        shift = (self.jitter(wobble), self.jitter(wobble))
        sx, sy = a[0] - ux * o1 + shift[0], a[1] - uy * o1 + shift[1]
        ex, ey = b[0] + ux * o2 + shift[0], b[1] + uy * o2 + shift[1]
        if length < 8:  # too short to show a bend
            return f"M{sx:.1f} {sy:.1f}L{ex:.1f} {ey:.1f}"
        bend = self.jitter(min(0.9, length * 0.02))
        mx, my = (sx + ex) / 2 - uy * bend, (sy + ey) / 2 + ux * bend
        return f"M{sx:.1f} {sy:.1f}Q{mx:.1f} {my:.1f} {ex:.1f} {ey:.1f}"

    def strokes(self, edges: list[tuple[Pt, Pt]], css: str = "s", passes: int = 2) -> str:
        """Two passes over the edges: a full one and a lighter partial one on the longer edges, so the
        tone varies along a line. Small marks get one pass."""
        # Small marks (rings, symbols) get a lighter wobble and no overshoot, or they read as stars.
        first = "".join(self.stroke(a, b) if passes > 1 else self.stroke(a, b, overshoot=False, wobble=0.2)
                        for a, b in edges)
        parts = []
        for a, b in edges:
            if passes < 2 or math.hypot(b[0] - a[0], b[1] - a[1]) < 18:
                continue
            t0, t1 = self.rng.uniform(0.0, 0.35), self.rng.uniform(0.6, 1.0)
            pa = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            pb = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            parts.append(self.stroke(pa, pb, overshoot=False))
        w1, o1 = self.rng.uniform(0.95, 1.3), self.rng.uniform(0.6, 0.8)
        out = (f'<path class="{css}" pathLength="1" stroke-width="{w1:.2f}" stroke-opacity="{o1:.2f}" '
               f'd="{first}"/>')
        if parts:
            w2, o2 = self.rng.uniform(0.8, 1.0), self.rng.uniform(0.5, 0.62)
            out += (f'<path class="{css}" pathLength="1" stroke-width="{w2:.2f}" stroke-opacity="{o2:.2f}" '
                    f'd="{"".join(parts)}"/>')
        return out

    def hatch(self, poly: list[Pt], spacing: float = 5.0) -> str:
        """45 degree lines clipped to a polygon."""
        segs = []
        cs = [p[0] + p[1] for p in poly]             # lines x + y = c
        c = math.floor(min(cs) / spacing) * spacing + spacing
        while c < max(cs):
            hits = []
            for i, a in enumerate(poly):
                b = poly[(i + 1) % len(poly)]
                fa, fb = a[0] + a[1] - c, b[0] + b[1] - c
                if (fa < 0) != (fb < 0):
                    t = fa / (fa - fb)
                    hits.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            hits.sort()
            for i in range(0, len(hits) - 1, 2):
                (x0, y0), (x1, y1) = hits[i], hits[i + 1]
                if math.hypot(x1 - x0, y1 - y0) > 2.5:
                    segs.append(f"M{x0 + 0.8:.1f} {y0 - 0.8:.1f}L{x1 - 0.8:.1f} {y1 + 0.8:.1f}")
            c += spacing
        return f'<path class="h" pathLength="1" d="{"".join(segs)}"/>' if segs else ""


def fmt(v: float) -> str:
    s = f"{v:.1f}"
    return "0" if s in ("0.0", "-0.0") else s.rstrip("0").rstrip(".")


def build() -> str:
    parts = model()
    # Fit the model, closed and exploded, between the two label columns.
    points = []
    for part in parts:
        for f in part.faces:
            for p in f.points:
                points.append(project(p))
                points.append(project((p[0] + part.explode[0], p[1] + part.explode[1], p[2] + part.explode[2])))
    min_x, max_x = min(p[0] for p in points), max(p[0] for p in points)
    min_y, max_y = min(p[1] for p in points), max(p[1] for p in points)
    left, right, top, bottom = 200.0, WIDTH - 200.0, 40.0, HEIGHT - 60.0
    scale = min((right - left) / (max_x - min_x), (bottom - top) / (max_y - min_y))
    offset = (left + ((right - left) - (max_x - min_x) * scale) / 2 - min_x * scale,
              top + ((bottom - top) - (max_y - min_y) * scale) / 2 - min_y * scale)
    pen = Pencil(scale, offset)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" class="breaker" viewBox="0 0 {WIDTH} {HEIGHT}" '
           f'fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" role="img" '
           f'aria-labelledby="bk-title">',
           '<title id="bk-title">Illustrative line drawing of an invented air circuit breaker, not to scale</title>']

    # Faint construction lines: the ground line of the rails and the pole centre lines.
    con = []
    a, b = pen.screen((-30.0, -5.0, 62.0)), pen.screen((100.0, -5.0, 62.0))
    con.append(pen.stroke(a, b, overshoot=False))
    for x in POLES:
        a, b = pen.screen((x, 64.0, 17.5)), pen.screen((x, -4.0, 17.5))
        con.append(pen.stroke(a, b, overshoot=False))
    a, b = pen.screen((-12.0, 32.0, -21.0)), pen.screen((-12.0, 32.0, 70.0))
    con.append(pen.stroke(a, b, overshoot=False))
    out.append(f'<g class="bk-construction"><path class="c" d="{"".join(con)}"/></g>')

    out.append('<g class="bk-art">')
    anchors, labels = [], []
    for part in parts:
        ex = project(part.explode)
        dx, dy = ex[0] * scale, ex[1] * scale
        gid = part.group or f"bk-{part.key}"
        body = []
        for f in sorted(part.faces, key=lambda f: (f.layer, f.order, depth(centroid(f.points)))):
            poly = [pen.screen(p) for p in f.points]
            d = "M" + "L".join(f"{fmt(x)} {fmt(y)}" for x, y in poly) + "Z"
            fill_class = "f trip-marker" if f.css == "trip-marker" else "f"
            body.append(f'<path class="{fill_class}" d="{d}"/>')
            if f.hatch:
                body.append(pen.hatch(poly))
            if f.css != "trip-marker":
                body.append(pen.strokes([(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]))
        marks = []
        for line in part.marks:
            pts = [pen.screen(p) for p in line]
            marks += [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        if marks:
            body.append(pen.strokes(marks, css="s m", passes=1))
        out.append(f'<g id="{gid}" class="bk-part" data-part="{part.key}" style="--dx:{fmt(dx)};--dy:{fmt(dy)}">'
                   + "".join(body) + "</g>")
        if not part.group:
            ax, ay = pen.screen(part.anchor)
            anchors.append((part, ax, ay, dx, dy))
    # The current path through the nearest pole: upper terminal, contacts, lower terminal (shown when live).
    x = POLES[-1] + 1.7
    path = [(x, 32.0, -14.0), (x, 32.0, 4.0), (x, 30.5, 9.5), (x, 14.5, 15.5), (x, 12.0, 4.0), (x, 12.0, -8.0)]
    pts = [pen.screen(p) for p in path]
    out.append('<path class="current-path" pathLength="1" d="M' + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + '"/>')
    out.append("</g>")

    # Labels: two columns, each sorted by its anchor's height, at least 34 units apart.
    out.append('<g class="bk-labels">')
    for side in ("left", "right"):
        group = sorted([a for a in anchors if a[0].side == side], key=lambda a: a[2])
        ys, last = [], top - 34.0
        for _, _, ay, _, _ in group:
            y = max(ay, last + 34.0)
            ys.append(y)
            last = y
        shift = max(0.0, ys[-1] - (HEIGHT - 70.0)) if ys else 0.0
        for (part, ax, ay, dx, dy), y in zip(group, ys, strict=True):
            y -= shift
            if side == "left":
                tx, anchor_text, lx, elbow = 24.0, "start", 24.0 + len(part.label) * 7.0 + 10.0, ax - 28.0
                elbow = max(elbow, lx + 8.0)
            else:
                tx, anchor_text, lx, elbow = WIDTH - 24.0, "end", WIDTH - 24.0 - len(part.label) * 7.0 - 10.0, ax + 28.0
                elbow = min(elbow, lx - 8.0)
            d = f"M{lx:.1f} {y - 4:.1f}H{elbow:.1f}L{ax:.1f} {ay:.1f}"
            out.append(
                f'<g class="bk-label" data-part="{part.key}">'
                f'<path class="bk-leader" pathLength="1" d="{d}" data-x="{lx:.1f}" data-y="{y - 4:.1f}" '
                f'data-elbow="{elbow:.1f}" data-ax="{ax:.1f}" data-ay="{ay:.1f}" data-dx="{fmt(dx)}" data-dy="{fmt(dy)}"/>'
                f'<text x="{tx:.1f}" y="{y:.1f}" text-anchor="{anchor_text}">{part.label.upper()}</text></g>')
    out.append("</g>")

    out.append('<g class="bk-anchors">' + "".join(
        f'<circle class="bk-anchor" data-part="{p.key}" cx="{ax:.1f}" cy="{ay:.1f}" r="3" '
        f'style="--dx:{fmt(dx)};--dy:{fmt(dy)}"/>' for p, ax, ay, dx, dy in anchors) + "</g>")
    out.append(f'<text class="bk-note" x="{WIDTH - 24}" y="{HEIGHT - 20}" text-anchor="end">'
               "ILLUSTRATIVE, NOT TO SCALE</text>")
    out.append("</svg>\n")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed file is out of date")
    args = ap.parse_args()
    svg = build()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != svg:
            print(f"{OUT} is out of date: run python tools/make_breaker_svg.py")
            return 1
        print(f"{OUT} is up to date")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8", newline="\n")
    print(f"wrote {OUT} ({len(svg.encode()) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
