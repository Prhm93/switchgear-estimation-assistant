"""Tests for the catalogue tools. No model needed."""

import pytest

from estimation_assistant.tools import PRICES, line_total, list_parts, lookup_price


@pytest.mark.parametrize("part, price", PRICES.items())
def test_lookup_price_returns_each_price_as_text(part, price):
    assert lookup_price(part) == str(price)


@pytest.mark.parametrize("name", ["  Cable Gland ", "BUSBAR", "McCb"])
def test_lookup_price_ignores_case_and_edge_spaces(name):
    assert lookup_price(name) == str(PRICES[name.strip().lower()])


def test_lookup_price_unknown_part_names_it_and_lists_valid_parts():
    reply = lookup_price("fuse")
    assert "fuse" in reply
    for part in PRICES:
        assert part in reply


def test_lookup_price_docstring_lists_every_part():
    # The model only knows the names the docstring gives it
    for part in PRICES:
        assert part in lookup_price.__doc__


def test_list_parts_returns_every_part_in_order():
    assert list_parts() == "mccb, acb, busbar, current transformer, cable gland"


@pytest.mark.parametrize(
    "unit_price, quantity, total",
    [(95.0, 3, 285.0), (1.75, 4, 7.0), (2850.0, 0, 0.0)],
)
def test_line_total(unit_price, quantity, total):
    assert line_total(unit_price, quantity) == total


def test_line_total_rounds_to_two_decimals():
    assert 0.1 * 3 != 0.3
    assert line_total(0.1, 3) == 0.3
