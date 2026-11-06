"""Tests for the WCAG contrast checker and the design tokens in app.css."""

import pytest

from backend.app.design.contrast import (
    COMPOSITES,
    GRADIENT_STOPS,
    REQUIRED_PAIRS,
    ContrastPair,
    composite,
    contrast_ratio,
    load_rgba_tokens,
    load_tokens,
    relative_luminance,
)


def test_luminance_of_black_and_white() -> None:
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance("#FFFFFF") == pytest.approx(1.0)


def test_black_on_white_is_21_to_1() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)


def test_ratio_does_not_depend_on_order() -> None:
    assert contrast_ratio("#121417", "#F2F1EC") == contrast_ratio("#F2F1EC", "#121417")


def test_short_hex_is_rejected() -> None:
    with pytest.raises(ValueError):
        relative_luminance("#fff")


def test_tokens_are_read_from_the_stylesheet() -> None:
    tokens = load_tokens()
    for name in ("bg", "surface", "surface-2", "text", "text-muted", "red", "blue", "focus"):
        assert name in tokens, f"--{name} missing from :root"


@pytest.mark.parametrize(
    "pair", REQUIRED_PAIRS, ids=lambda p: f"{p.foreground}-on-{p.background}"
)
def test_every_required_pair_meets_wcag_aa(pair: ContrastPair) -> None:
    """Text pairs need 4.5:1, UI components and large text need 3:1 (WCAG 2.2 AA)."""
    tokens = load_tokens()
    ratio = contrast_ratio(tokens[pair.foreground], tokens[pair.background])
    assert ratio >= pair.minimum, (
        f"{pair.foreground} on {pair.background}: {ratio:.2f} < {pair.minimum}"
    )


def test_every_solid_twin_matches_its_rgba_over_its_base() -> None:
    """A twin may differ from the recomputed composite by at most 1 per channel (rounding)."""
    tokens, rgba = load_tokens(), load_rgba_tokens()
    sources = {twin: (rgba[src], tokens[base]) for twin, (src, base) in COMPOSITES.items()}
    sources |= {twin: (stop, tokens[base]) for twin, (stop, base) in GRADIENT_STOPS.items()}
    for twin, (colour, base) in sources.items():
        expected = composite(colour, base)
        got = tokens[twin]
        diff = max(abs(int(expected[i:i + 2], 16) - int(got[i:i + 2], 16)) for i in (1, 3, 5))
        assert diff <= 1, f"--{twin} is {got}, but {colour} over {base} is {expected}"


def test_composite_of_opaque_and_clear_colours() -> None:
    assert composite((255, 0, 0, 1.0), "#000000") == "#FF0000"
    assert composite((255, 0, 0, 0.0), "#123456") == "#123456"
    assert composite((255, 255, 255, 0.5), "#000000") == "#808080"


def test_every_pair_names_existing_tokens() -> None:
    tokens = load_tokens()
    for pair in REQUIRED_PAIRS:
        assert pair.foreground in tokens and pair.background in tokens, pair
