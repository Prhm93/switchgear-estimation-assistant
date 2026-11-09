# Stage 4: Drawing understanding (Part A, OCR)

Branch `stage-4-drawing-reading`, from main `cb93c94` (Stage 3c merged). Part A runs on the laptop only.
Parts B to D follow, one per session, each reported and merged before the next.

Until now a drawing PDF without a text layer, and every scanned or photographed drawing, was marked
"not read yet". Drawing values came only from the DXF, so the "without DXF" scores were low. Part A reads
those drawings with Tesseract OCR, links each rating text to its way label, and scores the result
separately for the clean, scanned and photo version of every drawing.

## 1. What was built

| Part | Where | What it does |
|---|---|---|
| DrawingReading schema | `backend/app/drawing/reading.py` | One typed reading per drawing image, the same for every method (OCR now; vision model and detector later): text boxes, symbols, ways. Counts (ways, symbols per class) are always computed in code from the listed items, never taken from a method. |
| Box scorer | `backend/app/drawing/boxes.py` | IoU and one-to-one matching per class (IoU at least 0.5, highest score first; a duplicate is a false positive). TP, FP, misses, P, R, F1 and mean IoU per class. For Parts B and C. |
| Drawing data | `backend/app/drawing/data.py` | Training samples only from `data/training/` (answer keys with purpose `training`); test samples only from `data/projects/test` and `data/projects/reworded` (purpose `test`). The test loader refuses the training folder. |
| OCR | `backend/app/drawing/ocr.py` | Renders a PDF page with pypdfium2 at 150 or 300 dpi; an image is taken as a 150 dpi scan and enlarged twice (Lanczos) at 300. Tesseract reads each page twice, upright and turned a quarter turn, so the vertical way texts read as lines. Every box is returned in the answer key's coordinates. |
| Linker | `backend/app/drawing/link.py` | Turns OCR lines into drawing values with the same patterns as the frozen DXF rules (`extraction.py` is not imported or changed). It fixes common character errors (O to 0, S to 5, l to 1) and gives low confidence to any value that needed one. It links each vertical rating text to the nearest way label on its left, within 0.6 of the label spacing. Cable-schedule rows are matched after taking out the sheet's skew. |
| Pipeline and app | `backend/app/pipeline.py`, `config.py`, `services.py`, `web.py` | With `DRAWING_READING=ocr` (the app default) a drawing without a text layer, or a drawing image, is read by OCR instead of being marked "not read yet". OCR'd drawings are not sent to the model. |
| Reports | `backend/drawings.py` | `counts` (symbol classes per version) and `ocr` (OCR one drawing version of a test set and score it). |
| Evaluation | `backend/evaluate.py` | `--drawing-reading ocr --drawing-version clean\|scanned\|photo --ocr-dpi 150\|300` scores the "without DXF" upload set with one drawing version read by OCR. The default is `off`, which gives exactly the Stage 3 and 3c numbers. |

**Every OCR value** goes into `extracted_values` with method `ocr`. It also gets the sheet as its page,
the OCR words as its source text, and their box as its source region. Confidence is never above
medium: medium when every word scored at least the minimum word confidence and needed no fix, low
otherwise. "Approve all" leaves OCR values alone, so the engineer approves each one before it can
reach the estimate (tested).

**Tesseract settings** (`ocr.py`): `--psm 11` ("sparse text": labels scattered over a drawing, no
paragraphs). `--oem` is not set, so Tesseract runs in its default mode, `--oem 3` (the engine picks the
best one available; with the standard `eng` data that is the LSTM engine). Language: `eng` (the default).

**Setting the resolution**: `OCR_DPI` is 150 or 300, and **300 is the default**. At 300 dpi F1 is higher
on all six cases (both sets, all three versions). It also gives fewer wrong values and on photos about
twice the recall (0.572 against 0.274 on the test set). It costs 2 to 3 s more per sheet, and peak memory
stays under 350 MB in total. 150 dpi only saves time.

## 2. Licences and install

| Software | Licence | Use |
|---|---|---|
| Tesseract OCR 5.4.0 (with the `eng` data) | Apache-2.0 | A separate program, called for drawing OCR |
| pytesseract 0.3.13 | Apache-2.0 | Python wrapper that calls Tesseract. Declares Python up to 3.12; tested working on 3.14.4 |
| pypdfium2 5.14.0 (PDFium) | Apache-2.0 or BSD-3-Clause (PDFium: BSD-3-Clause) | Drawing PDF page to image (already used by the generator) |
| Pillow 13.0.0 | MIT-CMU | Drawing images (already used by the generator) |

All four are in the README licences table.

**Windows (laptop).** Install the UB Mannheim build of Tesseract 5.4 for Windows (installer from the
UB Mannheim Tesseract page on GitHub, English data only) into the default folder
`C:\Program Files\Tesseract-OCR`. The app finds it there even when it is not on PATH. Otherwise:

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"   # only if installed elsewhere
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version             # check
.venv\Scripts\python.exe -m pip install -r requirements.txt              # pytesseract
```

**Docker** (`deployment/Dockerfile`, `python:3.12-slim`), before the pip step:

```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
```

**CI** (`.github/workflows/tests.yml`) installs the same two apt packages and sets `REQUIRE_TESSERACT=1`,
so on GitHub a missing Tesseract fails the OCR tests instead of skipping them. On the laptop they skip
with a message when Tesseract is not found.

## 3. How to run it

```powershell
# Test sets (git-ignored), if not built yet
.venv\Scripts\python.exe -m data_generator build --set test
.venv\Scripts\python.exe -m data_generator build --set reworded

# OCR alone, one drawing version of one set, scored against answers.json
.venv\Scripts\python.exe -m backend.drawings ocr --set test --version scanned --dpi 300

# "Without DXF" scores with OCR (rules; then combined with the recorded LLM)
.venv\Scripts\python.exe -m backend.evaluate --set test --drawing-reading ocr --drawing-version photo
.venv\Scripts\python.exe -m backend.evaluate --set test --mode combined --drawing-reading ocr --drawing-version photo

# Symbol classes in the 300 training drawings
.venv\Scripts\python.exe -m backend.drawings counts

# The app: OCR is on by default; switch it off with
$env:DRAWING_READING = "off"
```

## 4. How it was tested

52 tests in six new files, all passing (laptop, 8 Nov 2026, Tesseract 5.4.0 found):

- `tests/unit/test_drawing_reading.py`: boxes must have a size and lie inside the image. Only drawing
  methods can make a reading. Counts are summed in code, and a duplicate way counts once.
- `tests/unit/test_box_scorer.py`: IoU, one-to-one matching, duplicates as false positives, per-class scores.
- `tests/unit/test_drawing_data.py`: training only from `data/training/`; the test loader refuses it;
  the full sets never share a project or a seed; the full training set counts.
- `tests/unit/test_drawing_link.py`: character fixes, way linking by position, skew, trailing noise.
- `tests/integration/test_drawing_ocr.py`: on the showcase, clean PDF values are right and their boxes
  sit on the answer-key boxes. Every OCR value is `ocr`, medium at most and has a region. 150 and
  300 dpi give boxes in the same coordinates. The app reads a scanned drawing by default. "Approve all"
  leaves OCR values unapproved, and they never reach the estimate. Without Tesseract the drawing stays
  "not read yet" with a note.
- `tests/integration/test_drawing_reading_off.py`: with drawing reading off, every value is the same as
  before, with and without the DXF.

The Stage 3c baseline was also rerun in full (section 5.3): every number is unchanged.

## 5. Results

All real runs on the laptop (8 GB, Windows, Python 3.14, Tesseract 5.4.0), 8 Nov 2026. Each run was done
on its own, one after another. A memory guard stopped any run if free system memory fell below 800 MB;
none was stopped. No real drawings are in `data/external/` yet, so **every number here is on synthetic
drawings only**.

**Which set to trust.** The linker was developed by looking at test projects T01 to T03. So the
**reworded set (R01 to R20) is the held-out result**. The original test set (T01 to T20) shows what
the method can do on the wording it was written for. The linker must not be tuned on the reworded set:
that would leave no held-out drawing result before the fresh Stage 7 set.

### 5.1 OCR alone: drawing values against answers.json

`python -m backend.drawings ocr --set <set> --version <version> --dpi <dpi>`. Drawing values only (no
specification or letter), 40 sheets per run (20 projects, 2 sheets each). Ratings are the way, incomer
and busbar ratings. Way labels are each diagram label read as a way id, against the ways on that sheet.
TP/FP/FN are right/wrong/missed. Time is mean (max) seconds per sheet, rendering and both OCR passes
included. Memory is the peak of the Python process plus the largest single Tesseract run.

**Test set (T01 to T20), 300 dpi**

| Group | Clean | Scanned | Photo |
|---|---|---|---|
| ratings | 207/0/21: 1.000, 0.908, **0.952** | 192/0/36: 1.000, 0.842, **0.914** | 116/4/112: 0.967, 0.509, **0.667** |
| poles | 187/0/21: 1.000, 0.899, **0.947** | 172/0/36: 1.000, 0.827, **0.905** | 100/2/108: 0.980, 0.481, **0.645** |
| breaking capacity | 136/0/18: 1.000, 0.883, **0.938** | 129/0/25: 1.000, 0.838, **0.912** | 63/3/91: 0.955, 0.409, **0.573** |
| way labels | 167/0/21: 1.000, 0.888, **0.941** | 155/0/33: 1.000, 0.824, **0.904** | 109/0/79: 1.000, 0.580, **0.734** |
| all drawing fields | 1297/10/300: 0.992, 0.812, **0.893** | 1225/16/372: 0.987, 0.767, **0.863** | 662/55/935: 0.923, 0.415, **0.572** |
| s per sheet | 2.89 (4.73) | 5.36 (7.04) | 4.22 (5.79) |
| peak MB | 231 + 115 | 140 + 100 | 138 + 84 |

**Reworded set (R01 to R20, held out), 300 dpi**

| Group | Clean | Scanned | Photo |
|---|---|---|---|
| ratings | 6/0/214: 1.000, 0.027, **0.053** | 5/0/215: 1.000, 0.023, **0.044** | 6/0/214: 1.000, 0.027, **0.053** |
| poles | 3/0/197: 1.000, 0.015, **0.030** | 3/0/197: 1.000, 0.015, **0.030** | 3/0/197: 1.000, 0.015, **0.030** |
| breaking capacity | 1/0/161: 1.000, 0.006, **0.012** | 1/0/161: 1.000, 0.006, **0.012** | 1/1/161: 0.500, 0.006, **0.012** |
| way labels | 168/0/12: 1.000, 0.933, **0.966** | 149/0/31: 1.000, 0.828, **0.906** | 90/0/90: 1.000, 0.500, **0.667** |
| all drawing fields | 329/5/1228: 0.985, 0.211, **0.348** | 318/3/1239: 0.991, 0.204, **0.339** | 140/32/1417: 0.814, 0.090, **0.162** |
| s per sheet | 3.14 (4.70) | 5.19 (7.16) | 4.05 (5.46) |
| peak MB | 227 + 115 | 136 + 100 | 137 + 85 |

For reference, the frozen DXF rules on the same reworded sheets score F1 0.053 (ratings), 0.113
(poles), 0.200 (breaking capacity) and 0.584 (all drawing fields). The rules and OCR fail on the same
wording.

**What the reworded result means.** Way labels read at **0.966 on reworded clean**, so Tesseract reads
these drawings well. The weak part is the **linker's label patterns**: they follow the frozen DXF rules,
which do not know reworded styles such as `In=630A` or `4 pole`. So the text is read, but it is not
turned into a value. The fix is better patterns, written without looking at the reworded set, not a
different OCR engine.

**150 against 300 dpi** (all drawing fields, F1 (TP/FP/FN), mean s per sheet, peak MB)

| Set, version | 300 dpi (default) | 150 dpi |
|---|---|---|
| test clean | **0.893** (1297/10/300), 2.89 s, 231 + 115 | 0.851 (1206/31/391), 1.41 s, 138 + 69 |
| test scanned | **0.863** (1225/16/372), 5.36 s, 140 + 100 | 0.804 (1096/34/501), 2.19 s, 119 + 69 |
| test photo | **0.572** (662/55/935), 4.22 s, 138 + 84 | 0.274 (258/25/1339), 1.53 s, 121 + 55 |
| reworded clean | **0.348** (329/5/1228), 3.14 s, 227 + 115 | 0.294 (271/16/1286), 1.40 s, 135 + 69 |
| reworded scanned | **0.339** (318/3/1239), 5.19 s, 136 + 100 | 0.282 (259/21/1298), 2.20 s, 116 + 69 |
| reworded photo | **0.162** (140/32/1417), 4.05 s, 137 + 85 | 0.077 (63/20/1494), 1.53 s, 120 + 55 |

The test-clean run at 300 dpi gives exactly the same counts as an earlier run of the same case
(1297/10/300). That earlier run took 5.24 s per sheet (14.95 s worst) and peaked at 214 MB for Python,
on a busier machine. Seconds per sheet depend on what else is running.

### 5.2 Without DXF: rules + OCR and combined + OCR, next to Stage 3c

`python -m backend.evaluate --set <set> [--mode combined] --drawing-reading ocr --drawing-version <v>`,
at 300 dpi. The upload is the specification, the letter and one drawing version (no DXF). Specification
and letter are read as in Stage 3c. Combined uses the v2 recordings: "strict" is the v2 quote check
(the fixed baseline), "relaxed" is the Stage 3c app default (tuned on these sets). P, R, F1 (TP/FP/FN)
over all fields.

| Set | Drawing | Rules | Combined, strict | Combined, relaxed |
|---|---|---|---|---|
| test | none (Stage 3c) | 1.000, 0.486, 0.654 (1508/0/1597) | 0.950, 0.486, 0.643 (1508/79/1597) | 0.945, 0.486, 0.642 (1508/87/1597) |
| test | clean + OCR | 0.996, 0.903, **0.948** (2805/10/300) | 0.969, 0.903, **0.935** (2805/89/300) | 0.967, 0.903, **0.934** (2805/97/300) |
| test | scanned + OCR | 0.994, 0.880, **0.934** (2733/16/372) | 0.966, 0.880, **0.921** (2733/95/372) | 0.964, 0.880, **0.920** (2733/103/372) |
| test | photo + OCR | 0.975, 0.699, **0.814** (2170/55/935) | 0.942, 0.699, **0.802** (2170/134/935) | 0.939, 0.699, **0.801** (2170/142/935) |
| reworded | none (Stage 3c) | 1.000, 0.005, 0.011 (16/0/3015) | 0.903, 0.343, 0.497 (1040/112/1991) | 0.896, 0.411, 0.563 (1245/144/1786) |
| reworded | clean + OCR | 0.986, 0.114, **0.204** (345/5/2686) | 0.921, 0.452, **0.606** (1369/117/1662) | 0.914, 0.519, **0.662** (1574/149/1457) |
| reworded | scanned + OCR | 0.991, 0.110, **0.198** (334/3/2697) | 0.922, 0.448, **0.603** (1358/115/1673) | 0.914, 0.516, **0.659** (1563/147/1468) |
| reworded | photo + OCR | 0.830, 0.051, **0.097** (156/32/2875) | 0.891, 0.389, **0.542** (1180/144/1851) | 0.887, 0.457, **0.603** (1385/176/1646) |

What these show:

- **Original wording.** OCR raises "without DXF" F1 from 0.654 to 0.948 (clean), 0.934 (scanned) and
  0.814 (photo) in rules mode. Precision stays at 0.975 or above.
- **Held-out reworded set.** In combined mode (relaxed), OCR raises F1 from 0.563 to 0.662 (clean),
  0.659 (scanned) and 0.603 (photo). The gain is smaller, because most reworded drawing values are not
  linked (5.1).
- **Combined against rules.** On the original wording combined is slightly lower than rules alone. The
  rules already find what the model finds there, so the model's values only add extras (as in Stage 3c).

**How the table was run.** The combined runs score four columns (the two v1 columns, v2 strict, v2
relaxed), and each column reads every drawing. To read each drawing only once, these runs used a
small wrapper outside the repo. It saved the OCR result of each drawing file (keyed by SHA-256 of
the bytes and the dpi) and gave it back on later reads. The app and the repo code were not changed. A
rules run read from the saved results gave exactly the same table as a fresh OCR run (checked on test
clean). Every combined cell above was scored from the same OCR result as its rules cell.

### 5.3 Stage 3c baseline, rerun with drawing reading off

`python -m backend.evaluate --set test|reworded [--mode llm|combined]`, drawing reading off (the
default). Every number is **the same as in docs/stage-3.md**:

| Set | Mode | With DXF | Without DXF |
|---|---|---|---|
| test | rules | 1.000 (3105/0/0) | 0.654 (1508/0/1597) |
| reworded | rules | 0.367 (709/123/2322) | 0.011 (16/0/3015) |
| test | LLM, strict / relaxed | 0.778 / 0.813 | 0.561 / 0.588 |
| reworded | LLM, strict / relaxed | 0.727 / 0.790 | 0.497 / 0.563 |
| test | combined, strict / relaxed | 0.944 / 0.941 | 0.643 / 0.642 |
| reworded | combined, strict / relaxed | 0.760 / 0.803 | 0.497 / 0.563 |

The v1 columns are also unchanged, and so are the relaxed-check counts (rescued values, rating-guard
removals, poles flags). The test `tests/integration/test_drawing_reading_off.py` checks the same thing
on every run.

### 5.4 Symbol classes in the training drawings

`python -m backend.drawings counts`: 300 training projects, 900 drawing images (from `data/training/`
only):

| Class | clean | scanned | photo |
|---|---|---|---|
| mccb | 1893 | 1893 | 1893 |
| switch_disconnector | 484 | 484 | 484 |
| busbar | 300 | 300 | 300 |
| acb | 300 | 300 | 300 |
| ct | 300 | 300 | 300 |
| earth | 300 | 300 | 300 |
| meter | 300 | 300 | 300 |
| mcb | 138 | 138 | 138 |
| **all** | 4015 | 4015 | 4015 |

The classes are unbalanced: mccb is 47% of the symbols and mcb is 3.4%. Part C should report each class
on its own and not rely on the overall score.

## 6. Known limits

- **Reworded styles are not read.** Rating texts such as `In=630A` or `4 pole` are not turned into
  values (ratings F1 0.053, poles 0.030 on reworded clean), although the text and the way labels are
  read (0.966). The linker's patterns follow the frozen DXF rules.
- **T03's photo read almost nothing.** 3 right drawing values against 67 missed, no way labels (0 of 8)
  and 1 of 10 ratings. Observed: a tilted photo with a serif-style font; cause not proven. The clean drawing of the same project reads
  normally. Photos are the weakest version on both sets.
- **No real drawings yet.** `data/external/` is empty. Every number is on synthetic drawings, which are
  cleaner than real ones (see docs/stage-1.md).
- **Tuned on the test set.** The linker was developed on T01 to T03, so the test-set numbers are not
  held out. The reworded numbers are, as long as the linker is not tuned on them.
- **Metering barely read.** `metering.ct_ratio` and `metering.meter` are almost never found: at most
  2 right of 20 in any OCR run, 0 in most.
- **Time.** 3 to 5 s per sheet at 300 dpi, so a two-sheet drawing adds about 6 to 11 s to an upload.
  It runs in the background task.
- **pytesseract** declares support up to Python 3.12. It works on the laptop's 3.14.4 (all tests pass),
  but that is not declared by its authors.

## 7. Plan for Parts B to D

- **Part B (Colab): vision model.** gemma4:e2b reads each drawing image into a `DrawingReading`. It runs
  in recorded mode, as in Stage 3, with the same SHA-256 check. Counts are summed in code, never taken
  from the model. Scored against the same answer keys as OCR, per clean, scanned and photo, on both test
  sets.
- **Part C (Colab): symbol detector.** A torchvision detector trained on `data/training/` only, scored
  per class with the IoU scorer (`boxes.py`) on the test drawings. torchvision's pretrained weights
  "may have their own licenses or terms ... derived from the dataset", so they are not clearly
  permissive. A from-scratch option is planned, and no weights are downloaded before Part C. **SAM 2**
  (Apache-2.0) will be tried as a comparison for finding symbol regions. Its weight licence will be
  checked before anything is downloaded. The trained model runs on CPU on the laptop if it fits;
  otherwise its outputs are recorded.
- **Part D: boxes on the drawing in the UI.** Each value's region is drawn over the drawing on the
  analysis screen, coloured by confidence (medium and low for OCR), in the design-v2 style.
