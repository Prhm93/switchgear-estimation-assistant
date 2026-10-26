"""Runs the tools from tools.py safely, so a bad request from the model never crashes the agent."""

import ollama
MODEL = "gemma4:e2b"
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


def run_agent(question:str, max_rounds:int = 5) -> str:
    """Ask the model, stop when it answers in text, and give up at the round limit."""

    # The history starts with the user's question
    messages = [{"role":"user", "content":question}]

    for round_number in range(1, max_rounds+1):
        print(f"Round {round_number}")

        # Ask the model, sending the whole history and the tool functions
        response = ollama.chat(
            model=MODEL,
            messages=messages,
            tools=list(TOOLS.values()),
            think=False,
        )

        # Keep the model's reply in the history
        messages.append(response.message)

        # No tool request means the model has finished
        if not response.message.tool_calls:
            return response.message.content
    return "Stopped: reached the round limit."
 
