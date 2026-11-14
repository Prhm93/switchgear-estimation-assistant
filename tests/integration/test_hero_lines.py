"""The hero background (Stage UX visual pass, V3): a faint grid and thin contour lines on a 2D canvas.

Changed on purpose: it replaces the UX-V WebGL shader (hero-shader.js), by the design decision of
12 Nov 2026. No WebGL and no filled shapes, only strokes. Colours come from the theme tokens, so the
light theme gets its own. It pauses when the tab is hidden or the hero is off screen, caps the pixel
ratio at 1.5 and the frame rate at 30, and draws one still frame for reduced motion.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from backend.app.design.contrast import load_rgba_tokens
from backend.app.paths import STATIC_DIR, TEMPLATES_DIR

LINES = STATIC_DIR / "js" / "hero-lines.js"


def source() -> str:
    return LINES.read_text(encoding="utf-8")


def test_the_shader_is_gone_and_the_lines_are_short_and_hand_written() -> None:
    assert not (STATIC_DIR / "js" / "hero-shader.js").exists()
    text = source()
    assert len(text.splitlines()) < 150
    assert "http://" not in text and "https://" not in text and "import " not in text  # nothing fetched
    assert 'getContext("2d")' in text and "webgl" not in text.lower()


def test_only_strokes_no_filled_shapes() -> None:
    text = source()
    assert "fill(" not in text and "fillRect" not in text and "fillStyle" not in text
    assert ".stroke()" in text


def test_it_is_loaded_on_the_home_page_only(client: TestClient) -> None:
    html = client.get("/").text
    assert re.search(r'<script src="[^"]*/static/js/hero-lines\.js" defer></script>', html)
    for path in TEMPLATES_DIR.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "hero-shader" not in text, path.name
        if path.name != "home.html":
            assert "hero-lines" not in text, path.name


def test_colours_come_from_the_theme_tokens() -> None:
    text = source()
    for token in ("--hero-grid", "--hero-line", "--hero-line-strong"):
        assert f'"{token}"' in text, token
    assert "themechange" in text  # redrawn when the theme switches
    for theme in ("dark", "light"):
        rgba = load_rgba_tokens(theme)
        for token in ("hero-grid", "hero-line", "hero-line-strong"):
            assert rgba[token][3] <= 0.2, (theme, token)  # faint lines only
    assert not re.search(r"rgba?\(\d", text)  # no colour written in the script


def test_it_is_cheap_and_pauses_when_unseen() -> None:
    text = source()
    assert re.search(r"Math\.min\(window\.devicePixelRatio \|\| 1, 1\.5\)", text)
    assert re.search(r"1000 / 30", text)  # 30 fps cap
    assert "visibilitychange" in text and "document.hidden" in text
    assert "IntersectionObserver" in text and "cancelAnimationFrame" in text


def test_reduced_motion_draws_one_still_frame() -> None:
    text = source()
    assert "prefers-reduced-motion: reduce" in text
    still = re.search(r"if \(reduce\) \{(.*?)\}", text, re.S).group(1)
    assert "draw(0)" in still and "return" in still
