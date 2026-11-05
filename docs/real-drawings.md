# Real drawings: how to make and label them

The synthetic drawings are clean and regular. To see how the system copes with drawings made by a person, draw ten small switchboard single-line diagrams yourself, export them to PDF and write an answer key for each by hand. They stay on your machine: `data/external/` is git-ignored and is never committed.

Do not trace or copy a drawing from a real project, a manufacturer or a website. Invent every board, rating, label and title block, as the synthetic generator does.

## 1. Pick a tool

Either free tool works; both export PDF.

- **QElectroTech** (GPL-2.0, an electrical diagram editor with a symbol library): <https://qelectrotech.org/>. Good for single-line diagrams; use its IEC symbols for breakers, switch-disconnectors, CTs, earth and meters.
- **LibreCAD** (GPL-2.0, a general 2D CAD program): <https://librecad.org/>. You draw the symbols yourself with lines and arcs, as `data_generator/symbols.py` does.

Using these tools to make drawings does not bring their licence into this repo: only your exported PDFs and your answer keys are used, and they stay local.

## 2. Draw ten boards

Keep each drawing to one A3 or A4 sheet. Vary them, so they test different things:

| # | Suggested content |
|---|---|
| 1 | ACB incomer, 4 MCCB ways, busbar label with rating and fault level |
| 2 | 6 ways mixing MCCB and switch-disconnector |
| 3 | 8 ways including 2 MCB ways |
| 4 | Incomer with CT and meter, notes block with form and IP rating |
| 5 | 10 ways, small text |
| 6 | Ratings written in a different order, e.g. `4P 250A MCCB` |
| 7 | A way marked `SPARE` with no device rating |
| 8 | A title block and a revision table only partly filled in |
| 9 | Ways drawn horizontally instead of vertically |
| 10 | Hand-drawn style: print, write one rating by hand, scan or photograph it |

Use an invented company in the title block, for example "Example Panels Ltd", and an invented drawing number.

## 3. Export

- **QElectroTech:** File, Export, choose PDF, one page per sheet.
- **LibreCAD:** File, Print preview, set the paper size and scale to fit, then File, Export as PDF.

Put each drawing in its own folder:

```text
data/external/real-sld/R01/sld.pdf
data/external/real-sld/R01/answers.json
```

For drawing 10, save the scan or photo as `sld_scanned.png` or `sld_photo.png` in the same folder.

Copy `data/external/SOURCES.template.md` to `data/external/SOURCES.md` and fill in one row per set (source "self-drawn", the tool, the date, your notes).

## 4. Write the answer key

The answer key has exactly the format of the synthetic ones (`data_generator/schemas.py`), with `"origin": "real"` and `"purpose": "real"`. It holds ground truth only: the value, the unit, the document, the page, the exact text and the region. There is no method, confidence or review status.

1. **Hash the file.** In PowerShell, from the repo folder:

   ```powershell
   (Get-FileHash data\external\real-sld\R01\sld.pdf -Algorithm SHA256).Hash.ToLower()
   ```

2. **Render the page at a fixed resolution** to read off pixel positions, for example 150 dpi:

   ```powershell
   .venv\Scripts\python.exe -c "from pathlib import Path; from data_generator.project import render_pdf_pages; im = render_pdf_pages(Path(r'data\external\real-sld\R01\sld.pdf'), 150)[0]; print(im.size); im.save(r'data\external\real-sld\R01\sld_150dpi.png')"
   ```

   The printed size is `width_px` and `height_px`; `dpi` is 150.

3. **Read boxes off the PNG** in any image viewer that shows the cursor position (for example GIMP or Paint.NET). A box is `[x0, y0, x1, y1]` in pixels, origin at the top-left corner, y going down. Draw it tight around the symbol: the conductor ends, the switch blade, the cross or circle.

4. **Write one value per statement.** If the same rating is written twice on the drawing, write two values. Use these field names:

   | Field | Example value and unit |
   |---|---|
   | `system.voltage` | `400`, `"V"` |
   | `system.frequency` | `50`, `"Hz"` |
   | `system.earthing` | `"TN-S"` |
   | `system.fault_level` | `36`, `"kA"` |
   | `enclosure.form` | `"4b"` |
   | `enclosure.ip_rating` | `"IP54"` |
   | `enclosure.cable_entry` | `"bottom"` |
   | `enclosure.width`, `enclosure.sections` | `2600`, `"mm"`; `4` |
   | `incomer.device`, `incomer.rating`, `incomer.poles` | `"acb"`; `1600`, `"A"`; `4` |
   | `busbar.rating` | `1600`, `"A"` |
   | `metering.ct_ratio`, `metering.meter` | `"1600/5"`, `"A"`; `"MFM"` |
   | `ways.count` | `6` |
   | `way.Q1.device` | `"mccb"`, `"mcb"` or `"switch_disconnector"` |
   | `way.Q1.rating`, `way.Q1.poles`, `way.Q1.breaking_capacity` | `250`, `"A"`; `4`; `36`, `"kA"` |
   | `way.Q1.description`, `way.Q1.cable`, `way.Q1.cable_length` | `"Chiller 1"`; `"4C 120 mm2 SWA"`; `40`, `"m"` |

   If something is written but unreadable or "TBC", give `"value": null` and keep the text.

5. **Check it.** The loader validates the schema, the hash and the image size:

   ```powershell
   .venv\Scripts\python.exe -c "from data_generator.real import discover; print([p.key.project_id for p in discover()])"
   ```

## Worked example

A one-sheet A3 drawing `R01/sld.pdf`: an 800 A ACB incomer, a 630 A busbar label with 25 kA, and one 250 A MCCB way labelled Q1. Rendered at 150 dpi the page is 2481 x 1754 px. The hash below is a placeholder; use the real one from step 1.

```json
{
  "schema_version": "1.0",
  "project_id": "R01",
  "origin": "real",
  "purpose": "real",
  "seed": null,
  "documents": [
    {"kind": "schematic", "file": "sld.pdf", "pages": 1,
     "sha256": "0000000000000000000000000000000000000000000000000000000000000000"}
  ],
  "drawings": [
    {
      "sheet": 1, "version": "clean", "file": "sld.pdf", "page": 1, "dpi": 150,
      "width_px": 2481, "height_px": 1754,
      "symbols": [
        {"id": "S01", "cls": "acb", "way": null, "bbox": [182, 96, 236, 214]},
        {"id": "S02", "cls": "busbar", "way": null, "bbox": [118, 412, 2390, 426]},
        {"id": "S03", "cls": "mccb", "way": "Q1", "bbox": [402, 470, 452, 564]},
        {"id": "S04", "cls": "earth", "way": null, "bbox": [130, 470, 176, 516]}
      ]
    }
  ],
  "values": [
    {"field": "incomer.rating", "value": 800, "unit": "A",
     "source": {"document": "schematic", "file": "sld.pdf", "page": 1, "source_text": "ACB 800A 4P 50kA",
                "regions": [{"version": "clean", "sheet": 1, "bbox": [250, 140, 450, 168]}]}},
    {"field": "busbar.rating", "value": 630, "unit": "A",
     "source": {"document": "schematic", "file": "sld.pdf", "page": 1, "source_text": "BUSBAR 630A TP&N 25kA 1s",
                "regions": [{"version": "clean", "sheet": 1, "bbox": [2050, 380, 2390, 406]}]}},
    {"field": "system.fault_level", "value": 25, "unit": "kA",
     "source": {"document": "schematic", "file": "sld.pdf", "page": 1, "source_text": "BUSBAR 630A TP&N 25kA 1s",
                "regions": [{"version": "clean", "sheet": 1, "bbox": [2050, 380, 2390, 406]}]}},
    {"field": "way.Q1.device", "value": "mccb", "unit": null,
     "source": {"document": "schematic", "file": "sld.pdf", "page": 1, "source_text": "MCCB 250A 4P 36kA",
                "regions": [{"version": "clean", "sheet": 1, "bbox": [440, 600, 466, 820]}]}},
    {"field": "way.Q1.rating", "value": 250, "unit": "A",
     "source": {"document": "schematic", "file": "sld.pdf", "page": 1, "source_text": "MCCB 250A 4P 36kA",
                "regions": [{"version": "clean", "sheet": 1, "bbox": [440, 600, 466, 820]}]}},
    {"field": "ways.count", "value": 1, "unit": null,
     "source": {"document": "schematic", "file": "sld.pdf", "page": 1, "source_text": null,
                "regions": [{"version": "clean", "sheet": 1, "bbox": [402, 470, 452, 564]}]}}
  ],
  "planted": [],
  "estimate": []
}
```

Notes on the example:

- `planted` is empty: real drawings have no planted problems. If you notice a real inconsistency, describe it in `SOURCES.md` instead.
- `estimate` is empty unless you also price the board from `data/catalogue/catalogue.csv`.
- `transform_from_clean` is left out: a scan or photo of a real drawing has no known transform. Give its boxes directly in its own pixels, as a separate entry in `drawings` with `"version": "scanned"` or `"photo"`.
