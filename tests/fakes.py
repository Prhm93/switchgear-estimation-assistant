"""Fake model providers for tests. They never call a model; their output is labelled fake.

``ScriptedProvider`` answers each page prompt from a script keyed by page
number. ``oracle_script`` builds such a script from a project's answer key
(the true values with their source texts as quotes), plus a few deliberately
bad items, so tests can see good values kept and bad ones rejected.
"""

from __future__ import annotations

import json
import re
from typing import Any

from estimation_assistant.providers import ModelReply

from data_generator.schemas import AnswerKey, DocumentKind

FAKE_MODEL = "fake-test-model"


class ScriptedProvider:
    """Replies with ``script[page]`` (a list of value dicts) to the prompt of that page."""

    mode = "ollama"
    model = FAKE_MODEL

    def __init__(self, script: dict[int, list[dict[str, Any]]], raw: dict[int, str] | None = None) -> None:
        self.script = script
        self.raw = raw or {}
        self.prompts: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str, schema: dict[str, Any]) -> ModelReply:
        self.prompts.append((system, prompt))
        page = int(re.search(r"^Page: (\d+)$", prompt, re.MULTILINE).group(1))
        content = self.raw.get(page, json.dumps({"values": self.script.get(page, [])}))
        return ModelReply(model=FAKE_MODEL, model_version="fake00000000", content=content, seconds=0.0)


def oracle_script(key: AnswerKey, document: DocumentKind) -> dict[int, list[dict[str, Any]]]:
    """The answer key's values of one document, as a perfect model would report them."""
    script: dict[int, list[dict[str, Any]]] = {}
    for v in key.values:
        src = v.source
        if src.document == document and src.page and src.source_text and v.value is not None:
            script.setdefault(src.page, []).append({"field": v.field, "value": v.value, "unit": v.unit,
                                                    "quote": src.source_text})
    return script
