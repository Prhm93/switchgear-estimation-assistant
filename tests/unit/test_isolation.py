"""The database tests can never be pointed at the app's own database."""

from __future__ import annotations

import pytest

from tests.isolation import UnsafeTestDatabase, database_url_for_tests, empty_test_database, ensure_test_database

APP = "postgresql+pg8000://sea:secret@localhost:5432/sea"


def test_the_test_database_is_the_app_name_plus_test() -> None:
    assert database_url_for_tests(APP).endswith("@localhost:5432/sea_test")


def test_an_explicit_test_database_must_be_named_test() -> None:
    assert database_url_for_tests(APP, "postgresql+pg8000://u:p@db:5432/other_test").endswith("/other_test")
    with pytest.raises(UnsafeTestDatabase):
        database_url_for_tests(APP, "postgresql+pg8000://u:p@db:5432/other")


def test_the_app_database_is_refused_as_a_test_database() -> None:
    with pytest.raises(UnsafeTestDatabase):
        database_url_for_tests(APP, APP)
    with pytest.raises(UnsafeTestDatabase):
        database_url_for_tests("postgresql+pg8000://u:p@db/sea_test", "postgresql+pg8000://u:p@db:5432/sea_test")


def test_the_write_helpers_refuse_a_database_not_named_test() -> None:
    with pytest.raises(UnsafeTestDatabase):
        empty_test_database(APP)
    with pytest.raises(UnsafeTestDatabase):
        ensure_test_database(APP)
