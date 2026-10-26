from pathlib import Path

from backend.app.documents import output_suffix_for


def test_pdf_outputs_docx():
    assert output_suffix_for(Path("report.pdf")) == ".docx"


def test_docx_keeps_docx():
    assert output_suffix_for(Path("report.docx")) == ".docx"


def test_text_keeps_suffix():
    assert output_suffix_for(Path("notes.txt")) == ".txt"
