"""Make "printed and scanned" and "phone photo" versions of a clean drawing.

Pillow and numpy only. Every geometric change is one homography ``H`` (clean
pixels to output pixels). The image is warped with ``H`` and the boxes are
moved with the same ``H`` (see ``geometry.py``), and ``H`` is stored in the
answer key so the tests can check the two agree.

Order matters: marks (stamp, handwritten note) go on the paper first, then
the geometric warp, then blur, light and noise, as in real life.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from data_generator import geometry as g

FONT_DIR = Path(__file__).parent / "fonts"
HAND_FONT = FONT_DIR / "Caveat-Variable.ttf"  # SIL OFL 1.1
STAMP_FONT = FONT_DIR / "IBMPlexSansCondensed-Medium.ttf"  # SIL OFL 1.1

# Invented stamp and note text only.
STAMP_LINES = [("RECEIVED", "TENDER OFFICE"), ("COPY", "FOR ESTIMATING ONLY"), ("RECEIVED", "DOC CONTROL")]
NOTES = ["checked against spec - ok", "see site survey notes", "confirm cable route on site",
         "client to confirm spare ways", "price as drawn"]


@dataclass
class Degraded:
    image: Image.Image
    h: np.ndarray  # clean pixels -> output pixels


def _paper(clean: Image.Image, paper: float, ink: float) -> np.ndarray:
    """Map white to the paper tone and black to the ink tone."""
    a = np.asarray(clean.convert("L"), dtype=np.float32) / 255.0
    return ink + (paper - ink) * a


def _stamp(size_px: int, lines: tuple[str, str], date: str, rng: np.random.Generator) -> Image.Image:
    """A rubber stamp as an alpha mask (255 = ink), slightly rotated."""
    w, h = int(size_px * 2.2), size_px
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([4, 4, w - 5, h - 5], radius=h // 8, outline=255, width=max(3, h // 22))
    big = ImageFont.truetype(str(STAMP_FONT), int(h * 0.3))
    small = ImageFont.truetype(str(STAMP_FONT), int(h * 0.16))
    d.text((w / 2, h * 0.32), lines[0], fill=255, font=big, anchor="mm")
    d.text((w / 2, h * 0.6), date, fill=255, font=small, anchor="mm")
    d.text((w / 2, h * 0.8), lines[1], fill=255, font=small, anchor="mm")
    # Uneven ink: knock out random specks.
    speck = rng.random((h, w)) < 0.18
    arr = np.asarray(m).copy()
    arr[speck] = (arr[speck] * 0.35).astype(np.uint8)
    return Image.fromarray(arr).rotate(float(rng.uniform(-12, 12)), expand=True, resample=Image.Resampling.BICUBIC)


def _hand_note(text: str, height_px: int, rng: np.random.Generator) -> Image.Image:
    """A handwritten-style note as an alpha mask, with a slight slant and baseline wobble."""
    font = ImageFont.truetype(str(HAND_FONT), height_px)
    x0, y0, x1, y1 = font.getbbox(text)
    m = Image.new("L", (x1 - x0 + 20, y1 - y0 + 20), 0)
    ImageDraw.Draw(m).text((10 - x0, 10 - y0), text, fill=255, font=font)
    m = m.transform(m.size, Image.Transform.AFFINE, (1, float(rng.uniform(-0.15, 0.05)), 0, 0, 1, 0),
                    resample=Image.Resampling.BICUBIC)
    return m.rotate(float(rng.uniform(-4, 4)), expand=True, resample=Image.Resampling.BICUBIC)


def _put(base: np.ndarray, mask: Image.Image, xy: tuple[int, int], tone: float) -> None:
    """Darken ``base`` towards ``tone`` where ``mask`` has ink (multiply-style)."""
    x, y = xy
    m = np.asarray(mask, dtype=np.float32) / 255.0
    hh, ww = m.shape
    hh, ww = min(hh, base.shape[0] - y), min(ww, base.shape[1] - x)
    if hh <= 0 or ww <= 0:
        return
    region = base[y:y + hh, x:x + ww]
    region[:] = region * (1 - m[:hh, :ww]) + np.minimum(region, tone) * m[:hh, :ww]


def _marks(arr: np.ndarray, rng: np.random.Generator, dpi: float, date: str,
           stamp_at_mm: tuple[float, float], note_at_mm: tuple[float, float], ink: float) -> None:
    px = dpi / g.MM_PER_INCH
    lines = STAMP_LINES[int(rng.integers(len(STAMP_LINES)))]
    stamp = _stamp(int(22 * px), lines, date, rng)
    _put(arr, stamp, (int(stamp_at_mm[0] * px), int(stamp_at_mm[1] * px)), ink + 70)
    note = _hand_note(NOTES[int(rng.integers(len(NOTES)))], int(6.5 * px), rng)
    _put(arr, note, (int(note_at_mm[0] * px), int(note_at_mm[1] * px)), ink + 15)


QUANT_STEP = 4  # output levels are multiples of 4: invisible, and the PNGs are about 40 % smaller


def _noise(arr: np.ndarray, rng: np.random.Generator, sigma: float) -> np.ndarray:
    """Add sensor noise, then quantise to steps of :data:`QUANT_STEP` grey levels."""
    noisy = arr + rng.normal(0, sigma, arr.shape)
    return np.clip(np.round(noisy / QUANT_STEP) * QUANT_STEP, 0, 255).astype(np.uint8)


def scanned(clean: Image.Image, rng: np.random.Generator, dpi: float, date: str,
            marks: bool = True, stamp_at_mm=(300.0, 18.0), note_at_mm=(140.0, 30.0)) -> Degraded:
    """Printed, then scanned in greyscale: grey paper, small skew, soft focus, noise.

    ``stamp_at_mm`` and ``note_at_mm`` are top-left positions measured from the
    top-left of the sheet, chosen by the caller to land on empty paper.
    """
    paper, ink = float(rng.uniform(212, 232)), float(rng.uniform(25, 50))
    arr = _paper(clean, paper, ink)
    if marks:
        _marks(arr, rng, dpi, date, stamp_at_mm, note_at_mm, ink)
    w, h = clean.size
    hmat = g.rotation_about(w / 2, h / 2, float(rng.uniform(-1.8, 1.8)),
                            dx=float(rng.uniform(-10, 10)), dy=float(rng.uniform(-10, 10)))
    img = Image.fromarray(arr.round().astype(np.uint8), "L")
    img = img.transform((w, h), Image.Transform.PERSPECTIVE, g.pil_perspective_coeffs(hmat),
                        resample=Image.Resampling.BICUBIC, fillcolor=int(paper))
    img = img.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.5, 1.0))))
    out = _noise(np.asarray(img, dtype=np.float32), rng, float(rng.uniform(1.5, 3.0)))
    return Degraded(Image.fromarray(out, "L"), hmat)


def photo(clean: Image.Image, rng: np.random.Generator, dpi: float, date: str, marks: bool = True,
          stamp_at_mm=(300.0, 18.0), note_at_mm=(140.0, 30.0), out_scale: float = 0.8) -> Degraded:
    """Photographed with a phone: perspective tilt, desk background, uneven light."""
    paper, ink = float(rng.uniform(236, 248)), float(rng.uniform(20, 40))
    arr = _paper(clean, paper, ink)
    if marks:
        _marks(arr, rng, dpi, date, stamp_at_mm, note_at_mm, ink)
    w, h = clean.size
    ow, oh = int(w * out_scale), int(h * out_scale)

    def jitter(lo: float, hi: float) -> float:
        return float(rng.uniform(lo, hi))

    dst = [[ow * jitter(0.03, 0.09), oh * jitter(0.03, 0.10)],
           [ow * (1 - jitter(0.02, 0.08)), oh * jitter(0.05, 0.14)],
           [ow * (1 - jitter(0.04, 0.11)), oh * (1 - jitter(0.03, 0.09))],
           [ow * jitter(0.01, 0.07), oh * (1 - jitter(0.06, 0.13))]]
    hmat = g.homography_from_points([[0, 0], [w, 0], [w, h], [0, h]], dst)
    desk = tuple(int(v) for v in rng.integers(70, 120, size=3))
    rgb = Image.fromarray(arr.round().astype(np.uint8), "L").convert("RGB")
    img = rgb.transform((ow, oh), Image.Transform.PERSPECTIVE, g.pil_perspective_coeffs(hmat),
                        resample=Image.Resampling.BICUBIC, fillcolor=desk)
    img = img.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.7, 1.3))))
    # Uneven light: a tilted plane plus a soft vignette, and a warm tint.
    yy, xx = np.mgrid[0:oh, 0:ow].astype(np.float32)
    xn, yn = xx / ow - 0.5, yy / oh - 0.5
    light = 0.95 + jitter(-0.25, 0.25) * xn + jitter(-0.2, 0.2) * yn - 0.35 * (xn ** 2 + yn ** 2)
    light = np.clip(light, 0.55, 1.05)[..., None]
    tint = np.array([1.0, jitter(0.96, 0.99), jitter(0.88, 0.95)], dtype=np.float32)
    out = np.asarray(img, dtype=np.float32) * light * tint
    out = _noise(out, rng, float(rng.uniform(1.0, 2.0)))
    return Degraded(Image.fromarray(out, "RGB"), hmat)
