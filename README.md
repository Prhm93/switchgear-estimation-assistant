# agentic-ai (private)

Learning notebooks and a small project: an agent that prices electrical parts with tools and answers questions from technical notes, on synthetic data. Built with Gemma 4 and Ollama on Colab.

Last updated: 2 Nov 2026

## Map

| Path | What it is | Read it when |
|---|---|---|
| `tutorials/01-llm-basics.ipynb` | Setup, messages, roles, history, JSON output, Pydantic (Stages 0 to 4) | You need the basics |
| `tutorials/02-tools-and-agent-loop.ipynb` | Functions, tool calls, the agent loop (Stage 5) | You need to understand tools |
| `tutorials/03-rag-basics.ipynb` | Embeddings, cosine similarity, ranking notes, answering from a note, and a map of how one question moves through the project | You need to understand retrieval |
| `project/src/tools.py` | The catalogue and three tools | You change parts or prices |
| `project/src/schemas.py` | The shape of a run: `ToolStep` and `AgentResult` | You change what a run returns |
| `project/src/retrieval.py` | Four synthetic notes, ranking by meaning, and the `search_notes` tool | You change the notes or the search |
| `project/src/checks.py` | Finds the numbers in a text and flags answer numbers with no evidence | You change the number check |
| `project/src/agent.py` | `run_tool` (safe execution), `run_agent` (the loop) and `build_result` | You change how the agent runs |
| `project/notebooks/01-colab-run-agent.ipynb` | Runs the project files on the real model | You test the agent |
| `project/notebooks/02-colab-rag.ipynb` | Retrieval experiments and the project test on the real model | You test retrieval |
| `project/docs/01-tool-layer-and-safe-execution.ipynb` | Written report on the tool layer | You explain the project to someone |
| `project/docs/02-agent-loop.ipynb` | Written report on the agent loop | You explain the project to someone |

## Status

| Piece | State |
|---|---|
| `tools.py` | Done, tested on the laptop and on Colab |
| `run_tool` | Done, tested on the laptop and on Colab |
| `run_agent` | Done. Runs requested tools, tested on the real model with no-tool, one-tool and two-tool questions. |
| `schemas.py`, typed `AgentResult` (answer plus the steps taken) | Done, tested on the real model |
| `retrieval.py`, `search_notes` tool | Done. Ranks four notes by meaning and returns the note id, score and text. The agent calls it. Tested on the real model: two question types, two embedding models compared. |
| Run result carries its sources | Done. `AgentResult.sources` lists the note ids returned by `search_notes`, filled by code from the run log, not by the model. The answer text itself does not repeat them. |
| Number check (`checks.py`) | Done. `AgentResult.unsupported` lists numbers in the answer that appear nowhere in the question or the tool log. Tested on the laptop with built results, and on the real model with three questions. It reads digits only, so numbers written as words are not checked. |
| Reading drawing images | Not started |

## How to restart after a break

1. `cd D:\parham\Parham_Learning\agentic-ai`
2. `.venv\Scripts\Activate.ps1`
3. `git pull`
4. Open the Colab notebook, select the Colab kernel (T4), and run the setup cells first. Colab forgets everything when a session ends.
5. Copy `schemas.py`, `tools.py`, `retrieval.py`, `checks.py` and `agent.py` into Colab with