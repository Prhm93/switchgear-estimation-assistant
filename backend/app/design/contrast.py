"""WCAG 2.2 contrast checks for the colour tokens in tokens.css, in both themes.

tokens.css is the single source of truth for colours. It has two theme blocks,
``:root[data-theme="dark"]`` (also plain ``:root``, the default) and
``:root[data-theme="light"]``, with the same token names. This module reads the
colour tokens of a theme and checks every foreground and background pair the UI
actually uses, in each theme, against the AA thresholds:

* 4.5:1 for normal text (WCAG 1.4.3),
* 3:1 for UI components, focus rings and large text (WCAG 1.4.11).

Glass surfaces and tints are semi-transparent. Each has a solid "twin" token
(its colour over the surface it sits on), and the pairs check text on the
twins. ``COMPOSITES`` says which rgba token over which base makes each twin,
and ``GRADIENT_STOPS`` does the same for the light ends of the allowed
gradients; tests/unit/test_contrast.py recomputes every twin so that it cannot
drift from its rgba value.

Run it directly to print a table of ratios::

    python -m backend.app.design.contrast
"""

import re
from pathlib import Path

from pydantic import BaseModel

from ..paths import TOKENS

TEXT_AA = 4.5
NON_TEXT_AA = 3.0
LARGE_TEXT_AA = 3.0  # WCAG 1.4.3: text of 24 px, or 18.7 px bold, and larger

THEMES: tuple[str, ...] = ("dark", "light")
_BLOCK = re.compile(r"(?P<selector>[^{}]+)\{(?P<body>[^{}]*)\}")
_HEX_TOKEN = re.compile(r"--(?P<name>[a-z0-9-]+)\s*:\s*(?P<value>#[0-9a-fA-F]{6})\s*;")
_RGBA_TOKEN = re.compile(
    r"--(?P<name>[a-z0-9-]+)\s*:\s*rgba\(\s*(?P<r>\d+)\s*,\s*(?P<g>\d+)\s*,\s*(?P<b>\d+)\s*,\s*(?P<a>[0-9.]+)\s*\)\s*;"
)

Rgba = tuple[int, int, int, float]


class ContrastPair(BaseModel):
    """A foreground token used on a background token, with its AA minimum."""

    foreground: str
    background: str
    minimum: float
    usage: str


# Every colour pairing used by the components, checked in both themes. Keep in step with app.css.
REQUIRED_PAIRS: tuple[ContrastPair, ...] = tuple(
    ContrastPair(foreground=fg, background=bg, minimum=minimum, usage=usage)
    for fg, bg, minimum, usage in (
        # Text on the page, the header and the sidebar.
        ("text", "bg", TEXT_AA, "body text"),
        ("text-muted", "bg", TEXT_AA, "secondary text, footer"),
        ("text-soft", "bg", TEXT_AA, "hero lede"),
        ("text-nav", "header-solid", TEXT_AA, "site navigation"),
        ("text", "sidebar-solid", TEXT_AA, "product name in the top bar"),
        ("text-soft", "sidebar-solid", TEXT_AA, "top bar link"),
        ("text-muted", "sidebar-solid", TEXT_AA, "sidebar environment line"),
        ("label", "sidebar-solid", TEXT_AA, "sidebar section labels"),
        ("text", "nav-active-solid", TEXT_AA, "selected top bar link, menu entry hover"),
        ("text", "veil-solid", TEXT_AA, "project switcher, glass button"),
        ("text-soft", "veil-solid", TEXT_AA, "hero pill"),
        ("count-text", "count-solid", TEXT_AA, "review count in the sidebar"),
        ("success-text", "mode-solid", TEXT_AA, "reading mode: live"),
        ("text-muted", "mode-solid", TEXT_AA, "reading mode: model run"),
        # Text in glass cards, rows and insets.
        ("text", "glass-solid", TEXT_AA, "text in glass cards"),
        ("text-muted", "glass-solid", TEXT_AA, "secondary text in glass cards"),
        ("text-soft", "glass-solid", TEXT_AA, "body copy in glass cards"),
        ("label-table", "glass-solid", TEXT_AA, "table headings"),
        ("blue-text", "glass-solid", TEXT_AA, "links in cards"),
        ("warning-text", "glass-solid", TEXT_AA, "[PLACEHOLDER] marks"),
        ("text", "deep-solid", TEXT_AA, "table rows and value rows"),
        ("text-muted", "deep-solid", TEXT_AA, "sources in rows"),
        ("blue-text", "deep-solid", TEXT_AA, "links in rows"),
        ("text", "row-hover-solid", TEXT_AA, "table row, hover"),
        ("text-muted", "row-hover-solid", TEXT_AA, "table row source, hover"),
        ("text", "inset-solid", TEXT_AA, "values in a conflict pair"),
        ("text-muted", "inset-solid", TEXT_AA, "sources and quotes in a conflict pair"),
        ("text", "conflict-chip", TEXT_AA, "values on the conflict cards of the review screen"),
        ("text-muted", "conflict-chip", TEXT_AA, "sources on the conflict cards of the review screen"),
        ("text", "field-solid", TEXT_AA, "text typed in an input"),
        ("text-muted", "field-solid", TEXT_AA, "input placeholder"),
        ("text", "upload-inner", TEXT_AA, "upload box input"),
        ("text-muted", "upload-inner", TEXT_AA, "upload box placeholder"),
        # Buttons.
        ("on-red", "red", TEXT_AA, "primary button label"),
        ("on-red", "red-hover", TEXT_AA, "primary button label, hover"),
        ("text", "veil-hover-solid", TEXT_AA, "glass button label, hover"),
        ("text", "tonal-solid", TEXT_AA, "tonal button label, selected pager item"),
        ("text", "tonal-hover-solid", TEXT_AA, "tonal button label, hover"),
        ("text", "active-solid", TEXT_AA, "selected filter, document chip and toggle segment"),
        ("text-soft", "neutral-chip", TEXT_AA, "edit icon button glyph, neutral chip"),
        ("text", "neutral-hover-solid", TEXT_AA, "icon button glyph, hover"),
        ("success-text", "approve-solid", TEXT_AA, "approve icon button glyph"),
        ("success-text", "approve-hover-solid", TEXT_AA, "approve icon button glyph, hover"),
        ("red-text", "reject-solid", TEXT_AA, "reject icon button glyph"),
        ("red-text", "reject-hover-solid", TEXT_AA, "reject icon button glyph, hover"),
        # Chips: coloured text on its own tint.
        ("success-text", "success-chip", TEXT_AA, "High and Approved chips"),
        ("blue-text", "review-chip", TEXT_AA, "Needs review chip, info alert"),
        ("red-text", "conflict-chip", TEXT_AA, "Conflict chip, error alert"),
        ("warning-text", "missing-chip", TEXT_AA, "Missing chip, warning alert"),
        # Non-text indicators (WCAG 1.4.11).
        ("red", "glass-solid", NON_TEXT_AA, "conflict dot and segment"),
        ("success", "glass-solid", NON_TEXT_AA, "ring gauge arc, approved segment, High dot"),
        ("warning", "glass-solid", NON_TEXT_AA, "review segment, Medium dot"),
        ("blue-text", "glass-solid", NON_TEXT_AA, "Low confidence ring"),
        ("success", "deep-solid", NON_TEXT_AA, "High dot in rows"),
        ("warning", "deep-solid", NON_TEXT_AA, "Medium dot in rows"),
        ("red", "deep-solid", NON_TEXT_AA, "Conflict dot in rows"),
        ("red", "bg", NON_TEXT_AA, "red line under the header, hero pill dot"),
        ("focus", "bg", NON_TEXT_AA, "keyboard focus ring"),
        ("focus", "glass-solid", NON_TEXT_AA, "keyboard focus ring in cards"),
        ("focus", "deep-solid", NON_TEXT_AA, "keyboard focus ring in rows"),
        ("focus", "sidebar-solid", NON_TEXT_AA, "keyboard focus ring in the top bar"),
        # The app screens (Stage UX): rows, chips and tabs directly on the page.
        # Rows on the page take the glass tone (text, chips and marks on glass-solid are checked above).
        ("text", "veil-page-solid", TEXT_AA, "glass button and step number on the page"),
        ("text-soft", "veil-page-solid", TEXT_AA, "file count on the Files tab"),
        ("text", "veil-hover-page-solid", TEXT_AA, "glass button on the page, hover"),
        ("text", "tonal-page-solid", TEXT_AA, "tonal button on the page"),
        ("text", "active-page-solid", TEXT_AA, "selected filter on the page"),
        ("count-text", "count-page-solid", TEXT_AA, "count on the Check tab"),
        # Stage UX-V: the technical-drawing style.
        ("red", "bg", LARGE_TEXT_AA, "the red accent word in a headline (headlines only, 24 px and larger)"),
        ("label-table", "bg", TEXT_AA, "uppercase mono labels and block titles on the page"),
        ("blue-text", "bg", TEXT_AA, "the Show all values toggle"),
        ("word-dim", "bg", TEXT_AA, "statement words on the home page before the scroll brightens them"),
        ("red-text", "bg", TEXT_AA, "step numbers on the home page"),
        ("text-muted", "veil-page-solid", TEXT_AA, "view button on Check"),
        ("text", "veil-hover-page-solid", TEXT_AA, "view button on Check, hover"),
        ("count-text", "count-veil-solid", TEXT_AA, "count on a view button"),
        ("count-text", "count-active-solid", TEXT_AA, "count on the open view button"),
        ("label-table", "bg", TEXT_AA, "table headings and panel labels on the page"),
        ("text-soft", "bg", TEXT_AA, "summary sentence on Check"),
        ("blue-text", "bg", TEXT_AA, "links on the page"),
        ("red-text", "bg", TEXT_AA, "error state of a file on the page"),
        ("warning-text", "bg", TEXT_AA, "not-read state of a file on the page"),
        ("text", "field-page-solid", TEXT_AA, "text typed in an input on the page"),
        ("text-muted", "field-page-solid", TEXT_AA, "input placeholder on the page"),
        ("text-soft", "surface", TEXT_AA, "menu entries"),
        ("red-text", "surface", TEXT_AA, "Delete in a menu"),
        ("red", "glass-solid", NON_TEXT_AA, "red edge of a conflict card"),
    )
)

# Solid twin -> (semi-transparent token, the token it sits on).
COMPOSITES: dict[str, tuple[str, str]] = {
    "glass-solid": ("glass", "bg"),
    "deep-solid": ("deep", "glass-solid"),
    "sidebar-solid": ("sidebar", "bg"),
    "veil-solid": ("veil", "glass-solid"),
    "veil-hover-solid": ("veil-hover", "glass-solid"),
    "tonal-solid": ("tonal", "glass-solid"),
    "tonal-hover-solid": ("tonal-hover", "glass-solid"),
    "nav-active-solid": ("nav-active", "sidebar-solid"),
    "active-solid": ("active", "glass-solid"),
    "row-hover-solid": ("row-hover", "glass-solid"),
    "success-chip": ("tint-success", "glass-solid"),
    "conflict-chip": ("tint-conflict", "glass-solid"),
    "missing-chip": ("tint-missing", "glass-solid"),
    "review-chip": ("tint-review", "glass-solid"),
    "neutral-chip": ("tint-neutral", "glass-solid"),
    "neutral-hover-solid": ("tint-neutral-hover", "deep-solid"),
    "approve-solid": ("tint-approve", "deep-solid"),
    "approve-hover-solid": ("tint-approve-hover", "deep-solid"),
    "reject-solid": ("tint-reject", "deep-solid"),
    "reject-hover-solid": ("tint-reject-hover", "deep-solid"),
    "count-solid": ("tint-count", "sidebar-solid"),
    "mode-solid": ("mode-bg", "sidebar-solid"),
    "field-solid": ("field", "glass-solid"),
    "inset-solid": ("inset", "glass-solid"),
    "header-solid": ("header", "bg"),
    "veil-page-solid": ("veil", "bg"),
    "veil-hover-page-solid": ("veil-hover", "bg"),
    "tonal-page-solid": ("tonal", "bg"),
    "active-page-solid": ("active", "bg"),
    "count-page-solid": ("tint-count", "bg"),
    "field-page-solid": ("field", "bg"),
    "count-veil-solid": ("tint-count", "veil-page-solid"),
    "count-active-solid": ("tint-count", "active-page-solid"),
}

# Twins of gradient stops and other colours that are not tokens: (r, g, b, alpha) over a token.
GRADIENT_STOPS: dict[str, tuple[Rgba, str]] = {
}


def _channel(value: int) -> float:
    """Linearise one sRGB channel (0-255) as defined by WCAG."""
    srgb = value / 255
    return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_colour: str) -> float:
    """Relative luminance of a #RRGGBB colour, from 0 (black) to 1 (white)."""
    match = re.fullmatch(r"#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})", hex_colour)
    if not match:
        raise ValueError(f"expected #RRGGBB, got {hex_colour!r}")
    red, green, blue = (_channel(int(part, 16)) for part in match.groups())
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: str, second: str) -> float:
    """WCAG contrast ratio between two colours, from 1 to 21."""
    lighter, darker = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _theme_block(theme: str, stylesheet: Path) -> str:
    """The body of the rule whose selector list names ``:root[data-theme="<theme>"]``."""
    css = re.sub(r"/\*.*?\*/", "", stylesheet.read_text(encoding="utf-8"), flags=re.S)
    wanted = f':root[data-theme="{theme}"]'
    for m in _BLOCK.finditer(css):
        if wanted in [part.strip() for part in m["selector"].split(",")]:
            return m["body"]
    raise ValueError(f"no {wanted} block in {stylesheet}")


def load_tokens(theme: str = "dark", stylesheet: Path = TOKENS) -> dict[str, str]:
    """Return the hex colour tokens of one theme, without ``--``."""
    return {m["name"]: m["value"] for m in _HEX_TOKEN.finditer(_theme_block(theme, stylesheet))}


def load_rgba_tokens(theme: str = "dark", stylesheet: Path = TOKENS) -> dict[str, Rgba]:
    """Return the rgba() colour tokens of one theme, without ``--``."""
    return {m["name"]: (int(m["r"]), int(m["g"]), int(m["b"]), float(m["a"]))
            for m in _RGBA_TOKEN.finditer(_theme_block(theme, stylesheet))}


def composite(rgba: Rgba, base: str) -> str:
    """The solid colour of ``rgba`` drawn over the #RRGGBB colour ``base``, rounded per channel."""
    *rgb, alpha = rgba
    under = (int(base[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(alpha * c + (1 - alpha) * u):02X}" for c, u in zip(rgb, under, strict=True))


def main() -> None:
    """Print the ratio of every required pair in each theme as a Markdown table."""
    print("| Theme | Foreground | Background | Ratio | Minimum | Result | Used for |")
    print("|---|---|---|---|---|---|---|")
    for theme in THEMES:
        tokens = load_tokens(theme)
        for pair in REQUIRED_PAIRS:
            ratio = contrast_ratio(tokens[pair.foreground], tokens[pair.background])
            result = "pass" if ratio >= pair.minimum else "FAIL"
            print(
                f"| {theme} | `--{pair.foreground}` {tokens[pair.foreground]} "
                f"| `--{pair.background}` {tokens[pair.background]} "
                f"| {ratio:.2f} | {pair.minimum} | {result} | {pair.usage} |"
            )


if __name__ == "__main__":
    main()
