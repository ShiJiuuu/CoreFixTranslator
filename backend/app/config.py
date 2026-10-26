from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def default_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def _s(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return int(default)


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return float(default)


def _b(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def app_env() -> dict[str, Any]:
    return {
        "host": _s("APP_HOST", "0.0.0.0"),
        "port": _i("APP_PORT", 8000),
        "data_dir": _s("DATA_DIR", "./data"),
    }


def env_defaults() -> dict[str, Any]:
    root = _s("MODEL_ROOT_URL", "http://127.0.0.1:8080").rstrip("/")
    base = _s("MODEL_BASE_URL", root + "/v1").rstrip("/")
    return {
        "model_root_url": root,
        "model_base_url": base,
        "model_alias": _s("MODEL_ALIAS", "qwen3.5-9b"),
        "model_timeout_seconds": _i("MODEL_TIMEOUT_SECONDS", 300),
        "enable_thinking": _b("MODEL_ENABLE_THINKING", False),
        "json_mode": _s("MODEL_JSON_MODE", "auto"),
        "temperature_translate": _f("MODEL_TEMPERATURE_TRANSLATE", 0.25),
        "top_p": _f("MODEL_TOP_P", 0.9),
        "top_k": _i("MODEL_TOP_K", 20),
        "repeat_penalty": _f("MODEL_REPEAT_PENALTY", 1.05),
        "seed": _i("MODEL_SEED", 42),
        "max_output_tokens": _i("TRANSLATION_MAX_OUTPUT_TOKENS", 6144),
        "target_output_tokens": _i("TRANSLATION_TARGET_OUTPUT_TOKENS", 2500),
        "token_expansion": _f("TRANSLATION_TOKEN_EXPANSION", 1.3),
        "prompt_overhead_tokens": _i("PROMPT_OVERHEAD_TOKENS", 800),
        "max_units_per_batch": _i("TRANSLATION_MAX_UNITS_PER_BATCH", 40),
        "max_upload_mb": _i("MAX_UPLOAD_SIZE_MB", 100),
        "default_target_language": _s("DEFAULT_TARGET_LANGUAGE", "zh-CN"),
        "temperature_chat": _f("MODEL_TEMPERATURE_CHAT", 0.7),
        "chat_context_ratio": _f("CHAT_CONTEXT_RATIO", 0.6),
        "chat_max_history_turns": _i("CHAT_MAX_HISTORY_TURNS", 20),
        "chat_max_output_tokens": _i("CHAT_MAX_OUTPUT_TOKENS", 2048),
        "chat_attachment_max_chars": _i("CHAT_ATTACHMENT_MAX_CHARS", 8000),
        "chat_attachment_total_chars": _i("CHAT_ATTACHMENT_TOTAL_CHARS", 16000),
    }


NUMERIC_RULES: dict[str, tuple[str, float, float]] = {
    "model_timeout_seconds": ("int", 10, 3600),
    "temperature_translate": ("float", 0.0, 2.0),
    "top_p": ("float", 0.0, 1.0),
    "top_k": ("int", 0, 200),
    "repeat_penalty": ("float", 1.0, 2.0),
    "seed": ("int", 0, 2147483647),
    "max_output_tokens": ("int", 256, 32768),
    "target_output_tokens": ("int", 128, 32768),
    "token_expansion": ("float", 0.5, 3.0),
    "prompt_overhead_tokens": ("int", 0, 8192),
    "max_units_per_batch": ("int", 1, 200),
    "max_upload_mb": ("int", 1, 1024),
    "temperature_chat": ("float", 0.0, 2.0),
    "chat_context_ratio": ("float", 0.2, 0.95),
    "chat_max_history_turns": ("int", 1, 100),
    "chat_max_output_tokens": ("int", 256, 8192),
    "chat_attachment_max_chars": ("int", 500, 100000),
    "chat_attachment_total_chars": ("int", 500, 200000),
}

EDITABLE_KEYS = [
    "model_root_url",
    "model_base_url",
    "model_alias",
    "model_timeout_seconds",
    "enable_thinking",
    "json_mode",
    "temperature_translate",
    "top_p",
    "top_k",
    "repeat_penalty",
    "seed",
    "max_output_tokens",
    "target_output_tokens",
    "token_expansion",
    "prompt_overhead_tokens",
    "max_units_per_batch",
    "max_upload_mb",
    "default_target_language",
    "temperature_chat",
    "chat_context_ratio",
    "chat_max_history_turns",
    "chat_max_output_tokens",
    "chat_attachment_max_chars",
    "chat_attachment_total_chars",
]


class ConfigError(ValueError):
    pass


def validate_patch(patch: dict[str, Any]) -> dict[str, Any]:
    unknown = [key for key in patch if key not in EDITABLE_KEYS]
    if unknown:
        raise ConfigError("unknown setting: " + ", ".join(unknown))

    clean: dict[str, Any] = {}
    for key, value in patch.items():
        if key in NUMERIC_RULES:
            kind, low, high = NUMERIC_RULES[key]
            try:
                number = int(value) if kind == "int" else float(value)
            except (TypeError, ValueError):
                raise ConfigError(key + " must be numeric")
            if number < low or number > high:
                raise ConfigError(key + " out of range [" + str(low) + ", " + str(high) + "]")
            clean[key] = number
        elif key == "enable_thinking":
            if isinstance(value, str):
                clean[key] = value.strip().lower() in ("1", "true", "yes", "on")
            else:
                clean[key] = bool(value)
        elif key == "json_mode":
            if value not in ("auto", "json_object", "none"):
                raise ConfigError("json_mode must be auto | json_object | none")
            clean[key] = value
        elif key in ("model_root_url", "model_base_url"):
            text = str(value).strip().rstrip("/")
            if not (text.startswith("http://") or text.startswith("https://")):
                raise ConfigError(key + " must start with http:// or https://")
            clean[key] = text
        elif key in ("model_alias", "default_target_language"):
            text = str(value).strip()
            if not text:
                raise ConfigError(key + " must not be empty")
            clean[key] = text
        else:
            clean[key] = value
    return clean
