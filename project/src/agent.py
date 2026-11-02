"""Runs the tools from tools.py safely and drives the agent loop."""

import ollama

from retrieval import search_notes
from schemas import AgentResult, ToolStep
from tools import line_total, list_parts, lookup_price

MODEL = "gemma4:e2b"

TOOLS = {
    "lookup_price": lookup_price,
    "list_parts": list_parts,
    "line_total": line_total,
    "search_notes": search_notes,
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


def run_agent(question: str, max_rounds: int = 5) -> AgentResult:
    """Ask the model, run the tools it requests, and return the answer with the steps taken."""
    # The history starts with the user's question
    messages = [{"role": "user", "content": question}]
    # A record of every tool run, kept for the final result
    steps: list[ToolStep] = []

    for round_number in range(1, max_rounds + 1):
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
            return AgentResult(answer=response.message.content or "", steps=steps)

        # Run each requested tool, record the step, and keep the result in the history
        for call in response.message.tool_calls:
            name = call.function.name
            arguments = dict(call.function.arguments)
            result = run_tool(name, arguments)
            print(f"  {name}({arguments}) -> {result}")
            steps.append(ToolStep(name=name, arguments=arguments, result=result))
            messages.append({"role": "tool", "tool_name": name, "content": result})

    return AgentResult(answer="Stopped: reached the round limit.", steps=steps)
