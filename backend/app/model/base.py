from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ModelError(Exception):
    code = "model_error"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class ModelUnreachable(ModelError):
    code = "model_unreachable"


class ModelTimeout(ModelError):
    code = "model_timeout"


class ModelBadResponse(ModelError):
    code = "invalid_model_output"


@dataclass
class ChatResult:
    text: str
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
