from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document

from .base import DocumentError, ParsedDocument, Unit

try:
    import fitz
except Exception:
    fitz = None


class PdfAdapter:
    extensions = (".pdf",)

    def parse(self, path: Path, options: dict[str, Any] | None = None) -> ParsedDocument:
        if fitz is None:
            raise DocumentError("parser_missing", "PyMuPDF is not installed")
        try:
            document = fitz.open(str(path))
        except Exception as exc:
            raise DocumentError("parse_failed", "cannot open pdf: " + str(exc)) from exc

        if getattr(document, "needs_pass", False):
            document.close()
            raise DocumentError("encrypted_document", "pdf is password protected")

        units: list[Unit] = []
        pages_with_text = 0
        empty_pages = 0
        for page_index in range(document.page_count):
            page = document[page_index]
            blocks = page.get_text("blocks") or []
            text_blocks = [block for block in blocks if len(block) >= 7 and block[6] == 0]
            text_blocks.sort(key=lambda block: (round(block[1], 1), round(block[0], 1)))
            page_units = 0
            for block_index, block in enumerate(text_blocks):
                text = str(block[4]).strip()
                if len(text) < 2:
                    continue
                units.append(
                    Unit(
                        id="p" + str(page_index) + "b" + str(block_index),
                        text=text,
                        location={"type": "pdf_block", "page": page_index, "block": block_index},
                    )
                )
                page_units += 1
            if page_units:
                pages_with_text += 1
            else:
                empty_pages += 1

        meta = {"pages": document.page_count, "pages_with_text": pages_with_text, "empty_pages": empty_pages}
        document.close()
        return ParsedDocument(units=units, meta=meta, handle={})

    def rebuild(self, parsed: ParsedDocument, translations: dict[str, str], out: Path) -> None:
        document = Document()
        last_page = None
        for unit in parsed.units:
            page = int(unit.location.get("page", 0))
            if last_page is not None and page != last_page:
                document.add_page_break()
            last_page = page
            document.add_paragraph(translations.get(unit.id) or unit.text)
        out.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(out))

    def verify(self, source: Path, out: Path, parsed: ParsedDocument) -> list[dict[str, Any]]:
        try:
            document = Document(str(out))
        except Exception as exc:
            return [{"check": "reopen", "ok": False, "detail": str(exc)}]
        return [
            {
                "check": "paragraphs",
                "ok": len(document.paragraphs) >= len(parsed.units),
                "expected_at_least": len(parsed.units),
                "output": len(document.paragraphs),
            }
        ]
