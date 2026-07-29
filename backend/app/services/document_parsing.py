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
from docx.table import Table
from docx.text.paragraph import Paragraph


class UnsupportedDocumentType(Exception):
    """Raised when the uploaded file's extension isn't handled yet."""


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Return the document's text content in TRUE reading order — paragraphs
    and tables interleaved exactly as they appear in the document body,
    not all paragraphs followed by all tables.

    This matters for any real form that has a letterhead paragraph, then
    a field table, then a signature-line footer paragraph (the common
    shape of an official reporting form): grouping by element type would
    put the footer text ahead of the table content it actually follows,
    which is disorienting to review even though it happened not to
    break extraction in testing. python-docx doesn't expose body order
    directly, so this walks the underlying XML body children instead.
    """
    document = Document(BytesIO(file_bytes))
    parts = []

    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]

        if tag == "p":
            paragraph = Paragraph(child, document)
            if paragraph.text.strip():
                parts.append(paragraph.text)

        elif tag == "tbl":
            table = Table(child, document)
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
