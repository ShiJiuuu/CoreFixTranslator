from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from ..base import DocumentError


def find_soffice() -> str | None:
    configured = os.environ.get("SOFFICE_BIN", "").strip()
    if configured and Path(configured).exists():
        return configured
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (
        "/usr/bin/soffice",
        "/usr/lib/libreoffice/program/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def convert_docx_to_pdf(docx_path: Path, pdf_path: Path, *, binary: str | None = None, timeout: int | None = None) -> None:
    soffice = binary or find_soffice()
    if not soffice:
        raise DocumentError(
            "pdf_converter_missing",
            "LibreOffice not found. Install libreoffice-writer or set SOFFICE_BIN, or set PDF_RENDER=docx.",
        )
    limit = int(timeout or os.environ.get("PDF_CONVERT_TIMEOUT_SECONDS", "300"))
    profile_dir = Path(tempfile.gettempdir()) / ("corefix-lo-" + uuid.uuid4().hex)
    profile_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as outdir:
        command = [
            soffice,
            "--headless",
            "--norestore",
            "--nolockcheck",
            "--nodefault",
            "-env:UserInstallation=file://" + str(profile_dir),
            "--convert-to",
            "pdf",
            "--outdir",
            outdir,
            str(docx_path),
        ]
        try:
            result = subprocess.run(command, capture_output=True, timeout=limit, text=True)
        except FileNotFoundError as exc:
            raise DocumentError("pdf_converter_missing", "LibreOffice binary not executable.") from exc
        except subprocess.TimeoutExpired as exc:
            raise DocumentError("pdf_conversion_timeout", "LibreOffice conversion timed out.") from exc

        produced = Path(outdir) / (docx_path.stem + ".pdf")
        if result.returncode != 0 or not produced.exists():
            detail = (result.stderr or result.stdout or "").strip()[-400:]
            raise DocumentError("pdf_conversion_failed", "LibreOffice failed: " + (detail or "unknown error"))
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced), str(pdf_path))

    shutil.rmtree(profile_dir, ignore_errors=True)
