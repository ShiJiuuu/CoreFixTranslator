from pathlib import Path

import pytest
from docx import Document

from backend.app.documents import output_suffix_for
from backend.app.documents.base import DocumentError, ParsedDocument, Unit
from backend.app.documents.pdf_doc import build_docx, convert_docx_to_pdf, flow_text


def test_pdf_outputs_pdf():
    assert output_suffix_for(Path("report.pdf")) == ".pdf"


def test_docx_keeps_docx():
    assert output_suffix_for(Path("report.docx")) == ".docx"


def test_text_keeps_suffix():
    assert output_suffix_for(Path("notes.txt")) == ".txt"


def test_pdf_builds_flowing_docx(tmp_path: Path):
    parsed = ParsedDocument(
        units=[
            Unit(id="p0b0", text="Hello", location={"page": 0}),
            Unit(id="p1b0", text="World", location={"page": 1}),
        ],
        meta={"pages": 2, "width": 595.0, "height": 842.0},
    )
    out = tmp_path / "flow.docx"
    build_docx(parsed, {"p0b0": "第一段", "p1b0": "第二段"}, out)

    document = Document(str(out))
    assert [p.text for p in document.paragraphs] == ["第一段", "第二段"]
    assert round(document.sections[0].page_width.pt) == 595


def test_pdf_converter_missing(tmp_path: Path):
    source = tmp_path / "empty.docx"
    Document().save(str(source))
    with pytest.raises(DocumentError) as info:
        convert_docx_to_pdf(source, tmp_path / "empty.pdf", binary="/nonexistent/soffice")
    assert info.value.code == "pdf_converter_missing"


def test_flow_text_joins_lines():
    assert flow_text("Hello\nworld") == "Hello world"
    assert flow_text("第一行\n第二行") == "第一行第二行"
    assert flow_text("Line 1\n\nLine 2") == "Line 1 Line 2"
