"""
Extracts plain text from an uploaded document, so the SAME extraction
pipeline that already works on pasted text can run on uploaded files too
— this module's only job is "bytes in, text out", nothing report-type
specific.

DOCX only for now (python-docx). PDF/TXT/CSV are mentioned in the
frontend's dropzone hint as "planned for prototype phase" — add a
branch here per format as each one is actually built, rather than
promising formats this doesn't handle yet.
"""

from io import BytesIO
from typing import Optional

from docx import Document


class UnsupportedDocumentType(Exception):
    """Raised when the uploaded file's extension isn't handled yet."""


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Return the document's text content, in reading order: paragraphs
    first, then any tables (row by row, cells joined with a space) —
    covers both a prose-style report and a form-style one with labelled
    fields laid out in a table, which real reporting forms often use.
    """
    document = Document(BytesIO(file_bytes))

    parts = [p.text for p in document.paragraphs if p.text.strip()]

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" ".join(cells))

    return "\n".join(parts)


def extract_text(filename: str, file_bytes: bytes) -> str:
    """
    Dispatch by file extension. Raises UnsupportedDocumentType for
    anything not yet handled, so the caller can return a clear error
    instead of silently returning empty text.
    """
    lowered = filename.lower()
    if lowered.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    if lowered.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="replace")

    raise UnsupportedDocumentType(
        f"'{filename}' isn't a supported format yet. DOCX and TXT are handled; "
        "PDF and CSV aren't built yet."
    )
