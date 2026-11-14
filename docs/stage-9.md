# Stage 9: the question box

Branch `stage-9`, from `stage-7`. Built in an unattended run on 13 Nov 2026; the choices made without the owner are
listed in section 6.

## 1. What was built

- **Ask column on the Summary**: one input and the answers, each with the passage it comes from (file, page and
  the passage text). It replaces "Coming soon"; the Ask button on Review and on the draft quote now opens it
  (`/enquiries/<id>#ask`). With HTMX the column is swapped in place; without script the page reloads at the column.
- `backend/app/rag.py` (no database): cuts each page into passages of two lines with one line shared with the
  next; embedders behind one interface: the **word embedder** (`words`, no model: each word hashed to one of 512
  places, threshold 0.2), used on the laptop and in every test, and **mxbai-embed-large** through Ollama
  (`EMBEDDER=ollama`, threshold 0.5, Colab only, not run yet).
- **Answers are quotes, not generated text**: the best line of the best passage, with its file and page. Below the
  threshold the box says there is no evidence and gives no answer. Every number in the quoted line is checked
  against the engineer's approved values ("36 matches an approved value" or "36 is read from the file and not
  approved by an engineer yet"); a clause number at the start of a line ("3.4 ") is not treated as a value.
  A passage with instruction-like text (the same detector as Stage 3) is shown as data with a warning, and nothing
  is done because of it: the question box can only read.
- `backend/app/ask.py`: passages are stored in `ask_passages` once per file and embedder (pgvector `vector` on
  PostgreSQL, searched with `<=>`, cosine distance; JSON and cosine in Python on SQLite); a file deleted or read
  again loses its passages, and they are made again on the next question. Every question is saved in
  `ask_questions` with the answer, sources, refusal, number check, embedder and actor, and written to the audit log
  ("ask", with the sources).
- **Migration 0007**, additive only: the two new tables.
- `backend/ask_eval.py`: scores the search. For each project and 12 fields, the question "What is the <field>?"
  is asked over the specification and the letter; a hit is the passage on the answer key's own file and page that
  holds its source text.

## 2. How to run it

```powershell
.venv\Scripts\python.exe -m backend.ask_eval --set fresh            # word embedder, laptop
# Colab (docs/colab-all.md, Cell 9): --embedder ollama --out data/recorded-ask/fresh-mxbai.json
# the evaluation report reads data/recorded-ask/ and adds the table to docs/evaluation.md
```

In the app: open an enquiry's Summary and type a question in the Ask column.

## 3. Results (laptop, 13 Nov 2026, word embedder; 12 fields per project where the files state them)

| Set | Questions | Right passage first | Right passage in the best 3 | Refused (no evidence) |
|---|---|---|---|---|
| fresh (not used for tuning) | 236 | 140 (0.593) | 181 (0.767) | 15 |
| test (not held out) | 236 | 114 (0.483) | 183 (0.775) | 16 |
| reworded (not held out) | 236 | 158 (0.669) | 179 (0.758) | 28 |

**mxbai-embed-large (Colab T4, 13 Nov 2026; scored on the laptop against the same answer keys).** Fresh set, not
used for tuning, same generator as the test set; the same 236 questions:

| Embedder | Right passage first | In the best 3 | Refused | Right refusals | Wrong refusals |
|---|---|---|---|---|---|
| words (threshold 0.2) | 140 (0.593) | 181 (0.767) | 15 | 5 | 10 |
| mxbai-embed-large (threshold 0.5) | 167 (0.708) | 185 (0.784) | 29 | 20 | 9 |
| showcase, mxbai | 8 of 12 | 9 of 12 | 3 | 2 | 1 |

- A refusal is **right** when the best passage did not hold the answer (answering would have quoted the wrong
  passage) and **wrong** when the best passage held it and only its score was under the threshold.
- mxbai ranks better (0.708 against 0.593 first) but **refuses more** (29 against 15). Most of its refusals are
  right (20 of 29), but 9 are wrong and they sit just under the threshold (scores 0.481 to 0.488), 7 of them on the
  incomer rating. The words embedder's wrong refusals are mostly the CT ratio (scores 0.17 to 0.20).
- The thresholds were not changed: they were set by hand before this run, and the fresh set is not used for
  tuning. A threshold for mxbai would be chosen on the test set and then checked once on the fresh set.
- The Colab words run gives exactly the laptop numbers above (140 and 181), so both embedders were scored on the
  same passages.
- The report table is also in `docs/evaluation.md` (fresh set section).
- Typical miss with words: "What IP rating is the enclosure?" on the showcase quotes "3.1 Rated operational voltage"
  because "rated" and "rating" share a stem; the right clause is in the best three. The quote always names its file
  and page, so a wrong passage is visible as such.

## 4. Tests

- `tests/integration/test_ask.py` (8): one input and no "Coming soon"; an answer cites file and page and is saved
  and audited, and is still there after a reload; no evidence gives a refusal; a quoted number becomes "approved"
  after the engineer approves it; a question with markup is stored as typed and shown escaped (Summary and
  Activity); an instruction planted in a page is flagged and nothing changes; passages are made once and dropped
  with the file; on PostgreSQL the pgvector search returns the nearest passage first (database test).
- `tests/unit/test_rag.py` (8) and `tests/unit/test_ask_eval.py` (2).
- Changed on purpose: `test_simple_flow` (the Ask button is a link to the question box, not "Coming soon") and
  `test_enquiry_summary` (the quiet column became the question box: one input, one button).

## 5. Known limits

- The word embedder matches words, not meaning: synonyms that share no word are missed (the reason for
  mxbai-embed-large). Its 0.2 threshold and mxbai's 0.5 were set by hand, not tuned on any set.
- Answers quote one line; a fact spread over two lines (a table row and its header) is quoted without its header.
- The existing agent (ai_engine) is not used: an extractive answer cannot invent a number, and no model runs on the
  laptop. Generated answers through the agent stay a Colab option.
- Questions about the drawing pictures are not answered (they have no text layer); the DXF text is searched.

## 6. Choices made without the owner (unattended run)

- Answers are quoted from the files instead of written by a model, so that "refuse when there is no evidence" and
  "check numbers" are checks in code.
- The question box lives on the Summary only; Review and the draft quote link to it.
- The last five questions are shown, newest first.
