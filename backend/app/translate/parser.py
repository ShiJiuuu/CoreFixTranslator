from __future__ import annotations

import json
import re
from typing import Any

_THINK_CLOSED = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.S | re.I)
_THINK_OPEN = re.compile(r"<think\b[^>]*>.*\Z", re.S | re.I)
_PLAIN_THINK = re.compile(r"^\s*Thinking Process:.*?(?=\n\s*\n|\Z)", re.S | re.I)
_FENCE = re.compile(r"^\s*(?:\x60{3}|~~~)[a-zA-Z0-9_-]*\s*$", re.M)


def strip_think(text: str) -> str:
    text = _THINK_CLOSED.sub("", text)
    text = _THINK_OPEN.sub("", text)
    text = _PLAIN_THINK.sub("", text)
    return text


def strip_fences(text: str) -> str:
    return _FENCE.sub("", text)


def extract_first_json(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def parse_translations(raw: str, expected_ids: list[str]) -> tuple[dict[str, str], dict[str, Any]]:
    issues: dict[str, Any] = {
        "parse_error": None,
        "missing": [],
        "unknown": [],
        "duplicated": [],
        "empty": [],
        "truncated": False,
    }
    clean = strip_fences(strip_think(raw or "")).strip()
    if not clean:
        issues["parse_error"] = "empty_output"
        issues["missing"] = list(expected_ids)
        return {}, issues

    blob = extract_first_json(clean)
    if blob is None:
        if clean.startswith("{") and not clean.endswith("}"):
            issues["truncated"] = True
        issues["parse_error"] = "no_json_object"
        issues["missing"] = list(expected_ids)
        return {}, issues

    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        issues["parse_error"] = "invalid_json: " + str(exc)
        issues["missing"] = list(expected_ids)
        return {}, issues

    items: list[Any] = []
    if isinstance(data, dict):
        raw_items = data.get("translations")
        if isinstance(raw_items, list):
            items = raw_items
        elif isinstance(data.get("segments"), list):
            items = data["segments"]
        else:
            issues["parse_error"] = "missing_translations_key"
            issues["missing"] = list(expected_ids)
            return {}, issues
    elif isinstance(data, list):
        items = data
    else:
        issues["parse_error"] = "unexpected_root_type"
        issues["missing"] = list(expected_ids)
        return {}, issues

    allowed = set(expected_ids)
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        text = item.get("text", item.get("translation"))
        if not isinstance(item_id, str) or item_id not in allowed:
            if isinstance(item_id, str):
                issues["unknown"].append(item_id)
            continue
        if item_id in result:
            issues["duplicated"].append(item_id)
            continue
        if not isinstance(text, str) or not text.strip():
            issues["empty"].append(item_id)
            continue
        result[item_id] = text

    issues["missing"] = [item_id for item_id in expected_ids if item_id not in result]
    return result, issues
