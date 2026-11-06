"""One interface for every model call, with four modes.

- ``rules``: no model at all. :func:`make_provider` returns ``None`` and the
  app uses its rule-based extractor only. This mode always works.
- ``recorded``: replays model replies saved earlier (on a Colab GPU). A
  recording belongs to one input file: it stores the SHA-256 of that file's
  bytes, and :func:`load_recording` refuses it for any other bytes. Each reply
  is found by the SHA-256 of its prompt, so a changed prompt is refused too
  rather than answered with an old reply.
- ``ollama``: live calls to an Ollama server (Colab, or any machine with a GPU).
- ``ollama-local``: the same client with settings for a laptop with 8 GB of
  RAM and no GPU: a small context window, the model unloaded two minutes
  after its last call (so it stays loaded through one document), and a long timeout.

Only the Python standard library is used (``urllib``), so no extra package is
needed and nothing has to be installed on a laptop that never calls a model.
Replies are structured output: the JSON schema of the expected answer is sent
as Ollama's ``format`` and the reply text must parse as JSON.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

ModelMode = Literal["rules", "recorded", "ollama", "ollama-local"]
MODES: tuple[str, ...] = ("rules", "recorded", "ollama", "ollama-local")
RECORDING_SCHEMA = "1.0"


class ModelUnavailable(RuntimeError):
    """The model cannot answer (server down, model not pulled, bad reply). The caller falls back to rules."""


class RecordingMismatch(ValueError):
    """A recording does not belong to this input: its SHA-256 or a prompt differs. Never replayed."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ModelReply(BaseModel):
    """One model answer: the raw reply text (JSON) and where it came from."""

    model_config = ConfigDict(extra="forbid")

    model: str
    model_version: str  # Ollama's model digest (first 12 characters), or "unknown"
    content: str
    seconds: float = Field(ge=0)


class ModelProvider(Protocol):
    """Anything that answers a system prompt plus a user prompt with JSON matching ``schema``."""

    mode: str
    model: str

    def generate(self, system: str, prompt: str, schema: dict[str, Any]) -> ModelReply: ...


# --- live: Ollama --------------------------------------------------------------------------------

class OllamaProvider:
    """Calls ``POST /api/chat`` on an Ollama server with structured output.

    ``temperature`` 0 and a fixed ``seed`` make the replies as repeatable as
    Ollama allows; they are still not guaranteed identical across GPUs, which
    is why the app replays recordings rather than calling the model again.
    """

    def __init__(self, url: str = "http://127.0.0.1:11434", model: str = "gemma4:e2b", *,
                 mode: str = "ollama", options: dict[str, Any] | None = None, keep_alive: str | None = None,
                 timeout_s: float = 300.0) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.mode = mode
        self.options = {"temperature": 0, "seed": 42, **(options or {})}
        self.keep_alive = keep_alive
        self.timeout_s = timeout_s
        self._version: str | None = None

    def _post(self, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method="POST" if data else "GET",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:  # noqa: S310 (configured URL)
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise ModelUnavailable(f"Ollama at {self.url} did not answer: {error}") from error

    def version(self) -> str:
        """The digest of the pulled model, so a recording says exactly which weights answered."""
        if self._version is None:
            tags = self._post("/api/tags", None)
            digest = next((m.get("digest", "") for m in tags.get("models", [])
                           if m.get("name") == self.model or m.get("model") == self.model), "")
            if not digest:
                raise ModelUnavailable(f"Model {self.model} is not pulled on {self.url}.")
            self._version = digest[:12]
        return self._version

    def generate(self, system: str, prompt: str, schema: dict[str, Any]) -> ModelReply:
        body: dict[str, Any] = {
            "model": self.model, "stream": False, "format": schema, "options": self.options,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if self.keep_alive is not None:
            body["keep_alive"] = self.keep_alive
        version = self.version()
        start = time.perf_counter()
        reply = self._post("/api/chat", body)
        seconds = time.perf_counter() - start
        content = (reply.get("message") or {}).get("content")
        if not isinstance(content, str):
            raise ModelUnavailable(f"Ollama reply has no message content: {str(reply)[:200]}")
        return ModelReply(model=self.model, model_version=version, content=content, seconds=round(seconds, 3))


def ollama_local(url: str, model: str) -> OllamaProvider:
    """Laptop settings: a 4k context and small batches to save memory; unloaded 2 minutes after the last call."""
    return OllamaProvider(url, model, mode="ollama-local", options={"num_ctx": 4096, "num_batch": 64},
                          keep_alive="2m", timeout_s=900.0)


# --- recorded ------------------------------------------------------------------------------------

class RecordedCall(BaseModel):
    """One saved model call, keyed by the SHA-256 of its full prompt."""

    model_config = ConfigDict(extra="forbid")

    key: str  # a label for people, e.g. "page 3"
    prompt_sha256: str
    reply: str
    seconds: float = Field(ge=0)


class Recording(BaseModel):
    """Saved model output for one input file. ``fake`` marks recordings made by tests, never by a model."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = RECORDING_SCHEMA
    model: str
    model_version: str
    created: str  # ISO 8601 date and time (UTC) of the run
    mode: str  # the mode that produced it: "ollama" or "ollama-local"
    prompt_version: str
    system_prompt: str
    prompt_template: str
    input_name: str  # e.g. "T03/specification.pdf"; for people only, never used to find a recording
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calls: list[RecordedCall] = Field(default_factory=list)
    fake: bool = False

    @property
    def label(self) -> str:
        """What the UI shows, e.g. ``gemma4:e2b, 2026-11-07``."""
        text = f"{self.model}, {self.created[:10]}"
        return f"{text} (fake test recording)" if self.fake else text


def load_recording(path: Path, data: bytes) -> Recording:
    """Read a recording and check it belongs to ``data``; raise :class:`RecordingMismatch` if not."""
    recording = Recording.model_validate_json(path.read_text(encoding="utf-8"))
    actual = sha256_bytes(data)
    if recording.input_sha256 != actual:
        raise RecordingMismatch(f"Recording {path.name} is for SHA-256 {recording.input_sha256[:12]}..., "
                                f"this file is {actual[:12]}...; refused.")
    return recording


def save_recording(recording: Recording, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(recording.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


class RecordedProvider:
    """Replays a :class:`Recording`. A prompt that was not recorded is refused, never answered."""

    mode = "recorded"

    def __init__(self, recording: Recording) -> None:
        self.recording = recording
        self.model = recording.model
        self._by_prompt = {c.prompt_sha256: c for c in recording.calls}

    def generate(self, system: str, prompt: str, schema: dict[str, Any]) -> ModelReply:
        if system != self.recording.system_prompt:
            raise RecordingMismatch("The system prompt changed since this recording was made; refused.")
        call = self._by_prompt.get(sha256_text(prompt))
        if call is None:
            raise RecordingMismatch("This prompt is not in the recording (the page text or prompt changed); "
                                    "refused.")
        return ModelReply(model=self.recording.model, model_version=self.recording.model_version,
                          content=call.reply, seconds=call.seconds)


class RecordingProvider:
    """Wraps a live provider and keeps every call, to be saved as a :class:`Recording`."""

    def __init__(self, inner: ModelProvider) -> None:
        self.inner = inner
        self.mode = inner.mode
        self.model = inner.model
        self.calls: list[RecordedCall] = []
        self.last_version = "unknown"
        self.system: str | None = None

    def generate(self, system: str, prompt: str, schema: dict[str, Any], key: str = "") -> ModelReply:
        reply = self.inner.generate(system, prompt, schema)
        self.system = system
        self.last_version = reply.model_version
        self.calls.append(RecordedCall(key=key or f"call {len(self.calls) + 1}", prompt_sha256=sha256_text(prompt),
                                       reply=reply.content, seconds=reply.seconds))
        return reply

    def recording(self, *, input_name: str, data: bytes, prompt_version: str, system_prompt: str,
                  prompt_template: str) -> Recording:
        return Recording(model=self.model, model_version=self.last_version,
                         created=datetime.now(UTC).replace(microsecond=0).isoformat(), mode=self.mode,
                         prompt_version=prompt_version, system_prompt=system_prompt, prompt_template=prompt_template,
                         input_name=input_name, input_sha256=sha256_bytes(data), calls=self.calls)


def make_provider(mode: str, *, url: str = "http://127.0.0.1:11434", model: str = "gemma4:e2b",
                  recording: Recording | None = None) -> ModelProvider | None:
    """The provider for a mode. ``rules`` gives ``None``; ``recorded`` needs a recording checked by hash."""
    if mode == "rules":
        return None
    if mode == "recorded":
        if recording is None:
            raise RecordingMismatch("Recorded mode needs a recording whose SHA-256 matches the file.")
        return RecordedProvider(recording)
    if mode == "ollama":
        return OllamaProvider(url, model)
    if mode == "ollama-local":
        return ollama_local(url, model)
    raise ValueError(f"Unknown model mode {mode!r}; expected one of {', '.join(MODES)}.")
