# Stage 8: safety and security

Branch `stage-8`, from `stage-9` (after the question box, so attacks are also tried through it). Built on
13 Nov 2026. Streamlit and AWS are left out.

## 1. What was tested, found and fixed

| Attack or check | How it is tested | Found | Now |
|---|---|---|---|
| Hidden instruction in a PDF | `test_security`: test project T08's white 1 pt line, asked about through the question box; `test_ask`: a planted page | Already flagged on Check and in the proof viewer (Stage 3) | Also flagged in the answer ("looks like an instruction ... was not followed"); nothing approved, nothing changed. The box can only read. |
| Zip bomb in a DOCX | `test_storage`: a DOCX whose parts unpack to more than 100 MB, and one with more than 2,000 parts | Not checked before: python-docx would unpack it in memory | Refused before reading, from the ZIP directory (`_check_zip`), with a plain reason |
| Pixel bomb in a PNG or JPG | `test_storage`: a small PNG declaring more than 90 million pixels; a broken picture | Pillow only warned below its own limit; a broken picture failed later in OCR | Refused at upload (`_check_pixels`); a picture that cannot be opened is refused with a reason |
| Fake file type | `test_security`, `test_storage`: a ZIP named `.pdf`, a fake JPEG signature | A JPEG was accepted on its first two bytes | Signature and opening checked; refused |
| Oversized, empty, wrong type | `test_security` through the web form | Already refused (Stage 2) | Tested again through the form, each with its reason |
| Path in a file name | `test_security`: `../../../evil.pdf`, `..\..\evil2.pdf` | Already safe: stored under generated names | Tested: no file outside storage; the name is cut to its last part and kept only as data |
| HTML and script in every field shown | `test_security`: enquiry name, note, file name, typed value, unit, reason, rename; `test_ask`: a question | Already escaped (Jinja2 autoescape) | Tested on every enquiry page and Activity |
| SQL injection | `test_security`: SQL text in name, note, file name and rename | Already safe (SQLAlchemy parameters; the one raw SQL, the pgvector search, uses bound parameters) | Tested: stored as data, every table still there |
| Audit of decisions | `test_security`: approve, edit, reject by three actors | Already audited (Stage 2) | Tested: one entry per decision with its actor and field; questions audited too (Stage 9) |
| Known vulnerabilities (pip-audit) | `pip-audit -r requirements.txt` and on the laptop environment | Requirements clean; the environment's pip 26.0.1 had 4 advisories | pip upgraded to 26.3 on the laptop; the image now upgrades pip before installing (`test_containers`) |
| Secrets | `python -m tools.secrets_scan` (patterns, committed files only; `test_secrets_scan`) | None | Clean |
| Licences | `python -m tools.licence_check`: every requirement and everything it pulls in (`test_licence_check`) | 47 packages, all permissive; certifi is MPL-2.0 (file-level copyleft; used unchanged) | No GPL, LGPL or AGPL |
| Containers | `test_containers` | Already: app as uid 10001, memory limits 256 MB (db) and 384 MB (app), ports on 127.0.0.1 only | Tested |

## 2. How to run the checks

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_security.py tests/integration/test_ask.py tests/unit/test_storage.py
.venv\Scripts\python.exe -m pip_audit -r requirements.txt
.venv\Scripts\python.exe -m tools.secrets_scan
.venv\Scripts\python.exe -m tools.licence_check
```

## 3. What could not be fixed in this stage

- **No login and no roles.** Anyone who can reach port 8000 can use the app. It listens on 127.0.0.1 only, which is
  the protection for a laptop demo; login with engineer and admin roles is not built.
- **No CSRF tokens.** Forms post without a token; with no login there is no session to steal, but a login would need
  them (and SameSite cookies).
- **No rate limit** on uploads or questions; a large upload is bounded by the size, page, pixel and unpacked-size
  limits only.
- **Prompt injection is flagged by patterns**: an instruction worded unlike the patterns is not flagged. It is still
  never obeyed, because no model output can approve a value, change a price or act; but a model reading
  (recorded mode) could be steered to misread a value, which is why model values are always ticked by a person.
- **pip-audit and the secrets scan are not in CI yet**; they need network access and run by hand.
- The secrets scan is patterns only; an unusual secret format would be missed.

## 4. Tests

- `tests/integration/test_security.py` (10), `tests/unit/test_storage.py` (bomb and picture tests added),
  `tests/unit/test_containers.py` (4), `tests/unit/test_secrets_scan.py` (3), `tests/unit/test_licence_check.py` (2).
