"""LLM extraction (Stage 3): schema, prompt, quote check, extraction and the combined rules + LLM result.

The model provider interface and the number check live in the AI engine
(``ai_engine/estimation_assistant``). Docker, CI and the README set
``PYTHONPATH`` so it imports; the fallback below covers a plain
``python -m backend.evaluate`` from the repo root.
"""

from __future__ import annotations

import sys

from backend.app.paths import REPO_ROOT

try:
    import estimation_assistant  # noqa: F401
except ImportError:  # pragma: no cover - depends on how Python was started
    sys.path.append(str(REPO_ROOT / "ai_engine"))
