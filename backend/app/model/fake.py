from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from .base import ChatResult


class FakeAdapter:
    """Deterministic adapter for tests and offline demos."""

    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = settings or {}

    def health(self) -> bool:
        return True

    def info(self) -> dict[str, Any]:
        return {"root": "fake", "base": "fake", "alias": "fake", "total_slots": 1, "slot_ctx": 32768}

    def tokenize(self, text: str) -> int:
        return max(1, len(text) // 2)

    def chat(
        self, messages: list[dict[str, str]], *, temperature: float, max_tokens: int, json_mode: bool = False
    ) -> ChatResult:
        last_user = ""
        for message in messages:
            if message.get("role") == "user":
                last_user = message.get("content", "")
        text = "（假模型）收到：" + last_user[-120:]
        return ChatResult(text=text, finish_reason="stop", usage={})

    async def chat_stream(
        self, messages: list[dict[str, str]], *, temperature: float, max_tokens: int
    ) -> AsyncIterator[str]:
        last_user = ""
        for message in messages:
            if message.get("role") == "user":
                last_user = message.get("content", "")
        text = "（假模型）收到：" + last_user[-120:] + "。这是用于界面联调的流式回复。"
        for index in range(0, len(text), 6):
            await asyncio.sleep(0)
            yield text[index : index + 6]

    def translate_batch(
        self,
        units: list[dict[str, str]],
        *,
        source_lang: str,
        target_lang: str,
        style: str | None,
        domain: str | None,
        glossary: list[tuple[str, str]] | None,
        max_tokens: int,
        temperature: float,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        translations = {unit["id"]: "[" + target_lang + "] " + unit["text"] for unit in units}
        return translations, {"finish_reason": "stop", "usage": {}, "issues": {}, "raw_chars": 0}

    def close(self) -> None:
        return None
