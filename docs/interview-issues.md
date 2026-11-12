# Interview issues

Known weak points to discuss openly, each with what was measured and what is not known yet.

1. **The symbol detector almost never finds an ACB.** The template detector (Stage 4 Part C) finds 0 to 3 of the
   20 ACBs per drawing version on both test sets. In every run, the number of MCCB false positives is close to the
   number of missed ACBs, so the ACBs are probably detected as MCCBs. This is **not verified** box by box. Nothing
   was tuned after seeing the test scores. Next step: a trained detector (torchvision, from scratch) through the
   same interface. See [stage-4.md, section 9](stage-4.md#9-part-c-symbol-detector-template-matching).
2. **182 false flags on the reworded set.** Cross-checks with model values (combined mode) on the reworded set
   find 6 of 10 planted conflicts, with 182 false flags (P 0.032). The causes are drawing values the model misreads
   and device spellings the normaliser does not know. No alias was added from the reworded set, because that
   would be tuning on it. A Stage 6 confidence rule is the planned fix. See [stage-5.md, section 3](stage-5.md#3-results-laptop-12-nov-2026-with-the-dxf).
