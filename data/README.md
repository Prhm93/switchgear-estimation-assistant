# Data

All data in this project is synthetic. Every enquiry, drawing, part code, price and company name is invented. Nothing comes from a real catalogue, price list, drawing or company document.

| Path | What it is | In git |
|---|---|---|
| `catalogue/catalogue.csv` | Invented parts catalogue (64 parts), with a data dictionary in `catalogue/README.md` | Yes |
| `projects/showcase/` | The showcase enquiry used in the demo | Yes |
| `projects/test/PLANTED.md` | The problems planted in the 20 test enquiries | Yes |
| `projects/test/T01` to `T20` | The 20 test enquiries | No, rebuilt from seeds |
| `projects/reworded/R01` to `R20` | The 20 reworded enquiries (Stage 3): the test plans in other words, seeds 2001 to 2020 | No, rebuilt from seeds |
| `projects/fresh/F01` to `F20` | The fresh held-out set (Stage 7): seeds 3001 to 3020, the test plans, every other enquiry reworded; never used for tuning | No, rebuilt from seeds |
| `projects/fresh/FROZEN.sha256` | The SHA-256 of every fresh-set file as first built, and the set's hash; the evaluation refuses a changed set | Yes |
| `training/TR0001` to `TR0300` | 300 training drawings for the Stage 4 symbol detector | No, rebuilt from seeds |
| `external/` | Real drawings you add yourself (see `docs/real-drawings.md`) | No, except `SOURCES.template.md` |

Rebuild everything (PowerShell, from the repo folder):

```powershell
.venv\Scripts\python.exe -m data_generator build --set all
```

Or one set at a time: `--set showcase`, `--set test`, `--set reworded`, `--set fresh`, `--set training`. `--workers 2` (the default) builds two items at a time; the output does not depend on it. The same seed gives byte-identical files on the same machine. Other platforms and CPUs give the same content, except a few pixel values in the scanned and photo PNGs on some CPUs, but not always the same bytes (see `docs/stage-1.md`). **Recorded model outputs (Stage 3) must therefore be made from byte copies of the laptop-built files, not from a rebuild on Colab or in CI:** their SHA-256 hashes are checked against the uploaded file.

The engine's earlier demo data still lives in code: part prices in `PRICES` (`ai_engine/estimation_assistant/tools.py`) and notes in `NOTES` (`ai_engine/estimation_assistant/retrieval.py`).

## One enquiry

```text
<project>/
  specification.pdf                   6 to 14 pages, numbered clauses, table of outgoing ways
  requirements.docx                   the customer's letter, plain words
  drawing/schematic.pdf               clean vector PDF: sheet 1 single-line diagram, sheet 2 front view
  drawing/schematic_sheet1_scanned.png   printed and scanned (greyscale)
  drawing/schematic_sheet1_photo.png     phone photo (colour)
  drawing/schematic_sheet2_scanned.png
  drawing/schematic_sheet2_photo.png
  drawing/schematic.dxf               the CAD source the PDF is rendered from (not an engineer input)
  answers.json                        the answer key
```

## The answer key

`answers.json` follows `data_generator/schemas.py` (`AnswerKey`). It holds ground truth only:

- `documents`: each file with its SHA-256 hash and page count.
- `values`: one entry per statement of a value in a document: `field`, `value`, `unit`, and `source` (document, file, page, exact `source_text`, and for the drawing a `regions` box in each of the three versions). The same field stated in two documents is two entries; that is how conflicts are recorded.
- `drawings`: for every sheet and version, the image size and a class and box for every symbol (`busbar`, `acb`, `mccb`, `mcb`, `switch_disconnector`, `ct`, `earth`, `meter`), plus the 3x3 transform from the clean page.
- `planted`: the planted problems, each with its sources and the behaviour a correct system shows.
- `estimate`: the correct estimate lines (catalogue code, quantity, unit, the fields each line depends on, and the planted problems that block it).

Boxes are pixels, origin top-left, `[x0, y0, x1, y1]`. For the clean PDF they are pixels of the page rendered at the stated `dpi` (150).
