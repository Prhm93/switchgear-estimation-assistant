"""End-to-end estimate check on the synthetic test projects, through the web app in rules mode.

Usage (PowerShell, from the repo folder, after
``python -m data_generator build --set test``)::

    .venv\\Scripts\\python.exe -m backend.check_estimates

For each test project this uploads the same files as :mod:`backend.evaluate`
into a fresh app with its own SQLite database, presses "Approve all agreed
values" (nothing else is approved), builds the draft estimate, exports the
DOCX and compares the priced lines with the answer key:

- **match**: the priced (code, quantity) lines equal the answer key's lines
  that are not blocked by a planted problem;
- **extra / missing**: lines priced that the key blocks, or the reverse;
- **unsafe**: priced lines that depend on a field of a planted problem (or on a
  section count or width that the problem could change). This must be 0.

The answer key blocks a whole catalogue code when any one way using it is
affected, and makes every way depend on ``ways.count``; the app blocks per way.
So "extra" lines are expected for those projects; they are shown, not hidden.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import services
from backend.app.config import Settings
from backend.app.main import create_app
from backend.evaluate import UPLOAD
from data_generator.project import load_answers
from data_generator.schemas import AnswerKey
from data_generator.sets import DATA, TEST_COUNT, testset_id


def problem_fields(key: AnswerKey) -> set[str]:
    """Fields no priced line may depend on: the planted problems' fields, minus values another document gives."""
    fields = {p.field for p in key.planted if p.field
              and not (p.kind.value == "missing_value" and "only the" not in p.description)}
    if any(f == "ways.count" or (f.startswith("way.") and f.endswith(".rating")) for f in fields) and any(
            line.blocked_by and "enclosure.sections" in line.basis for line in key.estimate):
        fields |= {"enclosure.sections", "enclosure.width"}  # the stated layout follows the disputed value
    return fields


def check(folder: Path) -> dict:
    key = load_answers(folder / "answers.json")
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(database_url=f"sqlite:///{Path(tmp, 'app.sqlite').as_posix()}",
                            storage_dir=Path(tmp, "storage"), environment="test")
        with TestClient(create_app(settings)) as client:
            start = time.perf_counter()
            location = client.post("/projects", data={"name": folder.name}, follow_redirects=False).headers["location"]
            pid = int(location.split("/")[2])
            client.post(f"/projects/{pid}/documents",
                        files=[("files", (Path(n).name, (folder / n).read_bytes())) for n in UPLOAD])
            read_s = time.perf_counter() - start
            client.post(f"/projects/{pid}/review/approve-agreed")
            client.post(f"/projects/{pid}/estimate")
            with client.app.state.sessions() as session:
                est = services.latest_estimate(session, pid)
                lines = [(ln.code, float(ln.quantity), set(ln.basis)) for ln in est.lines]
                problems = len(est.problems)
                est_id = est.id
            assert client.get(f"/projects/{pid}/estimates/{est_id}/report.docx").status_code == 200
            total_s = time.perf_counter() - start
    got = Counter((c, q) for c, q, _ in lines)
    want = Counter((e.code, e.quantity) for e in key.estimate if not e.blocked_by)
    bad = problem_fields(key)
    return {"project": folder.name, "planted": ", ".join(p.kind.value for p in key.planted) or "none",
            "match": got == want, "extra": sum((got - want).values()), "missing": sum((want - got).values()),
            "unsafe": sum(1 for _, _, basis in lines if basis & bad), "problems": problems,
            "read_s": read_s, "total_s": total_s}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.check_estimates", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=TEST_COUNT)
    parser.add_argument("--root", type=Path, default=DATA / "projects" / "test")
    args = parser.parse_args(argv)
    folders = [args.root / testset_id(i) for i in range(1, args.count + 1)]
    if missing := [f.name for f in folders if not (f / "answers.json").exists()]:
        print(f"missing test projects {missing}: run python -m data_generator build --set test", file=sys.stderr)
        return 2
    rows = [check(f) for f in folders]
    print("| Project | Planted | Lines equal the key | Extra lines | Missing lines | Unsafe lines | Problems listed "
          "| Upload and read (s) | Upload to DOCX (s) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['project']} | {r['planted']} | {'yes' if r['match'] else 'no'} | {r['extra']} | {r['missing']} "
              f"| {r['unsafe']} | {r['problems']} | {r['read_s']:.1f} | {r['total_s']:.1f} |")
    print(f"\n{sum(r['match'] for r in rows)} of {len(rows)} equal the key; unsafe lines in total: "
          f"{sum(r['unsafe'] for r in rows)}; mean upload to DOCX {sum(r['total_s'] for r in rows) / len(rows):.1f} s.")
    return 1 if any(r["unsafe"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
