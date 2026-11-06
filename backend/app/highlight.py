"""Split a page of document text into plain and highlighted segments.

The template renders each segment with autoescaping, so document text is
always shown as text: a ``<script>`` in a document appears as the characters
``<script>``, never as markup. This module only finds where the source texts
are; it never builds HTML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Segment:
    text: str
    value_ids: list[int] = field(default_factory=list)  # values whose source text this is

    @property
    def marked(self) -> bool:
        return bool(self.value_ids)


def _pattern(source_text: str) -> re.Pattern[str]:
    """Match the source text with any run of whitespace (a clause may wrap over lines), as whole words."""
    body = r"\s+".join(re.escape(w) for w in source_text.split())
    start = r"(?<!\w)" if source_text.strip()[0].isalnum() else ""
    end = r"(?!\w)" if source_text.strip()[-1].isalnum() else ""
    return re.compile(start + body + end)


def _find(text: str, source: str, anchor: str | None) -> re.Match[str] | None:
    """First occurrence; with an anchor (a table row's way id), only inside the line that starts with it."""
    pattern = _pattern(source)
    if anchor:
        for line in re.finditer(r"[^\n]+", text):
            if line.group(0).startswith(anchor + " "):
                if m := pattern.search(text, line.start(), line.end()):
                    return m
        return None
    return pattern.search(text)


def segments(text: str, sources: list[tuple[int, str, str | None]]) -> list[Segment]:
    """``sources`` holds (value id, source text, anchor or None). Each is marked at its first occurrence.

    Overlapping sources share one highlighted span (the union), listing every value id.
    """
    spans: list[tuple[int, int, int]] = []
    for value_id, source, anchor in sources:
        if source and source.strip() and (m := _find(text, source, anchor)):
            spans.append((m.start(), m.end(), value_id))
    spans.sort()
    merged: list[tuple[int, int, list[int]]] = []
    for start, end, vid in spans:
        if merged and start < merged[-1][1]:
            s, e, ids = merged[-1]
            merged[-1] = (s, max(e, end), ids + [vid])
        else:
            merged.append((start, end, [vid]))
    out: list[Segment] = []
    pos = 0
    for start, end, ids in merged:
        if start > pos:
            out.append(Segment(text[pos:start]))
        out.append(Segment(text[start:end], sorted(set(ids))))
        pos = end
    if pos < len(text):
        out.append(Segment(text[pos:]))
    return out
