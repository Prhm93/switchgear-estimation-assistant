"""The breaker drawing (Stage UX visual pass, V2) and its developer page.

tools/make_breaker_svg.py draws an invented, generic air circuit breaker with the standard library only
and a fixed seed, so the committed SVG is exactly what the generator writes. Each part is a group with
an id, a 3D explode vector and a leader line ending on an anchor defined in 3D. The page that shows it
alone exists only with DEBUG_PAGES on, which is off by default and in Docker.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.paths import REPO_ROOT, STATIC_DIR

sys.path.insert(0, str(REPO_ROOT / "tools"))
import make_breaker_svg as gen  # noqa: E402

SVG = (STATIC_DIR / "img" / "breaker.svg").read_text(encoding="utf-8")
PARTS = ["front-plate", "frame", "arc-chutes", "arcing-contacts", "moving-contacts", "fixed-contacts",
         "isolating-contacts", "rear-terminals", "slide-rails", "auxiliary-switches", "position-indicator"]


def group(part: str) -> str:
    return re.search(rf'<g id="bk-{part}" [^>]*>', SVG).group(0)


def test_the_committed_drawing_is_exactly_what_the_generator_writes() -> None:
    first, second = gen.build(), gen.build()
    assert first == second  # a fixed seed: the same bytes every build
    assert first == SVG, "run python tools/make_breaker_svg.py"


def test_the_generator_uses_only_the_standard_library() -> None:
    tree = ast.parse((REPO_ROOT / "tools" / "make_breaker_svg.py").read_text(encoding="utf-8"))
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert modules <= set(sys.stdlib_module_names), modules - set(sys.stdlib_module_names)


def test_pencil_look_is_geometry_not_a_filter_and_the_file_stays_small() -> None:
    assert "<filter" not in SVG and "feTurbulence" not in SVG and "feDisplacement" not in SVG
    assert "<image" not in SVG and "href=" not in SVG  # line art only, nothing loaded
    assert len(SVG.encode()) < 130_000


def test_every_part_is_a_group_with_an_id_and_an_explode_vector() -> None:
    for part in PARTS:
        g = group(part)
        assert f'data-part="{part}"' in g and re.search(r'style="--dx:-?[\d.]+;--dy:-?[\d.]+"', g), part
    moving = {p: re.search(r"--dx:(-?[\d.]+);--dy:(-?[\d.]+)", group(p)).groups() for p in PARTS}
    assert moving["front-plate"] == moving["position-indicator"] != ("0", "0")  # they slide forward together
    assert moving["arc-chutes"][0] == "0" and float(moving["arc-chutes"][1]) < 0  # lifted straight up
    for part in set(PARTS) - {"front-plate", "position-indicator", "arc-chutes"}:
        assert moving[part] == ("0", "0"), part


def test_each_label_has_a_leader_that_ends_on_its_part_anchor() -> None:
    labels = re.findall(r'<g class="bk-label" data-part="([^"]+)">(.*?)</g>', SVG)
    anchors = dict(re.findall(r'<circle class="bk-anchor" data-part="([^"]+)" (cx="[^"]+" cy="[^"]+")', SVG))
    assert {p for p, _ in labels} == set(PARTS) == set(anchors)
    for part, body in labels:
        leader = re.search(r'd="([^"]+)" data-x="[^"]+" data-y="[^"]+" data-elbow="[^"]+" '
                           r'data-ax="([^"]+)" data-ay="([^"]+)" data-dx="([^"]+)" data-dy="([^"]+)"', body)
        d, ax, ay, dx, dy = leader.groups()
        assert d.endswith(f"L{ax} {ay}"), part  # closed: the leader ends exactly on the anchor
        assert anchors[part] == f'cx="{ax}" cy="{ay}"', part
        assert re.search(rf'id="bk-{part}" [^>]*--dx:{re.escape(dx)};--dy:{re.escape(dy)}', SVG), part


def test_it_reads_as_an_invented_air_circuit_breaker() -> None:
    parts = {p.key: p for p in gen.model() if not p.group}
    plates = [m for m in parts["arc-chutes"].marks if m[0][1] == m[1][1] == 58.0]  # plates seen on the top
    per_chute = len(plates) // len(gen.POLES)
    assert 12 <= per_chute <= 16
    stems = {round(f.points[0][0], 1) for f in parts["rear-terminals"].faces}
    assert 3 <= len({round(x) for x in gen.POLES}) <= 4 and len(stems) >= 3
    assert "ILLUSTRATIVE, NOT TO SCALE" in SVG
    texts = re.findall(r"<text[^>]*>([^<]+)</text>", SVG)
    allowed = {p.label.upper() for p in parts.values()} | {"ILLUSTRATIVE, NOT TO SCALE"}
    assert set(texts) <= allowed  # labels only: no names, logos or model numbers


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator:
    clients = []

    def make(debug: bool | None) -> TestClient:
        extra = {} if debug is None else {"debug_pages": debug}
        settings = Settings(database_url=f"sqlite:///{(tmp_path / 'app.sqlite').as_posix()}",
                            storage_dir=tmp_path / "storage", environment="test", drawing_reading="off", **extra)
        client = TestClient(create_app(settings))
        clients.append(client.__enter__())
        return client

    yield make
    for c in clients:
        c.__exit__(None, None, None)


def test_the_debug_page_is_404_by_default(make_client) -> None:
    assert Settings().debug_pages is False
    assert make_client(None).get("/debug/breaker").status_code == 404
    assert make_client(False).get("/debug/breaker?anchors=1").status_code == 404


def test_the_debug_page_shows_the_drawing_and_its_anchor_points(make_client) -> None:
    client = make_client(True)
    page = client.get("/debug/breaker").text
    assert '<svg xmlns="http://www.w3.org/2000/svg" class="breaker"' in page and "show-anchors" not in page
    assert "/static/js/breaker.js" in page and "data-breaker-explode" in page
    with_anchors = client.get("/debug/breaker?anchors=1").text
    assert 'class="breaker-frame show-anchors"' in with_anchors


def test_docker_keeps_the_debug_pages_off() -> None:
    compose = (REPO_ROOT / "deployment" / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r'DEBUG_PAGES:\s*"false"', compose)
    assert "DEBUG_PAGES" not in (REPO_ROOT / "deployment" / "Dockerfile").read_text(encoding="utf-8")
