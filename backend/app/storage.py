from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

ALLOWED_EXT = {".docx", ".xlsx", ".xlsm", ".pdf", ".txt", ".md"}
MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


class UploadError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def safe_name(name: str) -> str:
    base = Path(name or "upload").name
    base = re.sub(r"[\x00-\x1f]", "", base)
    return base[:180] or "upload"


def sniff(ext: str, head: bytes) -> bool:
    if ext in (".docx", ".xlsx", ".xlsm"):
        return head[:4] == b"PK\x03\x04"
    if ext == ".pdf":
        return head[:5] == b"%PDF-"
    if ext in (".txt", ".md"):
        if b"\x00" in head:
            return False
        try:
            head.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False


def save_stream(stream, filename: str, data_dir: Path, max_bytes: int) -> dict:
    original = safe_name(filename)
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise UploadError("unsupported_format", "unsupported file type: " + (ext or "unknown"), 415)

    file_id = uuid.uuid4().hex
    folder = Path(data_dir) / "originals" / file_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ("source" + ext)

    digest = hashlib.sha256()
    size = 0
    head = b""
    with open(target, "wb") as out:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            if not head:
                head = chunk[:16]
            size += len(chunk)
            if size > max_bytes:
                out.close()
                target.unlink(missing_ok=True)
                raise UploadError("file_too_large", "file exceeds limit", 413)
            digest.update(chunk)
            out.write(chunk)

    if size == 0:
        target.unlink(missing_ok=True)
        raise UploadError("corrupted_file", "empty file", 400)
    if not sniff(ext, head):
        target.unlink(missing_ok=True)
        raise UploadError("corrupted_file", "file content does not match its extension", 400)

    return {
        "id": file_id,
        "original_filename": original,
        "stored_path": str(target),
        "mime_type": MIME.get(ext, "application/octet-stream"),
        "size_bytes": size,
        "sha256": digest.hexdigest(),
        "created_at": "",
        "ext": ext,
    }
