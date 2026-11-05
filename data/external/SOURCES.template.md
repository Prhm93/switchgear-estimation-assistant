# Sources of external drawings (template)

`data/external/` is git-ignored: nothing in it is committed except this template. Copy this file to `data/external/SOURCES.md` and add one row per set of drawings you put here. A set without a filled-in row is not used.

Only use drawings you made yourself or drawings whose licence clearly allows this use. Record the licence exactly as the source states it.

| Set folder | Source | Licence | Date obtained | Link | Notes |
|---|---|---|---|---|---|
| `real-sld/` | Self-drawn (see `docs/real-drawings.md`) | Own work | YYYY-MM-DD | n/a | Tool used, number of drawings, anything unusual |
|  |  |  |  |  |  |

## Local denylist

`data/external/denylist.txt` (also git-ignored) lists real manufacturer names, one per line, `#` for comments. The test `tests/integration/test_names.py` checks that none of them appears in generated files, and skips that check when the file is missing.
