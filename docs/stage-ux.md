# Stage UX: a first-time user gets a checked quote without explanation

Branch `stage-ux`, from main `8a912c1` (Stage 4 Part A). Three parts on one branch, each tested and
committed locally before the next: UX-1 (the flow and the clean-up), UX-2 (stock and the report),
UX-3 (the Ask panel). Stage 4 Parts B to D wait until this is merged.

The starting point was a UI audit with 34 problems (kept outside the repo, with before screenshots):
stale "OCR arrives in Stage 4" notes, test projects mixed with real ones, machine field names and rule ids on
screen, a Review page of 4,600 words with 278 hidden forms, an audit log without paging, no delete, archive,
rename or read again, and design samples in the main navigation.

## UX-1: the flow

### What changed for the user

- **One word, "Enquiry".** Addresses are `/enquiries/...`. Every old `/projects/...` address answers
  with a permanent redirect (308) to its new place (upload to Files, analysis to the proof viewer,
  review to Check, estimate to Quote, audit to Activity). The database table is still `projects`.
- **Top bar only:** "Enquiries" and "+ New enquiry". No sidebar. "System status" is a footer link.
  The design samples moved to `/health/design` (developers only; 404 in production).
- **Inside an enquiry:** three tabs, `1 Files · 2 Check · 3 Quote`, a header line that says honestly
  how the files were read ("Read with rules + OCR + gemma4:e2b (recorded 7 Nov 2026)"), and a Details
  menu with the proof viewer (the old Analysis page), Activity (the old audit log), Rename, Archive and
  Delete. The fixed "Rules ● live" box is gone.
- **Enquiries list:** one row per enquiry with a status pill ("Needs you (N)", "Ready to quote",
  "Quoted"), the quote total, when it was last updated and a menu. Archived enquiries are listed apart.
  When the list is empty it shows a drop zone and "Try the sample enquiry".
- **New enquiry is one screen:** the name is optional (taken from the specification's title when left
  empty); the files go in the same step. The page says what happens to a drawing before the upload
  (read by OCR, 3 to 5 s per sheet, or not read when drawing reading is off). Plain progress lines
  follow each file, and when reading ends the page moves on to Check by itself.
- **Check** opens with one summary sentence, then:
  - **Needs your decision:** conflicts side by side ("Use this" on either side, or type another
    value), then groups of values left for the engineer with the reason in words (read from a drawing
    picture, quote pieced together, left open in a document, way not in every document, medium or
    low confidence). Each group's forms load only when it is opened.
  - **Accept all** approves only high-confidence, non-conflict, exact-quote, non-OCR values. It shows
    the count first, asks once, and writes one audit entry per value with the actor, plus one summary
    entry.
  - **Items the customer wants:** the quote lines as they will be, with a value not yet approved
    clearly marked "Not yet approved". It never reaches the quote that way.
  - **Show all values:** collapsed; loaded on demand, 50 rows a page, with filters.
  - A side panel shows the proof of any value: the words around it on the page with the quote
    marked, or the drawing with a red box around an OCR value. Rule ids, hashes and field names are
    shown only there, under "Technical details", and in Activity under "Details".
- **Quote** rebuilds itself after every approve, edit or reject (and after a file is deleted). It shows
  the total large, says what each blocked line waits for with a link to its card, says when it is out of
  date, and exports DOCX (rebuilt first if out of date).
- **Delete, archive and rename** for an enquiry, **delete** and **read again** for a file. Each one
  that removes or replaces something has a confirmation step that says what will go, and each is in
  Activity. Deleting an enquiry keeps its past activity lines (no longer tied to it) and one "delete"
  entry with what was removed.
- **Activity:** plain sentences ("Approved Way Q8 rating 125 A"), 50 a page, filter by decisions, files,
  quote and report, questions, enquiry.
- **Plain labels everywhere:** "System voltage", "Way Q2 rating", "Specification, page 5", "Drawing,
  sheet 1", "Customer letter", device words (MCCB, ACB). Stale notes such as "OCR arrives in Stage 4"
  are gone; a drawing that was not read says why.
- **Look:** the same navy, red and blue, calmer: fewer cards, more space, about a third of the text.
  IBM Plex Sans everywhere, Plex Mono only for numbers, codes and document text, Instrument Serif only on
  the home page (a design-rule test enforces both). *Reversed in UX-V: there is no serif any more.*
- **Home page:** every number is a measured result from docs/stage-3.md and docs/stage-4.md. The strict
  quote check numbers are labelled as the fixed baseline and as not held out (these sets were used during
  development; fair scores come from a fresh set in Stage 7). The relaxed-check number is labelled "tuned
  on this set", and the OCR card says the linker was tuned on 3 of the test drawings. The
  "[PLACEHOLDER]" marks are gone.

### The sample enquiry

"Try the sample enquiry" (home page, empty Enquiries list) makes a new enquiry from the committed
showcase files: specification, customer letter, DXF and drawing PDF. It is read in combined mode with
the relaxed quote check. A saved gemma4:e2b run is used for a file only when its SHA-256 equals that
file's bytes; any other file is read by the rules (and the drawing PDF by OCR), and the header line
says exactly which were used. Only the sample uses recordings: a normal upload follows `MODEL_MODE`.
The recordings are not in the repo (data/recorded/README.md), so on a machine without them the sample
is read by rules and OCR and says so.

### Tests and test isolation

Database tests used to run on the app's own database, which is how ten "Showcase / ENQ-TEST" projects
ended up in the running app. Now:

- `tests/isolation.py` gives the database tests their own database on the same server, named after the
  app's with `_test` added (or `TEST_DATABASE_URL`). It is created, migrated, and emptied after every
  test. Every write helper refuses a database whose name does not end in `_test`, and a URL equal to the
  app's is refused.
- `tests/integration/test_isolation_db.py` proves it: the app database's row counts are read before and
  after a full enquiry flow on the test database, and must be equal.

New tests: `test_enquiry_lifecycle.py` (rename, archive and delete with confirmation and audit; delete
and read again for a file; Check renders few forms; no machine names on normal screens; Accept all
shows its count, needs the confirmation, approves exactly the allowed values with one audit entry
each; the quote rebuilds after a decision; the sample uses a recording only on a SHA-256 match and
says so; the empty list offers the sample), `test_labels.py`, `test_isolation.py`, migration 0005 is
additive and keeps every row. The older web, OCR, recorded and relaxed-check tests were moved to the
new addresses; what they check is unchanged.

Migration `0005_enquiry_lifecycle` only adds columns: `projects.updated_at` (filled from `created_at`),
`projects.archived_at`, `projects.is_sample`, `documents.read_method`.

### Results (run on this laptop)

- **Tests:** database tests 5 passed (on `sea_test`, including the proof that the app database is
  untouched); all other tests 605 passed. Run in two halves with at least 800 MB free.
- **Frozen numbers unchanged:** `python -m backend.evaluate --mode llm`, strict v2 column, on both sets:

  | Set | Expected | Measured |
  |---|---|---|
  | Test, with DXF | 0.778 | 0.778 (P 0.856, R 0.713) |
  | Test, without DXF | 0.561 | 0.561 (P 0.940, R 0.400) |
  | Reworded, with DXF | 0.727 | 0.727 (P 0.858, R 0.631) |
  | Reworded, without DXF | 0.497 | 0.497 (P 0.903, R 0.343) |

- **Sample enquiry in Docker** (app container capped at 384 MiB): created and read in 14.3 s; the
  specification, letter and DXF with rules and the recorded gemma4:e2b run (SHA-256 matched), the drawing
  PDF by OCR at 300 dpi. Container memory: 73.5 MiB idle, highest sample 281.9 MiB (docker stats about
  every 1.5 s, so a short peak can be missed). Not killed, no restart; the limit stays at 384 MiB and
  OCR_DPI stays at 300.
- **Check page of the sample:** 23 items, 193 values, 54 decisions (one of them accepting the 118 agreeing
  values).
- **Screenshots** (headless Edge, 1280 px and 518 px): 17 after screens, kept with the audit outside the
  repo, next to the before screens.

The Docker image now holds the four sample files (specification, letter, DXF, drawing PDF), so "Try the
sample enquiry" works in the container. The recordings stay outside the image, mounted read only.

### Limits

- The sample enquiry shows duplicate "Approved" lines in Activity where the rules and the model read the
  same value: each is a separate stored value and each approval is logged.
- Screens were checked with headless Edge at 1280 px and at Edge's narrowest window (518 px); a real
  390 px phone was not tested.

## UX-V: the technical-drawing style

Parts 1 to 3 were committed as a checkpoint, part 4 (the hero shader) in its own commit. The visual pass
below replaces most of this look; what it keeps is listed there.

### Decision reversed: no serif

UX-1 kept Instrument Serif for the home page. The UX-V style names IBM Plex Sans and IBM Plex
Mono only, so the serif is gone everywhere: its two woff2 files, `OFL-InstrumentSerif.txt`, its
`@font-face` rules, the `--font-serif` token, the home page preload and its row in the README licences
table. The design-rule test that kept the serif on the home page now checks that there is none.

### Part 1: the view bar on Check, and two fixes

- Under the tabs, a row of buttons: **Decisions N**, **Items N**, **Report**. The counts are read from
  the database on every request (Decisions is the number on the Check tab; Items is the number of
  items worked out from the files). The bar is built from one list, `web.VIEWS`; adding Ask or Stock in
  UX-2 and UX-3 is one line there plus one template, `partials/views/<key>.html`.
- The open view is highlighted and kept in the address, `/enquiries/{id}/check?view=items`, so Back and
  links work; with script a button swaps only the Check block and pushes the address. An unknown view
  falls back to Decisions, the default.
- The summary sentence and the "Needs your decision" heading are gone. "Accept all" is now a small link
  at the top of Decisions; its confirmation step is unchanged.
- **Items** (before UX-2): what the customer asks for, one row per item with quantity, how many
  documents state it and whether it is approved. **Report**: what the Word report holds, the "Read
  with ..." line, how many values are decided, the limits and the Export button. Neither shows a price,
  a total or the blocked lines: those stay on the Quote tab only, so nothing is said twice.
- Fix: a drawing source says which drawing: "Drawing (CAD), sheet 1" for the DXF, "Drawing (picture),
  sheet 1" for a drawing PDF or image. On a conflict card only true duplicates are merged (the same
  file and page with the same value, for example the rules and the model reading one line); the CAD
  file and a picture of the drawing stay separate, also when they agree.
- Fix: Export is disabled, with "Approve at least one value to export.", while nothing is approved, on
  Quote and on Report; the export address refuses with 409.
- Reported, not fixed: "ACB" and "one air circuit breaker" count as two different values, so the sample
  shows a conflict on Incomer device. This is a normalisation question for Stage 5; `normalise.py` is
  frozen.

### Part 2: the style on every page

- Same navy, red and blue tokens. Small labels and block titles are uppercase IBM Plex Mono; headings
  stay in Plex Sans. One red word in a headline (New *enquiry*, System *status*, Page not *found*); red
  on navy is 3.83:1, which passes AA for large text only, so the accent is used in headlines only and is
  checked at the large-text level.
- Fewer boxes: a decision is no longer a glass card but open space with a hairline above and "+"
  crosshair marks in its corners (`.xmarks`, an SVG in four background positions).
- Every app page has a faint drawing in the corner above the footer: an original single-line diagram
  with a title block "DRAWING NO. SEA/MSB-2 · SCALE 1:2" (decoration, hidden from screen readers and
  below 900 px).

### Part 3: the home page

- One headline with one red word, one button "Start an enquiry" (to the New enquiry page) and one link
  "Try the sample enquiry". The tilted cards, the app preview and the call-to-action panel are gone.
  Behind the hero, static contour lines in navy and blue with one red hairline (the shader of part 4
  will draw over them).
- A statement whose words brighten one by one as it scrolls into view. The full text is in the HTML
  and every word is readable before the reveal (the dim colour passes AA), so only its brightness moves.
- "How it works": three steps beside an original isometric line drawing of a four-section switchboard
  that draws itself with the scroll (`stroke-dashoffset`), labelled INCOMER, OUTGOING WAYS and FORM 4a.
- The measured numbers with the UX-1 labels word for word, and the intro line now reads "20 reworded
  copies, written to test the reading rules on new wording." Then trust and safety, and the footer.
- Motion is hand-written: `frontend/static/js/home.js` (IntersectionObserver plus one
  requestAnimationFrame per scroll), no library, no file from another site. Without script, or with
  reduced motion, everything is shown at once.

### Design-rule and contrast tests changed on purpose

| Test | Before | Now |
|---|---|---|
| Gradients | four rules: `.upload-box`, `.glow`, `.sheen`, `.cta-panel` | one: `.upload-box` (the other three and their tokens are removed) |
| 3D | tilt only in the home hero at 1100 px and wider | no 3D transforms anywhere |
| Serif | the serif on the home page only | no serif anywhere, no serif files |
| Mono | never for labels | also for small uppercase labels (`.label-mono`, `.block-title`); never for headings |
| New | | the "+" marks are SVG in four corners; every app page has the corner drawing |
| Contrast pairs | home glow, sheen, call-to-action, preview and paper pairs | removed with their parts; added: the red accent word (large text), the dim statement words, the view buttons and their counts, the mono labels, the home step numbers |

### Tests

New: `tests/integration/test_enquiry_views.py` (the bar, its live counts, the address of each view, no
prices in Items and Report, Export disabled and refused), `tests/unit/test_sources.py` (true duplicates
merged, CAD and picture kept apart and labelled), `tests/integration/test_home_page.py` (one headline,
one button, one link, the statement in the HTML, three steps and the labelled drawing, the UX-1 number
labels, own scripts only and no animation library, reduced motion). Results below come from the
checkpoint run.

### Part 4: the hero shader

`frontend/static/js/hero-shader.js`, 134 lines of hand-written WebGL: drifting contour lines, blue with
one red level, at half resolution with the device pixel ratio capped at 1.5. No frames while the tab is
hidden or the hero is off screen; with reduced motion, without WebGL or if the shader fails to compile,
the static line art stays. Tests: `tests/integration/test_hero_shader.py`.

### Results (run on this laptop)

After the checkpoint: database tests 5 passed, the rest 627 passed. The strict v2 numbers reproduce
exactly: 0.778 and 0.561 on the test set (with and without the CAD file), 0.727 and 0.497 on the
reworded set. One home screenshot with the shader was taken in headless Edge with a software renderer;
the rest were not, because the visual pass below replaced the look first.

## Visual pass (V1 to V4)

The design prototype is a visual reference only: no code, sample numbers or replies are
copied from it, and nothing from its vendor folder (React 16.0.0 and ReactDOM 16.0.1, MIT, with a
Modernizr 3.0.0pre piece, MIT). Kept from UX-V: the view logic (`?view=`, swapped in place, Back works),
the "Drawing (CAD)" and "Drawing (picture)" source labels with only true duplicates merged, the Export
rule (disabled, and refused with 409, while nothing is approved), no serif, and the tests' intent.
Replaced: the view bar (by six tiles, V4), the "+" marks and the corner single-line drawing (gone in V1),
the isometric switchboard and the static contour art (by the breaker drawing, V2 and V3).

### V1: tokens, two themes, fonts

- `frontend/static/css/tokens.css` holds the fonts, the colour tokens of the **dark** theme (the default,
  unchanged values) and a new **light** theme (the same navy, red and blue on near-white paper), and the
  type, spacing, shape and motion tokens. `app.css` uses tokens only; its two last literal colours (the
  missing segment and its legend) became tokens.
- The theme is `data-theme` on `<html>`. A one-line script in `base.html` applies the stored choice before
  the page paints; `static/js/theme.js` shows a sun or moon switch in the top bar of every page, flips the
  theme and stores it in `localStorage`. Every storage call is inside `try`/`catch`; without storage or
  script the page is dark and works.
- Contrast: every pair in `backend/app/design/contrast.py` is now checked in both themes (86 pairs, 172
  checks), and every solid twin is recomputed per theme. All pass AA; the lowest light-theme text pair
  is 4.69:1, and the red accent word is 4.34:1 on paper (large text only, minimum 3).
- Headings: -0.02em, the hero headline -0.03em (in em, so the spacing scales with the size).
- Fonts: IBM Plex Sans 400, 500 and 600 and IBM Plex Mono 400 and 500 were already self-hosted (woff2,
  `font-display: swap`, licence `frontend/static/fonts/OFL.txt`, SIL Open Font License 1.1, listed in the
  README licences table); nothing was downloaded.
- Tests changed on purpose: the hairline test (the light theme's hairlines are faint navy, 0.10 to 0.22);
  the crosshair and corner-drawing tests were replaced by one that checks they are gone; the contrast tests
  run per theme. New: no external address in any template or static file (only SVG namespace names;
  licence texts are not loaded), the five fonts on disk and each `@font-face` swaps, reduced motion turns
  transitions off, heading spacing, both themes define the same tokens, and the switch in every top bar.

Results (this laptop): database tests 5 passed, the rest 774 passed; the strict v2 numbers reproduce
(0.778, 0.561, 0.727, 0.497). Screenshots in `ui-audit/after-v/` (`v1-*`): home in both themes at 1280,
1440 and 1920 px, New enquiry and Check at 1440 px in both themes; the letters of the hero headline do
not touch at -0.03em at any of the three widths. The home page is still the UX-V layout until V3.

### V2: the breaker drawing

- `tools/make_breaker_svg.py` (standard library only, seed 6021) writes `frontend/static/img/breaker.svg`:
  an invented, generic withdrawable four-pole air circuit breaker in rough, illustrative proportions
  ("Illustrative, not to scale" on the drawing; no names, logos, model numbers or real product shapes).
  `python tools/make_breaker_svg.py --check` says whether the committed file is up to date; a test
  checks the same and that two builds are byte-identical.
- The model: a front plate with ON and OFF push buttons, a charging handle, a spring-charged window, a
  trip indicator, an operations counter and a trip-unit window; a body with an open side (a cutaway)
  showing fixed, moving and arcing contacts for each pole; four arc chutes with 14 thin splitter plates
  each; finger-ring isolating contacts and four rear terminal stems at the back; auxiliary switches; a
  position indicator; slide rails that run forward past the front plate.
- One three-quarter view (36 degrees round, 24 degrees down), orthographic. Hidden edges: back to front,
  every visible face filled with the paper colour (`--bg`, so it follows the theme); a solid's faces are
  drawn together and surface details (windows, buttons) after their surface.
- Pencil look in geometry, no SVG filter: two passes per edge (a full one and a lighter partial one, so
  tone varies along the line), offsets up to 0.6 px, a gentle bend, ends overshooting 1 to 3 px, widths
  0.8 to 1.3 and opacities 0.5 to 0.8; 45 degree hatching on shaded faces; faint dashed construction
  lines. 120 KB on disk, 34 KB compressed.
- Each part is a group `bk-<part>` with `data-part` and its 3D explode vector, projected (`--dx`, `--dy`):
  the front plate and position indicator slide forward, the arc chutes lift. Leader lines end on 3D anchor
  points and move with their part (`static/js/breaker.js`); hovering a part or its label turns both blue.
  The blue current-path pulse and the one-time red trip flash are classes (`is-live`, `is-tripped`).
- `/debug/breaker` (`?anchors=1` shows the anchor points) exists only with `DEBUG_PAGES=true`; it is off
  by default and set to `"false"` in the compose file, and the route answers 404 then.
- New tests: the drawing is exactly the generator's output, the generator imports only the standard
  library, no filter, every part has an id and an explode vector, every leader ends on its part's anchor,
  12 to 16 splitter plates per chute, only part labels as text, the debug page is 404 when off, and the
  large-text-only red never colours small text (it is the `.accent` word in headings of 24 px or more).

Results (this laptop): database tests 5 passed, the rest 788 passed; the strict v2 numbers reproduce
(0.778, 0.561, 0.727, 0.497). Screenshots (`v2-*`, 1440 px, from a local run with `DEBUG_PAGES=true`):
the page dark, with anchor points, with anchor points fully exploded (the leaders follow the lifted
chutes and the plate), and light.

### V3: the home page and its hero

- The hero is the prototype's, rebuilt in the app's own templates: "An engineer-led way to estimate",
  "Turn enquiries into checked estimates" (the one red word, -0.03em), "Drop the customer's files. Every
  value shows where it came from.", one red button (Start an enquiry), one link (Try the sample enquiry),
  "Sample data only" at the foot. The breaker drawing from V2 sits on the right, inlined, unchanged.
- Background, changed on purpose: `static/js/hero-lines.js` (2D canvas, under 150 lines) replaces the
  UX-V WebGL shader (`hero-shader.js` deleted; its tests replaced by `tests/integration/test_hero_lines.py`).
  A faint 64 px grid and 34 thin contour lines, strokes only, no filled shapes. Colours are tokens
  (`--hero-grid`, `--hero-line`, `--hero-line-strong`, one set per theme) and are read again on a theme
  switch. Guards: pixel ratio capped at 1.5, at most 30 frames a second, nothing drawn while the tab is
  hidden or the hero is off screen, one still frame for reduced motion.
- The drawing draws itself on load in about 3 s (`static/js/home.js`): the parts' strokes in order from
  the frame outwards, their paper fills with them, then the leader lines, then the labels. After that,
  scrolling the first screen lifts the arc chutes and slides the front plate forward. Reduced motion
  shows the finished drawing, still. Labels are set at 13 units (14 in the story) and
  `SeaBreaker.fitLeaders` starts each leader just clear of its label. No mask or fade over any label;
  below 1100 px the left-hand labels are hidden.
- Below the hero: "Read. Check. Approve." (the second word blue); the story "The drawing stays in view."
  with three steps (Drop the files, We read them, You approve) beside a card that sticks at the top bar
  height + 16 px and never grows past the screen (100svh minus the bar minus 32 px). `home.js` works out
  the active step in one place and sets `data-step` on the section; CSS brightens that step and shows
  its caption (Files received, Values found, Decision needed) from the same attribute. The safety strip
  ("Decisions, not guesses.", three lines), then the measured numbers with their exact UX-1 labels at
  body size, each label beside its number, then the footer.
- One product name: "Switchgear Estimation Assistant" in the top bar of every page, every tab title,
  every footer and the README; under 700 px the top bar drops the first word (CSS only, the full name
  stays in the HTML). `tests/integration/test_product_name.py` checks it.
- The home header is sticky; `--nav-h` holds its height (measured by `home.js`).
- Tests changed on purpose: `test_home_page.py` (new hero, statement, story, safety, numbers order,
  unique ids, no mask, left labels hidden below 1100 px) and the headline line in `test_health_page.py`.
- Until `home.js` starts the draw-on, a flag set before paint (`hero-pending`, only when motion is
  allowed, cleared by a 4 s timer if script never runs) hides the hero drawing, so it never flashes
  complete first.

Results (this laptop): database tests 5 passed, the rest 803 passed; the strict v2 numbers reproduce
(0.778, 0.561, 0.727, 0.497). Hero cost, headless Edge on the laptop's Intel UHD 620 at 1440 x 900: on
screen 30.3 frames a second (the cap), 2.85 ms of script per frame, browser frames every 16.7 ms;
scrolled off, 0 frames drawn. With software rendering (SwiftShader, no GPU) the script still takes 4.3 ms
but the browser delivers only about 2 frames a second while the hero is on screen. Gap between the
headline and the "Position indicator" label: 138 px at 1280, 140 px at 1440, 142 px at 1920 (2316 not
measured: too little free memory). Screenshots (`v3-*`): home dark and light at 1280, 1440 and 1920,
the hero mid draw-on, story steps 1 to 3 at 1440.

### V4: the start page, the enquiry Summary and plain wording

- Start (`/enquiries/new`): "Drop the customer's files, or describe it". Files, a typed note, or both
  start an enquiry; the optional name stays. A note alone is kept in the new table `enquiry_notes`
  (migration 0006, additive only: one table, nothing else changed) with an audit entry, and the enquiry
  opens on Files: "Add the customer's files to read this enquiry." above the note. A note is the
  engineer's own words: never read for values and never priced. "Try the sample enquiry" and "Recent
  enquiries" sit under the form; a small breaker drawing (no labels, aria-hidden, its own id prefix)
  sits beside the title.
- Summary (`/enquiries/<id>`, a new first tab before 1 Files): six tiles worked out by
  `enquiry.summary_tiles`, each opening the step with the detail. What is quoted (name and ways found),
  Parts found, Drawing attached, Do they agree? ("Not yet: N disagree", or "Yes" and how many decisions
  wait), Estimated cost ("Waiting for approvals" until something is approved, then the total from
  approved values only with "Draft, from N of M lines", M counting the lines still blocked), and
  Required, not found (from the app's list of required fields, not from the specification; TBC values
  apart as "Marked TBC: N"). An enquiry with no files still opens on Files. The Ask column is a quiet
  empty state ("Nothing asked yet.") with no input until UX-3.
- Plain wording: the Check views are "To check" and "Parts list" (the address keys stay
  `decisions` and `items`, so old links work); one line under them: "A value is one fact read from your
  files. Approve it and it can be priced."; Quote says "Nothing is approved yet. Go to Check and approve
  values." while nothing is approved.
- The count on Check (fix): it was conflicts + values to review + 1 when an "Accept all" line was
  waiting, so the 46th on the sample was the Accept all line (39 read from a drawing picture + 6 medium
  confidence + 1). The Accept all line is not a decision: the count is now conflicts + values to review
  (`Decisions.needs`), and the line sits apart at the end of "To check" under "Agreeing values", marked
  "Not counted as decisions". The Enquiries pill reads "Needs you" without a number when only agreeing
  values wait.
- "7 disagree" on Summary against 8 conflicts on Check: different data, not a different rule. The Docker
  enquiry read its drawing PDF with OCR (drawing reading on) and found one more conflict (`ways.count`);
  the preview server had drawing reading off. Both screens now use one count, `Decisions.disagree`, and a
  test checks that Summary shows the number of conflict cards Check shows.
- Tests changed on purpose: the view names in `test_enquiry_views.py`, `test_web_flow.py` and
  `test_enquiry_lifecycle.py`. New: `tests/unit/test_summary_tiles.py`,
  `tests/integration/test_enquiry_summary.py`, and a 0006 test in `test_migrations.py`.

Results (this laptop): database tests 5 passed, the rest 824 passed; the strict v2 numbers reproduce
(0.778, 0.561, 0.727, 0.497). No V4 screenshots were taken here (headless Edge skipped to save memory).

### V4, second part: the tile detail and the Summary buttons

Steps 6 and 7 of the visual-pass brief, finished after the first V4 commit.

- A tile opens its detail below the tiles (`?tile=<key>` in the address, so Back works; with script only
  the report block is swapped, from `/enquiries/<id>/tiles/<key>`). The agreement tile opens first.
  - What is quoted: the tile is now one line from the values ("ACB incomer 1250 A, 400 V, form 4a, IP54";
    a field the documents disagree on is left out, and "Nothing read from the files yet" when nothing was
    read). The detail lists the board-wide required fields with their value, "Documents disagree" or
    "Not found".
  - Parts found: the parts with quantity and state. Drawing attached: each drawing as "Drawing (CAD)" or
    "Drawing (picture)", with a link to the proof viewer.
  - Do they agree?: each conflict with its sides and sources, and "Use this", which calls the existing
    decision action (`/fields/use`) and comes back to the Summary. Typing another value stays on Check.
    The tile has a red outline while any conflict is open.
  - Estimated cost: the draft total from approved values only and the lines not priced yet, or "Waiting
    for approvals". Required, not found: the fields, then the TBC ones apart.
- Buttons under the detail: Report (the Word report; disabled with a reason until a value is approved,
  the same rule as the Quote page), View drawing (the proof viewer on the first drawing read) and View all
  values (Check).
- Kept as decided on 12 Nov 2026: the Check view bar ("To check", "Parts list", "Report") stays on Check;
  the tiles live on the Summary. "Try the sample enquiry" makes a fresh sample enquiry as in UX-1, and
  reading progress is the real per-file state, polled every second.
- Tests: the tile links and their HTMX swap, real rows in every detail, "Use this" from the Summary,
  the Report button off until something is approved, and the cost tile never showing a price built from
  unapproved values. Changed on purpose: the tile hrefs and the "What is quoted" value.

Results (this laptop): database tests 5 passed, the rest 832 passed; the strict v2 numbers reproduce
(0.778, 0.561, 0.727, 0.497). No screenshots taken here.
