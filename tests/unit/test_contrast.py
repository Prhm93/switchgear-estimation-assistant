"""Tests for the WCAG contrast checker and the design tokens in app.css."""

import pytest

from backend.app.design.contrast import (
    REQUIRED_PAIRS,
    ContrastPair,
    contrast_ratio,
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
    for name in ("bg", "surface", "surface-2", "border", "text", "text-muted", "accent", "steel"):
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
