from __future__ import annotations

import re
import statistics
from pathlib import Path
from typing import Any

try:
    import fitz
except Exception:
    fitz = None

from ..base import DocumentError
from .ir import BBox, Block, DocIR, FontInfo, Page, Span
from .text import flow_text

_BULLET = re.compile(r"^\s*[•·▪◦\-\*]\s+")
_NUMBERED = re.compile(
    r"^\s*(?:第[〇一二三四五六七八九十百千]+[章节篇部]|[0-9]+(?:\.[0-9]+)*[.、)]|[A-Za-z][.、)]|[一二三四五六七八九十]+[、.])\s*"
)
_CAPTION = re.compile(r"^\s*(?:图|表|Figure|Table|Fig\.)\s*[0-9]", re.I)
_PAGE_NUMBER = re.compile(r"^\s*(?:\d{1,4}|[ivxlcdm]{1,7})\s*$", re.I)
_CODE_FONTS = ("courier", "mono", "consolas", "menlo", "code", "source han code")

TOP_BAND = 0.08
BOTTOM_BAND = 0.92


def _hex_color(value: int) -> str:
    return "#%06x" % (value & 0xFFFFFF)


def _span_text(span: dict[str, Any]) -> str:
    chars = span.get("chars")
    if chars:
        return "".join(char.get("c", "") for char in chars)
    return str(span.get("text") or "")


def _font_info(span: dict[str, Any]) -> FontInfo:
    flags = int(span.get("flags") or 0)
    return FontInfo(
        family=str(span.get("font") or ""),
        size=float(span.get("size") or 10.0),
        weight=700 if flags & 16 else 400,
        italic=bool(flags & 2),
        color=_hex_color(int(span.get("color") or 0)),
    )


def _build_block(raw: dict[str, Any], page_index: int, index: int) -> Block | None:
    line_texts: list[str] = []
    spans: list[Span] = []
    weights: list[int] = []
    sizes: list[float] = []
    for line in raw.get("lines") or []:
        line_text = ""
        for span in line.get("spans") or []:
            text = _span_text(span)
            if not text:
                continue
            line_text += text
            spans.append(Span(text=text, font=_font_info(span)))
            sizes.append(float(span.get("size") or 10.0))
            weights.append(700 if int(span.get("flags") or 0) & 16 else 400)
        if line_text.strip():
            line_texts.append(line_text.strip())
    text = flow_text("\n".join(line_texts))
    if len(text) < 1:
        return None
    bbox = raw.get("bbox") or (0, 0, 0, 0)
    return Block(
        id="p" + str(page_index) + "b" + str(index),
        type="paragraph",
        bbox=BBox(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
        page_index=page_index,
        reading_order=0,
        spans=spans,
        source_text=text,
    )


def _split_groups(blocks: list[Block], threshold: float, horizontal: bool) -> list[list[Block]]:
    if horizontal:
        ordered = sorted(blocks, key=lambda block: block.bbox.x0)
        start = lambda block: block.bbox.x0
        end = lambda block: block.bbox.x1
    else:
        ordered = sorted(blocks, key=lambda block: block.bbox.y0)
        start = lambda block: block.bbox.y0
        end = lambda block: block.bbox.y1
    groups: list[list[Block]] = []
    current: list[Block] = []
    far: float | None = None
    for block in ordered:
        if current and far is not None and start(block) > far + threshold:
            groups.append(current)
            current = []
            far = None
        current.append(block)
        far = end(block) if far is None else max(far, end(block))
    if current:
        groups.append(current)
    return groups


def _xy_cut(blocks: list[Block], threshold: float) -> list[Block]:
    if len(blocks) <= 1:
        return blocks
    columns = _split_groups(blocks, threshold, horizontal=True)
    if len(columns) > 1:
        ordered: list[Block] = []
        for column in columns:
            ordered.extend(_xy_cut(column, threshold))
        return ordered
    rows = _split_groups(blocks, threshold, horizontal=False)
    if len(rows) > 1:
        ordered = []
        for row in rows:
            ordered.extend(_xy_cut(row, threshold))
        return ordered
    return sorted(blocks, key=lambda block: (round(block.bbox.y0, 1), round(block.bbox.x0, 1)))


def _body_size(pages: list[Page]) -> float:
    weights: dict[float, int] = {}
    for page in pages:
        for block in page.blocks:
            for span in block.spans:
                key = round(span.font.size * 2) / 2
                weights[key] = weights.get(key, 0) + len(span.text)
    if not weights:
        return 10.5
    return max(weights.items(), key=lambda item: (item[1], item[0]))[0]


def _classify(block: Block, page: Page, body_size: float) -> None:
    text = block.source_text
    max_size = max((span.font.size for span in block.spans), default=body_size)
    bold = any(span.font.weight >= 700 for span in block.spans)
    family = " ".join(span.font.family.lower() for span in block.spans)

    if _PAGE_NUMBER.match(text) and (block.bbox.y1 <= page.height * TOP_BAND or block.bbox.y0 >= page.height * BOTTOM_BAND):
        block.type = "pageNumber"
        return

    if any(marker in family for marker in _CODE_FONTS) and len(text) > 2:
        block.type = "code"
        return

    if _CAPTION.match(text) and max_size <= body_size * 1.05:
        block.type = "caption"
        return

    if max_size >= body_size * 1.15 and len(text) <= 200:
        block.type = "heading"
        ratio = max_size / max(body_size, 1.0)
        block.level = 1 if ratio >= 1.6 else 2 if ratio >= 1.3 else 3
        block.keep_with_next = True
        return

    if bold and len(text) <= 80 and max_size >= body_size:
        block.type = "heading"
        block.level = 3
        block.keep_with_next = True
        return

    if _BULLET.match(text) or _NUMBERED.match(text):
        block.type = "listItem"
        return

    if max_size <= body_size * 0.9 and block.bbox.y0 >= page.height * 0.78:
        block.type = "footnote"
        return

    block.type = "paragraph"


def _mark_running_heads(ir: DocIR) -> None:
    pages = ir.pages
    if len(pages) < 2:
        return
    counts: dict[str, int] = {}
    candidates: list[tuple[Block, Page, str, str]] = []
    for page in pages:
        for block in page.blocks:
            band = None
            if block.bbox.y1 <= page.height * TOP_BAND:
                band = "header"
            elif block.bbox.y0 >= page.height * BOTTOM_BAND:
                band = "footer"
            if band is None:
                continue
            key = re.sub(r"\d+", "#", block.source_text.strip().lower())
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
            candidates.append((block, page, key, band))
    threshold = max(2, int(len(pages) * 0.5))
    for block, _page, key, band in candidates:
        if counts.get(key, 0) >= threshold:
            block.type = band


def parse_pdf(path: Path, lang: str = "auto") -> DocIR:
    if fitz is None:
        raise DocumentError("parser_missing", "PyMuPDF is not installed")
    try:
        document = fitz.open(str(path))
    except Exception as exc:
        raise DocumentError("parse_failed", "cannot open pdf: " + str(exc)) from exc
    if getattr(document, "needs_pass", False):
        document.close()
        raise DocumentError("encrypted_document", "pdf is password protected")

    pages: list[Page] = []
    for page_index in range(document.page_count):
        page = document[page_index]
        page_info = Page(index=page_index, width=float(page.rect.width), height=float(page.rect.height))
        page_info.image_count = len(page.get_images(full=True))
        raw = page.get_text("rawdict")
        for block_index, raw_block in enumerate(raw.get("blocks") or []):
            if raw_block.get("type") != 0:
                continue
            block = _build_block(raw_block, page_index, block_index)
            if block is not None:
                page_info.blocks.append(block)
        pages.append(page_info)

    body_size = _body_size(pages)
    order = 0
    for page_info in pages:
        heights = [block.bbox.height for block in page_info.blocks if block.bbox.height > 0]
        median_height = statistics.median(heights) if heights else 10.0
        threshold = max(6.0, median_height * 0.8)
        ordered = _xy_cut(list(page_info.blocks), threshold)
        for block in ordered:
            _classify(block, page_info, body_size)
            block.reading_order = order
            order += 1
        page_info.blocks = ordered

    ir = DocIR(pages=pages, body_size=body_size, lang=lang)
    _mark_running_heads(ir)

    heading = next((block for block in ir.ordered_blocks() if block.type == "heading"), None)
    if heading is not None:
        ir.title = heading.source_text

    types: dict[str, int] = {}
    for block in ir.ordered_blocks():
        types[block.type] = types.get(block.type, 0) + 1
    ir.stats = {
        "pages": len(pages),
        "blocks": sum(types.values()),
        "types": types,
        "body_size": body_size,
        "images": sum(page.image_count for page in pages),
    }
    document.close()
    return ir
