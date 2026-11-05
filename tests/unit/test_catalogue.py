"""The invented parts catalogue: shape, committed file, matching rules."""

from pathlib import Path

import pytest

from data_generator import catalogue as cat

REPO = Path(__file__).resolve().parents[2]
CSV = REPO / "data" / "catalogue" / "catalogue.csv"


def test_about_sixty_parts_with_unique_codes():
    parts = cat.build_catalogue()
    assert 55 <= len(parts) <= 70
    codes = [p.code for p in parts]
    assert len(set(codes)) == len(codes)


def test_every_category_in_the_brief_is_present():
    found = {p.category for p in cat.build_catalogue()}
    assert found == set(cat.Category)


def test_committed_csv_matches_the_builder_byte_for_byte():
    assert CSV.read_bytes() == cat.catalogue_csv_text(cat.build_catalogue()).encode("utf-8")


def test_committed_csv_loads_and_validates():
    parts = cat.load_catalogue(CSV)
    assert parts == cat.build_catalogue()
    assert all(p.unit_price_gbp > 0 and p.labour_hours >= 0 for p in parts)
    assert {p.unit for p in parts} == {"each", "m"}


def test_match_prefers_the_lowest_breaking_capacity_that_fits():
    parts = cat.build_catalogue()
    p = cat.match_part(parts, cat.Category.MCCB, rating_a=250, poles=4, min_breaking_ka=25)
    assert p.breaking_ka == 36
    p = cat.match_part(parts, cat.Category.MCCB, rating_a=250, poles=4, min_breaking_ka=50)
    assert p.breaking_ka == 50


def test_match_raises_instead_of_guessing():
    parts = cat.build_catalogue()
    with pytest.raises(cat.NoMatchingPart):
        cat.match_part(parts, cat.Category.MCCB, rating_a=999, poles=4)
    with pytest.raises(cat.NoMatchingPart):
        cat.match_part(parts, cat.Category.MCCB, rating_a=100, poles=3, min_breaking_ka=50)
