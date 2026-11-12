"""Design rules (version 2), checked against the stylesheet and the templates.

These keep the look consistent as the stylesheet grows:

* glass cards with hairline edges only: every border is 0, none or a 1px
  hairline in rgba(156,192,255, 0.10 to 0.18); no solid opaque borders;
* one gradient only: the red-to-blue border of .upload-box (Stage UX-V removed the
  glow, the sheen and the call-to-action panel);
* no 3D transforms anywhere (Stage UX-V removed the tilted hero cards);
* card radii of 18 and 20px, pill buttons, a red primary button with a shadow;
* IBM Plex Sans everywhere and no serif (Stage UX-V); Plex Mono for numbers, codes,
  document text and small uppercase labels only;
* two colour themes in tokens.css (Stage UX visual pass): dark, the default, and light, with a
  switch in every top bar that remembers the choice; headings set tight (-0.02em, the hero -0.03em);
* 150 ms transitions, none for reduced-motion users, and a visible focus ring;
* no emoji or "magic" wording in the templates.
"""

import re

import pytest

from backend.app.design.contrast import load_rgba_tokens, load_tokens
from backend.app.paths import STATIC_DIR, STYLESHEET, TEMPLATES_DIR, TOKENS

# tokens.css (fonts, the two themes, type and motion) and app.css (everything else), read as one sheet.
CSS = TOKENS.read_text(encoding="utf-8") + "\n" + STYLESHEET.read_text(encoding="utf-8")
# Stage UX-V: the hero glow, the card sheen and the call-to-action panel are gone (the shader and
# hairline sections replace them); the red-to-blue upload border is the one gradient left.
ALLOWED_GRADIENTS = {".upload-box"}


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
    raise AssertionError(f"rule {selector!r} not found in tokens.css or app.css")


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


def test_hairline_tokens_are_faint() -> None:
    """Dark theme: faint light blue. Light theme (changed on purpose): faint navy-blue on paper."""
    for theme, colour, (low, high) in (("dark", (156, 192, 255), (0.10, 0.18)), ("light", (27, 69, 140), (0.10, 0.22))):
        rgba = load_rgba_tokens(theme)
        for name in ("hairline", "hairline-strong"):
            r, g, b, a = rgba[name]
            assert (r, g, b) == colour, (theme, name)
            assert low <= a <= high, (theme, name)


def test_every_border_is_none_or_a_hairline() -> None:
    """Hairline edges are allowed; solid opaque borders are not."""
    for selector, body in _rules():
        for m in re.finditer(r"(?:^|;|\s)(border(?:-[a-z]+)?)\s*:\s*([^;]+)", body):
            prop, value = m.group(1), m.group(2).strip()
            if prop == "border-radius" or prop == "border-collapse" or prop == "border-spacing":
                continue
            ok = value in ("0", "none") or re.fullmatch(r"1px solid var\(--hairline(?:-strong)?\)", value)
            assert ok, f"{selector}: {prop}: {value}"


def test_gradients_only_in_the_allowed_rule() -> None:
    found = set()
    for selector, body in _rules():
        if "gradient(" in body:
            assert selector in ALLOWED_GRADIENTS, f"gradient in {selector!r}"
            found.add(selector)
    assert found == ALLOWED_GRADIENTS
    # The 56px background grid is an SVG tile (one per theme), not a gradient.
    assert "background-size: 56px 56px" in _rule("body") and "var(--grid-tile)" in _rule("body")
    assert "gradient(" not in _rule("body") and "gradient(" not in _rule("body.page--home")
    assert TOKENS.read_text(encoding="utf-8").count("--grid-tile: url(\"data:image/svg+xml") == 2  # dark, light


def test_the_upload_box_border_runs_red_to_blue() -> None:
    body = _rule(".upload-box")
    assert re.search(r"linear-gradient\(90deg,\s*var\(--red\),\s*var\(--blue\)", body)


def test_no_3d_transforms() -> None:
    """Stage UX-V: the tilted hero cards are gone; nothing is drawn in 3D."""
    for word in ("perspective", "rotateY(", "rotateX(", "rotate3d(", "translateZ(", "preserve-3d"):
        assert word not in RULES_CSS, word


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


def test_there_is_no_serif() -> None:
    """Stage UX-V reverses the UX-1 decision: IBM Plex Sans and Plex Mono only, no serif font anywhere."""
    assert "--font-serif" not in CSS and "Instrument Serif" not in CSS and "InstrumentSerif" not in CSS
    fonts = STYLESHEET.parent.parent / "fonts"
    assert not list(fonts.glob("InstrumentSerif*")) and not (fonts / "OFL-InstrumentSerif.txt").exists()
    for path in TEMPLATES_DIR.rglob("*.html"):
        assert "InstrumentSerif" not in path.read_text(encoding="utf-8"), path.name


def test_mono_is_only_for_numbers_codes_and_document_text() -> None:
    """Plex Mono marks numbers, part codes, document text and small uppercase labels; never headings."""
    for selector in (".page-title", ".decision__title", ".panel__title", ".step", ".lead", ".btn"):
        assert "var(--font-mono)" not in _rule(selector), selector
    for selector in (".label-mono", ".block-title"):  # the technical-drawing labels
        body = _rule(selector)
        assert "var(--font-mono)" in body and "text-transform: uppercase" in body and "var(--fs-xs)" in body


def test_the_ux_v_crosshair_marks_and_corner_drawing_are_gone() -> None:
    """Changed on purpose: the visual pass replaces the "+" marks and the corner single-line drawing
    (a faint breaker drawing takes their place on the Start and Enquiry pages)."""
    assert ".xmarks" not in RULES_CSS and "--xmark" not in RULES_CSS and ".corner-drawing" not in RULES_CSS
    for path in TEMPLATES_DIR.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "xmarks" not in text and "corner_drawing" not in text, path.name


def test_headings_are_set_tight_in_em() -> None:
    """-0.02em for headings, -0.03em for the hero headline, so the spacing scales with the size."""
    assert "letter-spacing: -0.02em" in _rule("h1, h2, h3")
    for selector in (".page-title", ".section-title"):
        assert "letter-spacing: -0.02em" in _rule(selector), selector
    assert "letter-spacing: -0.03em" in _rule(".hero__title")


def test_both_themes_and_a_switch_in_every_top_bar() -> None:
    assert _rule(':root[data-theme="light"]') and "color-scheme: light" in _rule(':root[data-theme="light"]')
    base = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    assert '<html lang="en-GB" data-theme="dark">' in base  # dark without script or storage
    head = base.split("</head>")[0]
    assert head.index("css/tokens.css") < head.index("css/app.css")
    # The stored choice is applied before paint, and storage errors are caught.
    assert re.search(r'<script>try \{ if \(localStorage\.getItem\("sea-theme"\)', head)
    assert "catch (e)" in head
    for layout in ("layout_app.html", "home.html"):
        assert "{{ theme_button() }}" in (TEMPLATES_DIR / layout).read_text(encoding="utf-8"), layout
    js = (STATIC_DIR / "js" / "theme.js").read_text(encoding="utf-8")
    assert js.count("try {") >= 1 and "localStorage.setItem" in js and "catch (e)" in js
    assert "localStorage" not in js.split("try {")[0]  # no storage call outside a try block


def test_transitions_are_150ms_and_off_for_reduced_motion() -> None:
    """The motion tokens live in tokens.css; reduced motion sets them to zero."""
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
