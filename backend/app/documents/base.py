from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class DocumentError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Unit:
    id: str
    text: str
    location: dict[str, Any]
    protected: bool = False

    def as_payload(self) -> dict[str, str]:
        return {"id": self.id, "text": self.text}


@dataclass
class ParsedDocument:
    units: list[Unit]
    meta: dict[str, Any] = field(default_factory=dict)
    handle: Any = None


class DocumentAdapter(Protocol):
    extensions: tuple[str, ...]

    def parse(self, path: Path, options: dict[str, Any] | None = None) -> ParsedDocument: ...

    def rebuild(self, parsed: ParsedDocument, translations: dict[str, str], out: Path) -> None: ...

    def verify(self, source: Path, out: Path, parsed: ParsedDocument) -> list[dict[str, Any]]: ...
