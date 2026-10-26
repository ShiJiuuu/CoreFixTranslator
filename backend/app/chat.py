from __future__ import annotations

import json
from typing import Any

from . import db
from .translate.segmenter import estimate_tokens

SYSTEM_PROMPT = """你是部署在局域网服务器上的 AI 助手，帮助用户理解文档、翻译和整理信息。
回答简洁、准确、直接；不确定的内容要说明不确定。
附件正文会以文本节选的方式附在用户消息后面（可能被截断）；没有提供的内容不要假装看过。"""


def build_context(chat_id: str, settings: dict[str, Any], slot_ctx: int) -> list[dict[str, str]]:
    """Build a bounded chat context from stored messages.

    Budget is a fraction of the slot context minus the reserved output tokens.
    Oldest turns are dropped first; the system prompt always stays.
    """
    ratio = float(settings.get("chat_context_ratio", 0.6))
    reserve = int(settings.get("chat_max_output_tokens", 2048))
    max_turns = int(settings.get("chat_max_history_turns", 20))
    budget = max(512, int(max(1024, slot_ctx) * ratio) - reserve)

    history = db.messages_with_attachments(chat_id)
    selected: list[dict[str, str]] = []
    used = estimate_tokens(SYSTEM_PROMPT)

    for message in reversed(history):
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        text = (message.get("content") or "").strip()
        try:
            meta = json.loads(message.get("meta_json") or "{}")
        except json.JSONDecodeError:
            meta = {}
        attachment_text = str(meta.get("attachment_text") or "").strip()
        if attachment_text:
            text = text + "\n\n[附件内容，供参考，可能已截断]\n" + attachment_text
        if not text:
            continue
        cost = estimate_tokens(text)
        if len(selected) >= max_turns or used + cost > budget:
            break
        selected.append({"role": role, "content": text})
        used += cost

    selected.reverse()
    return [{"role": "system", "content": SYSTEM_PROMPT}] + selected
