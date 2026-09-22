"""
PDF text extraction against the static fixtures in tests/fixtures/ (see the README there):
a realistic browser-printed report and a few small AES-encrypted files. Everything in them is synthetic.
"""

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.services.document_parsing import ENCRYPTED_PDF_MESSAGE, UnreadableDocument, extract_text
from app.services.gazetteer import Gazetteer
from app.services.report_type_detection import detect_report_type

FIXTURES = Path(__file__).parent / "fixtures"

EM_DASH = chr(0x2014)
DEGREE = chr(0xB0)
LETTERHEAD = f"MINISTRY OF HEALTH {EM_DASH} FARWANIYA HEALTH REGION (SYNTHETIC)"
FOOTER = f"Synthetic test document {EM_DASH} all persons, facilities and data are fictitious"

# Characters that must never survive into the text handed to extraction.
_LEFTOVERS = {0xA0, 0xAD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, *range(0xFB00, 0xFB07)}


@pytest.fixture(scope="module")
def chromium_pdf() -> bytes:
    return (FIXTURES / "chromium_case_report.pdf").read_bytes()


@pytest.fixture(scope="module")
def chromium_text(chromium_pdf) -> str:
    return extract_text("chromium_case_report.pdf", chromium_pdf)


# ---------------------------------------------------------------------------
# A realistic report: embedded subset fonts, letterhead and footer on every page,
# numbered sections, a form-style table, wrapped lines
# ---------------------------------------------------------------------------


def test_fixture_is_a_three_page_document(chromium_pdf):
    assert len(PdfReader(BytesIO(chromium_pdf)).pages) == 3


def test_sections_come_out_in_reading_order(chromium_text):
    headings = [
        "Case Investigation Report: Suspected Influenza Cluster",
        "1. Background and notification",
        "2. Patient information",
        "3. Clinical course",
        "4. Public health actions",
    ]
    positions = [chromium_text.index(heading) for heading in headings]
    assert positions == sorted(positions)


def test_form_table_rows_come_out_one_per_line_in_order(chromium_text):
    rows = [
        "Patient name Sample Patient A",
        "Age / Sex 9 years / Male",
        "Region Farwaniya",
        "Reporting facility Ardiya Clinic",
        "Date of onset September 1, 2026",
        "Diagnosis status Suspected, laboratory confirmation pending",
        "Vaccination status Unvaccinated against seasonal influenza",
    ]
    lines = chromium_text.split("\n")
    start = lines.index(rows[0])
    assert lines[start : start + len(rows)] == rows


def test_dates_and_units_survive(chromium_text):
    for expected in ("September 3, 2026", "2026-09-04", "September 5, 2026", f"39.2{DEGREE}C"):
        assert expected in chromium_text


def test_repeated_letterhead_and_footer_are_kept_on_every_page(chromium_text):
    """Header/footer stripping is deliberately not part of this phase (decision D5)."""
    assert chromium_text.count(LETTERHEAD) == 3
    assert chromium_text.count(FOOTER) == 3


def test_no_invisible_characters_ligatures_or_control_codes_are_left(chromium_text):
    assert not {ord(ch) for ch in chromium_text} & _LEFTOVERS
    assert all(ch == "\n" or ch >= " " for ch in chromium_text)


def test_realistic_report_is_still_recognised_as_a_notifiable_disease_report(chromium_text):
    detected, _ = detect_report_type(
        chromium_text,
        disease_gazetteer=Gazetteer(["Influenza", "Measles"]),
        vaccine_gazetteer=Gazetteer(["Hexa", "MMR"]),
        lab_test_gazetteer=Gazetteer(["Influenza PCR"]),
    )
    assert detected == "notifiable"


# ---------------------------------------------------------------------------
# Known limitations, accepted for this phase (decision D5: only a small clean-up, no unwrapping
# or de-hyphenation). They are strict xfails so that fixing one is noticed: the test then
# fails with XPASS, and the marker (and the note in decisions-log.md) should be removed.
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="pypdf 6.19.0 splits soft-hyphenated words ('influ enza'); PDFium keeps them whole. "
    "If a real PDF shows this, revisit the engine choice (decision D1).",
)
def test_soft_hyphenated_words_come_out_whole(chromium_text):
    sentence = (
        "The influenza vaccination programme coordinator confirmed that the school "
        "had not been included in the autumn immunization campaign."
    )
    assert sentence in " ".join(chromium_text.split())


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="A hyphenated compound wrapped at a line end stays split ('9-year-' / 'old'), "
    "so an age pattern looking for '9-year-old' misses it. Needs line-wrap handling.",
)
def test_hyphenated_compound_wrapped_across_lines_comes_out_whole(chromium_text):
    assert "9-year-old" in chromium_text


# ---------------------------------------------------------------------------
# AES-encrypted files. Reading AES needs a crypto package that is deliberately not shipped
# (decision D4), so these are refused as password-protected.
# ---------------------------------------------------------------------------


def _crypto_package_installed() -> bool:
    return any(importlib.util.find_spec(name) for name in ("cryptography", "Crypto"))


@pytest.mark.parametrize("name", ["aes128_user_password.pdf", "aes256_user_password.pdf"])
def test_aes_pdf_with_a_user_password_is_refused(name):
    with pytest.raises(UnreadableDocument) as exc:
        extract_text(name, (FIXTURES / name).read_bytes())
    assert str(exc.value) == ENCRYPTED_PDF_MESSAGE


@pytest.mark.skipif(
    _crypto_package_installed(),
    reason="a crypto package is installed here, so an AES PDF that has only an owner password is readable",
)
def test_aes_pdf_with_only_an_owner_password_is_refused_without_a_crypto_package():
    name = "aes128_owner_only.pdf"
    with pytest.raises(UnreadableDocument) as exc:
        extract_text(name, (FIXTURES / name).read_bytes())
    assert str(exc.value) == ENCRYPTED_PDF_MESSAGE
