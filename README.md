# agentic-ai (private)

Learning notebooks and a small project: an agent that prices electrical parts with tools, on a synthetic catalogue. Built with Gemma 4 and Ollama on Colab.

Last updated: 26 Oct 2026

## Map

| Path | What it is | Read it when |
|---|---|---|
| `tutorials/01-llm-basics.ipynb` | Setup, messages, roles, history, JSON output, Pydantic (Stages 0 to 4) | You need the basics |
| `tutorials/02-tools-and-agent-loop.ipynb` | Functions, tool calls, the agent loop (Stage 5) | You need to understand tools |
| `project/src/tools.py` | The catalogue and three tools | You change parts or prices |
| `project/src/agent.py` | `run_tool` (safe execution) and `run_agent` (the loop) | You change how the agent runs |
| `project/notebooks/01-colab-run-agent.ipynb` | Runs the project files on the real model | You test the agent |
| `project/docs/01-tool-layer-and-safe-execution.ipynb` | Written report on the tool layer | You explain the project to someone |

## Status

| Piece | State |
|---|---|
| `tools.py` | Done, tested on the laptop |
| `run_tool` | Done, tested on the laptop |
| `run_agent`: model call and stop rule | Written, laptop tests pass, not yet run on the real model |
| `run_agent`: running the requested tools | Not written |
| Output checks, retrieval with sources, drawing images | Not started |

## How to restart after a break

1. `cd D:\parham\Parham_Learning\agentic-ai`
2. `.venv\Scripts\Activate.ps1`
3. `git pull`
4. Open the notebook, select the Colab kernel (T4), and run the setup cells first. Colab forgets everything when a session ends.
5. Paste `tools.py` and `agent.py` into Colab with `%%writefile` if the files are not there.

## Rules

1. Synthetic data only. No real prices, part numbers, drawings or company text.
2. Before every push, read `git status`.
3. Laptop tests use the terminal. Model tests need Colab, because Ollama is not installed on the laptop.

