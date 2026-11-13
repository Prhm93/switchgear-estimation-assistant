"""Check that the app's libraries and everything they pull in carry a permissive licence (Stage 8).

Reads the installed packages' own metadata (``License-Expression``, ``License`` and the licence classifiers) for
every library in ``requirements.txt`` and, recursively, each library it depends on. A licence counts as permissive
when it names MIT, BSD, Apache, ISC, PSF, MPL-2.0 (file-level, used by some certificate bundles), the Unlicense,
0BSD, Zope or HPND; anything naming GPL (including LGPL and AGPL) is refused, and anything else is listed for a
person to check. Exit code 1 when a refused or unknown licence is found.

Run: ``python -m tools.licence_check`` (in the environment where requirements.txt is installed).
"""

from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERMISSIVE = ("mit", "bsd", "apache", "isc", "psf", "python software foundation", "mpl-2.0", "mozilla public",
              "unlicense", "0bsd", "zope", "hpnd", "historical permission", "cmu", "zlib", "matplotlib")
REFUSED = re.compile(r"\b(a|l)?gpl|general public license", re.I)
NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def verdict(licence: str) -> str:
    """"refused" (any GPL), "ok" (a permissive name) or "unknown"."""
    if REFUSED.search(licence):
        return "refused"
    low = licence.lower()
    return "ok" if any(p in low for p in PERMISSIVE) else "unknown"


def licence_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    text = (meta.get("License") or "").strip()
    first_line = text.splitlines()[0] if text else ""
    return "; ".join(x for x in (*classifiers, first_line if len(first_line) < 120 else "") if x) or "not stated"


def requirement_names(path: Path = ROOT / "requirements.txt") -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        m = NAME.match(line)
        if m and not line.strip().startswith("-"):
            out.append(m.group(1))
    return out


def closure(names: list[str]) -> dict[str, metadata.Distribution]:
    """Every installed distribution reachable from ``names`` (extras' optional dependencies left out)."""
    seen: dict[str, metadata.Distribution] = {}
    todo = list(names)
    while todo:
        name = todo.pop()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in seen:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        seen[key] = dist
        for req in dist.requires or []:
            if "extra ==" in req:
                continue
            marker_ok = True
            if ";" in req:
                from packaging.markers import Marker  # packaging ships with pip and setuptools

                marker_ok = Marker(req.split(";", 1)[1]).evaluate()
            m = NAME.match(req)
            if m and marker_ok:
                todo.append(m.group(1))
    return seen


def main() -> int:
    found = closure(requirement_names())
    bad = 0
    for key in sorted(found):
        dist = found[key]
        licence = licence_of(dist)
        v = verdict(licence)
        bad += v != "ok"
        print(f"{v:8} {dist.metadata['Name']} {dist.version}: {licence}")
    print(f"\n{len(found)} packages, {bad} to check")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
