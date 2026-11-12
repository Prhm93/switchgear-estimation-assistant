"""The hero shader on the home page (Stage UX-V part 4).

Hand-written WebGL, under 150 lines, home page only. It draws at half resolution with the device pixel
ratio capped at 1.5, moves with the scroll and pauses when the tab is hidden or the hero is off screen.
Without WebGL, or with reduced motion, the static line art in the HTML stays and no canvas is made.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from backend.app.paths import STATIC_DIR, TEMPLATES_DIR

SHADER = STATIC_DIR / "js" / "hero-shader.js"


def source() -> str:
    return SHADER.read_text(encoding="utf-8")


def test_the_shader_is_hand_written_and_short() -> None:
    lines = source().splitlines()
    assert len(lines) < 150, len(lines)
    text = source()
    assert "http://" not in text and "https://" not in text and "import " not in text  # nothing fetched
    assert "precision mediump float" in text and "gl_FragColor" in text  # our own fragment shader


def test_it_is_loaded_on_the_home_page_only(client: TestClient) -> None:
    html = client.get("/").text
    assert re.search(r'<script src="[^"]*/static/js/hero-shader\.js" defer></script>', html)
    for path in TEMPLATES_DIR.rglob("*.html"):
        if path.name != "home.html":
            assert "hero-shader" not in path.read_text(encoding="utf-8"), path.name
    assert "hero-shader" not in client.get("/enquiries").text


def test_the_static_art_is_in_the_html_and_the_canvas_is_made_by_script(client: TestClient) -> None:
    html = client.get("/").text
    hero = re.search(r'<section class="hero[ "].*?</section>', html, re.S).group(0)
    assert 'class="hero__lines"' in hero and "<canvas" not in hero and "has-shader" not in hero
    css = (STATIC_DIR / "css" / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\.hero\.has-shader \.hero__lines \{ display: none; \}", css)


def test_it_stays_off_without_webgl_or_with_reduced_motion() -> None:
    text = source()
    assert "prefers-reduced-motion: reduce" in text
    assert 'getContext("webgl"' in text
    # The fallback is the static art: the class that hides it is added only after the shader compiled.
    first_class = text.index('classList.add("has-shader")')
    assert text.index("COMPILE_STATUS") < first_class and text.index("LINK_STATUS") < first_class


def test_it_is_cheap_half_resolution_capped_dpr_and_paused_when_unseen() -> None:
    text = source()
    assert re.search(r"Math\.min\(window\.devicePixelRatio \|\| 1, 1\.5\)", text)
    assert re.search(r"\*\s*0\.5", text)  # half resolution
    assert "visibilitychange" in text and "document.hidden" in text
    assert "IntersectionObserver" in text and "cancelAnimationFrame" in text
    assert "scrollY" in text and "u_scroll" in text  # moves with the scroll
