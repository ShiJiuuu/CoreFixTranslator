from __future__ import annotations

from pathlib import Path

from . import get_adapter


def extract_plain_text(path: Path, max_chars: int = 8000) -> str:
    """Extract readable text from a supported document for chat context."""
    adapter = get_adapter(path)
    parsed = adapter.parse(path)
    parts = [unit.text.strip() for unit in parsed.units if unit.text.strip()]
    text = "\n".join(parts)
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[内容已截断]"
    return text
