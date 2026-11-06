"""The model provider interface: modes, the Ollama client (against a local stand-in server), recordings.

No model is called. The Ollama tests run a tiny HTTP server in a thread that
answers like Ollama's /api/tags and /api/chat, so the request the client sends
can be checked.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import backend.app.llm  # noqa: F401  (makes the AI engine importable)
from estimation_assistant.providers import (MODES, ModelUnavailable, OllamaProvider, RecordedProvider, Recording,
                                            RecordingMismatch, RecordingProvider, load_recording, make_provider,
                                            save_recording, sha256_bytes)
from tests.fakes import ScriptedProvider


class _Ollama(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *args) -> None:  # keep test output quiet
        pass

    def _send(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self._send({"models": [{"name": "gemma4:e2b", "model": "gemma4:e2b", "digest": "abcdef1234567890"}]})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Ollama.requests.append(body)
        self._send({"message": {"role": "assistant", "content": '{"values": []}'}, "done": True})


@pytest.fixture
def ollama_url() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Ollama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _Ollama.requests.clear()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_modes() -> None:
    assert MODES == ("rules", "recorded", "ollama", "ollama-local")
    assert make_provider("rules") is None
    assert make_provider("ollama").mode == "ollama"
    local = make_provider("ollama-local")
    assert local.mode == "ollama-local" and local.options["num_ctx"] == 4096 and local.keep_alive == "2m"
    with pytest.raises(RecordingMismatch):
        make_provider("recorded")  # never without a recording checked by hash
    with pytest.raises(ValueError):
        make_provider("cloud")


def test_ollama_client_sends_structured_output_request(ollama_url) -> None:
    schema = {"type": "object", "properties": {"values": {"type": "array"}}}
    reply = OllamaProvider(ollama_url, "gemma4:e2b").generate("system text", "user text", schema)
    assert reply.content == '{"values": []}' and reply.model_version == "abcdef123456"
    body = _Ollama.requests[-1]
    assert body["format"] == schema and body["stream"] is False
    assert body["options"]["temperature"] == 0
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_ollama_down_raises_model_unavailable() -> None:
    with pytest.raises(ModelUnavailable):
        OllamaProvider("http://127.0.0.1:9", timeout_s=2).generate("s", "p", {})


def test_model_not_pulled_raises_model_unavailable(ollama_url) -> None:
    with pytest.raises(ModelUnavailable, match="not pulled"):
        OllamaProvider(ollama_url, "other-model:1b").generate("s", "p", {})


def _fake_recording(data: bytes) -> Recording:
    """A small FAKE recording made by this test, never by a model."""
    rec = RecordingProvider(ScriptedProvider({1: [{"field": "system.voltage", "value": 400, "unit": "V",
                                                   "quote": "400 V"}]}))
    rec.generate("SYSTEM", "Page: 1\nhello", {})
    recording = rec.recording(input_name="FAKE/input.txt", data=data, prompt_version="test",
                              system_prompt="SYSTEM", prompt_template="{text}")
    return recording.model_copy(update={"fake": True})


def test_recorded_replay_equals_the_saved_output(tmp_path: Path) -> None:
    data = b"fake input file"
    path = tmp_path / "fake.json"
    save_recording(_fake_recording(data), path)
    recording = load_recording(path, data)
    assert recording.fake and "fake test recording" in recording.label
    assert recording.input_sha256 == sha256_bytes(data)
    reply = RecordedProvider(recording).generate("SYSTEM", "Page: 1\nhello", {})
    assert json.loads(reply.content) == {"values": [{"field": "system.voltage", "value": 400, "unit": "V",
                                                      "quote": "400 V"}]}


def test_recording_for_other_bytes_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "fake.json"
    save_recording(_fake_recording(b"the laptop-built file"), path)
    with pytest.raises(RecordingMismatch, match="refused"):
        load_recording(path, b"the laptop-built file, rebuilt elsewhere")


def test_changed_prompt_is_refused_not_answered() -> None:
    provider = RecordedProvider(_fake_recording(b"x"))
    with pytest.raises(RecordingMismatch):
        provider.generate("SYSTEM", "Page: 1\nhello, changed", {})
    with pytest.raises(RecordingMismatch):
        provider.generate("ANOTHER SYSTEM PROMPT", "Page: 1\nhello", {})
