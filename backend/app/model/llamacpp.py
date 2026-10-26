from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from ..translate.parser import parse_translations
from ..translate.prompt import build_messages
from .base import ChatResult, ModelBadResponse, ModelTimeout, ModelUnreachable


def _short(text: str, limit: int = 300) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "..."


def estimate_tokens(text: str) -> int:
    cjk = 0
    for char in text:
        if "\u3400" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff":
            cjk += 1
    other = max(0, len(text) - cjk)
    return int(cjk + other * 0.3) + 1


class _ThinkFilter:
    """Drop think blocks from a stream, tolerating tags split across chunks."""

    def __init__(self) -> None:
        self.buf = ""
        self.in_think = False

    def feed(self, text: str) -> str:
        self.buf += text
        out: list[str] = []
        while True:
            lower = self.buf.lower()
            if self.in_think:
                end = lower.find("</think")
                if end < 0:
                    if len(self.buf) > 20000:
                        self.buf = self.buf[-2000:]
                    break
                close = self.buf.find(">", end)
                if close < 0:
                    break
                self.buf = self.buf[close + 1:]
                self.in_think = False
                continue
            start = lower.find("<think")
            if start < 0:
                if len(self.buf) > 8:
                    out.append(self.buf[:-8])
                    self.buf = self.buf[-8:]
                break
            if start > 0:
                out.append(self.buf[:start])
                self.buf = self.buf[start:]
                continue
            open_end = self.buf.find(">")
            if open_end < 0:
                if len(self.buf) > 64:
                    self.buf = ""
                break
            self.buf = self.buf[open_end + 1:]
            self.in_think = True
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self.in_think else self.buf
        self.buf = ""
        self.in_think = False
        return rest


class LlamaCppAdapter:
    def __init__(self, settings: dict[str, Any]):
        self.root = str(settings.get("model_root_url", "http://127.0.0.1:8080")).rstrip("/")
        self.base = str(settings.get("model_base_url", self.root + "/v1")).rstrip("/")
        self.alias = str(settings.get("model_alias", "qwen3.5-9b"))
        self.timeout = float(settings.get("model_timeout_seconds", 300))
        self.enable_thinking = bool(settings.get("enable_thinking", False))
        self.json_mode = str(settings.get("json_mode", "auto"))
        self.top_p = float(settings.get("top_p", 0.9))
        self.top_k = int(settings.get("top_k", 20))
        self.repeat_penalty = float(settings.get("repeat_penalty", 1.05))
        self.seed = int(settings.get("seed", 42))
        self._client = httpx.Client(timeout=httpx.Timeout(self.timeout, connect=10.0))
        self._info: dict[str, Any] | None = None
        self._tokens: dict[str, int] = {}

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.ConnectError as exc:
            raise ModelUnreachable("cannot reach model at " + self.root + ": " + str(exc)) from exc
        except httpx.ReadTimeout as exc:
            raise ModelTimeout("model timed out after " + str(self.timeout) + " seconds") from exc
        except httpx.HTTPError as exc:
            raise ModelUnreachable("model request failed: " + str(exc)) from exc
        if response.status_code >= 400:
            raise ModelBadResponse("model HTTP " + str(response.status_code) + ": " + _short(response.text))
        return response

    def _json(self, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
        response = self._request(method, url, json=payload)
        try:
            return response.json()
        except ValueError as exc:
            raise ModelBadResponse("model returned non-JSON: " + _short(response.text)) from exc

    def health(self) -> bool:
        try:
            return self._client.get(self.root + "/health", timeout=10.0).status_code == 200
        except httpx.HTTPError:
            return False

    def info(self) -> dict[str, Any]:
        if self._info is not None:
            return self._info
        data: dict[str, Any] = {"root": self.root, "base": self.base, "alias": self.alias}
        try:
            props = self._json("GET", self.root + "/props")
            generation = props.get("default_generation_settings") or {}
            data["total_slots"] = props.get("total_slots")
            data["slot_ctx"] = generation.get("n_ctx")
        except Exception as exc:
            data["props_error"] = str(exc)
        try:
            slots = self._json("GET", self.root + "/slots")
            if isinstance(slots, list):
                ctxs = [slot.get("n_ctx") for slot in slots if isinstance(slot, dict) and slot.get("n_ctx")]
                data["slots"] = [{"n_ctx": slot.get("n_ctx"), "busy": slot.get("is_processing")} for slot in slots if isinstance(slot, dict)]
                if ctxs:
                    data["slot_ctx"] = min(ctxs)
        except Exception as exc:
            data["slots_error"] = str(exc)
        try:
            models = self._json("GET", self.base + "/models")
            items = models.get("data") or []
            data["model_ids"] = [item.get("id") for item in items]
            if items and items[0].get("id"):
                data["resolved_model"] = items[0]["id"]
        except Exception as exc:
            data["models_error"] = str(exc)
        if not data.get("slot_ctx"):
            data["slot_ctx"] = 8192
        self._info = data
        return data

    def tokenize(self, text: str) -> int:
        if not text:
            return 0
        if text in self._tokens:
            return self._tokens[text]
        try:
            data = self._json("POST", self.root + "/tokenize", {"content": text})
            tokens = data.get("tokens")
            count = len(tokens) if isinstance(tokens, list) else int(data.get("n_tokens") or 0)
        except Exception:
            count = estimate_tokens(text)
        if len(self._tokens) > 4096:
            self._tokens.clear()
        self._tokens[text] = count
        return count

    def chat(self, messages: list[dict[str, str]], *, temperature: float, max_tokens: int, json_mode: bool = False) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.alias,
            "messages": messages,
            "temperature": temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repeat_penalty": self.repeat_penalty,
            "seed": self.seed,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if not self.enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if json_mode and self.json_mode in ("auto", "json_object"):
            payload["response_format"] = {"type": "json_object"}

        data = self._json("POST", self.base + "/chat/completions", payload)
        choices = data.get("choices") or []
        if not choices:
            raise ModelBadResponse("model returned no choices")
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        if not content and message.get("reasoning_content"):
            content = message["reasoning_content"]
        if not content:
            raise ModelBadResponse("model returned empty content")
        return ChatResult(text=content, finish_reason=choice.get("finish_reason"), usage=data.get("usage") or {})

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
        messages = build_messages(
            units,
            source_lang=source_lang,
            target_lang=target_lang,
            style=style,
            domain=domain,
            glossary=glossary or [],
        )
        result = self.chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True)
        expected = [unit["id"] for unit in units]
        translations, issues = parse_translations(result.text, expected)
        meta = {
            "finish_reason": result.finish_reason,
            "usage": result.usage,
            "issues": issues,
            "raw_chars": len(result.text),
        }
        return translations, meta

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": self.alias,
            "messages": messages,
            "temperature": temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repeat_penalty": self.repeat_penalty,
            "seed": self.seed,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if not self.enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        timeout = httpx.Timeout(self.timeout, connect=10.0)
        filter_ = _ThinkFilter()
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", self.base + "/chat/completions", json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise ModelBadResponse("model HTTP " + str(response.status_code) + ": " + _short(body))
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    piece = delta.get("content") or ""
                    if not piece:
                        continue
                    visible = filter_.feed(piece)
                    if visible:
                        yield visible
        tail = filter_.flush()
        if tail:
            yield tail

    def close(self) -> None:
        self._client.close()
