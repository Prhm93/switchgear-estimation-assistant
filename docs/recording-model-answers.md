# Recording model answers

The app runs without a GPU. The models (`gemma4:e2b` for text and drawings, `mxbai-embed-large` for the
question box) run once on a GPU machine with Ollama; their answers are saved as JSON recordings and replayed
offline in **recorded** mode.

## Rules

- A recording replays only for a file with exactly the same SHA-256, and only for the same prompt; anything else
  is refused and the app reads with the rules.
- PNG, PDF and DOCX bytes differ between Windows and Linux builds, so the GPU machine never rebuilds a set: it
  gets the files the app machine built, in zips.
- The fresh set is frozen: `python -m data_generator build --set fresh` checks every file against
  `data/projects/fresh/FROZEN.sha256` and stops if anything differs.
- Recordings are never committed. They live in git-ignored folders.

| Recording | Folder | Made by |
|---|---|---|
| Language model, specification, letter and DXF | `data/recorded/<set>/` | `backend.record` |
| Drawing reading (vision model) | `data/recorded-vision/<set>/` | `backend.record_vision` |
| Question box scores with real embeddings | `data/recorded-ask/` | `backend.ask_eval` |

## 1. Pack the files (app machine)

```powershell
git archive --format zip -o repo.zip HEAD
python -m backend.record pack --sets fresh --out laptop-files.zip      # read files with their SHA-256
Compress-Archive -Force -Path data\projects\fresh, data\projects\showcase -DestinationPath sets.zip
```

For the test and reworded sets, build them first (`python -m data_generator build --set test`, `--set reworded`)
and add them to the same commands.

## 2. Set up the GPU machine

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull gemma4:e2b
ollama pull mxbai-embed-large
unzip -q repo.zip -d sea && cd sea
pip install -q -r requirements.txt
pip install -q reportlab ezdxf python-docx pypdfium2 pdfplumber   # the data generator, used by the evaluation
unzip -q ../sets.zip -d data/projects
export PYTHONPATH=ai_engine:.
```

The model digests are saved in every recording.

## 3. Record, in this order

```bash
# Language model (--resume skips files already recorded)
python -m backend.record run --zip ../laptop-files.zip --sets fresh --mode ollama --out data/recorded --resume

# Drawing reading: one drawing first, then each version of the set
python -m backend.record_vision --set showcase --version scanned --out data/recorded-vision
for v in clean scanned photo; do
  python -m backend.record_vision --set fresh --version $v --out data/recorded-vision
done

# Question box: real embeddings, and the word embedder for comparison
python -m backend.ask_eval --set showcase --embedder ollama --out data/recorded-ask/showcase-mxbai.json
python -m backend.ask_eval --set fresh --embedder ollama --out data/recorded-ask/fresh-mxbai.json
python -m backend.ask_eval --set fresh --embedder words --out data/recorded-ask/fresh-words.json
```

The recorder skips every sheet that already has a recording, so a stopped run is started again with the same
command. To re-record some projects only, add `--projects F02,F12,F15,F19,F20`. A drawing reply cut off part-way
keeps its complete ways and is recorded as "cut off, N ways kept".

## 4. Replay and score (app machine)

Copy the folders back into `data/recorded/`, `data/recorded-vision/` and `data/recorded-ask/`, then:

```powershell
python -m backend.evaluation_report --set fresh                          # adds the model rows; saved rows reused
python -m backend.evaluation_report --set fresh --redo vision_ visiononly_  # score new drawing recordings again
python -m backend.evaluation_report --write-only                         # writes docs/evaluation.md
python -m backend.drawings vision --set fresh --version photo            # vision scores per version
$env:VISION_MODE = "recorded"                                            # the app adds vision values
```

A sheet without a recording is reported as "not read", never as an error. To use real embeddings in the app on a
machine that runs Ollama, set `EMBEDDER=ollama`.

`notebooks/04-colab-llm-extraction.ipynb` holds the Stage 3 language-model run as notebook cells.
