from __future__ import annotations

import asyncio
import csv
import io as pyio
import json
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from . import db
from .chat import build_context
from .config import EDITABLE_KEYS, ConfigError, env_defaults, validate_patch
from .model import ModelError, make_model
from .storage import UploadError, save_stream
from .translate.glossary import parse_glossary

router = APIRouter()
DATA_DIR = Path("data")


def configure(data_dir: Path) -> None:
    global DATA_DIR
    DATA_DIR = Path(data_dir)


def _job_dict(row: Any) -> dict[str, Any]:
    source = db.get_file(row["source_file_id"])
    return {
        "id": row["id"],
        "status": row["status"],
        "stage": row["stage"],
        "progress": row["progress"],
        "source_language": row["source_language"],
        "target_language": row["target_language"],
        "style": row["style"],
        "domain": row["domain"],
        "total_units": row["total_units"],
        "done_units": row["done_units"],
        "error_code": row["error_code"],
        "error_summary": row["error_summary"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "file_name": source["original_filename"] if source else None,
        "has_result": bool(row["result_file_id"]),
        "has_report": bool(row["report_path"]),
    }


class JobIn(BaseModel):
    file_id: str
    source_language: str = "auto"
    target_language: str = "zh-CN"
    style: str | None = None
    domain: str | None = None
    glossary_text: str | None = None
    glossary_id: str | None = None
    translate_headers: bool = False


class ChatIn(BaseModel):
    title: str | None = None


class ChatPatch(BaseModel):
    title: str


class MessageIn(BaseModel):
    content: str
    file_ids: list[str] = []


class GlossaryIn(BaseModel):
    name: str
    source_language: str = "en"
    target_language: str = "zh-CN"


class GlossaryPatch(BaseModel):
    name: str | None = None
    source_language: str | None = None
    target_language: str | None = None


class TermIn(BaseModel):
    source: str
    target: str
    note: str | None = None


class TermPatch(BaseModel):
    source: str | None = None
    target: str | None = None
    note: str | None = None


class ImportIn(BaseModel):
    text: str


@router.get("/api/health")
def health() -> dict[str, Any]:
    settings = db.load_settings()
    adapter = make_model(settings)
    try:
        reachable = adapter.health()
    finally:
        adapter.close()
    return {"status": "ok", "model_reachable": reachable, "root": settings.get("model_root_url")}


@router.get("/api/meta")
def meta() -> dict[str, Any]:
    settings = db.load_settings()
    return {
        "target_languages": [
            {"code": "zh-CN", "label": "简体中文"},
            {"code": "zh-TW", "label": "繁體中文"},
            {"code": "en", "label": "English"},
            {"code": "ja", "label": "日本語"},
            {"code": "ko", "label": "한국어"},
            {"code": "fr", "label": "Français"},
            {"code": "de", "label": "Deutsch"},
            {"code": "es", "label": "Español"},
            {"code": "ru", "label": "Русский"},
        ],
        "styles": [
            {"code": "natural", "label": "自然流畅"},
            {"code": "literal", "label": "忠实直译"},
            {"code": "formal", "label": "正式"},
            {"code": "concise", "label": "简明"},
        ],
        "domains": [
            {"code": "general", "label": "通用"},
            {"code": "business", "label": "商务"},
            {"code": "technical", "label": "技术"},
            {"code": "legal", "label": "法律"},
            {"code": "academic", "label": "学术"},
        ],
        "max_upload_mb": settings.get("max_upload_mb", 100),
        "default_target_language": settings.get("default_target_language", "zh-CN"),
    }


# ---------------- files ----------------

@router.post("/api/files")
def upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
    settings = db.load_settings()
    max_bytes = int(settings.get("max_upload_mb", 100)) * 1024 * 1024
    try:
        record = save_stream(file.file, file.filename or "upload", DATA_DIR, max_bytes)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})
    record["created_at"] = db.utcnow()
    db.add_file(record)
    return {
        "id": record["id"],
        "filename": record["original_filename"],
        "size_bytes": record["size_bytes"],
        "mime_type": record["mime_type"],
    }


@router.get("/api/files/{file_id}")
def file_info(file_id: str) -> dict[str, Any]:
    row = db.get_file(file_id)
    if row is None:
        raise HTTPException(status_code=404, detail="file not found")
    return {"id": row["id"], "filename": row["original_filename"], "size_bytes": row["size_bytes"]}


@router.get("/api/files/{file_id}/download")
def download_file(file_id: str) -> FileResponse:
    row = db.get_file(file_id)
    if row is None or not Path(row["stored_path"]).exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(row["stored_path"], filename=row["original_filename"])


# ---------------- jobs ----------------

@router.post("/api/jobs")
def create_job(payload: JobIn) -> dict[str, Any]:
    source = db.get_file(payload.file_id)
    if source is None:
        raise HTTPException(status_code=404, detail="file not found")

    settings = db.load_settings()
    pairs = parse_glossary(payload.glossary_text or "")
    if payload.glossary_id:
        if db.get_glossary(payload.glossary_id) is None:
            raise HTTPException(status_code=404, detail="glossary not found")
        pairs.extend(db.glossary_pairs(payload.glossary_id))

    job_id = db.new_id("j")
    db.create_job(
        {
            "id": job_id,
            "source_file_id": payload.file_id,
            "source_language": payload.source_language or "auto",
            "target_language": payload.target_language,
            "style": payload.style,
            "domain": payload.domain,
            "options": {
                "glossary": [list(pair) for pair in pairs],
                "translate_headers": bool(payload.translate_headers),
            },
            "settings": settings,
        }
    )
    return _job_dict(db.get_job(job_id))


@router.get("/api/jobs")
def list_jobs(limit: int = 30) -> dict[str, Any]:
    rows = db.list_jobs(max(1, min(limit, 100)))
    return {"jobs": [_job_dict(row) for row in rows]}


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    row = db.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _job_dict(row)


@router.get("/api/jobs/{job_id}/report")
def job_report(job_id: str) -> dict[str, Any]:
    row = db.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    if not row["report_path"] or not Path(row["report_path"]).exists():
        raise HTTPException(status_code=404, detail="report not ready")
    with open(row["report_path"], encoding="utf-8") as handle:
        return json.load(handle)


@router.get("/api/jobs/{job_id}/events")
def get_events(job_id: str) -> dict[str, Any]:
    if db.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {"events": [dict(row) for row in db.job_events(job_id)]}


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    if db.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    db.request_cancel(job_id)
    return _job_dict(db.get_job(job_id))


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str) -> dict[str, Any]:
    row = db.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    if row["status"] not in ("failed", "cancelled"):
        raise HTTPException(status_code=409, detail="only failed or cancelled jobs can be retried")
    db.update_job(
        job_id,
        status="queued",
        stage="queued",
        progress=0,
        attempts=0,
        cancel_requested=0,
        error_code=None,
        error_summary=None,
        completed_at=None,
    )
    db.add_event(job_id, "info", "retry requested", stage="queued")
    return _job_dict(db.get_job(job_id))


@router.get("/api/jobs/{job_id}/download")
def download(job_id: str, kind: str = "result") -> FileResponse:
    row = db.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    source = db.get_file(row["source_file_id"])

    if kind == "source":
        if source is None:
            raise HTTPException(status_code=404, detail="source file not found")
        return FileResponse(source["stored_path"], filename=source["original_filename"])

    if kind == "report":
        if not row["report_path"] or not Path(row["report_path"]).exists():
            raise HTTPException(status_code=404, detail="report not ready")
        return FileResponse(row["report_path"], media_type="application/json", filename="quality-report.json")

    if not row["result_file_id"]:
        raise HTTPException(status_code=404, detail="result not ready")
    result = db.get_file(row["result_file_id"])
    if result is None or not Path(result["stored_path"]).exists():
        raise HTTPException(status_code=404, detail="result file missing")

    original = Path(source["original_filename"]) if source else Path("translated")
    result_suffix = Path(result["stored_path"]).suffix
    name = original.stem + "." + str(row["target_language"]) + result_suffix
    return FileResponse(result["stored_path"], filename=name)


@router.delete("/api/jobs/{job_id}")
def delete_job(job_id: str) -> dict[str, Any]:
    row = db.get_job(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="job not found")
    if row["status"] in ("parsing", "translating", "rebuilding"):
        raise HTTPException(status_code=409, detail="cancel the job before deleting")
    result_id = row["result_file_id"]
    report_path = row["report_path"]
    with closing(db.connect()) as conn:
        conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        conn.execute("DELETE FROM job_events WHERE job_id=?", (job_id,))
    if result_id:
        result = db.get_file(result_id)
        if result:
            Path(result["stored_path"]).unlink(missing_ok=True)
    if report_path:
        Path(report_path).unlink(missing_ok=True)
    return {"deleted": True}


# ---------------- chats ----------------

@router.post("/api/chats")
def create_chat(payload: ChatIn | None = None) -> dict[str, Any]:
    title = (payload.title if payload and payload.title else "新对话").strip() or "新对话"
    chat_id = db.create_chat(title)
    return {"id": chat_id, "title": title}


@router.get("/api/chats")
def list_chats(limit: int = 50) -> dict[str, Any]:
    return {"chats": db.list_chats(max(1, min(limit, 100)))}


@router.get("/api/chats/{chat_id}")
def get_chat(chat_id: str) -> dict[str, Any]:
    chat = db.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return {
        "id": chat["id"],
        "title": chat["title"],
        "created_at": chat["created_at"],
        "updated_at": chat["updated_at"],
        "messages": db.messages_with_attachments(chat_id),
    }


@router.patch("/api/chats/{chat_id}")
def patch_chat(chat_id: str, payload: ChatPatch) -> dict[str, Any]:
    if db.get_chat(chat_id) is None:
        raise HTTPException(status_code=404, detail="chat not found")
    db.update_chat(chat_id, payload.title)
    chat = db.get_chat(chat_id)
    return {"id": chat["id"], "title": chat["title"]}


@router.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str) -> dict[str, Any]:
    if db.get_chat(chat_id) is None:
        raise HTTPException(status_code=404, detail="chat not found")
    db.delete_chat(chat_id)
    return {"deleted": True}


def _prepare_chat(chat_id: str, payload: MessageIn) -> list[dict[str, str]]:
    chat = db.get_chat(chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="content is empty")
    for file_id in payload.file_ids:
        if db.get_file(file_id) is None:
            raise HTTPException(status_code=404, detail="attachment not found: " + file_id)

    db.add_message(chat_id, "user", content)
    if payload.file_ids:
        messages = db.list_messages(chat_id)
        user_message = messages[-1]
        db.attach_files(user_message["id"], payload.file_ids)

    if chat["title"] == "新对话":
        db.update_chat(chat_id, content[:24])

    settings = db.load_settings()
    adapter = make_model(settings)
    try:
        info = adapter.info()
    except Exception:
        info = {}
    finally:
        adapter.close()
    return build_context(chat_id, settings, int(info.get("slot_ctx") or 8192))


@router.post("/api/chats/{chat_id}/messages")
def send_message(chat_id: str, payload: MessageIn) -> dict[str, Any]:
    messages = _prepare_chat(chat_id, payload)
    settings = db.load_settings()
    adapter = make_model(settings)
    try:
        result = adapter.chat(
            messages,
            temperature=float(settings.get("temperature_chat", 0.7)),
            max_tokens=int(settings.get("chat_max_output_tokens", 2048)),
        )
    except ModelError as exc:
        db.add_message(chat_id, "assistant", "", status="error", meta={"error": str(exc)})
        raise HTTPException(status_code=502, detail=str(exc))
    finally:
        adapter.close()
    message_id = db.add_message(chat_id, "assistant", result.text, status="complete")
    return {"message_id": message_id, "content": result.text}


def _sse(event: str, data: dict[str, Any]) -> str:
    return "event: " + event + "\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"


@router.post("/api/chats/{chat_id}/messages/stream")
async def stream_message(chat_id: str, payload: MessageIn, request: Request) -> StreamingResponse:
    messages = _prepare_chat(chat_id, payload)
    settings = db.load_settings()
    adapter = make_model(settings)

    async def event_stream():
        parts: list[str] = []
        status = "complete"
        error: str | None = None
        message_id: str | None = None
        try:
            async for delta in adapter.chat_stream(
                messages,
                temperature=float(settings.get("temperature_chat", 0.7)),
                max_tokens=int(settings.get("chat_max_output_tokens", 2048)),
            ):
                if await request.is_disconnected():
                    status = "stopped"
                    break
                parts.append(delta)
                yield _sse("delta", {"text": delta})
        except asyncio.CancelledError:
            status = "stopped"
            raise
        except ModelError as exc:
            status = "error"
            error = str(exc)
        except Exception as exc:
            status = "error"
            error = str(exc)
        finally:
            adapter.close()
            text = "".join(parts)
            if text or status == "complete":
                message_id = db.add_message(
                    chat_id,
                    "assistant",
                    text,
                    status=status,
                    meta={"error": error} if error else None,
                )

        if status == "error":
            yield _sse("error", {"message": error or "model error"})
        else:
            yield _sse("done" if status == "complete" else "stopped", {"message_id": message_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------- glossaries ----------------

@router.get("/api/glossaries")
def list_glossaries() -> dict[str, Any]:
    return {"glossaries": db.list_glossaries()}


@router.post("/api/glossaries")
def create_glossary(payload: GlossaryIn) -> dict[str, Any]:
    glossary_id = db.create_glossary(payload.name.strip(), payload.source_language, payload.target_language)
    row = db.get_glossary(glossary_id)
    return dict(row)


@router.get("/api/glossaries/{glossary_id}")
def get_glossary(glossary_id: str) -> dict[str, Any]:
    row = db.get_glossary(glossary_id)
    if row is None:
        raise HTTPException(status_code=404, detail="glossary not found")
    data = dict(row)
    data["terms"] = [dict(term) for term in db.list_terms(glossary_id)]
    return data


@router.patch("/api/glossaries/{glossary_id}")
def patch_glossary(glossary_id: str, payload: GlossaryPatch) -> dict[str, Any]:
    if db.get_glossary(glossary_id) is None:
        raise HTTPException(status_code=404, detail="glossary not found")
    db.update_glossary(glossary_id, payload.name, payload.source_language, payload.target_language)
    return dict(db.get_glossary(glossary_id))


@router.delete("/api/glossaries/{glossary_id}")
def delete_glossary(glossary_id: str) -> dict[str, Any]:
    if db.get_glossary(glossary_id) is None:
        raise HTTPException(status_code=404, detail="glossary not found")
    db.delete_glossary(glossary_id)
    return {"deleted": True}


@router.post("/api/glossaries/{glossary_id}/terms")
def create_term(glossary_id: str, payload: TermIn) -> dict[str, Any]:
    if db.get_glossary(glossary_id) is None:
        raise HTTPException(status_code=404, detail="glossary not found")
    source = payload.source.strip()
    target = payload.target.strip()
    if not source or not target:
        raise HTTPException(status_code=422, detail="source and target are required")
    term_id = db.upsert_term(glossary_id, source, target, payload.note)
    return {"id": term_id, "source": source, "target": target}


@router.patch("/api/glossaries/{glossary_id}/terms/{term_id}")
def patch_term(glossary_id: str, term_id: str, payload: TermPatch) -> dict[str, Any]:
    db.update_term(term_id, payload.source, payload.target, payload.note)
    return {"updated": True}


@router.delete("/api/glossaries/{glossary_id}/terms/{term_id}")
def delete_term(glossary_id: str, term_id: str) -> dict[str, Any]:
    db.delete_term(term_id)
    return {"deleted": True}


@router.post("/api/glossaries/{glossary_id}/import")
def import_terms(glossary_id: str, payload: ImportIn) -> dict[str, Any]:
    if db.get_glossary(glossary_id) is None:
        raise HTTPException(status_code=404, detail="glossary not found")
    imported = 0
    for line in payload.text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=>" in line:
            source, target = line.split("=>", 1)
        elif "\t" in line:
            source, target = line.split("\t", 1)
        elif "," in line:
            source, target = line.split(",", 1)
        else:
            continue
        source, target = source.strip(), target.strip()
        if source and target:
            db.upsert_term(glossary_id, source, target)
            imported += 1
    return {"imported": imported}


@router.get("/api/glossaries/{glossary_id}/export.csv")
def export_terms(glossary_id: str) -> PlainTextResponse:
    if db.get_glossary(glossary_id) is None:
        raise HTTPException(status_code=404, detail="glossary not found")
    buffer = pyio.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["source", "target", "note"])
    for term in db.list_terms(glossary_id):
        writer.writerow([term["source_term"], term["target_term"], term["note"] or ""])
    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=glossary.csv"},
    )


# ---------------- settings ----------------

@router.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return {"values": db.load_settings(), "defaults": env_defaults(), "editable": EDITABLE_KEYS}


@router.patch("/api/settings")
def patch_settings(patch: dict[str, Any]) -> dict[str, Any]:
    try:
        clean = validate_patch(patch)
    except ConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.save_settings(clean)
    return {"values": db.load_settings()}


@router.post("/api/model/test")
def test_model() -> JSONResponse:
    settings = db.load_settings()
    adapter = make_model(settings)
    started = time.time()
    try:
        reachable = adapter.health()
        info = adapter.info()
        return JSONResponse({"ok": bool(reachable), "latency_ms": int((time.time() - started) * 1000), "info": info})
    except ModelError as exc:
        return JSONResponse(status_code=502, content={"ok": False, "code": exc.code, "error": str(exc)})
    finally:
        adapter.close()
