from pathlib import Path

from backend.app.config import env_defaults
from backend.app.model import FakeAdapter
from backend.app.pipeline import translate_document


def test_text_pipeline_end_to_end(tmp_path: Path):
    source = tmp_path / "sample.txt"
    source.write_text("Hello world\n\nSecond line 123\n", encoding="utf-8")
    out = tmp_path / "out.txt"

    settings = env_defaults()
    report = translate_document(
        source,
        out,
        settings=settings,
        model=FakeAdapter(settings),
        source_lang="auto",
        target_lang="zh-CN",
    )

    text = out.read_text(encoding="utf-8")
    assert "[zh-CN] Hello world" in text
    assert "[zh-CN] Second line 123" in text
    assert report["units"] == 2
    assert report["translated"] == 2
    assert report["failed"] == []
    assert report["hard_checks_ok"] is True
