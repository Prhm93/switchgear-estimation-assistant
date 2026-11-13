"""Upload checks and local storage: generated keys, unchanged bytes, no path escape."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

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
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (40, 30), 255).save(buf, "JPEG")
    assert check_upload("photo.JPEG", buf.getvalue(), MB, 50) == FileType.JPG


def test_a_picture_that_cannot_be_opened_is_rejected():  # Stage 8: a JPG signature alone is not a picture
    with pytest.raises(UploadRejected, match="could not be opened"):
        check_upload("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100, MB, 50)


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


# --- Stage 8: archive and picture bombs ------------------------------------------------------------------

def _docx_with(extra: dict[str, bytes | int], level: int = 9) -> bytes:
    import zipfile as zf

    buf = io.BytesIO()
    with zf.ZipFile(buf, "w", zf.ZIP_DEFLATED, compresslevel=level) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
        for name, data in extra.items():
            if isinstance(data, int):  # that many zero bytes, written in 1 MB pieces (never all in memory)
                with z.open(name, "w", force_zip64=True) as f:
                    for _ in range(data // 1_000_000):
                        f.write(bytes(1_000_000))
            else:
                z.writestr(name, data)
    return buf.getvalue()


def test_a_zip_bomb_docx_is_rejected_before_it_is_opened():
    bomb = _docx_with({"word/media/huge.bin": 300_000_000})  # 300 MB of zeros packs to about 0.3 MB
    assert len(bomb) < 1_000_000
    with pytest.raises(UploadRejected, match="unpacks"):
        check_upload("letter.docx", bomb, max_bytes=25_000_000, max_pdf_pages=60)


def test_a_docx_with_too_many_parts_is_rejected():
    many = _docx_with({f"word/x{i}.xml": b"<x/>" for i in range(2_100)})
    with pytest.raises(UploadRejected, match="parts"):
        check_upload("letter.docx", many, max_bytes=25_000_000, max_pdf_pages=60)


def test_a_picture_bomb_is_rejected_by_its_pixel_count():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("1", (10_000, 10_000)).save(buf, "PNG")  # 100 million pixels, a few kB on disk
    with pytest.raises(UploadRejected, match="pixels"):
        check_upload("drawing.png", buf.getvalue(), max_bytes=25_000_000, max_pdf_pages=60)


def test_the_real_letter_and_drawing_pictures_still_pass():
    for name in ("requirements.docx", "drawing/schematic_sheet1_scanned.png", "drawing/schematic_sheet1_photo.png"):
        data = (SHOWCASE / name).read_bytes()
        check_upload(Path(name).name, data, max_bytes=25_000_000, max_pdf_pages=60)
