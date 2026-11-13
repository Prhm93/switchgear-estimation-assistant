# Interview issues

Known weak points to discuss openly, each with what was measured and what is not known yet.

1. **The symbol detector almost never finds an ACB, because it reads ACBs as MCCBs.** The template detector
   (Stage 4 Part C) finds 0 to 3 of the 20 ACBs per drawing version on the test set. Checked box by box (Stage 6
   Step 0): every ACB it misses is given the MCCB class, either as a well-overlapping MCCB box or as a smaller MCCB
   box inside the ACB, and those inner boxes are exactly the MCCB false positives. The cause is the drawing: an ACB
   is the MCCB symbol between draw-out chevrons, so the MCCB template matches its inner part. Nothing was tuned on
   the test sets. Next step: a chevron check or a trained detector (torchvision, from scratch). See
   [stage-4.md, section 12](stage-4.md#12-acb-and-mccb-confusion-box-by-box-stage-6-step-0-13-nov-2026).
2. **182 false flags on the reworded set, cut to 47 by confidence, at a cost.** Cross-checks with model values
   (combined mode) on the reworded set found 6 of 10 planted conflicts with 182 false flags (P 0.032). The Stage 6
   gate (a difference needs a value read reliably on one side) leaves 47 false flags but finds 4 of 10 (P 0.078):
   two real conflicts were seen only by model readings and are now checked value by value instead. The 47 left are
   device spellings, enclosure sizes and ways the model missed. See [stage-6.md](stage-6.md#3-results).
3. **The model's values are almost never right where the rules already read the text.** On the test set, the 192
   medium-confidence model values in combined mode are all wrong by the scorer, while on the reworded set medium
   values are right 68 % of the time. Confidence ranks well on the reworded set (high 0.985, medium 0.680,
   low 0.507), but the share right at one level depends on the wording, so a level is advice, not a probability.
