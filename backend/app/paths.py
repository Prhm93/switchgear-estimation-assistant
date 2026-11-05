"""Filesystem locations used by the app, resolved from the repo root.

Keeping them in one place means the app runs the same from the repo folder,
from pytest and inside the Docker image (where the repo is copied to /app).
"""

from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
FRONTEND_DIR: Path = REPO_ROOT / "frontend"
TEMPLATES_DIR: Path = FRONTEND_DIR / "templates"
STATIC_DIR: Path = FRONTEND_DIR / "static"
STYLESHEET: Path = STATIC_DIR / "css" / "app.css"
