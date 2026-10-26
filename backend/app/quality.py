from __future__ import annotations

import re
from typing import Any

from .documents.base import Unit

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_URL = re.compile(r"https?://[^\s<>\"')]+", re.I)
_PLACEHOLDER = re.compile(r"\{[^{}\n]{1,60}\}|%[sd]\b|%\([A-Za-z0-9_]+\)s|\[\[[^\]\n]{1,60}\]\]")


def check_units(units: list[Unit], translations: dict[str, str]) -> dict[str, Any]:
    empty: list[str] = []
    numbers: list[str] = []
    urls: list[str] = []
    placeholders: list[str] = []

    for unit in units:
        text = translations.get(unit.id, "")
        if not text.strip():
            empty.append(unit.id)
            continue
        source_numbers = set(_NUMBER.findall(unit.text))
        if source_numbers and not source_numbers.issubset(set(_NUMBER.findall(text))):
            numbers.append(unit.id)
        source_urls = set(_URL.findall(unit.text))
        if source_urls and not source_urls.issubset(set(_URL.findall(text))):
            urls.append(unit.id)
        source_marks = set(_PLACEHOLDER.findall(unit.text))
        if source_marks and not source_marks.issubset(set(_PLACEHOLDER.findall(text))):
            placeholders.append(unit.id)

    total = len(units)
    translated = total - len(empty)
    return {
        "total": total,
        "translated": translated,
        "empty": empty,
        "number_mismatch": numbers,
        "url_mismatch": urls,
        "placeholder_mismatch": placeholders,
        "ratios": {
            "translated": round(translated / total, 4) if total else 1.0,
            "number_ok": round(1 - len(numbers) / total, 4) if total else 1.0,
            "url_ok": round(1 - len(urls) / total, 4) if total else 1.0,
            "placeholder_ok": round(1 - len(placeholders) / total, 4) if total else 1.0,
        },
    }
