"""The theme switch (Stage UX visual pass): in the top bar of every page, dark by default."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app

PAGES = ["/", "/enquiries", "/enquiries/new", "/health"]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="off")
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.mark.parametrize("url", PAGES)
def test_every_page_has_the_switch_in_its_top_bar_and_starts_dark(client: TestClient, url: str) -> None:
    html = client.get(url).text
    assert '<html lang="en-GB" data-theme="dark">' in html
    bar = re.search(r'<header class="(?:topbar|site-header)">.*?</header>', html, re.S).group(0)
    button = re.search(r"<button[^>]*data-theme-toggle[^>]*>", bar).group(0)
    assert 'type="button"' in button and "hidden" in button  # shown by theme.js only
    assert 'aria-label="Switch to light theme"' in button
    assert "/static/js/theme.js" in html and "/static/css/tokens.css" in html
