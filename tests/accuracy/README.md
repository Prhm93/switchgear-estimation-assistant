# Accuracy tests

Accuracy tests score extraction against the true values in the synthetic test
projects (`answers.json`). `test_rules_accuracy.py` builds two test projects on
the fly (T01 and T08) and checks the rules-mode extractor on them, so CI runs a
small subset only.

The full baseline on all 20 test projects:

```powershell
.venv\Scripts\python.exe -m data_generator build --set test
.venv\Scripts\python.exe -m backend.evaluate
```

The scoring rules (what counts as correct, duplicates, values on several
pages) are in `backend/app/evaluation.py` and docs/stage-2.md.
