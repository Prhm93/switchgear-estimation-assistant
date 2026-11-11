"""Design rules (version 2), checked against the stylesheet and the templates.

These keep the look consistent as the stylesheet grows:

* glass cards with hairline edges only: every border is 0, none or a 1px
  hairline in rgba(156,192,255, 0.10 to 0.18); no solid opaque borders;
* gradients only in the four allowed rules: .upload-box (red-to-blue border),
  .glow (top radial glow), .sheen (card sheen) and .cta-panel (call to action);
* 3D tilt only in the home page hero, and only at 1100px and wider;
* card radii of 18 and 20px, pill buttons, a red primary button with a shadow;
* IBM Plex Sans everywhere, the serif display font on the home page only;
* 150 ms transitions, none for reduced-motion users, and a visible focus ring;
* no emoji or "magic" wording in the templates.
"""

import re

import pytest

from backend.app.design.contrast import load_rgba_tokens, load_tokens
from backend.app.paths import STYLESHEET, TEMPLATES_DIR

CSS = STYLESHEET.read_text(encoding="utf-8")
ALLOWED_GRADIENTS = {".upload-box", ".glow", ".sheen", ".cta-panel"}


def _without_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


RULES_CSS = _without_comments(CSS)


def _rules(css: str = RULES_CSS) -> list[tuple[str, str]]:
    """(selector list, declarations) for every rule, with @media wrappers left out of the selectors."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selector = m.group(1).strip()
        out.append((selector, m.group(2)))
    return out


def _rule(selector: str) -> str:
    """Declarations of the first rule whose selector list is exactly ``selector``."""
    for sel, body in _rules():
        if sel == selector:
            return body
    raise AssertionError(f"rule {selector!r} not found in app.css")


def _media_blocks(query: str) -> list[str]:
    """The bodies of every @media block with exactly this query."""
    blocks, pattern = [], re.compile(r"@media\s*" + re.escape(query) + r"\s*\{")
    for m in pattern.finditer(RULES_CSS):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(RULES_CSS[i], 0)
            i += 1
        blocks.append(RULES_CSS[m.end():i - 1])
    return blocks


def test_brand_palette_tokens_are_unchanged() -> None:
    tokens = {name: value.upper() for name, value in load_tokens().items()}
    assert tokens["bg"] == "#0A1630"
    assert tokens["surface"] == "#10224A"
    assert tokens["surface-2"] == "#16305F"
    assert tokens["text"] == "#F4F7FB"
    assert tokens["text-muted"] == "#A9B8D3"
    assert tokens["red"] == "#E31E24"
    assert tokens["blue"] == "#1C5FD1"
    assert tokens["blue-text"] == tokens["focus"] == "#9CC0FF"  # light blue for links and focus
    assert tokens["on-red"] == "#FFFFFF"


def test_hairline_tokens_are_faint_light_blue() -> None:
    rgba = load_rgba_tokens()
    for name in ("hairline", "hairline-strong"):
        r, g, b, a = rgba[name]
        assert (r, g, b) == (156, 192, 255), name
        assert 0.10 <= a <= 0.18, name


def test_every_border_is_none_or_a_hairline() -> None:
    """Hairline edges are allowed; solid opaque borders are not."""
    for selector, body in _rules():
        for m in re.finditer(r"(?:^|;|\s)(border(?:-[a-z]+)?)\s*:\s*([^;]+)", body):
            prop, value = m.group(1), m.group(2).strip()
            if prop == "border-radius" or prop == "border-collapse" or prop == "border-spacing":
                continue
            ok = value in ("0", "none") or re.fullmatch(r"1px solid var\(--hairline(?:-strong)?\)", value)
            assert ok, f"{selector}: {prop}: {value}"


def test_gradients_only_in_the_four_allowed_rules() -> None:
    found = set()
    for selector, body in _rules():
        if "gradient(" in body:
            assert selector in ALLOWED_GRADIENTS, f"gradient in {selector!r}"
            found.add(selector)
    assert found == ALLOWED_GRADIENTS
    # The 56px background grid is an SVG tile, not a gradient.
    assert "background-size: 56px 56px" in _rule("body")
    assert "gradient(" not in _rule("body") and "gradient(" not in _rule("body.page--home")


def test_the_upload_box_border_runs_red_to_blue() -> None:
    body = _rule(".upload-box")
    assert re.search(r"linear-gradient\(90deg,\s*var\(--red\),\s*var\(--blue\)", body)


def test_tilt_only_in_the_home_hero_and_only_on_wide_screens() -> None:
    wide = "".join(_media_blocks("(min-width: 1100px)"))
    outside = RULES_CSS
    for block in _media_blocks("(min-width: 1100px)"):
        outside = outside.replace(block, "")
    assert "perspective(" not in outside and "rotateY(" not in outside
    tilted = [sel for sel, body in _rules(wide) if "perspective(" in body or "rotateY(" in body]
    assert tilted and all(sel.startswith(".hero") for sel in tilted), tilted


def test_glass_cards_have_hairline_shadow_and_highlight() -> None:
    body = _rule(".glass")
    assert "background: var(--glass)" in body
    assert "1px solid var(--hairline)" in body
    assert "var(--shadow-card)" in body and "var(--highlight)" in body
    assert "border-radius: var(--radius-card)" in body
    glass = load_rgba_tokens()["glass"]
    assert glass[3] < 1  # semi-transparent


def test_card_radii_are_18_and_20px() -> None:
    assert re.search(r"--radius-tile\s*:\s*18px", CSS)
    assert re.search(r"--radius-card\s*:\s*20px", CSS)


def test_buttons_are_pills_and_primary_is_red_with_a_soft_red_shadow() -> None:
    assert "border-radius: var(--radius-pill)" in _rule(".btn")
    body = _rule(".btn--primary")
    assert "background: var(--red)" in body and "box-shadow: var(--shadow-red)" in body
    assert "background: var(--veil)" in _rule(".btn--secondary")  # secondary is glass
    assert "border-radius: 50%" in _rule(".icon-btn")  # icon buttons are filled circles
    assert "var(--tint-approve)" in _rule(".icon-btn--approve")
    assert "var(--tint-reject)" in _rule(".icon-btn--reject")


def test_the_serif_is_for_the_home_page_only() -> None:
    """Stage UX: IBM Plex Sans everywhere in the app; the serif display font only on the home page."""
    home_only = {".hero__title", ".section-title", ".cta-panel h2", ".page--home .brand__name", ".serif"}
    serif = {sel for sel, body in _rules() if "var(--font-serif)" in body}
    assert serif == home_only, serif
    assert "var(--font-serif)" not in _rule(".page-title") and "font-family" not in _rule(".page-title")
    assert "var(--font-sans)" in _rule("body")
    assert '"Instrument Serif"' in CSS
    assert "InstrumentSerif-Regular.woff2" in CSS and "InstrumentSerif-Italic.woff2" in CSS


def test_mono_is_only_for_numbers_codes_and_document_text() -> None:
    """Plex Mono marks numbers, part codes and text copied from a document; never headings or labels."""
    for selector in (".page-title", ".block-title", ".decision__title", ".panel__title", ".step", ".lead", ".btn"):
        assert "var(--font-mono)" not in _rule(selector), selector


def test_transitions_are_150ms_and_off_for_reduced_motion() -> None:
    assert re.search(r"--dur\s*:\s*150ms", CSS)
    reduced = "".join(_media_blocks("(prefers-reduced-motion: reduce)"))
    assert re.search(r"--dur\s*:\s*0ms", reduced)
    assert re.search(r"\.spinner::after\s*\{\s*animation:\s*none", reduced)


def test_keyboard_focus_ring_is_visible() -> None:
    body = _rule(":focus-visible")
    assert re.search(r"outline\s*:\s*2px solid var\(--focus\)", body)


def test_table_headings_stay_on_one_line() -> None:
    """The parked fix: no double gap in headings such as "VALUES APPROVED"."""
    assert "white-space: nowrap" in _rule(".data-table th")


TEMPLATES = sorted(TEMPLATES_DIR.rglob("*.html"))
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐✨]")


@pytest.mark.parametrize("path", TEMPLATES, ids=lambda p: p.name)
def test_templates_have_no_emoji_or_magic_wording(path) -> None:
    text = path.read_text(encoding="utf-8")
    assert not EMOJI.search(text), path.name
    for word in ("magic", "sparkle", "ai-powered", "powered by ai"):
        assert word not in text.lower(), (path.name, word)
