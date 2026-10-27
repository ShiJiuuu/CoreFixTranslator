from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class FontInfo:
    family: str = ""
    size: float = 10.0
    weight: int = 400
    italic: bool = False
    color: str = "#000000"


@dataclass
class Span:
    text: str
    font: FontInfo


@dataclass
class Block:
    id: str
    type: str
    bbox: BBox
    page_index: int
    reading_order: int
    spans: list[Span]
    source_text: str
    level: int | None = None
    keep_with_next: bool = False
    no_reflow: bool = False
    col_span: int = 1
    target_text: str | None = None
    overflow: bool = False

    def final_text(self) -> str:
        return (self.target_text or self.source_text).strip()


@dataclass
class Page:
    index: int
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)
    margin: dict[str, float] = field(default_factory=lambda: {"top": 36, "right": 36, "bottom": 36, "left": 36})
    image_count: int = 0


@dataclass
class DocIR:
    pages: list[Page] = field(default_factory=list)
    body_size: float = 10.5
    title: str | None = None
    lang: str = "auto"
    stats: dict[str, Any] = field(default_factory=dict)

    def ordered_blocks(self) -> list[Block]:
        blocks: list[Block] = []
        for page in self.pages:
            blocks.extend(sorted(page.blocks, key=lambda block: block.reading_order))
        return sorted(blocks, key=lambda block: block.reading_order)
