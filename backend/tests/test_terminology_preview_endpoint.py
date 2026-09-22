"""
GET /terminology/preview: the HTTP contract the review-table preview (M2) will call.

TestClient is used WITHOUT `with`, so the startup hook (database init) does not run and no
database is needed -- this endpoint has no DB dependency at all, unlike most of this file's
siblings (it's a pure file-backed lookup, same as the vocabularies.py functions it calls).
"""

import pytest
from fastapi.testclient import TestClient

from app import main

URL = "/terminology/preview"


@pytest.fixture(scope="module")
def client():
    return TestClient(main.app)


def _preview(client, report_type, value=None, **kwargs):
    params = {"report_type": report_type}
    if value is not None:
        params["value"] = value
    return client.get(URL, params=params, **kwargs)


# ---------------------------------------------------------------------------
# One happy path per report type, each hitting its own terminology system
# ---------------------------------------------------------------------------


def test_notifiable_disease_preview(client):
    response = _preview(client, "notifiable", "Anthrax")
    assert response.status_code == 200
    assert response.json() == {
        "system": "ICD-10",
        "code": "A22",
        "status": None,
        "note": None,
        "in_vocabulary": True,
    }


def test_immunization_preview(client):
    response = _preview(client, "immunization", "BCG")
    assert response.status_code == 200
    body = response.json()
    assert body["system"] == "CVX"
    assert body["code"] == "19"
    assert body["status"] == "EXACT"
    assert body["in_vocabulary"] is True


def test_laboratory_preview(client):
    response = _preview(client, "laboratory", "Dengue IgM Serology")
    assert response.status_code == 200
    body = response.json()
    assert body["system"] == "LOINC"
    assert body["code"] == "25338-5"
    assert body["status"] == "EXACT"
    assert body["in_vocabulary"] is True


def test_flagged_icd10_disease_carries_its_note_over_http(client):
    body = _preview(client, "notifiable", "Influenza").json()
    assert body["code"] == "J11"
    assert body["note"] is not None
    assert "J09-J11" in body["note"]


# ---------------------------------------------------------------------------
# The requirement this feature exists to satisfy: "doesn't match the vocabulary yet" must be
# distinguishable from "matched, but no code by deliberate clinical decision" -- for every one of
# the 3 real null-LOINC tests, and for a value that plainly isn't in any vocabulary at all.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "report_type,value,expected_status",
    [
        ("laboratory", "Poliovirus Stool PCR", "REJECTED_MISMATCH"),
        ("laboratory", "Hantavirus IgM Serology", "NO_DIRECT_LOINC"),
        ("laboratory", "Leprosy Skin Biopsy", "NO_DIRECT_LOINC"),
    ],
)
def test_deliberately_uncoded_lab_tests_are_clearly_not_unmatched(client, report_type, value, expected_status):
    body = _preview(client, report_type, value).json()
    assert body["code"] is None
    assert body["status"] == expected_status
    assert body["in_vocabulary"] is True
    assert body["note"] is not None and body["note"].strip() != ""


@pytest.mark.parametrize(
    "report_type,value",
    [
        ("notifiable", "Some Disease That Does Not Exist"),
        ("immunization", "Some Vaccine That Does Not Exist"),
        ("laboratory", "Some Made Up Test Nobody Has Heard Of"),
    ],
)
def test_unmatched_wording_looks_nothing_like_a_deliberate_no_code_case(client, report_type, value):
    body = _preview(client, report_type, value).json()
    assert body["code"] is None
    assert body["status"] is None
    assert body["note"] is None
    assert body["in_vocabulary"] is False


# ---------------------------------------------------------------------------
# Edge cases: no report type with a lookup, no/blank value, and a real pre-existing data quirk
# ---------------------------------------------------------------------------


def test_unknown_report_type_is_a_client_error_not_a_crash(client):
    response = _preview(client, "syndromic", "anything")  # a real report type elsewhere in the app,
    assert response.status_code == 422                     # just not one with a terminology lookup
    assert "syndromic" in response.json()["detail"]


def test_completely_bogus_report_type_is_also_a_client_error(client):
    assert _preview(client, "not-a-real-type", "anything").status_code == 422


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_blank_value_is_a_clean_no_match_not_an_error(client, value):
    response = _preview(client, "notifiable", value)
    assert response.status_code == 200
    assert response.json() == {
        "system": "ICD-10",
        "code": None,
        "status": None,
        "note": None,
        "in_vocabulary": False,
    }


def test_the_real_comment_key_in_cvx_codes_json_is_handled_safely_over_http(client):
    """cvx_codes.json's own '_comment' is a plain string, not a vaccine entry -- confirms the
    endpoint surfaces vocabularies.py's defensive handling of it rather than a raw 500."""
    response = _preview(client, "immunization", "_comment")
    assert response.status_code == 200
    assert response.json()["in_vocabulary"] is False


# ---------------------------------------------------------------------------
# This is advisory only: it must never touch extraction/confidence/save, and error responses must
# still be readable cross-origin the same as every other endpoint (both flows call this from the
# frontend's own separate origin, same as parse-document/detect-type/extract/save already do).
# ---------------------------------------------------------------------------


def test_error_response_still_carries_cors_headers(client):
    origin = "http://localhost:5500"
    response = _preview(client, "not-a-real-type", "x", headers={"Origin": origin})
    assert response.status_code == 422
    assert response.headers["access-control-allow-origin"] in ("*", origin)


def test_preview_module_defines_no_new_request_body_model():
    """A GET with query params, not a POST body -- confirms the endpoint stayed as simple as a
    read-only preview should be, matching this module's own design reasoning (see main.py)."""
    import inspect

    signature = inspect.signature(main.terminology_preview)
    assert list(signature.parameters) == ["report_type", "value"]
