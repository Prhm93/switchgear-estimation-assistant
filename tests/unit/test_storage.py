"""Upload checks and local storage: generated keys, unchanged bytes, no path escape."""

from __future__ import annotations

import io
import zipfile

import pytest

from backend.app.storage import FileType, LocalStorage, UploadRejected, check_upload, sha256_bytes
from data_generator.sets import DATA

SHOWCASE = DATA / "projects" / "showcase"
MB = 1_000_000


def _docx_bytes() -> bytes:
    return (SHOWCASE / "requirements.docx").read_bytes()


@pytest.mark.parametrize("name, file_type", [
    ("specification.pdf", FileType.PDF), ("requirements.docx", FileType.DOCX),
    ("drawing/schematic.dxf", FileType.DXF), ("drawing/schematic_sheet1_scanned.png", FileType.PNG),
])
def test_showcase_files_are_accepted(name, file_type):
    data = (SHOWCASE / name).read_bytes()
    assert check_upload(name.split("/")[-1], data, 25 * MB, 50) == file_type


def test_jpg_is_accepted():
    data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    assert check_upload("photo.JPEG", data, MB, 50) == FileType.JPG


@pytest.mark.parametrize("name", ["notes.txt", "macro.docm", "archive.zip", "drawing.dwg", "noextension", "x.exe"])
def test_other_types_are_rejected(name):
    with pytest.raises(UploadRejected, match="not accepted"):
        check_upload(name, b"%PDF-1.7 whatever", MB, 50)


def test_content_must_match_the_extension():
    with pytest.raises(UploadRejected, match="does not match"):
        check_upload("fake.pdf", _docx_bytes(), 25 * MB, 50)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("hello.txt", "not a word document")
    with pytest.raises(UploadRejected, match="does not match"):
        check_upload("fake.docx", zipped.getvalue(), MB, 50)


def test_size_and_page_limits():
    data = (SHOWCASE / "specification.pdf").read_bytes()
    with pytest.raises(UploadRejected, match="limit is"):
        check_upload("specification.pdf", data, len(data) - 1, 50)
    with pytest.raises(UploadRejected, match="pages; the limit is 3"):
        check_upload("specification.pdf", data, 25 * MB, 3)
    with pytest.raises(UploadRejected, match="empty"):
        check_upload("empty.pdf", b"", MB, 50)


def test_stored_bytes_and_hash_are_exactly_the_upload(tmp_path):
    storage = LocalStorage(tmp_path / "store")
    data = (SHOWCASE / "specification.pdf").read_bytes()
    stored = storage.save(data, FileType.PDF)
    assert storage.read(stored.key) == data
    assert stored.sha256 == sha256_bytes(data) and stored.size_bytes == len(data)


def test_keys_are_generated_never_the_filename(tmp_path):
    storage = LocalStorage(tmp_path / "store")
    a = storage.save(b"%PDF-1", FileType.PDF)
    b = storage.save(b"%PDF-1", FileType.PDF)
    assert a.key != b.key
    assert all(len(k) == 36 and k.endswith(".pdf") for k in (a.key, b.key))
    assert sorted(p.name for p in (tmp_path / "store").iterdir()) == sorted([a.key, b.key])


@pytest.mark.parametrize("key", [r"..\..\x.pdf", "../../x.pdf", "/etc/passwd", r"C:\Windows\x.pdf",
                                 "0123456789abcdef0123456789abcdef.pdf/../../x.pdf", "x.pdf", ""])
def test_keys_cannot_escape_the_storage_folder(tmp_path, key):
    storage = LocalStorage(tmp_path / "store")
    (tmp_path / "x.pdf").write_bytes(b"outside")
    with pytest.raises(ValueError, match="invalid storage key"):
        storage.read(key)
    with pytest.raises(ValueError, match="invalid storage key"):
        storage.delete(key)
    assert (tmp_path / "x.pdf").read_bytes() == b"outside"


def test_a_hostile_filename_is_checked_by_extension_only(tmp_path):
    """The name ..\\..\\x.pdf decides only the claimed type; storage never sees it."""
    data = (SHOWCASE / "specification.pdf").read_bytes()
    assert check_upload(r"..\..\x.pdf", data, 25 * MB, 50) == FileType.PDF
    storage = LocalStorage(tmp_path / "store")
    stored = storage.save(data, FileType.PDF)
    assert list((tmp_path / "store").iterdir()) == [(tmp_path / "store" / stored.key)]
    assert not (tmp_path / "x.pdf").exists()
