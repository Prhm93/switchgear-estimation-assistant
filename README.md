# switchgear-estimation-assistant

An agent that prices electrical parts with tools and answers questions from technical notes, on synthetic data.

> **Disclaimer:** this is an independent personal project. It uses synthetic data only. It is not affiliated with or endorsed by any company.

## Features

- **Tools:** look up a price, list the parts, work out a line total. Code does the arithmetic, not the model.
- **Agent loop:** the model asks for tools, code runs them, and a round limit stops the run.
- **Note search:** finds the closest of four notes by meaning, using embeddings.
- **Sources:** the run result lists the note ids used, filled in by code from the run log.
- **Number check:** the run result lists answer numbers that appear nowhere in the question or the tool log.

Built with Python, Pydantic and Ollama. Models: `gemma4:e2b` for chat, `mxbai-embed-large` for embeddings.

## Architecture

```text
question
   |
   v
run_agent (agent.py)  <--------------------------+
   |  asks the chat model, up to 5 rounds        |
   |                                             |
   +-- tool request --> run_tool (agent.py)      |
   |                      |-- lookup_price       |
   |                      |-- list_parts         |  tool results go
   |                      |-- line_total         |  back to the model
   |                      '-- search_notes ------+
   |                          (retrieval.py, embedding model)
   |
   +-- text answer --> build_result (agent.py)
                         |-- find_sources         note ids from the log
                         '-- unsupported_numbers  checks.py
                         |
                         v
                       AgentResult (schemas.py)
                       answer, steps, sources, unsupported
```

## Quick start

Python 3 is required. On Windows PowerShell, from the repo folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest
```

The tests need no model. To run the agent you need a running Ollama server with both models, which this project does on Colab (see below).

## Project structure

| Path | What it is |
|---|---|
| `src/estimation_assistant/tools.py` | The catalogue and three tools |
| `src/estimation_assistant/schemas.py` | The shape of a run: `ToolStep` and `AgentResult` |
| `src/estimation_assistant/retrieval.py` | Four synthetic notes, ranking by meaning, the `search_notes` tool |
| `src/estimation_assistant/checks.py` | The number check |
| `src/estimation_assistant/agent.py` | `run_tool`, `run_agent`, `build_result` |
| `tests/` | pytest tests for `tools.py` and `checks.py` |
| `notebooks/` | Colab runs on the real model |
| `docs/` | Written reports, with an [index](docs/README.md) |
| `data/` | A note on the data. All data is synthetic and lives in the code for now |
| `tutorials/` | Learning notebooks, kept separate from the project |

## Run the tests

```powershell
python -m pytest
```

There are 35 tests: 15 for `tools.py` and 20 for `checks.py`. They do not import `ollama` or call a model.

## Run on Colab

Colab forgets everything when a session ends, so repeat these steps each session.

1. Open a notebook from `notebooks/` and select a GPU runtime (T4).
2. Run the setup cells: GPU check, Ollama install, server start, Python client, model downloads.
3. Run the cell that creates `src/estimation_assistant/` and adds `src` to `sys.path`.
4. Run the `%%writefile` cells: schemas, tools, retrieval, checks, agent. The `%%writefile` line must be the first line of its cell.
5. Check the files with `!ls -l src/estimation_assistant`. A file of 1 byte means the cell was empty.

Download models with `ollama.pull(...).status`, not `!ollama pull`, which saves thousands of spinner characters into the notebook. If the embedding model changes, the notes must be embedded again by the same model.

When you change a `src` file, update its `%%writefile` cell too. To load a changed file in a live session, use the `importlib.import_module` cells. `from estimation_assistant import agent` alone can return the old module.

## Status

| Piece | State | Tested by |
|---|---|---|
| `tools.py` | Built | pytest |
| `checks.py` | Built | pytest |
| `schemas.py` | Built | Through the `checks.py` tests |
| Package layout and imports | Built | pytest; real model on Colab after the restructure (notebook 02, 3 Nov 2026) |
| `run_tool` | Built | By hand. No automated test |
| `run_agent` | Built | Real model: one-tool and two-tool questions re-run after the restructure (notebook 02, 3 Nov 2026); no-tool question before the restructure only |
| `retrieval.py`, `search_notes` | Built | Real model, re-run after the restructure (notebook 02, 3 Nov 2026): two question types, two embedding models |
| Sources and number check in the run result | Built | Real model, re-run after the restructure (notebook 02, 3 Nov 2026): three questions |
| `notebooks/01-colab-run-agent.ipynb` | Updated | Outputs predate the restructure; not re-run |
| `notebooks/02-colab-rag.ipynb` | Updated | Re-run on Colab after the restructure, 3 Nov 2026 |
| Reading drawing images | Not started | |

## Limits

- **Small tests.** Real-model results come from a few questions, on four notes. They show the parts work, not how often.
- **`run_tool` only catches `TypeError`.** Other errors stop the run. For example, `run_tool("lookup_price", {"part_name": 5})` raises `AttributeError`.
- **Refusal gap.** The search always returns the nearest note, even when no note fits. A refusal step exists only in a notebook prototype. In the project, `sources` lists the note even if the model declines to answer from it.
- **Number check, edge cases.** It reads digits only, so "three" is not checked. It ignores signs (`-5` reads as 5) and misreads `.5` as 5, `3rd` as 3, and `2,85` as 2 and 85.
- **Number check, scope.** It shows a number exists in the evidence, not that it is used correctly.
- **Tutorial results not yet cross-checked.** The multi-question cell (Cell 18) in `notebooks/02-colab-rag.ipynb` now has a saved output from 3 Nov 2026. The results typed up in `tutorials/03-rag-basics.ipynb` have not yet been checked against it.
- **Saved outputs are older than the code.** Notebook 01 outputs predate the restructure, and some come from older versions of the code. Notebook 02 was re-run on 3 Nov 2026, except Cell 11 (plain Python, no model), whose output is from an earlier run.
- **Notebook copies.** `%%writefile` cells are copies of `src` and can drift from it.
- **Search speed.** All four notes are embedded on every search, and only one note is returned.
- **Pricing.** There is one invented price per part type. Real quotes depend on ratings and sizes.

## Roadmap

1. Re-run notebook 01 on Colab (notebook 02 was re-run on 3 Nov 2026).
2. Add tests for `run_tool` and catch its other errors.
3. Add a refusal step to the agent, so a declined answer reports no source.
4. Keep the note embeddings between searches.
5. Read drawing images.
