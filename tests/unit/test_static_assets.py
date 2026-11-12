"""Everything the pages load is self-hosted: no external address, fonts on disk, reduced motion honoured.

Stage UX visual pass: no CDN, no online fonts or images, no animation library. The only addresses
allowed are XML namespace names (``http://www.w3.org/...`` inside SVG), which are identifiers that are
never fetched. Licence texts (``*.txt``) are not loaded by any page and may cite their source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.app.paths import STATIC_DIR, STYLESHEET, TEMPLATES_DIR, TOKENS

NAMESPACE = re.compile(r"https?://www\.w3\.org/[0-9]{4}/(?:svg|xlink|xhtml|XML)[^\s\"')]*")
ADDRESS = re.compile(r"(?:https?:)?//[a-z0-9.-]+\.[a-z]{2,}", re.I)
FILES = sorted(p for p in list(TEMPLATES_DIR.rglob("*")) + list(STATIC_DIR.rglob("*"))
               if p.is_file() and p.suffix in {".html", ".css", ".js", ".svg", ".json"})
FONTS = ["IBMPlexSans-Regular.woff2", "IBMPlexSans-Medium.woff2", "IBMPlexSans-SemiBold.woff2",
         "IBMPlexMono-Regular.woff2", "IBMPlexMono-Medium.woff2"]


def external_addresses(text: str) -> list[str]:
    """Addresses that a browser could fetch: anything like //host.tld, minus SVG namespace names."""
    return ADDRESS.findall(NAMESPACE.sub("", text))


def test_the_checker_finds_external_addresses() -> None:
    assert external_addresses('<script src="https://cdn.example.com/x.js">') == ["https://cdn.example.com"]
    assert external_addresses('<link href="//fonts.example.org/css">') == ["//fonts.example.org"]
    assert external_addresses("@import url(http://example.net/a.css);") == ["http://example.net"]
    assert external_addresses("<svg xmlns='http://www.w3.org/2000/svg'>") == []


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.relative_to(p.parents[1]).as_posix())
def test_no_external_address_in_templates_or_static_files(path: Path) -> None:
    found = external_addresses(path.read_text(encoding="utf-8", errors="replace"))
    assert not found, f"{path.name} refers to {found}"


def test_the_fonts_are_self_hosted_with_their_licence() -> None:
    fonts = STATIC_DIR / "fonts"
    for name in FONTS:
        file = fonts / name
        assert file.is_file() and file.read_bytes()[:4] == b"wOF2", name  # a real woff2 file
    assert "SIL OPEN FONT LICENSE" in (fonts / "OFL.txt").read_text(encoding="utf-8").upper()


def test_every_font_face_points_at_a_file_on_disk_and_swaps() -> None:
    css = TOKENS.read_text(encoding="utf-8")
    faces = re.findall(r"@font-face\s*\{([^}]*)\}", css)
    assert len(faces) == len(FONTS)
    for face in faces:
        url = re.search(r'url\("\.\./fonts/([^"]+)"\)', face).group(1)
        assert url in FONTS and (STATIC_DIR / "fonts" / url).is_file(), url
        assert "font-display: swap" in face
    assert "@font-face" not in STYLESHEET.read_text(encoding="utf-8")  # one place for fonts


def test_reduced_motion_turns_transitions_off() -> None:
    css = TOKENS.read_text(encoding="utf-8")
    block = re.search(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\n\}", css, re.S)
    assert block and re.search(r"--dur:\s*0ms", block.group(1))
