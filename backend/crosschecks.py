"""Score the cross-checks (Stage 5) on the planted problems of a test set.

Usage (PowerShell, from the repo folder)::

    .venv\\Scripts\\python.exe -m backend.crosschecks --set test
    .venv\\Scripts\\python.exe -m backend.crosschecks --set reworded --mode combined

Each project is read as the app reads an upload with the DXF (specification, letter, drawing PDF and
DXF; :func:`backend.evaluate.project_values`), and :func:`backend.app.crosscheck.differences` runs on
its values. Against the answer key's planted problems:

- a planted **rating or quantity conflict** is found when a difference names its field; for a quantity
  conflict on ``ways.count`` a "way in one file only" difference counts too (the extra or missing way);
- every other difference is a **false flag**; the control projects have no planted conflict, so any
  difference there is a false flag;
- a planted **missing value** is found when the app's missing-information list names its field.

Nothing is tuned here; the cross-check has no thresholds. ``--gate`` applies the Stage 6 confidence gate (a
difference needs a value read reliably on one side; :func:`backend.app.crosscheck.differences`), which the app
uses since Stage 6; without it the Stage 5 behaviour is scored.
"""

from __future__ import annotations

import argparse
import sys

from backend.app.crosscheck import differences, seen_from_values
from backend.app.enquiry import missing_information
from backend.app.paths import REPO_ROOT
from data_generator.schemas import AnswerKey

CONFLICTS = {"rating_conflict", "quantity_conflict"}


def missing_fields(values) -> set[str]:
    """Fields the app's missing-information list names (not found, or stated only as TBC)."""
    groups: dict[str, dict] = {}
    for v in values:
        groups.setdefault(v.field, {"values": []})["values"].append(v)
    return {m["field"] for m in missing_information(groups) if m["why"] == "Not found in any file read"
            or m["why"].startswith("Stated as TBC")}


def score_project(key: AnswerKey, values, gate: bool = False) -> dict:
    diffs = differences(seen_from_values(values), gate=gate)
    planted = [p for p in key.planted if p.kind.value in CONFLICTS]
    found, used = [], set()
    for p in planted:
        hits = [d for d in diffs if d.field == p.field]
        if p.field == "ways.count":
            hits += [d for d in diffs if d.field.startswith("way.") and d.field.count(".") == 1]
        if hits:
            found.append(p)
            used |= {id(d) for d in hits}
    false = [d for d in diffs if id(d) not in used]
    wanted_missing = [p for p in key.planted if p.kind.value == "missing_value"]
    missing = missing_fields(values)
    return {"planted": planted, "found": found, "false": false,
            "missing_planted": wanted_missing, "missing_found": [p for p in wanted_missing if p.field in missing]}


def run(set_name: str, mode: str, count: int | None = None, gate: bool = False) -> str:
    from backend.evaluate import project_values

    root = REPO_ROOT / "data" / "projects" / set_name
    folders = sorted(p.parent for p in root.glob("*/answers.json"))[:count]
    if not folders:
        return f"no projects in {root}: build the set with python -m data_generator build --set {set_name}"
    rows, totals = [], {"planted": 0, "found": 0, "false": 0, "missing_planted": 0, "missing_found": 0}
    for folder in folders:
        key = AnswerKey.model_validate_json((folder / "answers.json").read_bytes())
        result = score_project(key, project_values(folder, with_dxf=True, mode=mode, set_name=set_name), gate)
        for k in totals:
            totals[k] += len(result[k])
        planted = ", ".join(f"{p.kind.value} {p.field}" for p in result["planted"]) or "none"
        false = "; ".join(d.message for d in result["false"][:3]) + (" ..." if len(result["false"]) > 3 else "")
        rows.append(f"| {folder.name} | {planted} | {len(result['found'])}/{len(result['planted'])} | "
                    f"{len(result['false'])} | {false or ''} |")
    tp, fp, fn = totals["found"], totals["false"], totals["planted"] - totals["found"]
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else None
    fmt = lambda x: "n/a" if x is None else f"{x:.3f}"  # noqa: E731
    gated = ", confidence gate (Stage 6)" if gate else ", no gate (Stage 5)"
    out = [f"## Cross-checks, {set_name} set, {mode} mode, with the DXF{gated} ({len(folders)} projects)", "",
           f"Planted conflicts found: {tp} of {totals['planted']}; false flags: {fp}; "
           f"P {fmt(p)}, R {fmt(r)}, F1 {fmt(f)}. Planted missing values listed: "
           f"{totals['missing_found']} of {totals['missing_planted']}.", "",
           "| Project | Planted conflicts | Found | False flags | First false flags |", "|---|---|---|---|---|", *rows]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.crosschecks", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", dest="set_name", choices=["test", "reworded", "fresh"], default="test")
    parser.add_argument("--mode", choices=["rules", "combined"], default="rules")
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--gate", action="store_true", help="the Stage 6 confidence gate (as the app uses it)")
    args = parser.parse_args(argv)
    print(run(args.set_name, args.mode, args.count, args.gate))
    return 0


if __name__ == "__main__":
    sys.exit(main())
