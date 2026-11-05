"""Tests for the hand-drawn SVG icon set."""

import xml.etree.ElementTree as ET

from backend.app.paths import STATIC_DIR

SVG_NS = "{http://www.w3.org/2000/svg}"
REQUIRED_ICONS = {"switchboard", "breaker", "document", "drawing", "check", "warning"}


def _sprite() -> ET.Element:
    return ET.parse(STATIC_DIR / "icons" / "icons.svg").getroot()


def test_sprite_has_every_required_icon() -> None:
    ids = {symbol.get("id", "") for symbol in _sprite().iter(f"{SVG_NS}symbol")}
    assert REQUIRED_ICONS <= {symbol_id.removeprefix("i-") for symbol_id in ids}


def test_icons_are_plain_line_art() -> None:
    """Design rule: no gradients, filters (glow) or embedded images."""
    banned = {"linearGradient", "radialGradient", "filter", "image"}
    tags = {element.tag.removeprefix(SVG_NS) for element in _sprite().iter()}
    assert not tags & banned
