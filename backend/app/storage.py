"""File storage for uploaded originals, behind a small interface.

Originals are stored unchanged, under a key the app generates (a random hex
id plus the file type's extension). The user's filename is never used as a
path: it is kept only as data in the database. The SHA-256 is taken over the
uploaded bytes exactly as received.

:class:`LocalStorage` keeps files in a folder. Another backend (for example
object storage) only has to implement :class:`Storage`.
"""

from __future__ import annotations

import hashlib
import io
import re
import secrets
import warnings
import zipfile
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class FileType(StrEnum):
    PDF = "pdf"
    PNG = "png"
    JPG = "jpg"
    DXF = "dxf"
    DOCX = "docx"


EXTENSIONS: dict[str, FileType] = {".pdf": FileType.PDF, ".png": FileType.PNG, ".jpg": FileType.JPG,
                                   ".jpeg": FileType.JPG, ".dxf": FileType.DXF, ".docx": FileType.DOCX}
KEY_PATTERN = re.compile(r"^[0-9a-f]{32}\.(pdf|png|jpg|dxf|docx)$")


# Stage 8: limits against files that are small on disk but huge once opened.
MAX_UNPACKED_BYTES = 100_000_000  # a DOCX is a ZIP: the sum of its parts' unpacked sizes
MAX_ZIP_PARTS = 2_000
MAX_PIXELS = 90_000_000  # a PNG or JPG: width x height (an A1 sheet at 300 dpi is about 70 million)


class UploadRejected(ValueError):
    """The upload breaks a rule (type, size, pages). The message is safe to show to the user."""


class StoredFile(BaseModel):
    key: str
    sha256: str
    size_bytes: int
    file_type: FileType


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _looks_like_dxf(data: bytes) -> bool:
    """ASCII DXF starts with group code 0 and SECTION (optionally after comment groups 999)."""
    head = data[:2048].decode("ascii", errors="replace").replace("\r\n", "\n").split("\n")
    lines = [ln.strip() for ln in head]
    for i in range(0, len(lines) - 1, 2):
        if lines[i] == "999":
            continue
        return lines[i] == "0" and lines[i + 1] == "SECTION"
    return False


def _content_type(data: bytes) -> FileType | None:
    """The file type the bytes really are, from their signature; None when unknown."""
    if data.startswith(b"%PDF-"):
        return FileType.PDF
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return FileType.PNG
    if data.startswith(b"\xff\xd8\xff"):
        return FileType.JPG
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return FileType.DOCX if "word/document.xml" in z.namelist() else None
        except zipfile.BadZipFile:
            return None
    if _looks_like_dxf(data):
        return FileType.DXF
    return None


def pdf_page_count(data: bytes) -> int:
    import pdfplumber  # imported here: only PDF uploads need it

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return len(pdf.pages)


def check_upload(filename: str, data: bytes, max_bytes: int, max_pdf_pages: int) -> FileType:
    """Return the file type, or raise :class:`UploadRejected`.

    Both the extension and the content must be one of PDF, PNG, JPG, DXF or
    DOCX, and they must agree (a ``.pdf`` that is really a ZIP is rejected).
    """
    ext = Path(filename.replace("\\", "/")).suffix.lower()
    claimed = EXTENSIONS.get(ext)
    if claimed is None:
        raise UploadRejected(f"File type {ext or '(none)'} is not accepted. Use PDF, PNG, JPG, DXF or DOCX.")
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > max_bytes:
        raise UploadRejected(f"The file is {len(data) / 1e6:.1f} MB; the limit is {max_bytes / 1e6:.0f} MB.")
    actual = _content_type(data)
    if actual != claimed:
        raise UploadRejected(f"The file content does not match its {ext} extension.")
    if actual == FileType.DOCX:
        _check_zip(data)
    if actual in (FileType.PNG, FileType.JPG):
        _check_pixels(data)
    if actual == FileType.PDF:
        try:
            pages = pdf_page_count(data)
        except Exception as error:  # a broken PDF is a rejected upload, not a server error
            raise UploadRejected("The PDF could not be opened.") from error
        if pages > max_pdf_pages:
            raise UploadRejected(f"The PDF has {pages} pages; the limit is {max_pdf_pages}.")
    return actual


def _check_zip(data: bytes) -> None:
    """Refuse a ZIP bomb before any part is unpacked: too many parts, or too much once unpacked.

    The sizes come from the ZIP's directory; Python's zipfile never unpacks more than a part's stated size, so
    a part that lies about its size cannot get past this check when it is read later.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        parts = z.infolist()
    if len(parts) > MAX_ZIP_PARTS:
        raise UploadRejected(f"The document has {len(parts)} parts; the limit is {MAX_ZIP_PARTS}.")
    unpacked = sum(p.file_size for p in parts)
    if unpacked > MAX_UNPACKED_BYTES:
        raise UploadRejected(f"The document unpacks to {unpacked / 1e6:.0f} MB; the limit is "
                             f"{MAX_UNPACKED_BYTES / 1e6:.0f} MB.")


def _check_pixels(data: bytes) -> None:
    """Refuse a picture whose header gives more pixels than the limit (read from the header only)."""
    from PIL import Image

    try:
        with warnings.catch_warnings():  # Pillow's own bomb warning: this check gives the message instead
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as img:
                width, height = img.size
    except Image.DecompressionBombError as error:
        raise UploadRejected(f"The picture has too many pixels; the limit is {MAX_PIXELS / 1e6:.0f} million.") from error
    except Exception as error:  # a broken picture is a rejected upload, not a server error
        raise UploadRejected("The picture could not be opened.") from error
    if width * height > MAX_PIXELS:
        raise UploadRejected(f"The picture has {width * height / 1e6:.0f} million pixels; the limit is "
                             f"{MAX_PIXELS / 1e6:.0f} million.")


class Storage(Protocol):
    def save(self, data: bytes, file_type: FileType) -> StoredFile: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    """Files in one folder, named by generated key. Keys are validated before any path is built."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not KEY_PATTERN.match(key):
            raise ValueError(f"invalid storage key {key!r}")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):  # defence in depth; the pattern already rules this out
            raise ValueError(f"invalid storage key {key!r}")
        return path

    def save(self, data: bytes, file_type: FileType) -> StoredFile:
        key = f"{secrets.token_hex(16)}.{file_type.value}"
        path = self._path(key)
        with open(path, "xb") as f:  # "x": never overwrite
            f.write(data)
        return StoredFile(key=key, sha256=sha256_bytes(data), size_bytes=len(data), file_type=file_type)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)
