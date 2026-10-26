from __future__ import annotations

from pathlib import Path

from .base import DocumentAdapter, DocumentError, ParsedDocument, Unit
from .docx_doc import DocxAdapter
from .pdf_doc import PdfAdapter
from .text_doc import TextAdapter
from .xlsx_doc import XlsxAdapter

ADAPTERS = [DocxAdapter(), XlsxAdapter(), PdfAdapter(), TextAdapter()]
SUPPORTED_EXT = tuple(ext for adapter in ADAPTERS for ext in adapter.extensions)


def output_suffix_for(path: Path) -> str:
    ext = path.suffix.lower()
    for adapter in ADAPTERS:
        if ext in adapter.extensions:
            declared = getattr(adapter, "output_suffix", None)
            return declared or ext
    return ext


def get_adapter(path: Path) -> DocumentAdapter:
    ext = path.suffix.lower()
    for adapter in ADAPTERS:
        if ext in adapter.extensions:
            return adapter
    raise DocumentError("unsupported_format", "unsupported extension: " + (ext or "none"))


__all__ = [
    "ADAPTERS",
    "SUPPORTED_EXT",
    "DocumentAdapter",
    "DocumentError",
    "ParsedDocument",
    "Unit",
    "get_adapter",
    "output_suffix_for",
]
