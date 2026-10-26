#!/usr/bin/env python3
"""Probe a llama.cpp server and print a JSON report.

Usage:
    python scripts/probe_model.py --root http://127.0.0.1:8080
"""
from __future__ import annotations

import argparse
import json
import time

import httpx

ZH_SAMPLE = "本系统用于把技术文档翻译成目标语言，并尽可能保留原有格式。第三季度营收同比增长 12.5%，详见 https://example.com/report。"
EN_SAMPLE = "The quarterly report shows a 12.5% increase in revenue, driven by strong demand in APAC. See https://example.com/report for details."


def _get(client: httpx.Client, url: str) -> dict:
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def _post(client: httpx.Client, url: str, payload: dict) -> dict:
    response = client.post(url, json=payload)
    response.raise_for_status()
    return response.json()


def _chat(client: httpx.Client, base: str, alias: str, extra: dict) -> dict:
    payload = {
        "model": alias,
        "messages": [{"role": "user", "content": "用一句话说明什么是机器翻译。"}],
        "max_tokens": 96,
        "temperature": 0.2,
        "stream": False,
    }
    payload.update(extra)
    started = time.time()
    data = _post(client, base + "/v1/chat/completions", payload)
    elapsed = round(time.time() - started, 2)
    choices = data.get("choices") or [{}]
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    return {
        "elapsed_s": elapsed,
        "finish_reason": choices[0].get("finish_reason"),
        "has_think_tag": "<think" in content.lower() or "</think" in content.lower(),
        "has_reasoning_field": bool(message.get("reasoning_content")),
        "content_head": content[:160],
        "usage": data.get("usage"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="http://127.0.0.1:8080")
    parser.add_argument("--alias", default="qwen3.5-9b")
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    root = args.root.rstrip("/")
    report: dict = {"root": root, "checks": {}}
    client = httpx.Client(timeout=httpx.Timeout(args.timeout, connect=10.0))

    try:
        report["checks"]["health"] = _get(client, root + "/health")
    except Exception as exc:
        report["checks"]["health"] = {"error": str(exc)}

    props = None
    try:
        props = _get(client, root + "/props")
        generation = props.get("default_generation_settings") or {}
        report["context"] = {
            "total_slots": props.get("total_slots"),
            "props_n_ctx": generation.get("n_ctx"),
        }
    except Exception as exc:
        report["checks"]["props"] = {"error": str(exc)}

    try:
        slots = _get(client, root + "/slots")
        if isinstance(slots, list):
            ctxs = [slot.get("n_ctx") for slot in slots if isinstance(slot, dict) and slot.get("n_ctx")]
            report["context"]["slot_ctx"] = min(ctxs) if ctxs else None
            report["context"]["slot_count"] = len(slots)
    except Exception as exc:
        report["checks"]["slots"] = {"error": str(exc), "note": "older builds may return 404"}

    try:
        models = _get(client, root + "/v1/models")
        report["models"] = [item.get("id") for item in (models.get("data") or [])]
    except Exception as exc:
        report["checks"]["models"] = {"error": str(exc)}

    try:
        zh = _post(client, root + "/tokenize", {"content": ZH_SAMPLE})
        en = _post(client, root + "/tokenize", {"content": EN_SAMPLE})
        report["tokenize"] = {
            "zh_chars": len(ZH_SAMPLE),
            "zh_tokens": len(zh.get("tokens") or []),
            "en_chars": len(EN_SAMPLE),
            "en_tokens": len(en.get("tokens") or []),
        }
    except Exception as exc:
        report["checks"]["tokenize"] = {"error": str(exc), "note": "endpoint is /tokenize, not /v1/tokenize"}

    try:
        report["chat_json_thinking_off"] = _chat(
            client,
            root,
            args.alias,
            {
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_object"},
            },
        )
    except Exception as exc:
        report["checks"]["chat_json_thinking_off"] = {"error": str(exc)}

    try:
        report["chat_thinking_on"] = _chat(client, root, args.alias, {})
    except Exception as exc:
        report["checks"]["chat_thinking_on"] = {"error": str(exc)}

    ctx = (report.get("context") or {}).get("slot_ctx") or (report.get("context") or {}).get("props_n_ctx")
    if ctx:
        report["estimate"] = {
            "slot_ctx": ctx,
            "kv_gib_q8": round(int(ctx) * 16 * 1024 / (1024 ** 3), 2),
            "note": "q8_0 KV assumes 16 KiB/token for this hybrid architecture",
        }

    client.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
