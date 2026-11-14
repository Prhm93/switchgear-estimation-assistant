# Vision retry: re-record only the 10 cut-off sheets (Colab, T4)

On the first run (13 Nov 2026, `docs/colab-all.md`), 10 of the 120 fresh-set sheets have no vision recording: the
model's reply stopped part-way through the JSON. All are sheet 1 (the sheet with the ways):

| Project | Versions |
|---|---|
| F02 | scanned |
| F12 | clean, scanned, photo |
| F15 | clean, scanned, photo |
| F19 | clean, scanned |
| F20 | clean |

The vision reader now gives the model more output room (`VISION_OPTIONS`: `num_ctx` 8192, `num_predict` 4096) and keeps
the complete ways of a reply that is still cut off (the recording says "cut off, N ways kept"). The prompt is
unchanged (`vision-v1`), so the 110 recordings already made stay valid; only the 10 missing sheets are sent.

## On the laptop (PowerShell)

```powershell
# 1. The code with the new reader (from the last commit; no data, no recordings)
git archive --format zip -o $env:USERPROFILE\Downloads\repo.zip HEAD
# 2. The fresh set as the laptop built it (recordings only replay for these exact bytes)
Compress-Archive -Force -Path data\projects\fresh -DestinationPath $env:USERPROFILE\Downloads\fresh.zip
# 3. The 110 recordings already made, so the recorder skips those sheets
Compress-Archive -Force -Path data\recorded-vision\fresh -DestinationPath $env:USERPROFILE\Downloads\have.zip
```

## Notebook cells (new notebook, runtime type T4 GPU)

```text
# Cell 1: Confirm Colab gave us a GPU
!nvidia-smi --query-gpu=name,memory.total --format=csv

# Cell 2: Ollama and the vision model
!apt-get install -y -q zstd pciutils lshw
!curl -fsSL https://ollama.com/install.sh | sh
!nohup ollama serve > ollama.log 2>&1 &
!sleep 8 && ollama pull gemma4:e2b && ollama list

# Cell 3: Upload repo.zip, fresh.zip and have.zip; unpack and install
%cd /content
from google.colab import files as colab_files
uploaded = colab_files.upload()
assert {"repo.zip", "fresh.zip", "have.zip"} <= set(uploaded), "upload all three zips"
!mkdir -p /content/sea && unzip -q -o repo.zip -d /content/sea
%cd /content/sea
!pip install -q -r requirements.txt
!pip install -q reportlab ezdxf python-docx pypdfium2 pdfplumber
!unzip -q -o /content/fresh.zip -d data/projects
!mkdir -p data/recorded-vision && unzip -q -o /content/have.zip -d data/recorded-vision
!find data/recorded-vision/fresh -name '*.json' | wc -l   # expect 110
!touch /content/start-marker

# Cell 4: Re-record only the missing sheets (the recorder skips every sheet that already has a recording)
# If this fails with "connection refused", the Ollama server stopped: run the nohup line of Cell 2 again first.
for v in ["clean", "scanned", "photo"]:
    !python -m backend.record_vision --set fresh --version {v} --projects F02,F12,F15,F19,F20 --out data/recorded-vision
!find data/recorded-vision/fresh -name '*.json' | wc -l   # 120 when every sheet was read
!grep -l '"reply": "cut off' -r data/recorded-vision/fresh || echo "no reply was cut off"

# Cell 5: Download only the new recordings
!cd data && find recorded-vision -name '*.json' -newer /content/start-marker | zip -q /content/vision-retry.zip -@
!unzip -l /content/vision-retry.zip
colab_files.download("/content/vision-retry.zip")
```

If the session is recycled while idle, run from Cell 1 again (the new recordings are in `/content`, so download them
before leaving the session idle).

## Back on the laptop (PowerShell)

```powershell
Expand-Archive -Force $env:USERPROFILE\Downloads\vision-retry.zip -DestinationPath data
# forget the saved vision rows only, score them again with the new recordings (every other row is reused)
.venv\Scripts\python.exe -m backend.evaluation_report --set fresh --redo vision_ visiononly_
```

A sheet that is still not read is reported as "not read", never as an error.
