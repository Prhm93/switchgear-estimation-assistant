# Stage simple: a four-button path from files to quote

Branch `stage-simple`, from main `bea7554`. Built in an unattended run on 12 Nov 2026. Existing pages and code
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

## Choices made without the owner (one line each)

- One card per field, not per stored value: Approve keeps the shown value for every source that agrees (`services.resolve_field`), and each change is still its own review and audit entry.
- On a disagreement, Approve keeps the first file's value and sets the other aside with a reason; Change types the right one.
- The theme switch stays in the top bar (an earlier owner decision); it is not counted as a flow button.
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
