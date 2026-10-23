"""Runs the tools from tools.py safely, so a bad request from the model never crashes the agent."""

from tools import line_total, list_parts, lookup_price

TOOLS = {
    "lookup_price": lookup_price,
    "list_parts": list_parts,
    "line_total": line_total,
}


def run_tool(name: str, arguments: dict) -> str:
    """Run one tool by name and return its result as text.
    An unknown tool name or wrong inputs return a message instead of raising an error."""
    # Reject names the model made up
    if name not in TOOLS:
        return f"Unknown tool '{name}'. Valid tools: {', '.join(TOOLS)}"
    try:
        return str(TOOLS[name](**arguments))
    except TypeError as error:
        # Raised when the inputs do not match the tool's parameters
        return f"Bad inputs for '{name}': {error}"