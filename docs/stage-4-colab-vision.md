# Stage 4 Part B on Colab: vision recordings

The laptop has no GPU and no Ollama, so the vision model (`gemma4:e2b`) runs on a Colab T4. Colab
writes recordings, and the laptop replays them (`VISION_MODE=recorded`). Nothing here has been run yet:
every vision score reads NOT RUN YET until these cells have been run.

The recordings are matched by the SHA-256 of each drawing file's bytes. PNG and PDF bytes differ
between Windows and Linux builds, so Colab must use the **laptop-built** files from a zip and never
rebuild the sets.

## On the laptop, before Colab

```powershell
# Build the sets if they are not built yet, then zip the drawings of the two test sets and the showcase
.venv\Scripts\python.exe -m data_generator build --set test
.venv\Scripts\python.exe -m data_generator build --set reworded
Compress-Archive -Force -Path data\projects\test, data\projects\reworded, data\projects\showcase `
    -DestinationPath $env:USERPROFILE\Downloads\vision-sets.zip
```

## Notebook cells (new notebook, GPU runtime T4; each cell starts with its number)

1. `# Cell 1: GPU check`: `!nvidia-smi`
2. `# Cell 2: install Ollama`: `!curl -fsSL https://ollama.com/install.sh | sh`
3. `# Cell 3: start the server`: `import subprocess, time; server = subprocess.Popen(["ollama", "serve"]); time.sleep(5)`
4. `# Cell 4: model`: `import ollama; ollama.pull("gemma4:e2b").status`
5. `# Cell 5: the repo`: `!git clone https://github.com/Prhm93/switchgear-estimation-assistant.git` and then
   `%cd switchgear-estimation-assistant`. Use `!git checkout stage-4bcd` if the branch is not merged yet.
6. `# Cell 6: libraries`: `!pip install -q -r requirements.txt` (Colab's Python is 3.12, as in Docker).
7. `# Cell 7: the laptop-built sets`: upload `vision-sets.zip` (`from google.colab import files; files.upload()`),
   then `!unzip -o -q vision-sets.zip -d data/projects`.
8. `# Cell 8: one sheet first`: `!python -m backend.record_vision --set showcase --version scanned`. It should print
   `2 recorded, 0 already there, 0 failed`.
9. `# Cell 9: all versions of both test sets` (resumes if Colab stops; run it again to finish):

   ```python
   for s in ("test", "reworded"):
       for v in ("clean", "scanned", "photo"):
           !python -m backend.record_vision --set {s} --version {v}
   ```
10. `# Cell 10: download`: `!zip -q -r recorded-vision.zip data/recorded-vision` and then
    `files.download("recorded-vision.zip")`.

## Back on the laptop

```powershell
Expand-Archive -Force $env:USERPROFILE\Downloads\recorded-vision.zip -DestinationPath .   # into data\recorded-vision
.venv\Scripts\python.exe -m backend.drawings vision --set reworded --version photo          # score, per version
$env:VISION_MODE = "recorded"   # the app adds vision values where OCR left fields empty
```

`data/recorded-vision/` is git-ignored: the recordings are never committed.
