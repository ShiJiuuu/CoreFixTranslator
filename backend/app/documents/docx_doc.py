from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Iterator

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .base import DocumentError, ParsedDocument, Unit


def _set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    runs = paragraph.runs
    if runs:
        runs[0].text = text
        for run in runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def _iter_paragraphs(element: Any) -> Iterator[Paragraph]:
    # Walk every w:p under the part, including table cells, nested tables and sdt.
    for node in element.iter(qn("w:p")):
        yield Paragraph(node, None)


class DocxAdapter:
    extensions = (".docx",)

    def parse(self, path: Path, options: dict[str, Any] | None = None) -> ParsedDocument:
        options = options or {}
        try:
            doc = Document(str(path))
        except Exception as exc:
            raise DocumentError("parse_failed", "cannot open docx: " + str(exc)) from exc

        mapping: dict[str, Any] = {}
        units: list[Unit] = []
        skipped_links = 0
        index = 0

        for paragraph in _iter_paragraphs(doc.element.body):
            text = paragraph.text.strip()
            if not text:
                continue
            if getattr(paragraph, "hyperlinks", None):
                skipped_links += 1
                continue
            unit_id = "p" + str(index)
            index += 1
            units.append(Unit(id=unit_id, text=text, location={"type": "paragraph", "index": index}))
            mapping[unit_id] = paragraph

        headers = 0
        if options.get("translate_headers", False):
            for si, section in enumerate(doc.sections):
                for prefix, part in (("h", section.header), ("f", section.footer)):
                    for pi, paragraph in enumerate(_iter_paragraphs(part._element)):
                        text = paragraph.text.strip()
                        if not text:
                            continue
                        unit_id = prefix + str(si) + "p" + str(pi)
                        units.append(
                            Unit(id=unit_id, text=text, location={"type": prefix, "section": si, "index": pi})
                        )
                        mapping[unit_id] = paragraph
                        headers += 1

        meta = {
            "paragraphs": len(doc.paragraphs),
            "tables": len(doc.tables),
            "xml_paragraphs": len(units),
            "header_footer_units": headers,
            "skipped_hyperlinks": skipped_links,
        }
        return ParsedDocument(units=units, meta=meta, handle={"doc": doc, "mapping": mapping})

    def rebuild(self, parsed: ParsedDocument, translations: dict[str, str], out: Path) -> None:
        doc = parsed.handle["doc"]
        mapping = parsed.handle["mapping"]
        for unit_id, translated in translations.items():
            paragraph = mapping.get(unit_id)
            if paragraph is None:
                continue
            _set_paragraph_text(paragraph, translated)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))

    def verify(self, source: Path, out: Path, parsed: ParsedDocument) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        try:
            with zipfile.ZipFile(out) as archive:
                bad = archive.testzip()
            checks.append({"check": "zip_integrity", "ok": bad is None, "detail": bad})
        except Exception as exc:
            checks.append({"check": "zip_integrity", "ok": False, "detail": str(exc)})
            return checks

        try:
            doc = Document(str(out))
        except Exception as exc:
            checks.append({"check": "reopen", "ok": False, "detail": str(exc)})
            return checks

        expected_paragraphs = int(parsed.meta.get("paragraphs", 0))
        expected_tables = int(parsed.meta.get("tables", 0))
        checks.append(
            {
                "check": "paragraph_count",
                "ok": len(doc.paragraphs) == expected_paragraphs,
                "source": expected_paragraphs,
                "output": len(doc.paragraphs),
            }
        )
        checks.append(
            {
                "check": "table_count",
                "ok": len(doc.tables) == expected_tables,
                "source": expected_tables,
                "output": len(doc.tables),
            }
        )
        return checks
