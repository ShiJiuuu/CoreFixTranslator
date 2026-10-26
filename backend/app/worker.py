from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from . import db
from .documents.base import DocumentError
from .model import ModelError, make_model
from .pipeline import PipelineError, translate_document


class TranslationWorker(threading.Thread):
    def __init__(self, data_dir: Path, poll_seconds: float = 1.0):
        super().__init__(name="translation-worker", daemon=True)
        self.data_dir = Path(data_dir)
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        try:
            db.recover_stale()
        except Exception:
            pass
        while not self._stop.is_set():
            try:
                job = db.claim_next()
            except Exception:
                time.sleep(self.poll_seconds)
                continue
            if job is None:
                time.sleep(self.poll_seconds)
                continue
            try:
                self._process(job)
            except Exception as exc:
                db.add_event(job["id"], "error", "worker crash: " + str(exc))
                db.update_job(
                    job["id"],
                    status="failed",
                    stage="failed",
                    error_code="internal_error",
                    error_summary=str(exc)[:500],
                    completed_at=db.utcnow(),
                )

    def _process(self, job: Any) -> None:
        job_id = job["id"]
        source = db.get_file(job["source_file_id"])
        if source is None:
            db.update_job(
                job_id,
                status="failed",
                stage="failed",
                error_code="parse_failed",
                error_summary="source file missing",
                completed_at=db.utcnow(),
            )
            return

        settings = json.loads(job["settings_json"] or "{}") or db.load_settings()
        options = json.loads(job["options_json"] or "{}")
        source_path = Path(source["stored_path"])
        out_dir = self.data_dir / "results" / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / ("translated" + source_path.suffix.lower())

        db.update_job(job_id, status="translating", stage="translating")
        db.add_event(job_id, "info", "start translation", stage="translating")

        model = make_model(settings)

        def progress(stage: str, percent: int, done: int, total: int) -> None:
            db.update_job(job_id, stage=stage, progress=int(percent), done_units=int(done), total_units=int(total))

        def cancel() -> bool:
            row = db.get_job(job_id)
            return bool(row and row["cancel_requested"])

        glossary_pairs = [tuple(pair) for pair in options.get("glossary", []) if isinstance(pair, list) and len(pair) == 2]

        try:
            report = translate_document(
                source_path,
                out_path,
                settings=settings,
                model=model,
                source_lang=job["source_language"],
                target_lang=job["target_language"],
                style=job["style"],
                domain=job["domain"],
                glossary=glossary_pairs,
                options={"translate_headers": bool(options.get("translate_headers", False))},
                progress=progress,
                cancel=cancel,
            )
        except PipelineError as exc:
            self._fail(job_id, exc.code, exc.message)
            return
        except DocumentError as exc:
            self._fail(job_id, exc.code, exc.message)
            return
        except ModelError as exc:
            self._fail(job_id, exc.code, str(exc))
            return
        except Exception as exc:
            db.add_event(job_id, "error", traceback.format_exc()[-1500:])
            self._fail(job_id, "internal_error", str(exc))
            return
        finally:
            try:
                model.close()
            except Exception:
                pass

        report_path = out_dir / "quality-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        result_file_id = db.new_id("f")
        db.add_file(
            {
                "id": result_file_id,
                "original_filename": source["original_filename"],
                "stored_path": str(out_path),
                "mime_type": source["mime_type"],
                "size_bytes": out_path.stat().st_size,
                "sha256": "",
                "created_at": db.utcnow(),
            }
        )
        db.update_job(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            result_file_id=result_file_id,
            report_path=str(report_path),
            completed_at=db.utcnow(),
        )
        db.add_event(job_id, "info", "completed", stage="completed")

    def _fail(self, job_id: str, code: str, message: str) -> None:
        row = db.get_job(job_id)
        if row is not None and row["cancel_requested"]:
            db.update_job(job_id, status="cancelled", stage="cancelled", completed_at=db.utcnow())
            db.add_event(job_id, "warn", "cancelled", stage="cancelled")
            return
        db.update_job(
            job_id,
            status="failed",
            stage="failed",
            error_code=code,
            error_summary=(message or "")[:500],
            completed_at=db.utcnow(),
        )
        db.add_event(job_id, "error", message or code)
