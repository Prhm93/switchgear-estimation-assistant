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
4. **ACB read as MCCB, again on the fresh set.** The template detector finds 0 of 20 ACBs on the clean and scanned
   fresh drawings and 3 of 20 on photos (test set: the same pattern, item 1). The vision model does not fix it: it
   is asked only for the outgoing ways, never sees the incomer as its own item, and in 18 answers labels a way
   "ACB". Next step as item 1 (chevron check or a trained detector), then an incomer field in the vision schema.
5. **Two real conflicts lost by the Stage 6 gate.** On the reworded set the gate cut false flags from 182 to 47
   but found 4 of 10 planted conflicts instead of 6: both lost conflicts were seen only in model readings, which the
   gate does not trust on their own. On the fresh set it lost none (combined mode: 9 of 10 with and without the
   gate; false flags 67 to 23). Trade-off kept on purpose: an engineer still sees each value, but the conflict
   banner is quieter.
6. **The vision model pads empty ways.** On the fresh set about 160 of the about 290 ways it lists per drawing
   version have nothing read (no device, rating, poles or breaking capacity), usually labels past the last real
   way. They add no values (code drops empty fields and counts ways itself), but they make replies long.
7. **10 of 120 vision sheets cut off.** The reply stopped mid-JSON (Ollama's default context was too small for the
   picture plus a padded answer), so those sheets have no recording and are reported as "not read". Fixed in code:
   the reader keeps every complete way of a cut-off reply (as Stage 3b does for text) and asks for more room
   (`num_ctx` 8192, `num_predict` 4096). Re-recording the 10 sheets: `docs/colab-vision-retry.md` (not run yet).
8. **mxbai ranks better but refuses more.** Question box on the fresh set: the right passage first 0.708 with
   mxbai-embed-large against 0.593 with the word embedder, but 29 refusals against 15. 20 of mxbai's refusals are
   right (the best passage did not hold the answer); 9 are wrong and score 0.481 to 0.488, just under the hand-set
   0.5 threshold, 7 on the incomer rating. Not tuned on the fresh set; a threshold would be chosen on the test set.
9. **reportlab missing on Colab.** The evaluation imports the data generator, which needs reportlab, and that is in
   `requirements-data.txt`, not `requirements.txt`. The Colab install step now installs reportlab, ezdxf,
   python-docx, pypdfium2 and pdfplumber explicitly (`docs/colab-all.md`, Cell 4).
10. **Colab session recycled after idle.** A long wait between cells lost the runtime and `/content`. The recordings
   survived because they were written to Google Drive and the recorders resume (`--resume`, skip what exists).
11. **Ollama server stopped between cells.** Calls then fail with "connection refused"; the cell list now says to
   start `ollama serve` again before the next cell. The vision recorder lists the sheets that failed and carries on with the rest.
