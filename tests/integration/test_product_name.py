"""One product name everywhere (12 Nov 2026): "Switchgear Estimation Assistant".

It is in the top bar of every page, the tab title and the footer, and in the README. Under 700 px the
top bar may show a shorter form: the first word is wrapped so CSS can hide it, while the full name
stays in the HTML.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.paths import REPO_ROOT, STYLESHEET

NAME = "Switchgear Estimation Assistant"
PAGES = ["/", "/enquiries", "/enquiries/new", "/health"]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                        storage_dir=tmp_path / "storage", environment="test", drawing_reading="off")
    with TestClient(create_app(settings)) as c:
        yield c


def text_of(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", html).split())


def test_the_settings_name_is_the_product_name() -> None:
    assert Settings().app_name == NAME


@pytest.mark.parametrize("url", PAGES)
def test_every_page_names_the_product_in_its_title_top_bar_and_footer(client: TestClient, url: str) -> None:
    html = client.get(url).text
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    assert title.endswith(NAME), title
    bar = re.search(r'<header class="(?:topbar|site-header)">.*?</header>', html, re.S).group(0)
    brand = re.search(r'<span class="brand__name">.*?</a>', bar, re.S)  # the name, inner spans and all
    assert text_of(brand.group(0)) == NAME, brand.group(0)
    footer = re.search(r'<footer class="(?:footer|site-footer)">.*?</footer>', html, re.S).group(0)
    assert NAME in text_of(footer)


def test_an_enquiry_page_names_the_product_too(client: TestClient) -> None:
    created = client.post("/enquiries", data={"name": "Name check"}, follow_redirects=True)
    assert created.status_code == 200 and str(created.url).endswith("/files")
    html = created.text
    assert re.search(r"<title>.*" + NAME + r"</title>", html)
    assert NAME in text_of(re.search(r'<header class="topbar">.*?</header>', html, re.S).group(0))


def test_the_short_form_is_only_under_700px() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")
    block = re.search(r"@media \(max-width: 699px\) \{(.*?)\n\}", css, re.S).group(1)
    assert ".brand__lead { display: none; }" in block
    assert ".brand__lead" not in css.split("@media (max-width: 699px)")[0].split("/* 4.")[0]


def test_the_readme_uses_the_name() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith(f"# {NAME}")
    assert "Estimation Assistant" not in readme.replace(NAME, "")  # no other form of the name
