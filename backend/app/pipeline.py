from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .documents import get_adapter
from .documents.base import DocumentError
from .quality import check_units
from .translate.glossary import check_glossary, gather_terms
from .translate.segmenter import compute_budget, pack_batches


class PipelineError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


ProgressFn = Callable[[str, int, int, int], None]
CancelFn = Callable[[], bool]


def _noop(stage: str, percent: int, done: int, total: int) -> None:
    return None


def translate_document(
    source_path: Path,
    out_path: Path,
    *,
    settings: dict[str, Any],
    model: Any,
    source_lang: str,
    target_lang: str,
    style: str | None = None,
    domain: str | None = None,
    glossary: list[tuple[str, str]] | None = None,
    options: dict[str, Any] | None = None,
    progress: ProgressFn | None = None,
    cancel: CancelFn | None = None,
) -> dict[str, Any]:
    started = time.time()
    report_progress = progress or _noop
    should_cancel = cancel or (lambda: False)
    glossary = glossary or []
    options = options or {}

    try:
        adapter = get_adapter(source_path)
        parsed = adapter.parse(source_path, options)
    except DocumentError:
        raise
    except Exception as exc:
        raise PipelineError("parse_failed", str(exc)) from exc

    if not parsed.units:
        raise PipelineError("no_translatable_units", "no translatable text found in document")

    report_progress("parsing", 2, 0, len(parsed.units))

    info: dict[str, Any] = {}
    try:
        info = model.info() or {}
    except Exception:
        info = {}
    slot_ctx = int(info.get("slot_ctx") or 8192)

    text_budget, output_cap, target_output = compute_budget(settings, slot_ctx)
    payload = [unit.as_payload() for unit in parsed.units]
    batches = pack_batches(payload, text_budget, int(settings.get("max_units_per_batch", 40)))

    translations: dict[str, str] = {}
    failed: list[dict[str, str]] = []
    retries = 0

    for index, batch in enumerate(batches):
        if should_cancel():
            raise PipelineError("cancelled_by_user", "cancelled by user")

        batch_terms = gather_terms(batch, glossary)
        try:
            got, _meta = model.translate_batch(
                batch,
                source_lang=source_lang,
                target_lang=target_lang,
                style=style,
                domain=domain,
                glossary=batch_terms,
                max_tokens=output_cap,
                temperature=float(settings.get("temperature_translate", 0.25)),
            )
        except Exception as exc:
            code = getattr(exc, "code", "model_error")
            raise PipelineError(code, str(exc)) from exc

        translations.update(got)
        missing = [unit for unit in batch if unit["id"] not in translations]
        if missing:
            retries += 1
            try:
                got_two, _meta_two = model.translate_batch(
                    missing,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    style=style,
                    domain=domain,
                    glossary=batch_terms,
                    max_tokens=output_cap,
                    temperature=0.0,
                )
                translations.update(got_two)
            except Exception:
                pass

        for unit in batch:
            if unit["id"] not in translations:
                failed.append({"id": unit["id"], "reason": "missing_translation"})

        done_units = sum(len(item) for item in batches[: index + 1])
        percent = 5 + int(80 * (index + 1) / max(1, len(batches)))
        report_progress("translating", percent, done_units, len(parsed.units))

    if should_cancel():
        raise PipelineError("cancelled_by_user", "cancelled by user")

    partial = dict(translations)
    for unit in parsed.units:
        translations.setdefault(unit.id, unit.text)

    report_progress("rebuilding", 88, len(parsed.units), len(parsed.units))
    try:
        adapter.rebuild(parsed, translations, out_path)
    except Exception as exc:
        raise PipelineError("rebuild_failed", str(exc)) from exc

    report_progress("validating", 94, len(parsed.units), len(parsed.units))
    try:
        checks = adapter.verify(source_path, out_path, parsed)
    except Exception as exc:
        checks = [{"check": "verify", "ok": False, "detail": str(exc)}]

    quality = check_units(parsed.units, partial)
    glossary_check = check_glossary(payload, translations, glossary)
    hard_ok = all(bool(item.get("ok", True)) for item in checks)

    return {
        "file": {"source": str(source_path), "output": str(out_path), "format": source_path.suffix.lower(), "output_format": out_path.suffix.lower()},
        "document_meta": parsed.meta,
        "budget": {
            "slot_ctx": slot_ctx,
            "text_budget": text_budget,
            "output_cap": output_cap,
            "target_output": target_output,
            "batches": len(batches),
        },
        "units": len(parsed.units),
        "translated": len(parsed.units) - len(failed),
        "failed": failed,
        "retries": retries,
        "checks": checks,
        "hard_checks_ok": hard_ok,
        "quality": quality,
        "glossary": glossary_check,
        "model": {
            "alias": info.get("resolved_model") or info.get("alias"),
            "slot_ctx": info.get("slot_ctx"),
            "total_slots": info.get("total_slots"),
        },
        "duration_seconds": round(time.time() - started, 2),
    }
