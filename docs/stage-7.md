# Stage 7: evaluation on a fresh, held-out set

Branch `stage-7`, from `stage-6`. Built in an unattended run on 13 Nov 2026.

## 1. What was built

- **Fresh set**: 20 projects F01 to F20 from new seeds 3001 to 3020, the same generator plan as the test set,
  every even project reworded. Built once on the laptop; the SHA-256 of every file (180 files) is frozen in
  `data/projects/fresh/FROZEN.sha256` (set hash `c1488dbdeec22ed5...`). `python -m data_generator build --set
  fresh` and the report both refuse a set that differs. Nothing was tuned on it: no rule, threshold or
  normaliser alias changed after it was built.
- `python -m backend.evaluation_report --set fresh`, then `--set test`: one command per set for every method.
  - Rows: rules with and without the DXF, rules plus OCR on each drawing version, and rules plus the model (from
    recordings).
  - Also: the symbol detector per version, confidence calibration, cross-checks with the Stage 6 gate, and an
    error analysis with examples.
  - Output: `docs/evaluation.md`, the fresh set labelled "not used for tuning" and the test set beside it labelled
    "not held out". A row without matching recordings says "waiting for Colab recordings".
- **Nothing is lost when a run stops**: each project of each row is saved as it finishes in
  `data/eval-<set>-partial.json` (git-ignored, written atomically); a new run skips what is saved. Each drawing is
  read by OCR once per run (calibration and cross-checks use the same reading). Before each project the free memory
  is checked; under 800 MB the run waits five minutes. A first, unsaved run was lost to a low-memory stop; after this change the baseline
  run was stopped once the same way and resumed from its saved rows (17 of 20 projects of a row kept).

## 2. Results

Laptop, 13 Nov 2026. Full tables, per field group and the error analysis: [evaluation.md](evaluation.md).

**Field values, F1 (P, R)**

| Reading | Fresh, all 20 (not used for tuning) | Fresh, 10 plain | Fresh, 10 reworded | Test set (not held out) |
|---|---|---|---|---|
| Rules, DXF | **0.758** (0.971, 0.621) | 1.000 | 0.351 | 1.000 (1.000, 1.000) |
| Rules, no drawing | **0.405** (1.000, 0.254) | 0.656 | 0.013 | 0.654 (1.000, 0.486) |
| Rules + OCR, clean | **0.674** (0.993, 0.510) | 0.940 | 0.196 | 0.948 (0.996, 0.903) |
| Rules + OCR, scanned | **0.663** (0.989, 0.499) | 0.925 | 0.198 | 0.934 (0.994, 0.880) |
| Rules + OCR, photo | **0.493** (0.978, 0.329) | 0.752 | 0.063 | 0.814 (0.975, 0.699) |
| Rules + model | waiting for Colab recordings | | | 0.944 with DXF, 0.643 without (rules + strict v2 model; the model alone: 0.778, 0.561) |

- **On plain wording the held-out numbers match the test set** (rules with the DXF 1.000 on both; OCR clean 0.940
  against 0.948, scanned 0.925 against 0.934, photo 0.752 against 0.814): the rules and the OCR linker carry over
  to new seeds.
- **On reworded documents the rules fail**: F1 0.351 with the DXF and 0.013 without, because the reworded
  specification's way tables and clauses are not read (most misses are way ratings, poles, devices and breaking
  capacities on the specification's way-table page). This is the gap the model is for; its fresh numbers wait for
  Colab (`docs/colab-all.md`, Cell 6).
- Precision stays high everywhere (0.97 to 1.00): the rules miss values far more than they misread them. The 52
  wrong rules values with the DXF are way descriptions read from the DXF where the key names the load ("M.C.C.B.
  160 A 3-POLE Icu=36kA" against "Sprinkler pump").

**Symbol detector (template; breaker classes; IoU at least 0.5)**

| Version | Fresh P / R / F1 | ACB found | s per sheet | Test set F1 |
|---|---|---|---|---|
| clean | 0.887 / 0.887 / 0.887 | 0 of 20 | 8.9 | 0.896 |
| scanned | 0.892 / 0.892 / 0.892 | 0 of 20 | 8.5 | 0.909 |
| photo | 0.910 / 0.866 / 0.887 | 3 of 20 | 3.2 | 0.872 |

The detector holds its Stage 4 level on new seeds; the ACB is still almost never found (see stage-4.md section 12).

**Calibration and cross-checks (fresh)**

- Rules with the DXF: high values right 1678 of 1678; "conflict" values 73 of 125 (0.584; a conflict means the files
  disagree, not that a value is wrong).
- Rules + OCR on the scanned drawing: high 686 of 686, medium 688 of 689 (0.999), low 9 of 13 (0.692).
- Cross-checks with the gate: planted conflicts found 8 of 10, 1 false flag; planted missing values listed 5 of 5
  (test set: 10 of 10, 1 false flag, 4 of 5).

## 3. How to run it

```powershell
.venv\Scripts\python.exe -m data_generator build --set fresh           # once; checks FROZEN.sha256 afterwards
.venv\Scripts\python.exe -m backend.evaluation_report --set fresh      # about 25 min of reading; resumes if stopped
.venv\Scripts\python.exe -m backend.evaluation_report --set test       # the baseline, added beside it
.venv\Scripts\python.exe -m backend.evaluation_report --write-only     # rewrite docs/evaluation.md from saved rows
```

## 4. Tests

`tests/unit/test_evaluation_report.py` (7): wrong and missed values by the scorer's rule; the error table; cells
never invent a number; the per-field table; the saved file is read back by a new run and never by another set;
under the memory floor the run waits and never stops; a section is written only when every row is saved.
`tests/unit/test_data_sets.py`: fresh seeds and the frozen manifest.

## 5. Known limits

- Rules + model on the fresh set is not run (no Colab session in this run).
- The fresh set comes from the same generator as the test set: it is held out from tuning, not from the generator's
  style. Real drawings remain untested (data/external is empty).
- The plain/reworded split above was worked out from the saved rows (odd projects plain, even reworded), not by the
  report command.
- GitHub Actions already runs the tests on every push (Stage 0); the evaluation itself is too slow for CI and is
  run by hand.
