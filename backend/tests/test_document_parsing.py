"""
Tests for document parsing (DOCX/TXT text extraction).
"""

from io import BytesIO

import pytest
from docx import Document

from app.services.document_parsing import (
    UnsupportedDocumentType,
    extract_text,
    extract_text_from_docx,
)


def _make_docx_bytes(paragraphs, table_rows=None):
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    if table_rows:
        table = doc.add_table(rows=0, cols=len(table_rows[0]))
        for row_values in table_rows:
            row = table.add_row()
            for cell, value in zip(row.cells, row_values):
                cell.text = value
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extracts_paragraph_text():
    file_bytes = _make_docx_bytes(["Line one.", "Line two."])
    text = extract_text_from_docx(file_bytes)
    assert "Line one." in text
    assert "Line two." in text


def test_extracts_table_text():
    file_bytes = _make_docx_bytes(
        ["Header"],
        table_rows=[["Facility", "Ardiya Clinic"], ["Region", "Farwaniya"]],
    )
    text = extract_text_from_docx(file_bytes)
    assert "Facility" in text
    assert "Ardiya Clinic" in text
    assert "Farwaniya" in text


def test_empty_paragraphs_are_skipped():
    file_bytes = _make_docx_bytes(["Real line.", "", "   ", "Another real line."])
    text = extract_text_from_docx(file_bytes)
    lines = [l for l in text.split("\n") if l]
    assert lines == ["Real line.", "Another real line."]


def test_extract_text_dispatches_docx_by_extension():
    file_bytes = _make_docx_bytes(["Some content."])
    assert extract_text("report.docx", file_bytes) == extract_text_from_docx(file_bytes)


def test_extract_text_dispatches_txt_by_extension():
    file_bytes = "Plain text content.".encode("utf-8")
    assert extract_text("report.txt", file_bytes) == "Plain text content."


def test_unsupported_extension_raises():
    with pytest.raises(UnsupportedDocumentType):
        extract_text("report.pdf", b"whatever")
