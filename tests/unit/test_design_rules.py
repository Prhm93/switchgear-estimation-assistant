"""Design rules from the brief, checked against the stylesheet.

These keep the look consistent as the stylesheet grows: no outlined
buttons or bordered cards, one gradient only (the header), 16px card
radius, 150 ms transitions and a visible keyboard focus ring.
"""

import re

import pytest

from backend.app.design.contrast import load_tokens
from backend.app.paths import STYLESHEET

CSS = STYLESHEET.read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    """Return the declarations of the first rule whose selector list is exactly ``selector``."""
    pattern = re.compile(r"(?:^|\})\s*" + re.escape(selector) + r"\s*\{(?P<body>[^}]*)\}", re.M)
    match = pattern.search(CSS)
    assert match, f"rule {selector!r} not found in app.css"
    return match["body"]


def test_brand_palette_tokens() -> None:
    tokens = {name: value.upper() for name, value in load_tokens().items()}
    assert tokens["bg"] == "#0A1630"
    assert tokens["surface"] == "#10224A"
    assert tokens["surface-2"] == "#16305F"
    assert tokens["text"] == "#F4F7FB"
    assert tokens["text-muted"] == "#A9B8D3"
    assert tokens["red"] == "#E31E24"
    assert tokens["blue"] == "#1C5FD1"


def test_no_hairline_borders_anywhere() -> None:
    """Surfaces are separated by tone and shadow, not 1px lines."""
    assert not re.search(r"border[a-z-]*\s*:\s*1px", CSS)
    assert "--hairline" not in CSS


@pytest.mark.parametrize(
    "selector",
    [".panel", ".doc-card", ".kpi", ".btn", ".icon-btn", ".badge", ".segmented"],
)
def test_components_have_no_border(selector: str) -> None:
    body = _rule(selector)
    # "border: 0" and "border: none" are allowed; any other border value is not.
    assert not re.search(r"(^|;|\s)border\s*:(?!\s*(?:0|none)\s*;)", body), (
        f"{selector} has a border"
    )


def test_only_one_gradient_and_it_is_the_header() -> None:
    assert len(re.findall(r"gradient\(", CSS)) == 1
    assert "gradient(" in _rule(".topbar")


def test_header_has_thin_red_line() -> None:
    assert re.search(r"border-bottom\s*:\s*2px solid var\(--red\)", _rule(".topbar"))


def test_cards_use_16px_radius_and_soft_shadow() -> None:
    assert re.search(r"--radius-card\s*:\s*16px", CSS)
    for selector in (".panel", ".kpi"):
        body = _rule(selector)
        assert "var(--radius-card)" in body
        assert "var(--shadow-card)" in body


def test_primary_button_is_solid_red_with_shadow() -> None:
    body = _rule(".btn--primary")
    assert "background: var(--red)" in body
    assert "box-shadow" in body


def test_transitions_are_150ms() -> None:
    assert re.search(r"--dur\s*:\s*150ms", CSS)


def test_keyboard_focus_ring_is_visible() -> None:
    body = _rule(":focus-visible")
    assert re.search(r"outline\s*:\s*2px solid var\(--focus\)", body)
