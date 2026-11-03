"""Tests for run_tool in agent.py."""

from estimation_assistant import agent
from estimation_assistant.agent import run_tool


def test_run_tool_returns_message_when_tool_raises():
    """A tool error other than TypeError comes back as text instead of stopping the run."""
    result = run_tool("lookup_price", {"part_name": 5})
    assert isinstance(result, str)
    assert "lookup_price" in result
    assert "AttributeError" in result

def test_run_tool_returns_message_when_search_backend_fails(monkeypatch):
    """A failure inside search_notes, such as an unreachable embedding server, comes back as text."""

    def broken_search(question: str) -> str:
        raise ConnectionError("embedding server not reachable")

    monkeypatch.setitem(agent.TOOLS, "search_notes", broken_search)
    result = agent.run_tool("search_notes", {"question": "what does a busbar do"})
    assert result == "Tool 'search_notes' failed with ConnectionError: embedding server not reachable"
