from __future__ import annotations

import re
from typing import Any

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    other = max(0, len(text) - cjk)
    return int(cjk + other * 0.3) + 1


def compute_budget(settings: dict[str, Any], slot_ctx: int) -> tuple[int, int, int]:
    slot_ctx = max(1024, int(slot_ctx or 8192))
    max_output = max(256, int(settings.get("max_output_tokens", 6144)))
    target_output = max(128, int(settings.get("target_output_tokens", 2500)))
    expansion = max(0.5, float(settings.get("token_expansion", 1.3)))
    overhead = max(0, int(settings.get("prompt_overhead_tokens", 800)))

    output_cap = min(int(0.35 * slot_ctx), max_output)
    target = min(output_cap, target_output)
    text_budget = min(int(0.55 * slot_ctx) - overhead, target / expansion)
    return max(200, int(text_budget)), output_cap, target


def pack_batches(units: list[dict[str, Any]], max_tokens: int, max_units: int) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    used = 0
    for unit in units:
        cost = estimate_tokens(unit.get("text", ""))
        if current and (len(current) >= max_units or used + cost > max_tokens):
            batches.append(current)
            current = []
            used = 0
        current.append(unit)
        used += cost
    if current:
        batches.append(current)
    return batches
