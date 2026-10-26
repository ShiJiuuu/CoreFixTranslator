from __future__ import annotations

import re
from typing import Any


def parse_glossary(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            src, dst = line.split("=>", 1)
        elif "\t" in line:
            src, dst = line.split("\t", 1)
        else:
            continue
        src, dst = src.strip(), dst.strip()
        if src and dst:
            pairs.append((src, dst))
    return pairs


def match_terms(text: str, terms: list[tuple[str, str]]) -> list[tuple[str, str]]:
    lowered = text.casefold()
    hits: list[tuple[str, str]] = []
    for src, dst in sorted(terms, key=lambda pair: len(pair[0]), reverse=True):
        if src.casefold() in lowered:
            hits.append((src, dst))
    return hits


def gather_terms(units: list[dict[str, Any]], terms: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for unit in units:
        for src, dst in match_terms(str(unit.get("text", "")), terms):
            seen.setdefault(src, dst)
    return list(seen.items())


def check_glossary(
    units: list[dict[str, Any]], translations: dict[str, str], terms: list[tuple[str, str]]
) -> dict[str, Any]:
    violated: list[dict[str, str]] = []
    for unit in units:
        unit_id = str(unit.get("id"))
        source = str(unit.get("text", ""))
        target = translations.get(unit_id, "")
        for src, dst in match_terms(source, terms):
            if not re.search(re.escape(dst), target, re.I):
                violated.append({"id": unit_id, "term": src, "expected": dst})
    return {"violations": violated, "checked": len(units)}
