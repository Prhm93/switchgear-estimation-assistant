# Stage 6: confidence and review

Branch `stage-6`, from main f0741d4 (stage-simple merged). Built on 13 Nov 2026; the design choices
are listed in section 6.

## 1. What was built

- `backend/app/confidence.py`: one rule set gives every value a level, in this order.
  1. **How it was read**: the rules on a file's text are high (or the rule's own level); a model with an exact
     quote is medium, with a pieced quote low; OCR and the vision model keep their own level but never above
     medium; the symbol detector is low; a flag (poles from a cable core count) makes it low. A value the
     engineer approved or typed is high.
  2. **Conflict**: two live values of one item that differ, where at least one is high, make every value of
     the item a conflict. Two lower values that differ (model against model, picture against model) are a
     **weak difference**: each is low, says "Another reading (the drawing) gives a different value", and is
     checked on its own, never as a conflict card.
  3. **Agreement**: another file giving the same value raises the level one step, up to high for the rules and
     a model with an exact quote, and up to medium for a picture or a pieced quote.
- Each value also gets plain reasons and a **risk** number (conflict, then low, medium, high; within a level the
  detector, vision, OCR, model, rules). Nothing is stored: it is worked out each time a screen is shown, so it
  follows every approval and every new file.
- **Bulk acceptance**: only high values read by the rules from a file's text, with no file saying otherwise
  (no model, no picture, no pieced quote, no flag). A model value that another file confirms is high but is still
  ticked by a person. "Accept all" on Check and the agreeing-values card on Review use this one rule.
- **Review queue by risk**: after the agreeing-values card (kept first, see section 6), the conflicts come first,
  then the file-and-page cards with the riskiest value first, and inside a card the riskiest value first. On
  Check, the values in each reason group are listed riskiest first, and a new reason "Readings differ" holds the
  weak differences.
- **Ticks**: on a file-and-page card, values read from a picture or by a model start **unticked**; a person ticks
  each one. Each value shows why it is there ("Read from a drawing picture; Another reading (the specification)
  gives a different value").
- **Value panel**: shows the assessed level and its reasons instead of the reading's own level.
- **Guard**: two different values can never both be approved for one item ("Another value is already approved
  ... Use Change"). Settling a conflict now sets the other values aside before it approves the kept one.
- **Cross-check gate**: `differences(..., gate=True)` flags a difference between two files only when at least one
  of them gives a value read reliably (high before agreement); a way missing from a file is flagged only when the
  way's own values or the listing of the file it is missing from include such a value. The app uses the gate;
  `python -m backend.crosschecks --gate` scores it, and without `--gate` the Stage 5 behaviour is scored.
- **Calibration**: `python -m backend.calibration --set test|reworded --mode rules|combined` marks each value right
  or wrong by the scorer's own rule (`evaluation.correct_flags`, tested to agree with `score`) and reports the
  share right per level and per method and level.

## 2. How to run it

```powershell
.venv\Scripts\python.exe -m backend.calibration --set test --mode combined
.venv\Scripts\python.exe -m backend.crosschecks --set reworded --mode combined          # Stage 5, no gate
.venv\Scripts\python.exe -m backend.crosschecks --set reworded --mode combined --gate   # Stage 6
```

## 3. Results

Laptop, 13 Nov 2026, every project read with the DXF as the app reads an upload (strict v2 recordings for the
model, as in Stage 5). No threshold was tuned: the rules above were written before any of these numbers were run.

**False flags of the cross-check, before (Stage 5, no gate) and after (Stage 6 gate)**

| Set | Mode | Conflicts found, before | after | False flags, before | after | P before / after | F1 before / after |
|---|---|---|---|---|---|---|---|
| test | rules | 10 of 10 | 10 of 10 | 1 | 1 | 0.909 / 0.909 | 0.952 / 0.952 |
| test | combined | 8 of 10 | 8 of 10 | 3 | 3 | 0.727 / 0.727 | 0.762 / 0.762 |
| reworded | rules | 1 of 10 | 1 of 10 | 0 | 0 | 1.000 / 1.000 | 0.182 / 0.182 |
| reworded | combined | 6 of 10 | **4 of 10** | 182 | **47** | 0.032 / 0.078 | 0.061 / 0.131 |

- The gate removes 135 of the 182 false flags on the reworded set (74 %), and costs 2 of the 6 conflicts found
  there: those two were seen only by model readings on both sides, so they are now checked value by value (each
  value low, with the other reading named) instead of as a conflict card. Rules mode and the test set do not change.
- The 47 left: device spellings the normaliser does not know ("mccb (moulded case)" against "MCCB"; no alias added,
  see Stage 5), enclosure sizes in mm where the rules read the DXF and the model the specification, and ways that
  the DXF lists but the model missed in the reworded specification. Missing values listed do not change.

**Calibration: share of values right at each level** (`python -m backend.calibration`; TBC values left out)

| Set | Mode | high | medium | low | conflict |
|---|---|---|---|---|---|
| test | rules | 1.000 (3076) | (none) | 1.000 (1) | 1.000 (27) |
| test | combined | 0.991 (2798) | 0.000 (192) | 0.500 (2) | 0.681 (483) |
| reworded | rules | 1.000 (576) | 1.000 (8) | (none) | 0.504 (248) |
| reworded | combined | **0.985** (1513) | **0.680** (394) | **0.507** (284) | 0.595 (378) |

- On the reworded set with the model (the closest to held out), the levels are in the right order and well apart:
  high values are right 98.5 % of the time, medium 68 %, low 51 %. By method, rules high values are right 551 of
  551; model values raised to high by an agreeing file are right 940 of 962 (0.977).
- On the test set with the model, the 192 medium model values are all wrong by the scorer: the rules read the test
  wording almost completely, so a model value the rules did not also read is a misreading or the same fact on a
  page the answer key does not list. Medium is still the right advice there ("check it"), but the share right is
  far below the reworded set's.
- "Conflict" is not a correctness level: a planted conflict has two values that are each right for their own file
  (the test set's 27 rules conflict values are all right). It means "the files disagree; decide".

## 4. Tests

- `tests/unit/test_confidence.py` (10): base levels, agreement, conflict against weak difference, bulk rule, TBC,
  risk order, rejected values, the gate on differences and on missing ways.
- `tests/unit/test_calibration.py` (2): per-value right or wrong agrees with the scorer; the table.
- `tests/integration/test_confidence_review.py` (5): model readings that differ are no conflict card and start
  unticked with their reason; an agreeing model value is high but never bulk-accepted; page cards riskiest first;
  never two different approved values; the value panel shows the level and why.
- Changed on purpose: tests that read the stored reading level of bulk-approved values now read the assessed
  level (`test_simple_flow`, `test_enquiry_lifecycle`); picture values start unticked (`test_review_groups`); the
  showcase is "Quoted" after export, because the letter's medium values now agree with the specification and go
  with "Accept all" (`test_web_flow`).

## 5. Known limits

- The gate trades recall for precision: a real conflict that only model or picture readings see is not a
  conflict card; its values are still checked one by one (low, with the other reading named), never bulk-accepted.
- The rule was chosen from the Stage 5 description of the reworded false flags (model misreadings), before any
  gated number was run, and no threshold was tuned; but the reworded set was looked at, so the fair number comes
  from the fresh Stage 7 set.
- Levels are worked out on every screen; with hundreds of values this is a few milliseconds, not measured on
  very large enquiries.

## 6. Design choices

- The agreeing-values card stays first on Review (the stage-simple flow); "ordered by risk" applies to the
  rest of the queue.
- "Agreeing" is read as "no file says otherwise", not "confirmed by two files"; agreement raises the level.
- A rules value with medium confidence that another file confirms becomes high and may be bulk-accepted.
- Model and picture values start unticked; rules values with lower confidence stay ticked on their card.
- No migration: levels are not stored (migration 0007 is kept for the question box).

## 7. End of stage: full suite and strict numbers

- Full suite in two halves (laptop, Docker Postgres, at least 800 MB free before each half): database tests
  5 passed; the rest 961 passed in 5 min 50 s. The 961 include 31 tests already written for Stages 7 to 9 in the
  working folder (not part of this branch's commits).
- Strict v2 numbers (`python -m backend.evaluate --set test|reworded --mode llm`) reproduce exactly: 0.778 and 0.561
  on the test set (with and without the DXF), 0.727 and 0.497 on the reworded set.
- Step 0 (box-by-box ACB and MCCB check) is its own commit; its findings are in
  [stage-4.md, section 12](stage-4.md#12-acb-and-mccb-confusion-box-by-box-stage-6-step-0-13-nov-2026).
