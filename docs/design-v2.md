# Design version 2

Design v2 changes the look only. Every Stage 2 flow works as before:
- the same forms post to the same routes;
- the same values reach the estimate;
- the same audit events are written.

The approved designs are [`docs/design/mockup-home.html`](design/mockup-home.html) and [`docs/design/mockup-dashboard.html`](design/mockup-dashboard.html). Their colours, spacing, radii, shadows, type sizes and layout were copied into `frontend/static/css/app.css` and the templates. Their canvas runtime (`support.js`, `x-dc` tags) is not used.

## What changed

- **Design system** (`frontend/static/css/app.css`, rewritten):
  - glass cards with hairline edges, a soft wide shadow and an inset top highlight, radius 18 to 20 px;
  - pill buttons: the primary is solid red with a soft red shadow, the secondary is glass;
  - icon buttons are tonal circles: approve green, edit neutral, reject red;
  - tonal chips: High, Needs review, Conflict, Missing and Approved;
  - a ring gauge, a segment bar, side-by-side conflict cards and filter pills;
  - a faint 56 px grid background.
  The palette is unchanged. Light blue `#9CC0FF` is used for links and the focus ring.
- **Fonts**: Instrument Serif (SIL OFL 1.1) for page titles and big headings, self-hosted as woff2 in `frontend/static/fonts/` with `OFL-InstrumentSerif.txt`, and added to the README licences table. IBM Plex Sans and IBM Plex Mono are unchanged.
- **Routes** (in `backend/app/web.py` and `backend/app/main.py`):

  | Route | What it is now |
  |---|---|
  | `/` | the new home page; it works without a database |
  | `/projects` | the projects list (the old dashboard) |
  | `/projects/{id}` | the new read-only project dashboard |
  | `/health` | the design and health-check page |
  | `/system` | redirects to `/health` (301) |

  All POST routes are unchanged.
- **App layout** (`layout_app.html`): a left sidebar on every app page, holding:
  - the three-bar product mark and the project switcher;
  - Dashboard, Documents, Analysis, Review (with a count badge), Estimate, Audit log and System check;
  - the reading-mode panel ("Rules · live", "Model run: none until Stage 3");
  - Engineer and "Environment: development".

  Below 900 px the sidebar becomes a top bar.
- **Project dashboard**, fed by the project's data:
  - a ring gauge of approved values;
  - open conflicts, missing information and the estimate (lines, total, blocked lines);
  - the values table with conflicts first and filter links;
  - the first conflict side by side, the documents, and the last five audit events.

  Its buttons post to the existing routes. "Approve high confidence" is the existing approve-agreed action. Approve posts `/values/{id}/approve`. Edit, reject and "Compare" open the value on the review screen.
- **Parked fixes**: the sidebar reads "Environment: development". Table headings no longer wrap (`white-space: nowrap`), so "VALUES APPROVED" has no double gap.

## Numbers on the home page

| Number | Source |
|---|---|
| 20 test enquiries | `docs/stage-1.md` |
| 17 planted problems, plus 4 clean controls | `docs/stage-1.md` and `data/projects/test/PLANTED.md` |
| 0.486, the rules recall without the DXF | `docs/stage-2.md` |
| Hero cards | the real showcase values: the incomer ACB 1250 A on spec page 5, and the Q2 rating, 250 A on spec page 5 against 200 A on drawing sheet 1 |
| The missing-information example | test project T12 (way Q3 rating "TBC") |
| "Values approved" | counted live from the newest project whose name contains "showcase" |

Three numbers are not measured yet and read `[PLACEHOLDER]`:
- "4 drawing conditions", because the scanned, photo and real drawings are scored from Stage 4;
- the version line in the footer;
- the hero's "Values approved" when no showcase project exists.

"Model answers must quote their source" is marked as a Stage 3 feature. "Sign in" is hidden until Stage 8.

## Mockups

The approved designs are [`docs/design/mockup-home.html`](design/mockup-home.html) (home page) and [`docs/design/mockup-dashboard.html`](design/mockup-dashboard.html) (project dashboard); open them in a browser.

## Differences from the mockups, and why

1. **Hairline dividers are 0.10, not 0.08.** The mockup draws a few dividers at alpha 0.08. The rule is 0.10 to 0.18, so 0.10 is the faintest allowed hairline.
2. **The grid is an SVG tile, not two linear gradients.** It looks the same, and it keeps the gradient list to the four allowed places.
3. **"Needs review" chips are blue, not red.** The mockup uses red for "Needs review" in one hero card. Red stays for Conflict and amber for Missing, so the three states never share a colour. The hero conflict card shows "Conflict".
4. **Left out until their stages build them:** the search box, Catalogue, and "Request from customer".
5. **No "Use 250 A / Use 200 A" buttons.** Resolving a conflict is a review decision, so the dashboard shows a "Compare" link to the field on the review screen, where both values are approved, edited or rejected with a reason.
6. **Filters are links**, for example `/projects/{id}?show=review`, not buttons that need script.
7. **Model run:** "none until Stage 3", instead of a model name.
8. **Fonts are self-hosted**, not loaded from Google Fonts. The mockup's IBM Plex Serif on the document page in the preview is drawn in IBM Plex Mono, as the analysis screen shows document text.
9. **The dashboard table has one row per extracted value, at most 12**, with a link to the review screen for the rest. The mockup shows five combined rows.
10. **The sidebar also has Documents and System check**, because the upload screen and the health page need a way in.

## Contrast (WCAG 2.2 AA)

Every semi-transparent colour has a solid twin token: its colour over the surface it sits on, rounded per channel.
- `backend/app/design/contrast.py` checks text on the twins.
- `tests/unit/test_contrast.py` recomputes every twin from its rgba value (allowing 1 per channel) so the twins cannot drift.

All 75 pairs pass:
- **Lowest text pair:** white on red, 4.69:1 (minimum 4.5).
- **Lowest non-text pair:** red on glass, 3.44:1 (minimum 3.0).

Output of `python -m backend.app.design.contrast`:

| Foreground | Background | Ratio | Minimum | Result | Used for |
|---|---|---|---|---|---|
| `--text` #F4F7FB | `--bg` #0A1630 | 16.70 | 4.5 | pass | body text |
| `--text-muted` #A9B8D3 | `--bg` #0A1630 | 8.96 | 4.5 | pass | secondary text, footer |
| `--text-soft` #C9D6EC | `--bg` #0A1630 | 12.23 | 4.5 | pass | hero lede |
| `--text-nav` #D3DDEE | `--header-solid` #0A1630 | 13.11 | 4.5 | pass | site navigation |
| `--text-nav` #D3DDEE | `--header-glow-solid` #0C1E41 | 12.01 | 4.5 | pass | site navigation where the glow is brightest |
| `--text` #F4F7FB | `--header-glow-solid` #0C1E41 | 15.30 | 4.5 | pass | product name in the header over the glow |
| `--text` #F4F7FB | `--sidebar-solid` #081229 | 17.31 | 4.5 | pass | sidebar brand and project name |
| `--text-soft` #C9D6EC | `--sidebar-solid` #081229 | 12.68 | 4.5 | pass | sidebar navigation |
| `--text-muted` #A9B8D3 | `--sidebar-solid` #081229 | 9.29 | 4.5 | pass | sidebar environment line |
| `--label` #8597B8 | `--sidebar-solid` #081229 | 6.30 | 4.5 | pass | sidebar section labels |
| `--text` #F4F7FB | `--nav-active-solid` #0D2451 | 14.08 | 4.5 | pass | selected sidebar item |
| `--text` #F4F7FB | `--veil-solid` #1A2C53 | 12.78 | 4.5 | pass | project switcher, glass button |
| `--text-soft` #C9D6EC | `--veil-solid` #1A2C53 | 9.36 | 4.5 | pass | hero pill |
| `--count-text` #FF9CA0 | `--count-solid` #381528 | 8.05 | 4.5 | pass | review count in the sidebar |
| `--success-text` #7EE2B4 | `--mode-solid` #111C36 | 10.80 | 4.5 | pass | reading mode: live |
| `--text-muted` #A9B8D3 | `--mode-solid` #111C36 | 8.43 | 4.5 | pass | reading mode: model run |
| `--text` #F4F7FB | `--glass-solid` #0F1F44 | 15.04 | 4.5 | pass | text in glass cards |
| `--text-muted` #A9B8D3 | `--glass-solid` #0F1F44 | 8.07 | 4.5 | pass | secondary text in glass cards |
| `--text-soft` #C9D6EC | `--glass-solid` #0F1F44 | 11.01 | 4.5 | pass | body copy in glass cards |
| `--label-table` #8FA2C4 | `--glass-solid` #0F1F44 | 6.26 | 4.5 | pass | table headings |
| `--blue-text` #9CC0FF | `--glass-solid` #0F1F44 | 8.77 | 4.5 | pass | links in cards |
| `--warning-text` #F2C66D | `--glass-solid` #0F1F44 | 10.06 | 4.5 | pass | [PLACEHOLDER] marks |
| `--text` #F4F7FB | `--glass-soft-solid` #0E1F43 | 15.08 | 4.5 | pass | home page tiles |
| `--text-soft` #C9D6EC | `--glass-soft-solid` #0E1F43 | 11.05 | 4.5 | pass | home page tile text |
| `--red-text` #FF8A8E | `--glass-soft-solid` #0E1F43 | 7.16 | 4.5 | pass | step numbers on the home page |
| `--text` #F4F7FB | `--deep-solid` #0C1A39 | 15.99 | 4.5 | pass | table rows and value rows |
| `--text-muted` #A9B8D3 | `--deep-solid` #0C1A39 | 8.58 | 4.5 | pass | sources in rows |
| `--blue-text` #9CC0FF | `--deep-solid` #0C1A39 | 9.32 | 4.5 | pass | links in rows |
| `--text` #F4F7FB | `--row-hover-solid` #112858 | 13.31 | 4.5 | pass | table row, hover |
| `--text-muted` #A9B8D3 | `--row-hover-solid` #112858 | 7.14 | 4.5 | pass | table row source, hover |
| `--text` #F4F7FB | `--inset-solid` #0C1A38 | 16.01 | 4.5 | pass | values in a conflict pair |
| `--text-muted` #A9B8D3 | `--inset-solid` #0C1A38 | 8.59 | 4.5 | pass | sources and quotes in a conflict pair |
| `--text` #F4F7FB | `--conflict-chip` #351F3E | 13.79 | 4.5 | pass | values on the conflict cards of the review screen |
| `--text-muted` #A9B8D3 | `--conflict-chip` #351F3E | 7.40 | 4.5 | pass | sources on the conflict cards of the review screen |
| `--text` #F4F7FB | `--field-solid` #102148 | 14.66 | 4.5 | pass | text typed in an input |
| `--text-muted` #A9B8D3 | `--field-solid` #102148 | 7.86 | 4.5 | pass | input placeholder |
| `--text` #F4F7FB | `--upload-inner` #0D1C3D | 15.63 | 4.5 | pass | upload box input |
| `--text-muted` #A9B8D3 | `--upload-inner` #0D1C3D | 8.38 | 4.5 | pass | upload box placeholder |
| `--text-muted` #A9B8D3 | `--sheen-solid` #1E2E4D | 6.75 | 4.5 | pass | labels at the light corner of a hero card |
| `--text-soft` #C9D6EC | `--cta-solid` #0E2653 | 10.07 | 4.5 | pass | call-to-action panel text |
| `--text` #F4F7FB | `--frame` #0C1A3A | 15.96 | 4.5 | pass | app preview on the home page |
| `--text-muted` #A9B8D3 | `--frame` #0C1A3A | 8.56 | 4.5 | pass | app preview navigation |
| `--text` #F4F7FB | `--preview-row-solid` #102148 | 14.66 | 4.5 | pass | values in the app preview |
| `--text-muted` #A9B8D3 | `--preview-row-solid` #102148 | 7.86 | 4.5 | pass | sources in the app preview |
| `--ink` #1B2740 | `--paper` #F4F7FB | 13.85 | 4.5 | pass | document text in the preview |
| `--ink-muted` #5A6B88 | `--paper` #F4F7FB | 5.02 | 4.5 | pass | document page label in the preview |
| `--ink-mark` #0E2C66 | `--paper-mark` #CDDCF3 | 9.63 | 4.5 | pass | highlighted source in the preview |
| `--on-red` #FFFFFF | `--red` #E31E24 | 4.69 | 4.5 | pass | primary button label |
| `--on-red` #FFFFFF | `--red-hover` #C8161C | 5.85 | 4.5 | pass | primary button label, hover |
| `--text` #F4F7FB | `--veil-hover-solid` #263962 | 10.60 | 4.5 | pass | glass button label, hover |
| `--text` #F4F7FB | `--tonal-solid` #13326E | 11.44 | 4.5 | pass | tonal button label, selected pager item |
| `--text` #F4F7FB | `--tonal-hover-solid` #143A7F | 10.07 | 4.5 | pass | tonal button label, hover |
| `--text` #F4F7FB | `--active-solid` #13316B | 11.64 | 4.5 | pass | selected filter, document chip and toggle segment |
| `--text-soft` #C9D6EC | `--neutral-chip` #1D2F57 | 8.97 | 4.5 | pass | edit icon button glyph, neutral chip |
| `--text` #F4F7FB | `--neutral-hover-solid` #26385D | 10.82 | 4.5 | pass | icon button glyph, hover |
| `--success-text` #7EE2B4 | `--approve-solid` #112F41 | 8.91 | 4.5 | pass | approve icon button glyph |
| `--success-text` #7EE2B4 | `--approve-hover-solid` #164048 | 7.21 | 4.5 | pass | approve icon button glyph, hover |
| `--red-text` #FF8A8E | `--reject-solid` #2A1B36 | 7.09 | 4.5 | pass | reject icon button glyph |
| `--red-text` #FF8A8E | `--reject-hover-solid` #441B34 | 6.39 | 4.5 | pass | reject icon button glyph, hover |
| `--success-text` #7EE2B4 | `--success-chip` #15364C | 8.07 | 4.5 | pass | High and Approved chips |
| `--blue-text` #9CC0FF | `--review-chip` #122E66 | 7.09 | 4.5 | pass | Needs review chip, info alert |
| `--red-text` #FF8A8E | `--conflict-chip` #351F3E | 6.55 | 4.5 | pass | Conflict chip, error alert |
| `--warning-text` #F2C66D | `--missing-chip` #353842 | 7.28 | 4.5 | pass | Missing chip, warning alert |
| `--red` #E31E24 | `--glass-solid` #0F1F44 | 3.44 | 3.0 | pass | conflict dot and segment |
| `--success` #2EA06E | `--glass-solid` #0F1F44 | 4.90 | 3.0 | pass | ring gauge arc, approved segment, High dot |
| `--warning` #E0A93B | `--glass-solid` #0F1F44 | 7.62 | 3.0 | pass | review segment, Medium dot |
| `--blue-text` #9CC0FF | `--glass-solid` #0F1F44 | 8.77 | 3.0 | pass | Low confidence ring |
| `--success` #2EA06E | `--deep-solid` #0C1A39 | 5.21 | 3.0 | pass | High dot in rows |
| `--warning` #E0A93B | `--deep-solid` #0C1A39 | 8.10 | 3.0 | pass | Medium dot in rows |
| `--red` #E31E24 | `--deep-solid` #0C1A39 | 3.66 | 3.0 | pass | Conflict dot in rows |
| `--red` #E31E24 | `--bg` #0A1630 | 3.83 | 3.0 | pass | red line under the header, hero pill dot |
| `--focus` #9CC0FF | `--bg` #0A1630 | 9.74 | 3.0 | pass | keyboard focus ring |
| `--focus` #9CC0FF | `--glass-solid` #0F1F44 | 8.77 | 3.0 | pass | keyboard focus ring in cards |
| `--focus` #9CC0FF | `--deep-solid` #0C1A39 | 9.32 | 3.0 | pass | keyboard focus ring in rows |
| `--focus` #9CC0FF | `--sidebar-solid` #081229 | 10.10 | 3.0 | pass | keyboard focus ring in the sidebar |

## Tests

| File | What it checks |
|---|---|
| `tests/unit/test_design_rules.py` (rewritten) | the palette is unchanged; the hairline tokens are rgb(156,192,255) with alpha 0.10 to 0.18; every border is `0`, `none` or a 1px hairline; gradients only in `.upload-box`, `.glow`, `.sheen` and `.cta-panel`; the grid has no gradient; the upload border runs red to blue; `perspective(`/`rotateY(` only in `.hero` rules inside `@media (min-width: 1100px)`; glass cards have hairline, shadow and highlight; radii are 18 and 20 px; pill buttons, a red primary with a red shadow, glass secondary, tinted icon buttons; serif titles; 150 ms transitions, `--dur: 0ms` and no spinner animation under reduced motion; a 2px focus ring; table headings do not wrap; no emoji or "magic" wording in any template |
| `tests/unit/test_contrast.py` | every pair above, the twin recomputation, the composite maths, and that every pair names a real token |
| `tests/integration/test_web_flow.py` | adds three tests: the project dashboard shows the project's own counts (ring label, conflict pair, conflicts first, the sidebar review count, the environment) and approving from it uses the review route; the home page links to the showcase project once one exists; an unknown project dashboard is a 404. The existing flow tests now read `/projects` instead of `/` |
| `tests/integration/test_health_page.py` | now uses `/health`; adds the `/system` redirect, the home page without a database (disclaimer, no "Sign in", `[PLACEHOLDER]` present) and the Instrument Serif files served as woff2 |

Results on the laptop (Python 3.14), 6 Nov 2026:
- **Without `DATABASE_URL`:** 386 passed, 4 skipped (the Postgres-only tests).
- **With the Docker Postgres:** 390 passed.

## How to run it

```powershell
docker compose -f deployment/docker-compose.yml up --build
```

Then open:
- <http://127.0.0.1:8000/> for the home page;
- <http://127.0.0.1:8000/projects> for the projects;
- <http://127.0.0.1:8000/health> for the design and health page.

## Known limits

- On a 390 px phone, the wide tables (dashboard values, estimate lines, audit log) scroll sideways inside their card.
- The home page counts come from the newest project whose name contains "showcase"; no such project means `[PLACEHOLDER]`.
- The analysis screen still shows document text, not a rendered page image; highlighted regions on drawings arrive with Stage 4.
