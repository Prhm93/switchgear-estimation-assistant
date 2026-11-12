"""The home page (Stage UX visual pass, V3): hero, statement, story, safety strip, numbers, footer.

Changed on purpose from UX-V: the hero is now the prototype's ("Turn enquiries into checked estimates")
with the breaker drawing on the right, the long statement becomes "Read. Check. Approve.", the three
steps become a sticky story whose drawing stays in view, and the trust list becomes the safety strip.
The measured numbers keep their exact UX-1 labels and come after the safety strip.

The page must read in full without script: every word is in the HTML, and only the motion is scripted.
No animation library and no script from another site.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from backend.app.paths import STATIC_DIR, STYLESHEET, TEMPLATES_DIR

NUMBER_LABELS = [  # exactly as UX-1 labelled them
    "model alone on the test enquiries, with the CAD file. Strict quote check, fixed baseline. Not held out: "
    "these sets were used during development. Fair scores come from a fresh set in Stage 7.",
    "the same on the reworded enquiries (0.497 without the CAD file)",
    "with the relaxed quote check, the app default: tuned on this set, so not a fair score (0.790 reworded, "
    "also tuned)",
    "drawing values read by OCR from a clean drawing; 0.863 scanned, 0.572 photographed (3 to 5 s per sheet). "
    "Test set; the linker was tuned on 3 of these drawings.",
]
STEPS = [("Drop the files", "Files received"), ("We read them", "Values found"), ("You approve", "Decision needed")]
SAFETY = ["Every value shows its source.", "Nothing reaches the quote until you approve.",
          "Prices come only from your catalogue."]


def text_of(html: str) -> str:
    """What a reader sees: tags removed and white space collapsed."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def section(html: str, marker: str) -> str:
    return re.search(rf"<section {marker}.*?</section>", html, re.S).group(0)


def test_the_hero_is_the_prototype_headline_with_one_add_files_button_and_the_drawing(client: TestClient) -> None:
    html = client.get("/").text
    h1 = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    assert len(h1) == 1 and h1[0].count('class="accent"') == 1
    assert text_of(h1[0]) == "Turn enquiries into checked estimates"
    hero = section(html, 'class="hero"')
    assert "An engineer-led way to estimate" in hero
    assert "Add the customer's files. Every value shows where it came from." in hero
    # stage-simple: one big button; the sample enquiry and the New enquiry page moved behind "More".
    assert re.findall(r'class="btn btn--primary btn--xl"[^>]*>.*?Add files', hero, re.S)
    assert hero.count("btn--primary") == 1 and "<button" not in hero
    assert 'action="/enquiries/sample"' not in hero
    assert "Sample data only" in hero
    # The breaker drawing sits on the right, inline so the theme colours and the motion reach it.
    assert '<svg xmlns="http://www.w3.org/2000/svg" class="breaker"' in hero and "hero__art" in hero
    assert "<canvas" not in hero  # the canvas is made by hero-lines.js


def test_the_statement_is_read_check_approve_with_the_second_word_blue(client: TestClient) -> None:
    statement = section(client.get("/").text, 'class="statement"')
    assert text_of(statement).endswith("Read. Check. Approve.")
    assert re.search(r'<span class="accent-blue">Check\.</span>', statement)


def test_the_story_has_three_steps_and_one_place_sets_the_active_step(client: TestClient) -> None:
    story = section(client.get("/").text, 'id="how"')
    assert 'data-step="1"' in story.split(">")[0]  # without script, step 1 is shown
    assert "The drawing stays in view." in story
    for n, (step, caption) in enumerate(STEPS, start=1):
        assert re.search(rf'<li class="story__step" data-n="{n}">.*?<h3>{step}</h3>', story, re.S), step
        assert re.search(rf'<span class="story__caption" data-n="{n}">{caption}</span>', story), caption
    assert 'class="breaker"' in story and 'id="story-bk-title"' in story
    js = (STATIC_DIR / "js" / "home.js").read_text(encoding="utf-8")
    assert js.count("dataset.step =") == 1  # the step is worked out in one place only
    css = STYLESHEET.read_text(encoding="utf-8")
    for n in "123":  # step text and caption both follow the section's attribute, so they change together
        assert f'.story[data-step="{n}"] .story__step[data-n="{n}"]' in css
        assert f'.story[data-step="{n}"] .story__caption[data-n="{n}"]' in css


def test_the_story_card_sticks_under_the_top_bar_and_fits_the_screen() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")
    card = re.search(r"\.story__card \{([^}]*)\}", css).group(1)
    assert "position: sticky" in card and "top: calc(var(--nav-h) + 16px)" in card
    assert "max-height: calc(100svh - var(--nav-h) - 32px)" in card
    assert re.search(r"\.site-header \{[^}]*position: sticky", css)


def test_safety_strip_then_numbers_with_the_ux1_labels(client: TestClient) -> None:
    html = client.get("/").text
    safety = section(html, 'id="safety"')
    assert "Decisions, not guesses." in safety
    for item in SAFETY:
        assert item in safety, item
    numbers = section(html, 'id="accuracy"')
    assert html.index('id="safety"') < html.index('id="accuracy"')
    text = text_of(numbers)
    for number, label in zip(("0.778", "0.727", "0.813", "0.893"), NUMBER_LABELS, strict=True):
        assert f"{number} {label}" in text, number  # each label right after its number
    assert "20 reworded copies, written to test the reading rules on new wording." in text


def test_numbers_are_quiet_and_near_body_size() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")
    value = re.search(r"\.number__value \{([^}]*)\}", css).group(1)
    size = re.search(r"font-size: var\(--fs-([a-z0-9]+)\)", value).group(1)
    assert size in {"base", "md", "lg", "xl"}  # not a display size


def test_footer_has_the_name_the_disclaimer_and_the_status_link(client: TestClient) -> None:
    html = client.get("/").text
    footer = re.search(r'<footer class="site-footer">.*?</footer>', html, re.S).group(0)
    assert "Switchgear Estimation Assistant" in footer
    assert "Not affiliated with or endorsed by any company" in footer and 'href="/health"' in footer


def test_every_id_on_the_page_is_unique(client: TestClient) -> None:
    """The drawing appears twice (hero and story): the story copy carries its own id prefix."""
    ids = Counter(re.findall(r'\sid="([^"]+)"', client.get("/").text))
    assert not [i for i, n in ids.items() if n > 1], [i for i, n in ids.items() if n > 1]
    for target in re.findall(r'aria-labelledby="([^"]+)"', client.get("/").text):
        assert target in ids, target


def test_no_label_is_faded_by_a_mask() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")
    assert "mask-image" not in css and "mask:" not in css


def test_scripts_are_our_own_and_no_animation_library(client: TestClient) -> None:
    html = client.get("/").text
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html):
        url = urlparse(src)
        assert url.netloc in ("", "testserver") and url.path.startswith("/static/js/"), src  # same site only
    for name in ("home.js", "hero-lines.js", "breaker.js"):
        assert f"/static/js/{name}" in html, name
    for path in list((STATIC_DIR / "js").glob("*.js")) + list(TEMPLATES_DIR.rglob("*.html")):
        text = path.read_text(encoding="utf-8").lower()
        assert "gsap" not in text and "scrolltrigger" not in text and "lenis" not in text, path.name
    home_js = (STATIC_DIR / "js" / "home.js").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in home_js and "SeaBreaker.setExplode" in home_js


def test_reduced_motion_shows_the_finished_drawing() -> None:
    home_js = (STATIC_DIR / "js" / "home.js").read_text(encoding="utf-8")
    # The draw-on is added by script only, and only when motion is allowed.
    assert home_js.index("prefers-reduced-motion") < home_js.index('classList.add("is-drawing")')
    css = STYLESHEET.read_text(encoding="utf-8")
    reduced = "".join(re.findall(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", css, re.S))
    assert ".is-drawing" in reduced


def test_left_labels_are_hidden_below_1100px() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")
    block = re.search(r"@media \(max-width: 1099px\) \{(.*?)\n\}", css, re.S).group(1)
    assert re.search(r'\.hero \.bk-label:has\(text\[text-anchor="start"\]\) \{ display: none; \}', block)


def test_the_finished_drawing_does_not_flash_before_the_draw_on(client: TestClient) -> None:
    """Without this, the drawing paints complete, then vanishes and draws on. A flag set before paint hides
    it until home.js starts; only when motion is allowed, and a timer shows it anyway if script fails."""
    head = client.get("/").text.split("</head>")[0]
    flag = next(s for s in re.findall(r"<script>(.*?)</script>", head, re.S) if "hero-pending" in s)
    assert "prefers-reduced-motion: reduce" in flag and 'classList.add("hero-pending")' in flag
    assert re.search(r"setTimeout\(.*hero-pending.*\d{4}\)", flag, re.S)
    css = STYLESHEET.read_text(encoding="utf-8")
    assert ".hero-pending .hero__art .breaker { visibility: hidden; }" in css
    home_js = (STATIC_DIR / "js" / "home.js").read_text(encoding="utf-8")
    assert 'classList.remove("hero-pending")' in home_js
