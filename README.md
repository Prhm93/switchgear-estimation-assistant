# Switchgear Estimation Assistant

A web application that helps an engineer turn a customer enquiry for low-voltage switchgear into a checked, traceable draft estimate. The engineer uploads a specification, a schematic and a requirements document; the system extracts requirements, reads the drawing, cross-checks the two, matches parts to a catalogue and builds a draft estimate from approved values only. Every value links to its source and shows how it was found and how confident the system is.

> **Disclaimer:** this is an independent personal project. It uses synthetic data only: every document, drawing, part code and price is invented. It is not affiliated with or endorsed by any company.

The product is built in stages. Built so far:
- Synthetic data: an invented parts catalogue and an enquiry generator with exact answer keys (Stage 1).
- A working path from upload to Word report, with an audit log (Stage 2).
- Model extraction with a quote check, replayed from recorded runs on the laptop (Stage 3).
- OCR of drawing PDFs and images, a vision-model reader replayed from recordings, a breaker symbol detector, and boxes on the drawing (Stage 4).
- A redesign of every screen around one plain path, Files, Check, Quote (Stage UX).

See [Status](#status).

![Review screen with a conflict shown side by side (Stage 2 design)](docs/images/stage-2-review.png)

## Quick start (Docker)

Needs Docker Desktop. On an 8 GB laptop, cap the Docker memory first ([steps](docs/stage-0.md#cap-docker-and-wsl-memory)). From the repo folder in PowerShell:

```powershell
docker compose up --build
```

Then open these addresses:
- <http://127.0.0.1:8000/>: the home page.
- <http://127.0.0.1:8000/enquiries>: the enquiries. Old `/projects` addresses redirect here.
- <http://127.0.0.1:8000/health>: system status. It is also the "System status" link in the footer.
- <http://127.0.0.1:8000/healthz>: the same status as JSON.

A walk-through of the screens is in [Using the app](#using-the-app). Stop the app with `Ctrl+C` or `docker compose down`.

> **Warning:** never add `-v` to `docker compose down`. It deletes the database volume, and with it every enquiry.

## Using the app

1. **+ New enquiry.** Drop the customer's files (specification PDF, drawing as DXF, PDF or image, letter as DOCX), type a sentence about the enquiry, or both. A typed note alone starts the enquiry, and it opens on Files asking for the files. **Try the sample enquiry** loads the showcase files instead.
2. **Summary.** Six checks, each from the enquiry's own values:
   - what is quoted;
   - the parts found;
   - whether a drawing is attached;
   - whether the documents agree;
   - the estimated cost;
   - the required fields not found.
   Each check opens its detail below. The cost reads "Waiting for approvals" until a value is approved.
3. **1 Files.** Each file with its reading state, which updates as it is read. "Read again" and delete both ask first.
4. **2 Check.**
   - **To check** holds the conflicts side by side, then the values left for the engineer. "Accept all" approves only high-confidence, exact-quote, agreeing values that were not read from a picture; it shows the count first and asks once.
   - **Parts list** holds the items the customer wants.
   - A value is one fact read from the files. Approve it and it can be priced.
5. **3 Quote.** Lines built from approved values only, rebuilt after every decision, and the Word report.
6. **Details (⋯).** The proof viewer (each file's text with every value's source highlighted) and Activity (the audit log).

Values are read by rules, and drawing PDFs and images also by OCR. The sample enquiry also replays the recorded model runs whose input hash matches. Every value shows how it was read and its confidence. The theme switch (dark or light) is in the top bar.

## Local development

Python 3.12 or later. In PowerShell, from the repo folder:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest
```

Run the app without Docker, with a local SQLite database (created and migrated on start):

```powershell
$env:PYTHONPATH = "ai_engine;."
$env:DATABASE_URL = "sqlite:///./storage/dev.sqlite"
uvicorn backend.app.main:app --reload
```

Without `DATABASE_URL` the app still starts: the home page works, `/health` shows the database as "Not configured" and the product screens explain that a database is needed.

Run the database tests against the Docker database:

```powershell
docker compose up -d db
$env:DATABASE_URL = "postgresql+pg8000://sea:sea-local-only@127.0.0.1:5432/sea"
python -m pytest
Remove-Item Env:DATABASE_URL
```

The tests never write to the app's database: they use their own `<name>_test` database on the same server and empty it after each test.

Two settings change how values are read: `MODEL_MODE` (`rules`, the default, `recorded`, `ollama` or `ollama-local`) and `QUOTE_CHECK` (`relaxed`, the default, or `strict`, the Stage 3 baseline).

## Project structure

| Path | What it is |
|---|---|
| `backend/app/` | FastAPI app: storage, reading, rule extraction, catalogue matcher, estimate rules, screens, DOCX report, audit log, evaluation |
| `backend/migrations/` | Alembic migrations (`backend/alembic.ini`) |
| `ai_engine/estimation_assistant/` | The AI engine: tools, safe tool runner, agent loop, retrieval, number check |
| `frontend/templates/` | Jinja2 templates |
| `frontend/static/` | Design tokens and both themes (`css/tokens.css`), the stylesheet (`css/app.css`), self-hosted fonts, line icons, the breaker drawing (`img/breaker.svg`), small scripts |
| `tools/` | `make_breaker_svg.py`, which writes the illustrative breaker drawing from a fixed seed (`--check` says whether the file is up to date) |
| `tests/unit/`, `tests/integration/`, `tests/accuracy/` | pytest suites; CI runs a two-project accuracy subset |
| `deployment/` | Dockerfile and docker compose file (the root `compose.yaml` includes it) |
| `data_generator/` | Synthetic enquiry generator: catalogue, specification PDF, DXF schematic, scanned and photo versions, letter, answer keys |
| `data/` | Catalogue, showcase project, planted-problem list; test and training sets are rebuilt from seeds ([data/README.md](data/README.md)) |
| `docs/` | Stage reports (`stage-N.md`) and the earlier engine reports |
| `notebooks/` | Colab notebooks that run the engine on a T4 GPU |
| `tutorials/` | Learning notebooks, kept separate from the product |

## Status

| Stage | Scope | State |
|---|---|---|
| 0 Setup | Repo structure, Docker stack (Postgres + pgvector, app), design system health-check page, CI | Done: [report](docs/stage-0.md) |
| 1 Synthetic data | Enquiry generator, showcase project, 20 test projects, 300 training drawings, parts catalogue, real-drawing format | Done: [report](docs/stage-1.md) |
| 2 Thin slice (rules mode) | Upload to DOCX report with audit log | Done: [report](docs/stage-2.md) |
| Design v2 | Home page, sidebar app layout, project dashboard, glass design system (look only) | Done, then replaced by Stage UX: [report](docs/design-v2.md) |
| UX Redesign | "Enquiry" everywhere, top bar, steps Files, Check and Quote, Summary with six checks, start page with notes, dark and light themes, home page with the breaker drawing, test isolation, delete, archive and rename | Done: [report](docs/stage-ux.md) |
| 3 LLM extraction | Ollama and recorded modes, quote check, rules vs LLM scores | Done: Part A, 3b (cut-off fix, v2 Colab run and LLM scores) and 3c (relaxed quote check, the app default; strict v2 check kept as the baseline): [report](docs/stage-3.md) |
| 4 Drawing understanding | OCR, vision reading, symbol detector | In progress: Part A (Tesseract OCR of drawing PDFs and images, 300 dpi default; values marked for review) built and measured per clean, scanned and photo version. Part B (vision model, recorded mode; no recordings yet, NOT RUN YET), Part C (template symbol detector, all-class F1 0.867 to 0.909 per set and version; ACB almost never found) and Part D (boxes on the drawing in the proof viewer) built: [report](docs/stage-4.md) |
| 5 Cross-document checks | Conflicts and missing information | Not started |
| 6 Confidence and review | Approve, edit, reject; approved values only | Not started |
| 7 Evaluation | One-command evaluation of all test projects | Not started (CI already runs the tests) |
| 8 Hardening | Login, roles, upload checks, logging | Not started |
| 9 Assistant | Questions about a project, with sources | Not started |

Stage 9 (the question box) is listed after Stage 8. It is built before it, so that Stage 8's attack tests can run through the question box.

### Strict baseline scores

Strict quote check, fixed baseline. Not held out. Fair scores come from a fresh set in Stage 7.

| Set | With the DXF | Without the DXF |
|---|---|---|
| Test (20 enquiries) | 0.778 | 0.561 |
| Reworded (20 enquiries) | 0.727 | 0.497 |

Each score is the F1 over every value, model reading replayed from recordings. Details are in [docs/stage-3.md](docs/stage-3.md).

### AI engine (carried over)

| Piece | State | Tested by |
|---|---|---|
| `tools.py` | Built | pytest |
| `checks.py` (number check) | Built | pytest |
| `schemas.py` | Built | Through the `checks.py` tests |
| `run_tool` | Built | pytest: a wrong input type and a failing search backend both return a message |
| `run_agent` | Built | Real model on Colab (notebook 02, 3 Nov 2026) |
| `retrieval.py`, `search_notes` | Built | Real model on Colab (notebook 02, 3 Nov 2026) |
| Move to `ai_engine/` (Stage 0) | Done | pytest (all 37 engine tests pass); notebooks not re-run on Colab since the move |
| `providers.py` (Stage 3): modes rules, recorded, ollama, ollama-local | Built | pytest, with a local stand-in for the Ollama server and fake recordings; no real model call yet |

## AI engine

The engine is the `estimation_assistant` package in `ai_engine/`. It is a tool-using agent: the model asks for tools, code runs them, and a round limit stops the run. Code does the arithmetic, not the model; a number check lists answer numbers that appear nowhere in the question or the tool log. Models: `gemma4:e2b` for chat, `mxbai-embed-large` for embeddings, served by Ollama on Colab. Ollama is not needed on the laptop.

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

### Run on Colab

Colab forgets everything when a session ends, so repeat these steps each session.

1. Open a notebook from `notebooks/` and select a GPU runtime (T4).
2. Run the setup cells: GPU check, Ollama install, server start, Python client, model downloads.
3. Run the cell that creates `ai_engine/estimation_assistant/` and adds `ai_engine` to `sys.path`.
4. Run the `%%writefile` cells: schemas, tools, retrieval, checks, agent. The `%%writefile` line must be the first line of its cell.
5. Check the files with `!ls -l ai_engine/estimation_assistant`. A file of 1 byte means the cell was empty.

Download models with `ollama.pull(...).status`, not `!ollama pull`, which saves thousands of spinner characters into the notebook. When you change an engine file, update its `%%writefile` cell too.

## Synthetic data

Rebuild the data sets from their fixed seeds (PowerShell, from the repo folder):

```powershell
.venv\Scripts\python.exe -m data_generator build --set showcase   # committed, data/projects/showcase
.venv\Scripts\python.exe -m data_generator build --set test       # 20 enquiries, data/projects/test (git-ignored)
.venv\Scripts\python.exe -m data_generator build --set training   # 300 drawings, data/training (git-ignored)
```

Each enquiry has a specification PDF, a requirements letter (DOCX), a two-sheet schematic (DXF rendered to a vector PDF, plus a scanned and a phone-photo version of each sheet) and an `answers.json` answer key. The planted problems of the test set are listed in [data/projects/test/PLANTED.md](data/projects/test/PLANTED.md). Real drawings go in the git-ignored `data/external/`, with the same answer-key format: see [docs/real-drawings.md](docs/real-drawings.md).

## Licences

Only permissive licences are used. AGPL libraries (for example PyMuPDF and Ultralytics YOLO) are excluded, and so are fpdf2 (LGPL), pdf2image and Poppler (GPL). Versions are those tested (Stage 0 for the web stack, Stage 1 for the data generator, Stage 2 for reading and export).

| Component | Version | Licence | Used for |
|---|---|---|---|
| FastAPI | 0.162.0 | MIT | Web framework |
| Starlette | 1.10.0 | BSD-3-Clause | ASGI toolkit under FastAPI |
| Uvicorn | 0.54.0 | BSD-3-Clause | ASGI server |
| Jinja2 | 3.1.6 | BSD-3-Clause | Templates |
| Pydantic, pydantic-settings | 2.14.1, 2.16.2 | MIT | Data models, settings |
| SQLAlchemy | 2.1.8 | MIT | Database access |
| Alembic | 1.20.1 | MIT | Migrations |
| pg8000 | 1.31.6 | BSD-3-Clause | PostgreSQL driver (chosen over psycopg, which is LGPL) |
| ollama (Python client) | 0.6.3 | MIT | Model calls in live mode |
| pytest | 9.2.0 | MIT | Tests (development only) |
| httpx2, httpcore2 | 2.16.0 | BSD-3-Clause | Test client (development only); replaces httpx for Starlette's TestClient |
| ezdxf | 1.4.5 | MIT | App: reads the text entities of uploaded DXF drawings. Generator: writes the schematic DXF and renders it through its matplotlib backend (the PyMuPDF backend is not used) |
| matplotlib | 3.11.2 | Matplotlib licence (PSF-based, BSD-style) | Vector PDF of the schematic |
| reportlab | 5.1.0 | BSD-3-Clause | Specification PDF |
| python-docx | 1.2.0 | MIT | App: reads letters, exports the DOCX report. Generator: requirements letter |
| pdfplumber, pdfminer.six | 0.11.10, 20260107 | MIT | App: PDF text and tables per page |
| htmx | 2.0.4 | Zero-Clause BSD | Partial page updates, vendored (`frontend/static/js/htmx.LICENSE.txt`) |
| python-multipart | 0.0.33 | Apache-2.0 | App: file uploads |
| pypdfium2 (PDFium) | 5.14.0 | Apache-2.0 or BSD-3-Clause (PDFium: BSD-3-Clause) | PDF to image (generator; app: drawing PDF pages for OCR), PDF text in tests |
| Pillow | 13.0.0 | MIT-CMU | Scan and photo effects; app: drawing images for OCR |
| pytesseract | 0.3.13 | Apache-2.0 | App: calls Tesseract for drawing OCR (Stage 4). Declares Python up to 3.12 only; tested working on 3.14.4 |
| Tesseract OCR (with the `eng` data) | 5.4.0 on the laptop (UB Mannheim build); Debian's `tesseract-ocr` package in Docker and CI | Apache-2.0 | App: drawing OCR, a separate program, not a Python package |
| numpy | 2.5.4 | BSD-3-Clause | Scan and photo effects, homographies; app: the symbol detector (Stage 4 Part C) |
| PostgreSQL | 16 | PostgreSQL Licence | Database (Docker image) |
| pgvector | 0.8.7 | PostgreSQL Licence | Vector search extension |
| IBM Plex Sans, IBM Plex Mono | 1.1.0 | SIL OFL 1.1 | Fonts, self-hosted (`frontend/static/fonts/OFL.txt`) |
| IBM Plex Sans Condensed, IBM Plex Serif, IBM Plex Mono (TTF) | from the Google Fonts repository | SIL OFL 1.1 | Drawing and specification text in generated documents (`data_generator/fonts/OFL-IBMPlex.txt`) |
| Caveat | variable font, Google Fonts repository | SIL OFL 1.1 | Handwritten-style note on scanned and photo drawings (`data_generator/fonts/OFL-Caveat.txt`) |
| Icons | n/a | This repo | Drawn for this project |
| Gemma 4 E2B (`gemma4:e2b`) | n/a | Apache-2.0 ([model card](https://huggingface.co/google/gemma-4-E2B-it)) | Chat and vision model, on Colab only |
| mxbai-embed-large | v1 | Apache-2.0 ([model card](https://huggingface.co/mixedbread-ai/mxbai-embed-large-v1)) | Embedding model, on Colab only |

Transitive dependencies (for example AnyIO, Click, MarkupSafe, Mako, scramp, typing-extensions, fontTools, lxml, contourpy, kiwisolver, cycler, pyparsing, python-dateutil, truststore, charset-normalizer, cryptography, cffi, pycparser) are MIT, BSD, Apache-2.0, Apache-2.0 OR BSD-3-Clause (cryptography), MIT-0 or PSF-2.0. Drawings for `data/external/` may be made in QElectroTech or LibreCAD (both GPL-2.0); those tools are not dependencies and none of their code is in the repo. Model licences are from the Hugging Face model cards (checked 5 Nov 2026).

## Limits

- **Rules written for the generator.** The rules were written after reading the generator's templates, so their score on the generator's own wording measures template coverage, not how well they read new wording. The reworded set tests that.
- **Model runs are recorded.** A recorded model mode replays saved model outputs on the laptop; live model calls run on Colab only. The relaxed quote check is the app default; the strict check is kept as the fixed baseline above.
- **Not built yet.** The Ask column on the Summary is an empty placeholder, there is no stock list and no PDF report (Word only), and there is no login. Drawing PDFs and images are read by OCR since Stage 4 Part A; OCR values are medium confidence at most and always need the engineer's review, and reworded rating styles are not read yet. See [docs/stage-2.md](docs/stage-2.md#known-limits) and [docs/stage-4.md](docs/stage-4.md#6-known-limits).
- **Synthetic data is cleaner than real data.** See [docs/stage-1.md](docs/stage-1.md#limits) for how it differs.
- **Engine, small tests.** Real-model results come from a few questions on four notes. They show the parts work, not how often.
- **Engine, refusal gap.** The search always returns the nearest note, even when no note fits.
- **Engine, number check.** It reads digits only ("three" is not checked), ignores signs and misreads `.5`, `3rd` and `2,85`. It shows a number exists in the evidence, not that it is used correctly.
- **Notebook copies.** `%%writefile` cells are copies of the engine files and can drift from them.
- **Old paths in saved outputs.** Saved outputs in notebooks 01 and 02 predate the move to `ai_engine/` and stay that way until the notebooks are re-run. In notebook 02, the outputs of cells 30 to 40 still show the old `src/` paths. Notebook 01's saved outputs show no paths.
