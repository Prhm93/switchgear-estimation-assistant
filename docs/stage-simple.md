# Stage simple: a four-button path from files to quote

Branch `stage-simple`, from main `bea7554`. Built on 12 Nov 2026. Existing pages and code
are reused; nothing was deleted, and no library was added.

## What was built

- **Home:** one big **Add files** button. Choosing files sends them at once (`upload.js`, `data-autosubmit`)
  with `next=review`, and the enquiry opens on **Review**.
- **Review** (`/enquiries/<id>/review`): "Reading your files" while files are read (it asks again every second),
  then a progress line ("12 of 71 checked") and one card at a time. Each card shows the value, where it was read,
  the proof (the drawing around its box, or the page text with the words marked), and **Approve** or **Change**.
  Cards where the files disagree come first and name both files.
- **Make quote** appears when every card is checked. It builds the quote (cost rules unchanged: approved values
  only) and opens the short quote (`/enquiries/<id>/draft-quote`): Part, Description, Qty, Line total, and the
  draft total. **Show workings** is a small link to the full Quote page.
- **Ask** is shown on Review and on the short quote, switched off, with "Coming soon".
- **More:** one small link in the top bar of every page. It holds Review, Summary, All values, Parts list, Quote
  with workings, Report, Files, Proof viewer, Activity, Enquiries, New enquiry and Try the sample enquiry.
- **Boxes:** thin outlines (2 px, about 15% fill, never opaque), coloured by how the value was read, with a
  one-line key: "Read by rules", "Read from a picture, needs review", "Symbol found", then "Boxes show where each
  value was read." Symbol boxes carry their device and score, for example "MCCB 0.82".

## Measured

- The showcase files (specification, letter and DXF): 71 cards, all with a value to approve. That is 73 clicks
  from upload to quote (Add files, 71 Approve, Make quote), plus choosing the files in the file dialog. The draft
  total was GBP 20,978.75 over 17 lines.

## Tests

`tests/integration/test_simple_flow.py` (8 tests): one button on the home page, upload opens Review, at most four
visible buttons, Approve and Change, the planted disagreement first and named, all checked leads to the short
quote, and "Reading your files" while files are read. `tests/integration/test_proof_boxes.py` was changed on
purpose (box kinds, legend, symbol labels, thin see-through outlines), and so was the home hero test.

## Design choices (one line each)

- One card per field, not per stored value: Approve keeps the shown value for every source that agrees (`services.resolve_field`), and each change is still its own review and audit entry.
- On a disagreement, Approve keeps the first file's value and sets the other aside with a reason; Change types the right one.
- The theme switch stays in the top bar (an earlier design decision); it is not counted as a flow button.
- Without script, the home page's Add files cannot send the files; the New enquiry page (behind More) still works without script.
- Old screens keep their own tabs and Details menu; they are reached through More.
- "Accept all" stays on the Check page, behind More, so the short path has no bulk approval.
- Line total = the part's materials plus its labour hours at the quote's rate, before the margin (shown only, not stored).
- Box colours: rules light blue, picture amber, symbol green; the green does not mean approved, and the key says so in words.
- "Value" is explained on Review with the Check page's existing line; one short line explains "To check".
- No stock column is shown: the stock list was never committed.

## Known limits

- 71 cards for the showcase is a lot of clicks; a reviewed bulk approval is a Stage 6 question.
- The drawing crop renders the whole sheet picture once per card (cached for five minutes).
- No screenshots were taken in this run.

## End of stage

- Full suite in two halves (laptop, Docker Postgres, at least 800 MB free): database tests 5 passed; the rest
  892 passed. The first run of the rest had one failure (a duplicate line under the Check views); it was fixed,
  and the rerun passed.
- Strict numbers were not rerun: this stage changes only screens.

## Fix: groups on Review (10 clicks or fewer)

- **Order:** one card "N agreeing values" with "Approve these N" (the existing "Accept all" rule: high
  confidence, no conflict, exact quote, not read from a picture); then one card per real conflict (Approve or
  Change); then one card per file and page for every other value (read from a picture, by a model with a pieced
  quote, or with lower confidence), each value listed with its box or its marked text and ticked by default,
  and one button "Approve N ticked". The progress line counts groups: "2 of 6 groups checked".
- **Safety kept:** nothing is approved without a click (opening Review changes nothing); each value is approved
  on its own, with its own review row, approved status and audit entry; the server approves only ids that are on
  that card and still waiting, so the count shown is the count approved; an un-ticked value is "left for later"
  (one audit entry), stays unapproved and is never priced.
- **Measured (showcase: specification, letter, DXF):** 3 groups: 130 agreeing values, 1 conflict (way Q2 rating),
  7 values on one page. 5 clicks from upload to quote (Add files, Approve these 130, Approve, Approve 7 ticked,
  Make quote), down from 73. Same draft total as before: GBP 20,978.75.
- **Tests:** `tests/integration/test_simple_flow.py` (rewritten for groups) and the new
  `tests/integration/test_review_groups.py` (one card per sheet, all ticked with boxes, un-tick leaves a value for
  later, ids outside the card never approved, one file and page per group).

Design choices (one line each):
- Groups are worked out from what each value is, not its status, so the group count does not shrink as you go.
- "Left for later" is stored as an audit entry (`review_later`), so no database change was needed.
- Lower-confidence values read by rules from text also go into the file-and-page cards, since "Approve these N" must not take them.
- The agreeing card lists its values behind a small "Show the N values" link, not one by one.
- The ticked count updates with a few lines of our own script (`review.js`); without script the form still sends exactly the ticked values.
- Full suite after the fix: database tests 5 passed; the rest 896 passed.

## Fix: plain top bar, pinned sketch, file list before reading, agreeing values one tick each

- **Top bar:** How it works, Safety, Measured and Enquiries as plain links on every page, the theme switch kept,
  and one "Menu" in their place under 700 px. The More dropdown is removed.
- **Home sketch:** on wide screens with motion allowed, the hero is about two screens tall and the drawing sits
  near the top, pinned (`position: sticky`) for one screen of scrolling; the scroll through that part opens it
  and closes it again (a half sine of the progress), so it never ends open and out of view. Reduced motion and
  narrow screens: the still drawing, as before. The contour background and its guards are unchanged.
- **Upload:** choosing or dropping files lists them (each with Remove); "Add files" becomes "Add more", and
  reading starts only on "Read these files".
- **Agreeing values:** the line "Approve means: I checked this against the file and it is right. Only approved
  values are used in the quote."; one tick per value (all ticked); "Yes, these are right (N ticked)" with a live
  count; "Check one by one" shows single cards with Approve and Change; a Change link per value stores the
  engineer's value as approved ("changed by engineer"), keeps the value read, and writes its own audit entry; an
  un-ticked value stays to check, is never priced, and is counted in "N approved, N changed, N still to check".
- **Measured (showcase):** 6 clicks from upload to quote (Add files, Read these files, Yes these are right (130
  ticked), Approve on the conflict, Approve 7 ticked, Make quote), plus choosing the files. Same draft total.

Design choices (one line each):
- The nav links point to the home page sections (`/#how`, `/#safety`, `/#accuracy`) from every page.
- An enquiry's other screens (Summary, tabs, Activity, proof viewer) are one plain link, "All details of this enquiry", on Review and the short quote.
- "Try the sample enquiry" moved to a quiet line after the numbers on the home page, so the hero keeps one button.
- "Read these files" is in the page but hidden until files are chosen; without script, the page points to the full upload page.
- Change on one agreeing value changes that value only; if the engineer then approves a sibling with the old value, Check shows the disagreement.
- An un-ticked agreeing value is left for later the same way as on picture cards (a `review_later` audit entry).
- "Check one by one" is a link (`?one=1`), not a stored setting.
- Full suite after these fixes: database tests 5 passed; the rest 904 passed.

## Fix: proof viewer boxes, enlarged crop and two-way highlight

- **Boxes:** 1 px outlines, filled at most 6 percent, drawn a little larger than the text on every side, on the
  drawing, in the enlarged crop and on Review cards; symbol boxes the same. No box has an opaque fill.
- **Enlarged crop:** selecting a box shows it about three times larger beside the drawing (below it on narrow
  screens), turned upright when its text is vertical, with the value read under it.
- **Two-way highlight:** a box (click, or Enter on a focused box) marks its card in "Read on this sheet" with an
  outline and scrolls it into view; "Show on the drawing" on a card pulses its box and marks its line in the text
  panel. One box, one card and one text line are active at a time (`frontend/static/js/proof.js`). Without
  script, the links still jump between box and card. The legend and "Boxes show where each value was read." stay.
- **Tests:** `tests/integration/test_proof_boxes.py` (padding, focusable boxes, crop panel, 1 px and 6 percent
  limits on every box rule) and the new `tests/unit/test_proof_js.py` (runs `proof.js` in Node on a small fake
  page: box to card, card to box and text line, one active at a time, Enter, crop size and turn; skipped without
  Node).

Design choices (one line each):
- Padding is a share of the sheet width (`web.BOX_PAD`, 1/150), about 4 px when a sheet fills a column about 600 px wide; it is not measured in the browser.
- Text counts as vertical when its box is more than 1.5 times taller than wide; it is turned a quarter clockwise (text that reads bottom to top).
- The crop shows the padded box plus one more padding of drawing around it; its width is three times that region on screen, never wider than the column.
- Space also selects a focused box, like Enter.
- The text line is marked on every selection (from a box or a card); only the card or the box is scrolled into view, not the text.
- The JavaScript test uses Node, already on the laptop, with a hand-made fake page instead of a browser library.
- Full suite after this fix: database tests 5 passed; the rest 910 passed.
