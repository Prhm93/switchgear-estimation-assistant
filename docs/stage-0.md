# Stage 0: Setup

Branch: `stage-0-setup`. Date: 5 November 2026.

## What was built

1. **New repo layout.** The existing engine package moved from `src/estimation_assistant/` to `ai_engine/estimation_assistant/` (moved with `git mv`, so history follows it). New folders: `backend/`, `frontend/templates/`, `frontend/static/`, `tests/unit/`, `tests/integration/`, `tests/accuracy/`, `deployment/`. The import name `estimation_assistant` did not change.
2. **FastAPI backend** (`backend/app/`):
   - `config.py`: typed settings from environment variables (`APP_ENV`, `DATABASE_URL`). With no database URL the app still starts.
   - `db.py`: a database health check that never raises. It reports `ok`, `unavailable` or `not_configured`, plus the pgvector version. Errors show only the error class name, never the URL or password.
   - `main.py`: an app factory with two routes. `GET /` is the design system health-check page; `GET /healthz` returns JSON for Docker and monitoring.
   - `design/contrast.py`: a WCAG 2.2 contrast checker that reads the colour tokens directly from `app.css`.
3. **Alembic** (`backend/alembic.ini`, `backend/migrations/`): migration `0001` enables the `vector` extension. The app container applies migrations on start.
4. **Docker stack** (`deployment/docker-compose.yml`, included by the root `compose.yaml`): `pgvector/pgvector:pg16` and the app image (`python:3.12-slim`, non-root user, one uvicorn worker, a health check). Both services have memory limits, Postgres uses small-memory settings, and both ports bind to `127.0.0.1` only.
5. **Design system**: one stylesheet (`frontend/static/css/app.css`) with all tokens in `:root`, IBM Plex Sans and Mono self-hosted as woff2 with the OFL licence file, a line SVG icon sprite drawn for this project, and a small accessible tabs script.
6. **Health-check page**: service status, a type specimen, buttons (primary, secondary, ghost, disabled), circular icon buttons, a segmented toggle, tabs, document cards, the four review badges, the four confidence levels, an extracted value with its source and method, a conflict shown with both sources, the six icons, and colour swatches.
7. **CI**: `.github/workflows/tests.yml` runs pytest on Python 3.12 on every push and pull request. `DATABASE_URL` is not set in CI, so the two database tests skip.

## Why

- The import name stayed `estimation_assistant`, so the 37 engine tests and the Colab notebooks only needed path changes, not code changes.
- **pg8000 instead of psycopg.** psycopg is LGPL-3.0, and the licence rule allows permissive licences only. pg8000 is BSD-3-Clause, and SQLAlchemy supports it.
- **Contrast is a test, not a one-off check.** The checker parses `app.css`, so a token change that breaks contrast fails the test suite.
- **Native radio inputs for the toggle** give keyboard support without any script. Tabs follow the WAI-ARIA tabs pattern (arrow keys, Home, End).
- **Python 3.12 in Docker and CI**, because every planned library (including PyTorch, torchvision and OpenCV in later stages) ships wheels for it. The laptop venv runs Python 3.14.4, and every Stage 0 dependency installed and passed there too (see Results).

## Changes to the brief's palette

Four pairs built from the original values fail WCAG AA. I kept the brief's tokens and added separate tokens for these uses:

| Problem with the original value | Ratio | Fix |
|---|---|---|
| Off-white label on `--accent` #E3262E (primary button) | 4.05 (needs 4.5) | Button fill uses `--accent-fill` #C81F27 (5.04). `--accent` stays #E3262E for underlines, focus rings and outlines |
| `--accent` #E3262E as text on `--surface` | 3.61 (needs 4.5) | Red text uses `--accent-text` #FF7075 (6.16) |
| `--steel` #2F6FB5 as link text on `--bg` | 3.57 (needs 4.5) | Links use `--steel-text` #7EB0EA (8.16). `--steel` stays for the Low confidence outline (3.20, needs 3.0) |
| My first control-outline colour #656C76 on `--surface-2` | 2.72 (needs 3.0) | `--border-strong` #737A84 (3.32). This one was caught by the test |

`--border` #33383F is kept for decorative 1px separators only. Controls use `--border-strong`.

## How to run it

PowerShell, from the repo folder:

```powershell
# Full stack
docker compose up --build
# then open http://127.0.0.1:8000/  and  http://127.0.0.1:8000/healthz

# Tests (no database needed)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m pytest

# Tests including the database tests (stack running)
$env:DATABASE_URL = "postgresql+pg8000://sea:sea-local-only@127.0.0.1:5432/sea"
python -m pytest
Remove-Item Env:DATABASE_URL

# Contrast table
python -m backend.app.design.contrast
```

## How it was tested

| Suite | Tests | What it checks |
|---|---|---|
| `tests/unit/test_tools.py`, `test_checks.py`, `test_agent.py` | 37 | The engine tests, unchanged apart from moving to `tests/unit/` |
| `tests/unit/test_settings.py` | 3 | Defaults, environment overrides, empty `DATABASE_URL` |
| `tests/unit/test_db.py` | 3 | Not-configured state, pg8000 driver (licence rule), no password in error details |
| `tests/unit/test_contrast.py` | 30 | Luminance maths, token parsing, and the 25 colour pairs used by the components |
| `tests/unit/test_icons.py` | 2 | All six required icons exist; no gradients, filters or images |
| `tests/integration/test_health_page.py` | 6 | `/healthz` with no database and with an unreachable one, every component on the page, banned wording, fonts, CSS and icons served |
| `tests/integration/test_database.py` | 2 | pgvector installed and `/healthz` reports `ok` against a real database (skipped without `DATABASE_URL`) |

I also checked the page visually with a headless Edge screenshot at 1280 px wide (`docs/images/stage-0-health-check.png`). That screenshot exposed three layout defects (wrapped card metadata, a full-width toggle, a stretched badge), which were fixed before the final capture.

## Results (all run on 5 November 2026)

| Run | Result |
|---|---|
| `python -m pytest`, laptop, Python 3.14.4, no database | 81 passed, 2 skipped |
| `python -m pytest`, laptop, Python 3.14.4, `DATABASE_URL` set to the Docker database | 83 passed |
| `python -m pytest` in a clean `python:3.12-slim` container, no database | 81 passed, 2 skipped |
| `docker compose up --build` | Both containers healthy; migration `0001` applied (`alembic_version` = `0001`) |
| `GET /healthz` on the stack | `{"app":"ok", ..., "database":{"state":"ok","pgvector":"0.8.7"}}` |
| `GET /` on the stack | 200, 16.4 KB HTML, 36 ms |
| Contrast check | 25 of 25 pairs pass (table below) |

The CI workflow has not run on GitHub yet; it runs on the first push of this branch.

### Memory (`docker stats --no-stream`)

| Container | Idle | After 300 page loads | Limit |
|---|---|---|---|
| app | 54.8 MiB | 55.2 MiB | 384 MiB |
| db | 35.4 MiB | 32.2 MiB | 256 MiB |
| **Total** | **90.2 MiB** | **87.4 MiB** | 640 MiB |

Other measurements:

- `vmmemWSL`, the WSL virtual machine that runs Docker, including its kernel, the Docker engine and its file cache: 703 MB working set after the image builds.
- Without a `.wslconfig` cap, Docker reported 4.0 GB available to the VM. The laptop has 7.8 GB of RAM.
- Image sizes: app 257 MB, `pgvector/pgvector:pg16` 621 MB.

**Fit on an 8 GB laptop:** the stack's containers use about 90 MiB. The whole Docker VM used about 0.7 GB, and a 3 GB cap leaves room for later stages and builds. With Windows, a browser and an editor open, total memory in use at the time of measurement was 6.7 of 7.8 GB, so the stack fits. The cap below stops the VM from growing past 3 GB during builds.

### Contrast table (`python -m backend.app.design.contrast`)

| Foreground | Background | Ratio | Minimum | Result | Used for |
|---|---|---|---|---|---|
| `--text` #F2F1EC | `--bg` #121417 | 16.31 | 4.5 | pass | body text |
| `--text` #F2F1EC | `--surface` #1C1F24 | 14.61 | 4.5 | pass | text in panels and cards |
| `--text` #F2F1EC | `--surface-2` #262A31 | 12.74 | 4.5 | pass | text in raised controls |
| `--text-muted` #A3A8B0 | `--bg` #121417 | 7.72 | 4.5 | pass | secondary text |
| `--text-muted` #A3A8B0 | `--surface` #1C1F24 | 6.91 | 4.5 | pass | secondary text in cards |
| `--text-muted` #A3A8B0 | `--surface-2` #262A31 | 6.03 | 4.5 | pass | secondary text in raised controls |
| `--on-accent` #F2F1EC | `--accent-fill` #C81F27 | 5.04 | 4.5 | pass | primary button label |
| `--on-accent` #F2F1EC | `--accent-fill-hover` #B01B22 | 6.14 | 4.5 | pass | primary button label, hover |
| `--steel-text` #7EB0EA | `--bg` #121417 | 8.16 | 4.5 | pass | links |
| `--steel-text` #7EB0EA | `--surface` #1C1F24 | 7.31 | 4.5 | pass | links and Low badge in cards |
| `--success-text` #5CC487 | `--surface` #1C1F24 | 7.63 | 4.5 | pass | Approved and High badge |
| `--warning-text` #F0B84A | `--surface` #1C1F24 | 9.18 | 4.5 | pass | Needs review and Medium badge |
| `--accent-text` #FF7075 | `--surface` #1C1F24 | 6.16 | 4.5 | pass | Conflict badge |
| `--steel-text` #7EB0EA | `--surface-2` #262A31 | 6.37 | 4.5 | pass | Extracted badge in a card |
| `--success-text` #5CC487 | `--surface-2` #262A31 | 6.65 | 4.5 | pass | Approved badge in a card |
| `--warning-text` #F0B84A | `--surface-2` #262A31 | 8.00 | 4.5 | pass | Needs review badge in a card |
| `--accent-text` #FF7075 | `--surface-2` #262A31 | 5.37 | 4.5 | pass | Conflict badge in a card |
| `--accent` #E3262E | `--bg` #121417 | 4.03 | 3.0 | pass | active tab underline, focus ring |
| `--accent` #E3262E | `--surface` #1C1F24 | 3.61 | 3.0 | pass | active state in cards |
| `--steel` #2F6FB5 | `--surface` #1C1F24 | 3.20 | 3.0 | pass | Low confidence outline |
| `--success` #3FA46A | `--surface` #1C1F24 | 5.30 | 3.0 | pass | status dot |
| `--warning` #E0A126 | `--surface` #1C1F24 | 7.31 | 3.0 | pass | status dot |
| `--border-strong` #737A84 | `--bg` #121417 | 4.26 | 3.0 | pass | input and toggle outlines |
| `--border-strong` #737A84 | `--surface` #1C1F24 | 3.81 | 3.0 | pass | input and toggle outlines in panels |
| `--border-strong` #737A84 | `--surface-2` #262A31 | 3.32 | 3.0 | pass | circular action buttons in a card |

## Path changes from the package move

| File | Change |
|---|---|
| `pyproject.toml` | `pythonpath = ["src"]` became `["ai_engine", "."]` (`.` makes `backend` importable). Test markers and project metadata were added |
| `notebooks/01-colab-run-agent.ipynb`, cell 9 | `!mkdir -p src/estimation_assistant` and `!touch src/estimation_assistant/__init__.py` now use `ai_engine/estimation_assistant`; `sys.path.insert(0, "src")` became `sys.path.insert(0, "ai_engine")` |
| `notebooks/01-colab-run-agent.ipynb`, cells 11, 13, 15, 17, 19 | `%%writefile src/estimation_assistant/{schemas,tools,retrieval,checks,agent}.py` now writes to `ai_engine/estimation_assistant/...` |
| `notebooks/02-colab-rag.ipynb`, cell 28 | The same `mkdir`, `touch` and `sys.path` changes as notebook 01, cell 9 |
| `notebooks/02-colab-rag.ipynb`, cells 30, 32, 34, 36, 38 | `%%writefile` targets moved to `ai_engine/estimation_assistant/...` |
| `notebooks/02-colab-rag.ipynb`, cell 40 | `!ls -l` and `!grep` paths moved to `ai_engine/estimation_assistant/...` |
| `notebooks/02-colab-rag.ipynb`, cell 45 | `!ls -l src/estimation_assistant` became `!ls -l ai_engine/estimation_assistant` |
| `notebooks/03-colab-vision.ipynb` | No change needed: it does not write or import the package |
| `docs/01-tool-layer-and-safe-execution.ipynb` (cells 0, 5), `docs/02-agent-loop.ipynb` (cells 0, 6), `docs/03-retrieval.ipynb` (cell 1), `tutorials/02-tools-and-agent-loop.ipynb` (cell 64) | Path mentions in the text updated |
| `data/README.md`, `README.md` | Path mentions updated |
| `tests/test_*.py` | Moved to `tests/unit/`, contents unchanged |

Only cell sources were edited. Saved cell outputs were left as they were, because they record past runs; notebook 02's saved outputs still show `src/...` paths. The notebooks have not been re-run on Colab since the move.

## Cap Docker and WSL memory

Docker Desktop runs inside a WSL 2 virtual machine. Without a cap, WSL may use up to half the RAM (Docker reported 4.0 GB on this laptop) and holds on to file cache. For an 8 GB laptop, 3 GB is a safe cap: the stack needs about 0.1 GB inside the VM, the VM itself about 0.7 GB, and that leaves headroom for image builds.

1. Stop Docker Desktop: right-click the whale icon, then **Quit Docker Desktop**.
2. Create or edit `C:\Users\<you>\.wslconfig`:

   ```powershell
   notepad "$env:USERPROFILE\.wslconfig"
   ```

   Content:

   ```ini
   [wsl2]
   memory=3GB
   processors=4
   swap=2GB

   [experimental]
   autoMemoryReclaim=gradual
   ```

   `autoMemoryReclaim` returns cached memory to Windows when the VM is idle. If WSL warns that the key is unknown in `[experimental]`, move it under `[wsl2]`.
3. Apply it:

   ```powershell
   wsl --shutdown
   ```

4. Start Docker Desktop again and check the limit:

   ```powershell
   docker info --format "{{.MemTotal}}"
   ```

   Expect about 3.1 GB (3,100,000,000 bytes, give or take).

Later stages that build PyTorch images may need the cap raised to 4 GB while building.

## Renaming the GitHub repo and the local folder

The GitHub remote is still `Prhm93/agentic-rag-assistant`. To rename (I have not done this):

1. On GitHub: open the repo, then **Settings**, **General**, **Repository name**, enter `switchgear-estimation-assistant`, and click **Rename**. GitHub redirects the old URL.
2. Point the local clone at the new URL:

   ```powershell
   git remote set-url origin https://github.com/Prhm93/switchgear-estimation-assistant.git
   git remote -v
   ```

3. Rename the local folder. First close every editor, terminal and notebook using it, then:

   ```powershell
   docker compose down          # from the repo folder; the volume keeps its name
   cd D:\parham\Parham_Learning
   Rename-Item agentic-ai switchgear-estimation-assistant
   cd switchgear-estimation-assistant
   ```

4. Recreate the virtual environment, because a venv stores absolute paths and breaks when its folder moves:

   ```powershell
   Remove-Item -Recurse -Force .venv
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt
   python -m pytest
   ```

5. Run `docker compose up -d`. The compose project name is fixed (`switchgear-estimation-assistant`), so the database volume is reused.

## Known limits

- **No product features.** No upload, extraction, catalogue or estimate yet. The values on the health-check page are labelled placeholders.
- **HTMX not added yet.** Stage 0 needs no server round-trips. HTMX will be vendored with the first interactive screen in Stage 2.
- **Storage interface not built.** It arrives with uploads in Stage 2.
- **Test client warning.** Starlette 1.10 emits a deprecation warning recommending `httpx2` over `httpx` for the test client. It is harmless; switching is deferred until that package has been reviewed.
- **pg8000 socket timeout** is 10 s (`backend/app/db.py`). It bounds the health check, but it also applies to every query, so it may need raising when long queries arrive.
- **Notebooks not re-run** on Colab since the move to `ai_engine/` (see above).
- **CI not yet observed on GitHub**; it runs on the first push.
- **Accessibility** was checked for contrast (automated) and keyboard use (by design: native controls, ARIA tabs, visible focus, skip link). No screen reader test has been done.
- **Default database password** (`sea-local-only`) is for local development only. Ports bind to 127.0.0.1. Production configuration is Stage 8.
