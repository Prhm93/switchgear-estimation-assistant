"""WCAG 2.2 contrast checks for the colour tokens in app.css.

The stylesheet is the single source of truth for colours. This module reads
the hex tokens from its ``:root`` block and checks every foreground and
background pair the UI actually uses against the AA thresholds:

* 4.5:1 for normal text (WCAG 1.4.3),
* 3:1 for UI components, focus rings and large text (WCAG 1.4.11).

Run it directly to print a table of ratios::

    python -m backend.app.design.contrast
"""

import re
from pathlib import Path

from pydantic import BaseModel

from ..paths import STYLESHEET

TEXT_AA = 4.5
NON_TEXT_AA = 3.0

_ROOT_BLOCK = re.compile(r":root\s*\{(?P<body>.*?)\}", re.DOTALL)
_HEX_TOKEN = re.compile(r"--(?P<name>[a-z0-9-]+)\s*:\s*(?P<value>#[0-9a-fA-F]{6})\s*;")


class ContrastPair(BaseModel):
    """A foreground token used on a background token, with its AA minimum."""

    foreground: str
    background: str
    minimum: float
    usage: str


# Every colour pairing used by the components. Keep in step with app.css.
REQUIRED_PAIRS: tuple[ContrastPair, ...] = tuple(
    ContrastPair(foreground=fg, background=bg, minimum=minimum, usage=usage)
    for fg, bg, minimum, usage in (
        # Body text and secondary text on each surface level.
        ("text", "bg", TEXT_AA, "body text"),
        ("text", "surface", TEXT_AA, "text in panels and cards"),
        ("text", "surface-2", TEXT_AA, "text in raised controls"),
        ("text-muted", "bg", TEXT_AA, "secondary text"),
        ("text-muted", "surface", TEXT_AA, "secondary text in cards"),
        ("text-muted", "surface-2", TEXT_AA, "secondary text in raised controls"),
        # Filled primary button: label on the accent fill.
        ("on-accent", "accent-fill", TEXT_AA, "primary button label"),
        ("on-accent", "accent-fill-hover", TEXT_AA, "primary button label, hover"),
        # Coloured text (links, badge labels) on dark surfaces.
        ("steel-text", "bg", TEXT_AA, "links"),
        ("steel-text", "surface", TEXT_AA, "links and Low badge in cards"),
        ("success-text", "surface", TEXT_AA, "Approved and High badge"),
        ("warning-text", "surface", TEXT_AA, "Needs review and Medium badge"),
        ("accent-text", "surface", TEXT_AA, "Conflict badge"),
        # The same badges inside document cards, which sit on surface-2.
        ("steel-text", "surface-2", TEXT_AA, "Extracted badge in a card"),
        ("success-text", "surface-2", TEXT_AA, "Approved badge in a card"),
        ("warning-text", "surface-2", TEXT_AA, "Needs review badge in a card"),
        ("accent-text", "surface-2", TEXT_AA, "Conflict badge in a card"),
        # Non-text indicators: active tab underline, focus ring, badge borders.
        ("accent", "bg", NON_TEXT_AA, "active tab underline, focus ring"),
        ("accent", "surface", NON_TEXT_AA, "active state in cards"),
        ("steel", "surface", NON_TEXT_AA, "Low confidence outline"),
        ("success", "surface", NON_TEXT_AA, "status dot"),
        ("warning", "surface", NON_TEXT_AA, "status dot"),
        ("border-strong", "bg", NON_TEXT_AA, "input and toggle outlines"),
        ("border-strong", "surface", NON_TEXT_AA, "input and toggle outlines in panels"),
        ("border-strong", "surface-2", NON_TEXT_AA, "circular action buttons in a card"),
    )
)


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


def load_tokens(stylesheet: Path = STYLESHEET) -> dict[str, str]:
    """Return the hex colour tokens from the first ``:root`` block, without ``--``."""
    match = _ROOT_BLOCK.search(stylesheet.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"no :root block in {stylesheet}")
    return {m["name"]: m["value"] for m in _HEX_TOKEN.finditer(match["body"])}


def main() -> None:
    """Print the ratio of every required pair as a Markdown table."""
    tokens = load_tokens()
    print("| Foreground | Background | Ratio | Minimum | Result | Used for |")
    print("|---|---|---|---|---|---|")
    for pair in REQUIRED_PAIRS:
        ratio = contrast_ratio(tokens[pair.foreground], tokens[pair.background])
        result = "pass" if ratio >= pair.minimum else "FAIL"
        print(
            f"| `--{pair.foreground}` {tokens[pair.foreground]} "
            f"| `--{pair.background}` {tokens[pair.background]} "
            f"| {ratio:.2f} | {pair.minimum} | {result} | {pair.usage} |"
        )


if __name__ == "__main__":
    main()
