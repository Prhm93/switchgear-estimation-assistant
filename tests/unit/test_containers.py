"""Stage 8: the containers run as a non-root user, with memory limits, and listen on this machine only."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (ROOT / "deployment" / "Dockerfile").read_text(encoding="utf-8")
COMPOSE_TEXT = (ROOT / "deployment" / "docker-compose.yml").read_text(encoding="utf-8")


def services() -> dict[str, str]:
    """Each service's block of the compose file (no YAML library: the file's layout is fixed and simple)."""
    body = COMPOSE_TEXT.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    parts = re.split(r"^  (\w+):\n", body, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_the_app_image_runs_as_an_unprivileged_user() -> None:
    lines = [ln.strip() for ln in DOCKERFILE.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    users = [ln.split()[1] for ln in lines if ln.startswith("USER ")]
    assert users and users[-1] not in ("root", "0")
    first_user = next(i for i, ln in enumerate(lines) if ln.startswith("USER "))
    cmd = next(i for i, ln in enumerate(lines) if ln.startswith("CMD "))
    assert first_user < cmd  # the server starts as that user
    assert re.search(r"useradd [^\n]*--uid 10001", DOCKERFILE)


def test_every_service_has_a_memory_limit_and_a_local_only_port() -> None:
    found = services()
    assert set(found) == {"db", "app"}
    for name, block in found.items():
        limit = re.search(r"limits:\s*\n\s*memory: (\d+)m", block)
        assert limit and int(limit.group(1)) <= 512, name
        for port in re.findall(r'^\s*- "([^"]+:\d+)"', block, flags=re.M):
            assert port.startswith("127.0.0.1:"), (name, port)


def test_recorded_model_runs_are_mounted_read_only_and_debug_pages_are_off() -> None:
    app = services()["app"]
    assert re.search(r"- \.\./data/recorded:/app/data/recorded:ro", app)
    assert 'DEBUG_PAGES: "false"' in app


def test_pip_is_upgraded_before_the_requirements_are_installed() -> None:
    assert re.search(r'pip install --upgrade "pip>=26\.3" && pip install -r requirements\.txt', DOCKERFILE)
