from __future__ import annotations

import json
import sqlite3
from contextlib import closing
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import env_defaults

_LOCK = threading.Lock()
_DB_PATH = Path("data/app.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY,
  original_filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  source_file_id TEXT NOT NULL,
  result_file_id TEXT,
  source_language TEXT NOT NULL,
  target_language TEXT NOT NULL,
  style TEXT,
  domain TEXT,
  options_json TEXT NOT NULL DEFAULT '{}',
  settings_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL,
  progress INTEGER NOT NULL DEFAULT 0,
  stage TEXT,
  total_units INTEGER,
  done_units INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  error_code TEXT,
  error_summary TEXT,
  report_path TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS job_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  at TEXT NOT NULL,
  level TEXT NOT NULL,
  stage TEXT,
  code TEXT,
  message TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_job ON job_events(job_id, id);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


SCHEMA_EXTRA = """
CREATE TABLE IF NOT EXISTS chats (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY,
  chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'complete',
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON chat_messages(chat_id, created_at);

CREATE TABLE IF NOT EXISTS chat_attachments (
  message_id TEXT NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
  file_id TEXT NOT NULL REFERENCES files(id),
  PRIMARY KEY (message_id, file_id)
);
CREATE INDEX IF NOT EXISTS idx_attachments_file ON chat_attachments(file_id);

CREATE TABLE IF NOT EXISTS glossaries (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source_language TEXT NOT NULL,
  target_language TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS glossary_terms (
  id TEXT PRIMARY KEY,
  glossary_id TEXT NOT NULL REFERENCES glossaries(id) ON DELETE CASCADE,
  source_term TEXT NOT NULL,
  target_term TEXT NOT NULL,
  note TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE (glossary_id, source_term)
);
CREATE INDEX IF NOT EXISTS idx_terms_glossary ON glossary_terms(glossary_id);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def configure(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(path: Path) -> None:
    configure(path)
    with closing(connect()) as conn:
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_EXTRA)


def new_id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex[:16]


def db_path() -> str:
    return str(_DB_PATH)


def counts() -> dict[str, int]:
    tables = {
        "jobs": "jobs",
        "chats": "chats",
        "messages": "chat_messages",
        "glossaries": "glossaries",
        "terms": "glossary_terms",
        "files": "files",
    }
    result: dict[str, int] = {}
    with closing(connect()) as conn:
        for label, table in tables.items():
            result[label] = int(conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0])
    return result


def load_settings() -> dict[str, Any]:
    values = env_defaults()
    with closing(connect()) as conn:
        for row in conn.execute("SELECT key, value FROM settings"):
            try:
                values[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                continue
    return values


def save_settings(patch: dict[str, Any]) -> None:
    stamp = utcnow()
    with closing(connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for key, value in patch.items():
            conn.execute(
                "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), stamp),
            )
        conn.execute("COMMIT")


def add_file(record: dict[str, Any]) -> None:
    with closing(connect()) as conn:
        conn.execute(
            "INSERT INTO files(id, original_filename, stored_path, mime_type, size_bytes, sha256, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                record["id"],
                record["original_filename"],
                record["stored_path"],
                record["mime_type"],
                record["size_bytes"],
                record["sha256"],
                record["created_at"],
            ),
        )


def get_file(file_id: str) -> sqlite3.Row | None:
    with closing(connect()) as conn:
        return conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()


def create_job(job: dict[str, Any]) -> None:
    with closing(connect()) as conn:
        conn.execute(
            "INSERT INTO jobs(id, source_file_id, source_language, target_language, style, domain,"
            " options_json, settings_json, status, progress, stage, attempts, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                job["id"],
                job["source_file_id"],
                job["source_language"],
                job["target_language"],
                job.get("style"),
                job.get("domain"),
                json.dumps(job.get("options") or {}, ensure_ascii=False),
                json.dumps(job.get("settings") or {}, ensure_ascii=False),
                "queued",
                0,
                "queued",
                0,
                utcnow(),
            ),
        )


def get_job(job_id: str) -> sqlite3.Row | None:
    with closing(connect()) as conn:
        return conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


def list_jobs(limit: int = 30) -> list[sqlite3.Row]:
    with closing(connect()) as conn:
        return list(conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)))


def claim_next() -> sqlite3.Row | None:
    with _LOCK:
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id FROM jobs WHERE status='queued' AND cancel_requested=0"
                " ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            conn.execute(
                "UPDATE jobs SET status='parsing', stage='parsing', started_at=?,"
                " attempts=attempts+1 WHERE id=? AND status='queued'",
                (utcnow(), row["id"]),
            )
            conn.execute("COMMIT")
            return conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    keys = list(fields)
    clause = ", ".join(key + "=?" for key in keys)
    values = [fields[key] for key in keys]
    values.append(job_id)
    with closing(connect()) as conn:
        conn.execute("UPDATE jobs SET " + clause + " WHERE id=?", values)


def request_cancel(job_id: str) -> None:
    with closing(connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return
        if row["status"] == "queued":
            conn.execute(
                "UPDATE jobs SET status='cancelled', stage='cancelled', completed_at=? WHERE id=?",
                (utcnow(), job_id),
            )
        elif row["status"] in ("parsing", "translating", "rebuilding"):
            conn.execute("UPDATE jobs SET cancel_requested=1 WHERE id=?", (job_id,))
        conn.execute("COMMIT")


def add_event(job_id: str, level: str, message: str, stage: str | None = None, code: str | None = None) -> None:
    with closing(connect()) as conn:
        conn.execute(
            "INSERT INTO job_events(job_id, at, level, stage, code, message) VALUES(?,?,?,?,?,?)",
            (job_id, utcnow(), level, stage, code, message),
        )


def job_events(job_id: str, limit: int = 100) -> list[sqlite3.Row]:
    with closing(connect()) as conn:
        return list(
            conn.execute("SELECT * FROM job_events WHERE job_id=? ORDER BY id DESC LIMIT ?", (job_id, limit))
        )


def recover_stale(timeout_seconds: int = 1800) -> int:
    # Called once at worker startup: any job still marked running belongs to a dead process.
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT id, started_at, attempts FROM jobs"
            " WHERE status IN ('parsing','translating','rebuilding')"
        ).fetchall()
        count = 0
        for row in rows:
            started = row["started_at"]
            if not started:
                continue
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds()
            except ValueError:
                continue
            if age <= timeout_seconds:
                continue
            if int(row["attempts"] or 0) < 3:
                conn.execute(
                    "UPDATE jobs SET status='queued', stage='queued', progress=0, started_at=NULL,"
                    " error_code=NULL, error_summary=NULL WHERE id=?",
                    (row["id"],),
                )
            else:
                conn.execute(
                    "UPDATE jobs SET status='failed', stage='failed', error_code='stale_timeout',"
                    " error_summary='worker stopped responding', completed_at=? WHERE id=?",
                    (utcnow(), row["id"]),
                )
            count += 1
        return count

# ---------------- chats ----------------

def create_chat(title: str) -> str:
    chat_id = new_id("c")
    stamp = utcnow()
    with closing(connect()) as conn:
        conn.execute(
            "INSERT INTO chats(id, title, created_at, updated_at) VALUES(?,?,?,?)",
            (chat_id, title or "新对话", stamp, stamp),
        )
    return chat_id


def list_chats(limit: int = 50) -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT c.*,"
            " (SELECT content FROM chat_messages m WHERE m.chat_id=c.id ORDER BY m.created_at DESC LIMIT 1) AS last_message,"
            " (SELECT COUNT(*) FROM chat_messages m WHERE m.chat_id=c.id) AS message_count"
            " FROM chats c ORDER BY c.updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_chat(chat_id: str):
    with closing(connect()) as conn:
        return conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()


def update_chat(chat_id: str, title: str | None = None) -> None:
    with closing(connect()) as conn:
        if title is None:
            conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (utcnow(), chat_id))
        else:
            conn.execute("UPDATE chats SET title=?, updated_at=? WHERE id=?", (title, utcnow(), chat_id))


def delete_chat(chat_id: str) -> None:
    with closing(connect()) as conn:
        conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))


def list_messages(chat_id: str) -> list:
    with closing(connect()) as conn:
        return list(
            conn.execute(
                "SELECT * FROM chat_messages WHERE chat_id=? ORDER BY created_at, rowid", (chat_id,)
            )
        )


def add_message(chat_id: str, role: str, content: str, status: str = "complete", meta: dict | None = None) -> str:
    message_id = new_id("m")
    with closing(connect()) as conn:
        conn.execute(
            "INSERT INTO chat_messages(id, chat_id, role, content, status, meta_json, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (message_id, chat_id, role, content, status, json.dumps(meta or {}, ensure_ascii=False), utcnow()),
        )
        conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (utcnow(), chat_id))
    return message_id


def attach_files(message_id: str, file_ids: list) -> None:
    if not file_ids:
        return
    with closing(connect()) as conn:
        for file_id in file_ids:
            conn.execute(
                "INSERT OR IGNORE INTO chat_attachments(message_id, file_id) VALUES(?,?)",
                (message_id, file_id),
            )


def messages_with_attachments(chat_id: str) -> list[dict]:
    with closing(connect()) as conn:
        messages = conn.execute(
            "SELECT * FROM chat_messages WHERE chat_id=? ORDER BY created_at, rowid", (chat_id,)
        ).fetchall()
        result = []
        for message in messages:
            files = conn.execute(
                "SELECT f.id, f.original_filename, f.size_bytes, f.mime_type FROM chat_attachments a"
                " JOIN files f ON f.id=a.file_id WHERE a.message_id=?",
                (message["id"],),
            ).fetchall()
            item = dict(message)
            item["attachments"] = [dict(file) for file in files]
            result.append(item)
        return result


# ---------------- glossaries ----------------

def create_glossary(name: str, source_language: str, target_language: str) -> str:
    glossary_id = new_id("g")
    with closing(connect()) as conn:
        conn.execute(
            "INSERT INTO glossaries(id, name, source_language, target_language, created_at) VALUES(?,?,?,?,?)",
            (glossary_id, name, source_language, target_language, utcnow()),
        )
    return glossary_id


def list_glossaries() -> list[dict]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT g.*, (SELECT COUNT(*) FROM glossary_terms t WHERE t.glossary_id=g.id) AS term_count"
            " FROM glossaries g ORDER BY g.created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_glossary(glossary_id: str):
    with closing(connect()) as conn:
        return conn.execute("SELECT * FROM glossaries WHERE id=?", (glossary_id,)).fetchone()


def update_glossary(glossary_id: str, name: str | None, source_language: str | None, target_language: str | None) -> None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM glossaries WHERE id=?", (glossary_id,)).fetchone()
        if row is None:
            return
        conn.execute(
            "UPDATE glossaries SET name=?, source_language=?, target_language=? WHERE id=?",
            (name or row["name"], source_language or row["source_language"], target_language or row["target_language"], glossary_id),
        )


def delete_glossary(glossary_id: str) -> None:
    with closing(connect()) as conn:
        conn.execute("DELETE FROM glossaries WHERE id=?", (glossary_id,))


def list_terms(glossary_id: str) -> list:
    with closing(connect()) as conn:
        return list(
            conn.execute(
                "SELECT * FROM glossary_terms WHERE glossary_id=? ORDER BY source_term", (glossary_id,)
            )
        )


def upsert_term(glossary_id: str, source: str, target: str, note: str | None = None) -> str:
    term_id = new_id("t")
    with closing(connect()) as conn:
        existing = conn.execute(
            "SELECT id FROM glossary_terms WHERE glossary_id=? AND source_term=?", (glossary_id, source)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE glossary_terms SET target_term=?, note=?, updated_at=? WHERE id=?",
                (target, note, utcnow(), existing["id"]),
            )
            return existing["id"]
        conn.execute(
            "INSERT INTO glossary_terms(id, glossary_id, source_term, target_term, note, updated_at)"
            " VALUES(?,?,?,?,?,?)",
            (term_id, glossary_id, source, target, note, utcnow()),
        )
    return term_id


def update_term(term_id: str, source: str | None, target: str | None, note: str | None) -> None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM glossary_terms WHERE id=?", (term_id,)).fetchone()
        if row is None:
            return
        conn.execute(
            "UPDATE glossary_terms SET source_term=?, target_term=?, note=?, updated_at=? WHERE id=?",
            (source or row["source_term"], target or row["target_term"], note if note is not None else row["note"], utcnow(), term_id),
        )


def delete_term(term_id: str) -> None:
    with closing(connect()) as conn:
        conn.execute("DELETE FROM glossary_terms WHERE id=?", (term_id,))


def glossary_pairs(glossary_id: str) -> list[tuple[str, str]]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT source_term, target_term FROM glossary_terms WHERE glossary_id=?", (glossary_id,)
        ).fetchall()
        return [(row["source_term"], row["target_term"]) for row in rows]
