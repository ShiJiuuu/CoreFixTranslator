from __future__ import annotations

import os
from typing import Any

from .fake import FakeAdapter
from .llamacpp import LlamaCppAdapter


def make_model(settings: dict[str, Any]):
    """Return the configured backend. MODEL_BACKEND=fake enables offline demos and tests."""
    if os.environ.get("MODEL_BACKEND", "llama").strip().lower() == "fake":
        return FakeAdapter(settings)
    return LlamaCppAdapter(settings)
