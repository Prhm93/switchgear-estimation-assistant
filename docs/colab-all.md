# Everything that needs a GPU, in one Colab session (T4)

Three jobs, one session: the language model reads the fresh set (Stage 7), the vision model reads drawing pictures
(Stage 4 Part B, starting with one drawing as a smoke test), and the question box runs with real embeddings
(Stage 9). None of this has been run yet: every result that needs it reads "waiting for Colab recordings".

Recordings only replay for the exact bytes the laptop built (the SHA-256 is checked), so Colab never rebuilds a set:
it gets the laptop's files in zips.

## On the laptop, before Colab (PowerShell)

```powershell
# 1. The code, from the last commit (no data, no recordings)
git archive --format zip -o $env:USERPROFILE\Downloads\repo.zip HEAD
# 2. The read files of the fresh set (specification, letter, DXF) with their SHA-256, for the language model
.venv\Scripts\python.exe -m backend.record pack --sets fresh --out $env:USERPROFILE\Downloads\laptop-files.zip
# 3. The drawings of the fresh set and the showcase, for the vision model and the question box
Compress-Archive -Force -Path data\projects\fresh, data\projects\showcase `
    -DestinationPath $env:USERPROFILE\Downloads\sets.zip
```

The fresh set is frozen: `python -m data_generator build --set fresh` checks every file against
`data/projects/fresh/FROZEN.sha256` and stops if anything differs.

## Notebook cells (new notebook, runtime type T4 GPU; each cell starts with its number)

```text
# Cell 1: Confirm Colab gave us a GPU
!nvidia-smi --query-gpu=name,memory.total --format=csv

# Cell 2: Install what the Ollama installer needs, then Ollama, and start the server
!apt-get install -y -q zstd pciutils lshw tesseract-ocr
!curl -fsSL https://ollama.com/install.sh | sh
!nohup ollama serve > ollama.log 2>&1 &
!sleep 8 && ollama --version

# Cell 3: Download the two models (their digests are saved in every recording)
!ollama pull gemma4:e2b
!ollama pull mxbai-embed-large
!ollama list

# Cell 4: Upload repo.zip, laptop-files.zip and sets.zip; unpack the code and install the app requirements
%cd /content
from google.colab import files
uploaded = files.upload()
assert {"repo.zip", "laptop-files.zip", "sets.zip"} <= set(uploaded), "upload all three zips"
!mkdir -p /content/sea && unzip -q -o repo.zip -d /content/sea
%cd /content/sea
!pip install -q -r requirements.txt
!unzip -q -o /content/sets.zip -d data/projects
import os
os.environ["PYTHONPATH"] = "ai_engine:."

# Cell 5: Keep the outputs in Google Drive (they survive a stopped session)
from google.colab import drive
drive.mount("/content/drive")
OUT = "/content/drive/MyDrive/switchgear-colab-all"
!mkdir -p {OUT}/recorded {OUT}/recorded-vision {OUT}/recorded-ask

# Cell 6: Language model on the fresh set (every file checked against its SHA-256; --resume skips finished files)
!python -m backend.record run --zip /content/laptop-files.zip --sets fresh --mode ollama --out {OUT}/recorded --resume

# Cell 7: Vision model, smoke test on ONE drawing first: the showcase, scanned version
!python -m backend.record_vision --set showcase --version scanned --out {OUT}/recorded-vision
!ls -R {OUT}/recorded-vision | head -20

# Cell 8: Vision model on the fresh set, one version at a time (only after Cell 7 printed a sensible reading)
for v in ["clean", "scanned", "photo"]:
    !python -m backend.record_vision --set fresh --version {v} --out {OUT}/recorded-vision

# Cell 9: Question box with real embeddings (mxbai-embed-large), the same questions as on the laptop
!python -m backend.ask_eval --set showcase --embedder ollama --out {OUT}/recorded-ask/showcase-mxbai.json
!python -m backend.ask_eval --set fresh --embedder ollama --out {OUT}/recorded-ask/fresh-mxbai.json
!python -m backend.ask_eval --set fresh --embedder words --out {OUT}/recorded-ask/fresh-words.json

# Cell 10: Download everything in one zip
!cd {OUT} && zip -q -r /content/colab-all.zip .
files.download("/content/colab-all.zip")
```

If the session stops, run the cells again from the top: Cells 6 and 8 skip what is already recorded in Drive.

## Back on the laptop (PowerShell)

```powershell
Expand-Archive -Force $env:USERPROFILE\Downloads\colab-all.zip -DestinationPath $env:TEMP\colab-all
Copy-Item -Recurse -Force $env:TEMP\colab-all\recorded\fresh data\recorded\                 # language model
Copy-Item -Recurse -Force $env:TEMP\colab-all\recorded-vision\* data\recorded-vision\        # vision model
Copy-Item -Recurse -Force $env:TEMP\colab-all\recorded-ask data\                             # question box
.venv\Scripts\python.exe -m backend.evaluation_report --set fresh                         # adds the model rows (saved rows reused)
.venv\Scripts\python.exe -m backend.evaluation_report --write-only                         # docs/evaluation.md, fresh and test
.venv\Scripts\python.exe -m backend.drawings vision --set fresh --version photo               # vision scores
```

The `data/recorded*` folders are git-ignored: recordings are never committed. The new rows of `docs/evaluation.md`
replace "waiting for Colab recordings" only where a recording now matches the file's bytes.

## What each job answers

| Job | Question it answers | Where the result goes |
|---|---|---|
| Cell 6 | Does the model, untuned, keep its scores on a set nobody looked at? | `docs/evaluation.md`, rules + model rows |
| Cells 7 and 8 | Does the vision model read ratings on scanned and photo drawings better than OCR? | `docs/stage-4.md` and `docs/evaluation.md` |
| Cell 9 | Does mxbai-embed-large find the right passage more often than the word embedder (fresh: 0.593 at 1, 0.767 in 3)? Is its 0.5 threshold right? | `docs/stage-9.md` |

To use real embeddings in the app on a machine that runs Ollama: `$env:EMBEDDER = "ollama"`; passages are made again
for the new embedder on the next question (the word passages stay and are not mixed with them).
