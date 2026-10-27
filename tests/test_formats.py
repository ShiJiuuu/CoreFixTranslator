from pathlib import Path

import pytest
from docx import Document

from backend.app.documents import output_suffix_for
from backend.app.documents.base import DocumentError
from backend.app.documents.pdf.render_pdf import convert_docx_to_pdf


def test_pdf_outputs_pdf(monkeypatch):
    monkeypatch.delenv("PDF_RENDER", raising=False)
    assert output_suffix_for(Path("report.pdf")) == ".pdf"


def test_pdf_outputs_docx_when_configured(monkeypatch):
    monkeypatch.setenv("PDF_RENDER", "docx")
    assert output_suffix_for(Path("report.pdf")) == ".docx"


def test_docx_keeps_docx():
    assert output_suffix_for(Path("report.docx")) == ".docx"


def test_text_keeps_suffix():
    assert output_suffix_for(Path("notes.txt")) == ".txt"


def test_pdf_converter_missing(tmp_path: Path):
    source = tmp_path / "empty.docx"
    Document().save(str(source))
    with pytest.raises(DocumentError) as info:
        convert_docx_to_pdf(source, tmp_path / "empty.pdf", binary="/nonexistent/soffice")
    assert info.value.code == "pdf_converter_missing"
