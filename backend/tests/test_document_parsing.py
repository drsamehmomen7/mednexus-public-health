"""
Tests for document parsing (DOCX, TXT and PDF text extraction).
"""

from io import BytesIO

import pytest
from docx import Document
from pypdf.errors import DependencyError

from app.services import document_parsing as dp
from app.services.document_parsing import (
    CHARS_PER_PAGE_ESTIMATE,
    CORRUPT_DOCX_MESSAGE,
    CORRUPT_PDF_MESSAGE,
    ENCRYPTED_PDF_MESSAGE,
    MAX_PAGES,
    MAX_UPLOAD_BYTES,
    NO_TEXT_PDF_MESSAGE,
    NOT_A_PDF_MESSAGE,
    DocumentTooLarge,
    UnreadableDocument,
    UnsupportedDocumentType,
    extract_text,
    extract_text_from_docx,
    extract_text_from_pdf,
    normalize_pdf_text,
)
from app.services.gazetteer import Gazetteer
from app.services.report_type_detection import detect_report_type
from tests.pdf_fixtures import encrypt_pdf, make_pdf


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
        extract_text("report.csv", b"whatever")


def test_preserves_true_reading_order_across_paragraphs_and_tables():
    """
    Real bug found while testing generated case-report forms: grouping
    all paragraphs before all tables put a footer paragraph (written
    AFTER the table in the document) ahead of the table's field data in
    the extracted text — disorienting even though it happened not to
    break extraction in that case. A letterhead paragraph, then a
    table, then a footer paragraph must come out in that order.
    """
    doc = Document()
    doc.add_paragraph("LETTERHEAD")
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Field"
    table.rows[0].cells[1].text = "Value"
    doc.add_paragraph("FOOTER")

    buf = BytesIO()
    doc.save(buf)
    text = extract_text_from_docx(buf.getvalue())

    lines = [l for l in text.split("\n") if l]
    assert lines == ["LETTERHEAD", "Field Value", "FOOTER"]


# ---------------------------------------------------------------------------
# PDF: what comes out
# ---------------------------------------------------------------------------

_GOOD_PDF = make_pdf([["Patient: Test Person", "Age: 34 years"]])


def test_extracts_pdf_text():
    assert extract_text_from_pdf(_GOOD_PDF) == "Patient: Test Person\nAge: 34 years"


def test_pdf_pages_are_joined_by_a_blank_line_in_order():
    pdf = make_pdf([["Page one A", "Page one B"], ["Page two"], ["Page three"]])
    assert extract_text_from_pdf(pdf) == "Page one A\nPage one B\n\nPage two\n\nPage three"


def test_pdf_repeated_letterhead_is_kept_on_every_page():
    """Repeated headers are deliberately not stripped in this phase; the accuracy pass decides."""
    pdf = make_pdf([["MINISTRY LETTERHEAD", f"body of page {n}"] for n in (1, 2, 3)])
    assert extract_text_from_pdf(pdf).count("MINISTRY LETTERHEAD") == 3


def test_pdf_hard_wrapped_lines_are_not_unwrapped():
    pdf = make_pdf([["The patient was admitted with", "fever and cough."]])
    assert extract_text_from_pdf(pdf) == "The patient was admitted with\nfever and cough."


def test_extract_text_dispatches_pdf_by_extension_case_insensitively():
    pdf = make_pdf([["Some content."]])
    assert extract_text("report.pdf", pdf) == "Some content."
    assert extract_text("REPORT.PDF", pdf) == "Some content."


def test_partly_scanned_pdf_returns_only_the_text_it_has():
    """Known limitation (decisions-log): a scanned page next to a typed one passes silently."""
    pdf = make_pdf([["Typed letterhead only"], []])
    assert extract_text_from_pdf(pdf) == "Typed letterhead only"


# ---------------------------------------------------------------------------
# PDF: character clean-up (built from code points: most of these are invisible)
# ---------------------------------------------------------------------------

_NORMALIZATION_CASES = [
    ("fl ligature", "in" + chr(0xFB02) + "uenza", "influenza"),
    ("fi ligature", "con" + chr(0xFB01) + "rmed", "confirmed"),
    ("ff, ffi, ffl and st ligatures", chr(0xFB00) + " " + chr(0xFB03) + " " + chr(0xFB04) + " " + chr(0xFB05) + chr(0xFB06), "ff ffi ffl stst"),
    ("no-break space", "a" + chr(0xA0) + "b", "a b"),
    ("narrow no-break, thin and ideographic spaces", "a" + chr(0x202F) + "b" + chr(0x2009) + "c" + chr(0x3000) + "d", "a b c d"),
    ("soft hyphen", "vacci" + chr(0xAD) + "nation", "vaccination"),
    ("zero-width characters and BOM", chr(0xFEFF) + "a" + chr(0x200B) + "b" + chr(0x200D) + "c", "abc"),
    ("line separator", "a" + chr(0x2028) + "b", "a\nb"),
    ("Symbol-font bullet", chr(0xF0B7) + " item", chr(0x2022) + " item"),
    ("CR LF, lone CR and form feed", "a\r\nb\rc\fd", "a\nb\nc\nd"),
    ("space and tab runs, indentation, trailing spaces", "  a   b\t\tc  \n    d", "a b c\nd"),
    ("3+ newlines collapse to one blank line", "a\n\n\n\n\nb", "a\n\nb"),
    ("plain ASCII is untouched", "Patient: Test Person, Age: 34.", "Patient: Test Person, Age: 34."),
    ("whitespace only becomes empty", " \n\t \n", ""),
    # what it deliberately does NOT do in this phase
    ("wrapped line is not unwrapped", "first part of a\nsentence", "first part of a\nsentence"),
    ("line-end hyphen is not joined", "vaccina-\ntion", "vaccina-\ntion"),
    ("repeated line is not removed", "Header\nbody\nHeader", "Header\nbody\nHeader"),
]


@pytest.mark.parametrize(
    "raw,expected",
    [(case[1], case[2]) for case in _NORMALIZATION_CASES],
    ids=[case[0] for case in _NORMALIZATION_CASES],
)
def test_normalize_pdf_text(raw, expected):
    assert normalize_pdf_text(raw) == expected


# ---------------------------------------------------------------------------
# PDF: every way a file can fail has its own honest message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [b"", b"Just a plain text report.", b"   \n  ", _make_docx_bytes(["hello"])],
    ids=["empty", "plain text", "whitespace", "a DOCX renamed .pdf"],
)
def test_file_that_is_not_a_pdf_is_reported_as_such(data):
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("report.pdf", data)
    assert str(exc.value) == NOT_A_PDF_MESSAGE


@pytest.mark.parametrize(
    "data",
    [b"%PDF-1.4\n" + bytes(range(256)) * 10, b"%PDF-1.4\n", _GOOD_PDF[: int(len(_GOOD_PDF) * 0.6)]],
    ids=["header plus garbage", "header only", "truncated"],
)
def test_damaged_pdf_is_reported_as_unreadable(data):
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("report.pdf", data)
    assert str(exc.value) == CORRUPT_PDF_MESSAGE


def test_password_protected_pdf_is_refused():
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("report.pdf", encrypt_pdf(_GOOD_PDF, "secret"))
    assert str(exc.value) == ENCRYPTED_PDF_MESSAGE


def test_pdf_with_only_owner_restrictions_is_read():
    restricted = encrypt_pdf(_GOOD_PDF, "", owner_password="owner")
    assert extract_text("report.pdf", restricted) == "Patient: Test Person\nAge: 34 years"


def test_pdf_without_a_text_layer_is_reported_as_a_scan():
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("report.pdf", make_pdf([[], []]))
    assert str(exc.value) == NO_TEXT_PDF_MESSAGE


def test_pdf_page_limit():
    at_limit = make_pdf([[f"page {n}"] for n in range(1, MAX_PAGES + 1)])
    assert f"page {MAX_PAGES}" in extract_text("report.pdf", at_limit)

    over = make_pdf([[f"page {n}"] for n in range(1, MAX_PAGES + 2)])
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("report.pdf", over)
    assert str(exc.value) == f"That PDF has {MAX_PAGES + 1} pages; the limit is {MAX_PAGES}. Reports are expected to be short."


def test_unexpected_parser_failure_becomes_a_clean_message(monkeypatch):
    class Exploding:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("internal parser explosion with details")

    monkeypatch.setattr(dp, "PdfReader", Exploding)
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("report.pdf", _GOOD_PDF)
    assert str(exc.value) == CORRUPT_PDF_MESSAGE


@pytest.mark.parametrize(
    "library_message,expected",
    [
        ("cryptography>=3.1 is required for AES algorithm", ENCRYPTED_PDF_MESSAGE),
        ("jbig2dec binary is not available.", CORRUPT_PDF_MESSAGE),
    ],
    ids=["AES without a crypto package", "any other missing dependency"],
)
def test_missing_dependency_is_only_called_encryption_when_it_is_about_aes(monkeypatch, library_message, expected):
    class NeedsDependency:
        def __init__(self, *args, **kwargs):
            raise DependencyError(library_message)

    monkeypatch.setattr(dp, "PdfReader", NeedsDependency)
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("report.pdf", _GOOD_PDF)
    assert str(exc.value) == expected


# ---------------------------------------------------------------------------
# All formats: corrupt DOCX, size and length limits, unsupported types
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [b"this is not a zip file", _make_docx_bytes(["hello"])[:200]],
    ids=["not a zip", "truncated"],
)
def test_damaged_docx_is_reported_as_unreadable(data):
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("report.docx", data)
    assert str(exc.value) == CORRUPT_DOCX_MESSAGE


def test_limits_are_the_approved_ones():
    """Decision D3: 10 MB and 30 pages for every format; DOCX and TXT pages are estimated at 3,000 characters."""
    assert MAX_UPLOAD_BYTES == 10 * 1024 * 1024
    assert MAX_PAGES == 30
    assert CHARS_PER_PAGE_ESTIMATE == 3000


def test_user_facing_messages_are_the_approved_wording():
    """Decision D6: this text is shown to the user as-is, so changing it should be a deliberate act."""
    assert NOT_A_PDF_MESSAGE == (
        "That file has a .pdf extension but isn't a valid PDF (it may be empty, "
        "damaged, or a different file type that was renamed)."
    )
    assert CORRUPT_PDF_MESSAGE == (
        "This PDF couldn't be read. It may be damaged or use a feature MedNexus "
        "doesn't support yet. Try re-saving or re-exporting it as a new PDF."
    )
    assert ENCRYPTED_PDF_MESSAGE == (
        "This PDF is password-protected (encrypted), so MedNexus can't read it. "
        "Upload an unprotected copy."
    )
    assert NO_TEXT_PDF_MESSAGE == (
        "No readable text found in that document. This PDF looks like a scan or "
        "image-only file (no selectable text), and OCR isn't supported yet. Upload "
        "a text-based PDF or paste the report text instead."
    )
    assert CORRUPT_DOCX_MESSAGE == (
        "This Word file couldn't be read. It may be damaged or not a real .docx "
        "document. Try re-saving it as a new .docx."
    )


@pytest.mark.parametrize("filename", ["r.pdf", "r.docx", "r.txt", "r.csv"])
def test_size_limit_applies_to_every_format(filename):
    with pytest.raises(DocumentTooLarge) as exc:
        extract_text(filename, b"0" * (MAX_UPLOAD_BYTES + 1))
    assert str(exc.value) == "That file is larger than the 10 MB limit."


def test_a_file_exactly_at_the_size_limit_gets_past_the_size_check():
    with pytest.raises(UnreadableDocument):  # turned away for length (10 MB of text), not for size
        extract_text("r.txt", b"a" * MAX_UPLOAD_BYTES)


def test_txt_length_limit_is_about_thirty_pages():
    limit = MAX_PAGES * CHARS_PER_PAGE_ESTIMATE
    assert extract_text("r.txt", b"a" * limit) == "a" * limit
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("r.txt", b"a" * (limit + 1))
    assert str(exc.value) == (
        f"That document is about {MAX_PAGES + 1} pages long; the limit is {MAX_PAGES}. "
        "Reports are expected to be short."
    )


def test_docx_length_limit_uses_the_same_estimate():
    too_long = _make_docx_bytes(["a" * (MAX_PAGES * CHARS_PER_PAGE_ESTIMATE + 1)])
    with pytest.raises(UnreadableDocument) as exc:
        extract_text("r.docx", too_long)
    assert "pages long" in str(exc.value)


def test_missing_filename_is_an_unsupported_type_not_a_crash():
    with pytest.raises(UnsupportedDocumentType):
        extract_text(None, b"x")


def test_unsupported_message_names_the_supported_formats():
    with pytest.raises(UnsupportedDocumentType) as exc:
        extract_text("report.csv", b"a,b")
    assert str(exc.value) == "'report.csv' isn't a supported format yet. DOCX, TXT and PDF are handled; CSV isn't built yet."


# ---------------------------------------------------------------------------
# Downstream contract: PDF text reaches report-type detection like pasted text
# ---------------------------------------------------------------------------

_DISEASE_GAZETTEER = Gazetteer(["Influenza", "Measles", "Meningococcal disease"])
_VACCINE_GAZETTEER = Gazetteer(["Hexa", "MMR", "Meningococcal ACWY"])
_LAB_TEST_GAZETTEER = Gazetteer(["Influenza PCR", "Measles IgM Serology"])

# Hard-wrapped the way a PDF is, with a multi-word term straddling a line break.
_HARD_WRAPPED_REPORTS = {
    "notifiable": ["Suspected case of Influenza, onset", "2026-01-04, diagnosis confirmed by PCR."],
    "immunization": ["1st dose of Hexa vaccine administered, no adverse event", "following immunization."],
    "laboratory": ["Nasopharyngeal swab specimen collected for Influenza", "PCR. Result: Positive."],
}


@pytest.mark.parametrize("expected_type", list(_HARD_WRAPPED_REPORTS))
def test_pdf_text_is_detected_like_the_same_text_pasted(expected_type):
    lines = _HARD_WRAPPED_REPORTS[expected_type]
    from_pdf = extract_text("report.pdf", make_pdf([lines]))
    pasted = " ".join(lines)
    gazetteers = (_DISEASE_GAZETTEER, _VACCINE_GAZETTEER, _LAB_TEST_GAZETTEER)
    assert detect_report_type(from_pdf, *gazetteers)[0] == detect_report_type(pasted, *gazetteers)[0] == expected_type
