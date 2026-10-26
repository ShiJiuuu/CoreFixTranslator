import json
from pathlib import Path

from backend.app import chat
from backend.app.documents.extract import extract_plain_text


def test_extract_plain_text(tmp_path: Path):
    source = tmp_path / "note.txt"
    source.write_text("Hello\nworld", encoding="utf-8")
    assert "Hello" in extract_plain_text(source)


def test_context_includes_attachment_text(monkeypatch):
    history = [
        {
            "role": "user",
            "content": "看看这个文件",
            "meta_json": json.dumps({"attachment_text": "FILE BODY CONTENT"}),
        }
    ]
    monkeypatch.setattr(chat.db, "messages_with_attachments", lambda chat_id: history)
    context = chat.build_context(
        "chat-1",
        {"chat_context_ratio": 0.6, "chat_max_output_tokens": 2048, "chat_max_history_turns": 20},
        32768,
    )
    assert context[0]["role"] == "system"
    assert "FILE BODY CONTENT" in context[-1]["content"]
