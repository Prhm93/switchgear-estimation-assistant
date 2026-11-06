# Ollama on the laptop (ollama-local mode)

Status: **written, not tried.** Ollama is not installed on the laptop, and the app never needs it: rules
and recorded modes work without it. This guide is for Part B of Stage 3, to find out whether
`gemma4:e2b` is usable on an 8 GB laptop with no GPU. Every number below is **NOT RUN YET**.

## 1. Install with everything on D:

1. Download the Windows installer `OllamaSetup.exe` from the official download page (ollama.com/download).
2. Install the program on D: instead of the default folder under `%LOCALAPPDATA%`:

   ```powershell
   & "$env:USERPROFILE\Downloads\OllamaSetup.exe" /DIR="D:\Ollama"
   ```

3. Keep the models on D: too. Quit Ollama from the tray icon, then set the model folder for your user:

   ```powershell
   New-Item -ItemType Directory -Force D:\Ollama\models | Out-Null
   [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "D:\Ollama\models", "User")
   # One model in memory at a time, one request at a time: the least memory.
   [Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "1", "User")
   [Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "1", "User")
   ```

   Open a new PowerShell window (so it sees the variables) and start Ollama again from the Start menu.

4. Pull the model and check where it went:

   ```powershell
   ollama pull gemma4:e2b
   ollama list
   Get-ChildItem D:\Ollama\models -Recurse | Measure-Object Length -Sum   # size on disk
   ```

   If `D:\Ollama\models` stays empty, Ollama was started before the variable was set: quit it from the
   tray and start it again.

## 2. Free memory first

8 GB is tight. Before a measurement:

- close the browser tabs you do not need;
- if Docker is not needed for the measurement, stop it (`docker compose -f deployment/docker-compose.yml stop`);
  the recording command below needs no database;
- the `.wslconfig` cap from Stage 0 still applies when Docker runs.

## 3. Run ollama-local on one set of files

`ollama-local` is the same client as `ollama` with laptop settings: an 8192-token context
(`num_ctx`), a reply limit of 6144 tokens (`num_predict`), small batches, and the model unloaded two
minutes after its last call.

**Untested:** the context was 4096 tokens until Stage 3b. It was raised to 8192 because the Colab
recordings showed the longest replies (pages with a way table) being cut off mid-JSON. A larger context
needs more memory for the model's key-value cache, and how much more on this laptop is **not measured**.
If the run below runs out of memory, measure with 4096 first and record which replies come back with
`done_reason` "length" (cut off).

Use the laptop's own files (no zip upload needed, but the zip keeps the same hash checks):

```powershell
.venv\Scripts\python.exe -m backend.record pack --out laptop-files.zip --sets showcase
.venv\Scripts\python.exe -m backend.record run --zip laptop-files.zip --mode ollama-local --sets showcase --out data\recorded-laptop
```

The command prints, per file, the values kept, the values rejected and the seconds taken. Keep
`data\recorded-laptop` apart from `data\recorded` (the Colab recordings) so the two runs are not mixed.

To try it in the app instead:

```powershell
$env:MODEL_MODE = "ollama-local"
$env:PYTHONPATH = "ai_engine;."
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000
```

If Ollama is not running, the app says so in the document's note and reads the file with the rules only.

## 4. Measure memory and time

In a second PowerShell window, while step 3 runs, sample the memory of the Ollama processes once a
second and keep the peak:

```powershell
$peak = 0
while ($true) {
    $mb = (Get-Process | Where-Object Name -like "ollama*" | Measure-Object WorkingSet64 -Sum).Sum / 1MB
    if ($mb -gt $peak) { $peak = $mb }
    Write-Host ("now {0:N0} MB, peak {1:N0} MB, free RAM {2:N0} MB" -f $mb, $peak,
        ((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1KB))
    Start-Sleep -Seconds 1
}
```

Stop it with Ctrl+C when the run ends. `ollama ps` shows the size of the loaded model and whether it
runs on the CPU.

Seconds per document: the `record run` output gives seconds per file; the recordings also keep the
seconds of every model call (`calls[].seconds`).

## 5. Results (fill in during Part B)

| Measure | Value |
|---|---|
| Model size on disk (`gemma4:e2b`) | NOT RUN YET |
| Peak memory of the Ollama processes (8192-token context) | NOT RUN YET |
| Free RAM left at the peak | NOT RUN YET |
| Seconds per document: specification | NOT RUN YET |
| Seconds per document: letter | NOT RUN YET |
| Seconds per document: DXF text | NOT RUN YET |
| Usable on the 8 GB laptop? | NOT RUN YET |

## Removing it

Uninstall "Ollama" from Settings > Apps, delete `D:\Ollama`, and remove the three user variables:

```powershell
"OLLAMA_MODELS", "OLLAMA_MAX_LOADED_MODELS", "OLLAMA_NUM_PARALLEL" |
    ForEach-Object { [Environment]::SetEnvironmentVariable($_, $null, "User") }
```
