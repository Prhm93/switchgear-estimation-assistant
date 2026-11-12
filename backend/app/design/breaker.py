"""The breaker drawing (frontend/static/img/breaker.svg) inlined into a page.

It is inlined, not linked as an image, so the theme colours and the motion in breaker.js reach it. When
a page shows it more than once, each further copy gets an id prefix so every id on the page stays unique.
"""

from __future__ import annotations

from functools import lru_cache

from markupsafe import Markup

from backend.app.paths import STATIC_DIR

BREAKER_SVG = STATIC_DIR / "img" / "breaker.svg"


@lru_cache(maxsize=4)
def breaker_svg(prefix: str = "") -> Markup:
    """The drawing as trusted markup (it is our own generated file); ``prefix`` goes before every id."""
    svg = BREAKER_SVG.read_text(encoding="utf-8")
    if prefix:
        svg = svg.replace('id="bk-', f'id="{prefix}bk-').replace('aria-labelledby="bk-', f'aria-labelledby="{prefix}bk-')
    return Markup(svg)
