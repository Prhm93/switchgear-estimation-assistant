"""The home page (Stage UX-V): one headline, one button, one link, scroll effects done by hand.

The page must read in full without script: the statement, the steps and the numbers are all in the
HTML, and only their reveal is animated. No animation library and no script from another site.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from backend.app.paths import STATIC_DIR, TEMPLATES_DIR

STATEMENT = ("A customer enquiry arrives as three documents that rarely agree. The assistant reads each one, "
             "shows where every value came from, puts disagreements side by side and leaves every decision "
             "to the engineer. Nothing reaches the quote until it is approved.")
NUMBER_LABELS = [  # exactly as UX-1 labelled them
    "model alone on the test enquiries, with the CAD file. Strict quote check, fixed baseline. Not held out: "
    "these sets were used during development. Fair scores come from a fresh set in Stage 7.",
    "the same on the reworded enquiries (0.497 without the CAD file)",
    "with the relaxed quote check, the app default: tuned on this set, so not a fair score (0.790 reworded, "
    "also tuned)",
    "drawing values read by OCR from a clean drawing; 0.863 scanned, 0.572 photographed (3 to 5 s per sheet). "
    "Test set; the linker was tuned on 3 of these drawings.",
]


def text_of(html: str) -> str:
    """What a reader sees: tags removed and white space collapsed."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_one_headline_with_one_red_word_one_button_and_one_link(client: TestClient) -> None:
    html = client.get("/").text
    h1 = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    assert len(h1) == 1 and h1[0].count('class="accent"') == 1
    hero = re.search(r'<section class="hero[ "].*?</section>', html, re.S).group(0)
    assert re.findall(r'class="btn btn--primary[^"]*"[^>]*>\s*Start an enquiry', hero)
    assert hero.count("btn--primary") == 1 and 'href="/enquiries/new"' in hero
    assert 'action="/enquiries/sample"' in hero and "Try the sample enquiry" in hero
    assert "float-card" not in html and "perspective" not in html  # the tilted cards are gone


def test_the_statement_is_in_the_html_and_only_its_reveal_is_scripted(client: TestClient) -> None:
    html = client.get("/").text
    statement = re.search(r'<section class="statement".*?</section>', html, re.S).group(0)
    assert STATEMENT in text_of(statement)
    assert statement.count('class="word"') == len(STATEMENT.split())


def test_how_it_works_has_three_steps_beside_a_switchboard_drawing(client: TestClient) -> None:
    html = client.get("/").text
    how = re.search(r'<section id="how".*?</section>', html, re.S).group(0)
    assert len(re.findall(r'<li class="how__step"', how)) == 3
    drawing = re.search(r'<svg class="iso".*?</svg>', how, re.S).group(0)
    for label in ("INCOMER", "OUTGOING WAYS", "FORM 4a"):
        assert f">{label}<" in drawing, label
    assert 'class="draw"' in drawing and "pathLength" in drawing  # drawn with stroke-dashoffset on scroll


def test_numbers_keep_the_ux1_labels_and_the_new_intro_line(client: TestClient) -> None:
    text = text_of(client.get("/").text)
    for number in ("0.778", "0.727", "0.813", "0.893"):
        assert number in text
    for label in NUMBER_LABELS:
        assert label in text, label[:40]
    assert "20 reworded copies, written to test the reading rules on new wording." in text
    assert "never saw" not in text


def test_trust_and_footer(client: TestClient) -> None:
    html = client.get("/").text
    assert 'id="trust"' in html and "prices never come from a model" in text_of(html)
    assert "Not affiliated with or endorsed by any company" in html and 'href="/health"' in html


def test_scripts_are_our_own_and_no_animation_library(client: TestClient) -> None:
    html = client.get("/").text
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html):
        url = urlparse(src)
        assert url.netloc in ("", "testserver") and url.path.startswith("/static/js/"), src  # same site only
    assert "/static/js/home.js" in html
    for path in list((STATIC_DIR / "js").glob("*.js")) + list(TEMPLATES_DIR.rglob("*.html")):
        text = path.read_text(encoding="utf-8").lower()
        assert "gsap" not in text and "scrolltrigger" not in text and "lenis" not in text, path.name
    home_js = (STATIC_DIR / "js" / "home.js").read_text(encoding="utf-8")
    assert "IntersectionObserver" in home_js and "prefers-reduced-motion" in home_js


def test_reduced_motion_shows_everything_at_once() -> None:
    css = (STATIC_DIR / "css" / "app.css").read_text(encoding="utf-8")
    reduced = "".join(re.findall(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", css, re.S))
    assert ".statement .word" in reduced and ".iso .draw" in reduced
