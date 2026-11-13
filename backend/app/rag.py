"""The question box (Stage 9): answers about one enquiry from its own files, with the source passage.

How a question is answered:

1. The enquiry's stored page text is cut into short **passages** (two lines, one line of overlap), each keeping
   its file and page (:func:`chunk_pages`).
2. Passages and the question are turned into vectors by an **embedder** (:class:`Embedder`): ``ollama`` uses
   ``mxbai-embed-large`` on an Ollama server (Colab); ``words`` needs no model: a fixed hashing of the words, so
   the laptop and the tests work with nothing downloaded. In the app, the vectors are stored with pgvector.
3. The closest passages are found by cosine similarity (:func:`search`). If the best one is below the
   embedder's ``min_score``, the answer is a **refusal**: there is no evidence in the files, so nothing is said.
4. Otherwise the answer quotes the best line of the best passage and names its file and page
   (:func:`answer`); no text is generated, so nothing can be invented. Every **number** in the quote is checked
   against the engineer's approved values: one that is not approved is said to be "not approved yet".
5. Files are data, never instructions: a passage with instruction-like text (:mod:`backend.app.injection`) is
   shown with a note that it was not followed.

``min_score`` of the word embedder (0.2) was set on the made-up passages of the unit tests only, not on any
data set.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from backend.app import normalise as norm
from backend.app.injection import find_instructions

CLAUSE = re.compile(r"^\s*\d+(?:\.\d+)+\s+")  # a numbered clause at the start of a line ("3.4 ")
NUMBER = re.compile(r"(?<![A-Za-z0-9.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")  # as ai_engine checks
WORD = re.compile(r"[a-z]+|\d+(?:\.\d+)?")
STOP = set("a an and are as at be by can do does for from has have how i in is it its many much of on or "
           "please shall should tell that the their there these this to was what when where which who will "
           "with would you".split())
SUFFIXES = ("ing", "ed", "es", "s")


@dataclass(frozen=True)
class PageText:
    document_id: int
    document: str  # the file's name as uploaded
    kind: str  # specification, schematic, requirements
    page: int
    text: str


@dataclass(frozen=True)
class Passage:
    document_id: int
    document: str
    kind: str
    page: int
    text: str


@dataclass(frozen=True)
class Approved:
    """An approved value, for the number check."""

    field: str
    value: Any
    unit: str | None


@dataclass
class Answer:
    question: str
    text: str
    refused: bool
    sources: list[Passage] = field(default_factory=list)
    score: float | None = None
    quote: str | None = None
    unapproved_numbers: list[float] = field(default_factory=list)
    approved_numbers: list[float] = field(default_factory=list)
    flagged: bool = False

    def sources_json(self) -> list[dict[str, Any]]:
        return [{"document_id": p.document_id, "document": p.document, "page": p.page, "text": p.text}
                for p in self.sources]


class Embedder(Protocol):
    name: str
    min_score: float  # below this, the best passage is no evidence

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbedderUnavailable(RuntimeError):
    """The embedding server could not be reached or gave a bad answer."""


def _stem(word: str) -> str:
    for suffix in SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def words(text: str) -> list[str]:
    return [_stem(w) for w in WORD.findall(text.lower()) if w not in STOP]


class HashingEmbedder:
    """Words (no model): each word is hashed to one of ``dim`` places with a sign; vectors have unit length."""

    name = "words"
    min_score = 0.2

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for w in words(text):
                h = hashlib.sha256(w.encode("utf-8")).digest()
                vec[int.from_bytes(h[:4], "big") % self.dim] += 1.0 if h[4] % 2 else -1.0
            length = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / length for x in vec])
        return out


class OllamaEmbedder:
    """``mxbai-embed-large`` on an Ollama server (Colab); never needed on the laptop."""

    name = "mxbai-embed-large"
    min_score = 0.5  # a cosine that mxbai gives to unrelated English text is below this; checked on Colab only

    def __init__(self, url: str = "http://127.0.0.1:11434", model: str = "mxbai-embed-large",
                 timeout: float = 60.0) -> None:
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout
        self.name = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        request = urllib.request.Request(f"{self.url}/api/embed", data=body,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - fixed scheme
                reply = json.loads(response.read())
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise EmbedderUnavailable(f"no embeddings from {self.url}: {error}") from error
        vectors = reply.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbedderUnavailable("the embedding server gave a bad answer")
        return vectors


def make_embedder(mode: str, url: str = "http://127.0.0.1:11434") -> Embedder:
    if mode == "words":
        return HashingEmbedder()
    if mode == "ollama":
        return OllamaEmbedder(url)
    raise ValueError(f"unknown embedder {mode!r}; use words or ollama")


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    la, lb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (la * lb) if la and lb else 0.0


def chunk_pages(pages: Sequence[PageText], lines: int = 2, overlap: int = 1) -> list[Passage]:
    """Short passages of ``lines`` non-empty lines, ``overlap`` lines shared with the next one."""
    out: list[Passage] = []
    step = max(1, lines - overlap)
    for p in pages:
        rows = [r.strip() for r in p.text.splitlines() if r.strip()]
        for start in range(0, max(1, len(rows) - overlap), step):
            chunk = rows[start:start + lines]
            if chunk:
                out.append(Passage(p.document_id, p.document, p.kind, p.page, "\n".join(chunk)))
    return out


def search(question: str, passages: Sequence[Passage], vectors: Sequence[Sequence[float]], embedder: Embedder,
           k: int = 3) -> list[tuple[float, Passage]]:
    """The ``k`` closest passages, best first."""
    if not passages or not question.strip():
        return []
    q = embedder.embed([question])[0]
    scored = sorted(((cosine(q, v), p) for p, v in zip(passages, vectors, strict=True)), key=lambda x: -x[0])
    return scored[:k]


def _numbers(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in NUMBER.findall(text)]


def _approved_numbers(approved: Sequence[Approved]) -> set[float]:
    out = set()
    for a in approved:
        key = norm.value_key(a.value)
        if isinstance(key, (int, float)):
            out.add(round(float(key), 3))
        elif isinstance(a.value, str):
            out |= {round(n, 3) for n in _numbers(a.value)}
    return out


def _best_line(question: str, passage: Passage) -> str:
    q = set(words(question))
    rows = passage.text.splitlines()
    return max(rows, key=lambda r: (len(q & set(words(r))), -rows.index(r)))


def answer(question: str, hits: Sequence[tuple[float, Passage]], approved: Sequence[Approved],
           min_score: float) -> Answer:
    """Quote the best passage with its source, or refuse when there is no evidence (module docstring)."""
    question = question.strip()
    if not question or not hits or hits[0][0] < min_score:
        return Answer(question=question, refused=True, score=hits[0][0] if hits else None,
                      text="There is no evidence in this enquiry's files that answers this, so no answer is given. "
                           "Try other words, or check the files.")
    score, best = hits[0]
    quote = _best_line(question, best)
    where = f"{best.document}, {'sheet' if best.kind == 'schematic' else 'page'} {best.page}"
    parts = [f"{where} says: “{quote}”"]
    allowed = _approved_numbers(approved)
    numbers = _numbers(CLAUSE.sub("", quote, count=1))  # "3.4 Prospective fault level: 36 kA": 36, not 3.4
    ok = [n for n in numbers if round(n, 3) in allowed]
    not_ok = [n for n in numbers if round(n, 3) not in allowed]
    if ok:
        parts.append(f"{_list(ok)} {'matches an' if len(ok) == 1 else 'match'} approved value"
                     f"{'' if len(ok) == 1 else 's'}.")
    if not_ok:
        parts.append(f"{_list(not_ok)} {'is' if len(not_ok) == 1 else 'are'} read from the file and not approved "
                     "by an engineer yet.")
    flagged = bool(find_instructions(best.page, best.text))
    if flagged:
        parts.append("This passage contains text that looks like an instruction to the system. It is shown as data "
                     "and was not followed.")
    others = [p for s, p in hits[1:] if s >= min_score and p != best]
    return Answer(question=question, text=" ".join(parts), refused=False, sources=[best, *others[:2]], score=score,
                  quote=quote, unapproved_numbers=not_ok, approved_numbers=ok, flagged=flagged)


def _list(numbers: Sequence[float]) -> str:
    return ", ".join(f"{n:g}" for n in numbers)
