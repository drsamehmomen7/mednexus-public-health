"""
POST /reports/parse-document: the HTTP contract the upload flows rely on.

Single and Batch upload show the server's `detail` text to the user verbatim, so the status codes and
messages here are part of the interface. TestClient is used WITHOUT `with`, so the startup hook
(database init) does not run and no database is needed.
"""

import asyncio
import threading
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from docx import Document
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile as StarletteUploadFile

from app import main
from app.services.document_parsing import (
    CORRUPT_DOCX_MESSAGE,
    CORRUPT_PDF_MESSAGE,
    ENCRYPTED_PDF_MESSAGE,
    MAX_UPLOAD_BYTES,
    NO_TEXT_PDF_MESSAGE,
    NOT_A_PDF_MESSAGE,
)
from tests.pdf_fixtures import encrypt_pdf, make_pdf

FIXTURES = Path(__file__).parent / "fixtures"
URL = "/reports/parse-document"

_TEXT = "Patient: Test Person\nAge: 34 years"
_PDF = make_pdf([["Patient: Test Person", "Age: 34 years"]])
_DAMAGED_PDF = b"%PDF-1.4\n" + bytes(range(256))


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)


def _upload(client, filename, data, **kwargs):
    return client.post(URL, files={"file": (filename, data, "application/octet-stream")}, **kwargs)


def _docx_bytes(paragraphs):
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Success: the response shape is unchanged for every format, so the frontend needs no changes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,data",
    [
        ("report.txt", _TEXT.encode("utf-8")),
        ("report.docx", _docx_bytes(["Patient: Test Person", "Age: 34 years"])),
        ("report.pdf", _PDF),
        ("REPORT.PDF", _PDF),
    ],
    ids=["txt", "docx", "pdf", "upper-case extension"],
)
def test_supported_upload_returns_its_text(client, filename, data):
    response = _upload(client, filename, data)
    assert response.status_code == 200
    assert response.json() == {"text": _TEXT}


def test_realistic_browser_printed_pdf_is_read(client):
    response = _upload(client, "case_report.pdf", (FIXTURES / "chromium_case_report.pdf").read_bytes())
    assert response.status_code == 200
    lines = response.json()["text"].split("\n")
    assert "2. Patient information" in lines
    assert "Age / Sex 9 years / Male" in lines


# ---------------------------------------------------------------------------
# Failures: each has its own status and its own honest message, passed through verbatim
# ---------------------------------------------------------------------------

_FAILURES = [
    (
        "unsupported type",
        "report.csv",
        b"a,b",
        415,
        "'report.csv' isn't a supported format yet. DOCX, TXT and PDF are handled; CSV isn't built yet.",
    ),
    ("not really a pdf", "report.pdf", b"plain text with a .pdf name", 422, NOT_A_PDF_MESSAGE),
    ("damaged pdf", "report.pdf", _DAMAGED_PDF, 422, CORRUPT_PDF_MESSAGE),
    ("password-protected pdf", "report.pdf", encrypt_pdf(_PDF, "secret"), 422, ENCRYPTED_PDF_MESSAGE),
    (
        "AES-encrypted pdf",
        "report.pdf",
        (FIXTURES / "aes128_user_password.pdf").read_bytes(),
        422,
        ENCRYPTED_PDF_MESSAGE,
    ),
    ("scanned pdf", "report.pdf", make_pdf([[]]), 422, NO_TEXT_PDF_MESSAGE),
    (
        "too many pages",
        "report.pdf",
        make_pdf([[f"page {n}"] for n in range(1, 32)]),
        422,
        "That PDF has 31 pages; the limit is 30. Reports are expected to be short.",
    ),
    ("damaged docx", "report.docx", b"this is not a zip file", 422, CORRUPT_DOCX_MESSAGE),
    ("empty text file", "report.txt", b"  \n ", 422, "No readable text found in that document."),
    (
        "over the size limit",
        "report.txt",
        # "z" never occurs in a multipart boundary (hex digits, dashes, CR/LF). python-multipart 0.0.9 scans
        # payloads made of bytes that DO occur there at ~2 s/MB, which would make this one test take ~20 s.
        b"z" * (MAX_UPLOAD_BYTES + 1),
        413,
        "That file is larger than the 10 MB limit.",
    ),
]


@pytest.mark.parametrize(
    "filename,data,status,message",
    [case[1:] for case in _FAILURES],
    ids=[case[0] for case in _FAILURES],
)
def test_failure_maps_to_its_status_and_message(client, filename, data, status, message):
    response = _upload(client, filename, data)
    assert response.status_code == status
    assert response.json() == {"detail": message}


@pytest.mark.parametrize(
    "filename,data,status",
    [("report.csv", b"a,b", 415), ("report.pdf", _DAMAGED_PDF, 422)],
    ids=["415", "422"],
)
def test_error_responses_are_readable_from_the_browser(client, filename, data, status):
    """The frontend is served from another origin; without CORS headers the browser hides the message."""
    origin = "http://localhost:5500"
    response = _upload(client, filename, data, headers={"Origin": origin})
    assert response.status_code == status
    assert response.headers["access-control-allow-origin"] in ("*", origin)


def test_at_most_one_byte_past_the_size_limit_is_read_into_memory(client, monkeypatch):
    requested = []
    original_read = StarletteUploadFile.read

    async def recording_read(self, size=-1):
        requested.append(size)
        return await original_read(self, size)

    monkeypatch.setattr(StarletteUploadFile, "read", recording_read)
    assert _upload(client, "report.txt", _TEXT.encode("utf-8")).status_code == 200
    assert requested == [MAX_UPLOAD_BYTES + 1]


# ---------------------------------------------------------------------------
# Parsing must not freeze the server (PDF parsing is CPU-bound)
# ---------------------------------------------------------------------------


def test_a_slow_parse_does_not_block_other_requests(monkeypatch):
    """
    Parsing runs in a worker thread. The stub below only finishes early if the event loop keeps serving
    other requests meanwhile; if parsing ran on the loop itself, it would hold the loop for the whole
    wait and `loop_was_free` would come out False.
    """
    started = threading.Event()
    loop_is_free = threading.Event()
    observed = {}

    def slow_parse(filename, data):
        started.set()
        observed["loop_was_free"] = loop_is_free.wait(timeout=5)
        return "parsed text"

    monkeypatch.setattr(main, "extract_text", slow_parse)

    async def scenario():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            upload = asyncio.ensure_future(http.post(URL, files={"file": ("report.txt", b"x")}))
            for _ in range(500):  # up to 5 s for the worker thread to pick the upload up
                if started.is_set() or upload.done():
                    break
                await asyncio.sleep(0.01)
            health = await http.get("/health")
            loop_is_free.set()
            return await upload, health

    upload, health = asyncio.run(scenario())

    assert observed["loop_was_free"] is True
    assert health.status_code == 200
    assert upload.status_code == 200
    assert upload.json() == {"text": "parsed text"}
