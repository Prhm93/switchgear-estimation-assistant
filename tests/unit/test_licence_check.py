"""Stage 8: the licence check refuses any GPL family licence and passes the app's own libraries."""

from __future__ import annotations

from tools.licence_check import closure, licence_of, requirement_names, verdict


def test_gpl_family_is_refused_and_permissive_names_pass() -> None:
    for refused in ("GPL-3.0-or-later", "GNU Lesser General Public License v3 (LGPLv3)", "AGPL-3.0"):
        assert verdict(refused) == "refused", refused
    for ok in ("MIT", "BSD-3-Clause", "Apache-2.0 OR BSD-3-Clause", "MIT-CMU", "PSF-2.0", "MPL-2.0"):
        assert verdict(ok) == "ok", ok
    assert verdict("Proprietary") == "unknown"


def test_every_installed_requirement_and_its_dependencies_are_permissive() -> None:
    names = requirement_names()
    assert "fastapi" in names and "pg8000" in names
    found = closure(names)
    assert len(found) >= len(names)
    assert {key: licence_of(d) for key, d in found.items() if verdict(licence_of(d)) != "ok"} == {}
