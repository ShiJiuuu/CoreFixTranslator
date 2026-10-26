from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import DocumentError, ParsedDocument, Unit


class TextAdapter:
    extensions = (".txt", ".md")

    def parse(self, path: Path, options: dict[str, Any] | None = None) -> ParsedDocument:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError as exc:
                raise DocumentError("parse_failed", "text file is not valid UTF-8") from exc

        lines = text.splitlines()
        units = [
            Unit(id="l" + str(index), text=line.strip(), location={"line": index})
            for index, line in enumerate(lines)
            if line.strip()
        ]
        return ParsedDocument(units=units, meta={"lines": len(lines)}, handle=lines)

    def rebuild(self, parsed: ParsedDocument, translations: dict[str, str], out: Path) -> None:
        lines = list(parsed.handle or [])
        for unit in parsed.units:
            line_no = int(unit.location["line"])
            translated = translations.get(unit.id)
            if translated:
                lines[line_no] = translated
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def verify(self, source: Path, out: Path, parsed: ParsedDocument) -> list[dict[str, Any]]:
        lines = out.read_text(encoding="utf-8").splitlines()
        return [
            {
                "check": "line_count",
                "ok": len(lines) == int(parsed.meta.get("lines", 0)),
                "source": parsed.meta.get("lines"),
                "output": len(lines),
            }
        ]
