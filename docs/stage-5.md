# Stage 5: cross-document checks

Branch `stage-5`, from `stage-4bcd` (Stage 4 Parts B to D, not merged yet). Built on 12 Nov 2026; the design
choices are listed at the end.

## 1. What was built

- `backend/app/crosscheck.py`: `differences()` finds every field on which two **files** give values that do not
  overlap at all, after the scorer's normalising (`250` equals `250 A`; `ACB` equals `air circuit breaker`
  through the existing `normalise.device`). A way listed in one file but not in another is a difference too
  (a quantity question). Each difference keeps both sides with their sources (file, page, value id) and a plain
  sentence, for example "The specification says 630 A; the drawing says 400 A". Files are always named in one
  order: specification, drawing, letter.
- Not a difference: two readings of the **same** file (rules and model, say), files that share a value even if
  one also has another reading, and values that state no value: `None` (TBC) and placeholder text a model may
  copy for it (`TBC`, `TBA`, `-`, `N/A`, empty). Those belong to the missing-information list.
- Flagged only: the check never picks, approves or rejects anything, and never changes what it is given (tested).
- Check page: each conflict card now says which case it is. A difference between files keeps the chip "The
  documents disagree" and adds the sentence naming both files; two readings of one file get "Two readings of
  one file differ". `Decisions.between_files` holds the differences by field. Ways missing from a file were
  already listed by the Stage UX code (`partial_ways`) and are unchanged.
- `python -m backend.crosschecks --set test|reworded --mode rules|combined` scores the check on the planted
  problems of a set, reading each project as the app reads an upload with the DXF.
- `normalise.py` is **not** changed: the ACB alias the roadmap names was already there.

## 2. How a result counts

- A planted rating or quantity conflict is **found** when a difference names its field; for a quantity
  conflict on `ways.count`, a "way in one file only" difference counts too.
- Every other difference is a **false flag**; the control projects have no planted conflict, so any difference
  there is a false flag, even one that follows from a planted conflict (the CT ratio on T05 follows its planted
  incomer rating, and is counted as false).
- A planted **missing value** is listed when the app's missing-information list names its field.

## 3. Results (laptop, 12 Nov 2026, with the DXF)

| Set | Mode | Conflicts found | False flags | P | R | F1 | Missing values listed |
|---|---|---|---|---|---|---|---|
| test | rules | 10 of 10 | 1 | 0.909 | 1.000 | 0.952 | 4 of 5 |
| test | combined (tuned on this set) | 8 of 10 | 3 | 0.727 | 0.800 | 0.762 | 3 of 5 |
| reworded | rules | 1 of 10 | 0 | 1.000 | 0.100 | 0.182 | 5 of 5 |
| reworded | combined | 6 of 10 | 182 | 0.032 | 0.600 | 0.061 | 3 of 5 |

- "Tuned on this set": before the placeholder rule, test/combined had 42 false flags (P 0.160, F1 0.267); the
  rule was added after seeing them. Found conflicts did not change in any row; reworded/combined false flags went
  from 212 to 182, and rules mode did not change.
- Test/combined misses T01 and T14, which rules mode finds; most likely a model value matches the other file's
  value, so the files share a value and are not apart (not checked value by value). The false flags are the T05
  CT ratio and two sizes in mm (T15, T18).
- Reworded/rules finds 1 of 10 because the frozen rules read little of the reworded wording (Stage 3).
- Reworded/combined is the honest held-out number and it is poor: the model misreads many drawing values
  (cable sizes and other ways' numbers as ratings) and spells devices in ways the normaliser does not know
  ("m.c.c.b.", "sw_disconnector", "mccb (moulded case)"). No alias was added from the reworded set, because that
  would be tuning on it.

## 4. Tests

`tests/unit/test_crosscheck.py` (10 tests) and `tests/integration/test_crosscheck_check.py` (2 tests: the
showcase's planted difference names both files and nothing is approved; a made-up second reading of one file is
called "Two readings of one file differ").

## 5. Known limits

- Many false flags whenever model values are included on reworded files; a Stage 6 confidence rule (for example,
  only flag between values of medium confidence or better) is the next step, not built here.
- Device spellings outside the normaliser's aliases are differences; adding aliases needs a separate decision and the
  strict numbers to stay exact.
- Differences are flagged on Check only; the Summary tile and the report still count conflicts as before.

## 6. Design choices

- `normalise.py` left unchanged (the ACB alias was already there; reworded-set spellings not added).
- Placeholder text counts as a missing value, like TBC (chosen after seeing the test-set combined run; labelled).
- The existing chip text "The documents disagree" is kept for differences between files, so earlier tests and
  screens keep their wording.

## 7. End of stage: full suite and strict numbers

- Full suite in two halves (laptop, Docker Postgres, at least 800 MB free): database tests 5 passed; the rest
  876 passed in 5 min 17 s.
- Strict v2 numbers (`python -m backend.evaluate --set test|reworded --mode llm`) reproduce exactly: 0.778 and
  0.561 on the test set (with and without the DXF), 0.727 and 0.497 on the reworded set.
