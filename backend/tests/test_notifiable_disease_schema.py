"""
Tests for the NotifiableDiseaseCase schema.

These use synthetic (fake) data only — no real patient information.
Run with: pytest
"""

import pytest
from pydantic import ValidationError

from app.schemas.notifiable_disease import (
    NotifiableDiseaseCase,
    DiagnosisStatus,
    PatientSex,
)


def test_valid_confirmed_case():
    """A well-formed, fully confirmed case should validate without errors."""
    case = NotifiableDiseaseCase(
        disease_name="Hepatitis C",
        diagnosis_status=DiagnosisStatus.CONFIRMED,
        onset_date="2026-06-01",
        report_date="2026-06-10",
        patient_age=34,
        patient_sex=PatientSex.MALE,
        region="Cairo",
        facility_name="Example General Hospital",
        lab_confirmed=True,
        lab_test_type="PCR",
        source_excerpt="Patient presented with fatigue; PCR confirmed HCV.",
    )
    assert case.disease_name == "Hepatitis C"
    assert case.diagnosis_status == DiagnosisStatus.CONFIRMED
    assert case.lab_confirmed is True


def test_minimal_valid_case_with_only_required_fields():
    """Only disease_name, diagnosis_status, report_date, and region are required."""
    case = NotifiableDiseaseCase(
        disease_name="Measles",
        diagnosis_status=DiagnosisStatus.SUSPECTED,
        report_date="2026-07-01",
        region="Giza",
    )
    assert case.patient_sex == PatientSex.UNKNOWN
    assert case.lab_confirmed is False


def test_missing_required_field_raises_error():
    """Omitting a required field (report_date) must fail validation."""
    with pytest.raises(ValidationError):
        NotifiableDiseaseCase(
            disease_name="Cholera",
            diagnosis_status=DiagnosisStatus.PROBABLE,
            region="Alexandria",
        )


def test_invalid_diagnosis_status_raises_error():
    """A status outside suspected/probable/confirmed must fail validation."""
    with pytest.raises(ValidationError):
        NotifiableDiseaseCase(
            disease_name="Measles",
            diagnosis_status="definitely",  # not a valid enum value
            report_date="2026-07-01",
            region="Giza",
        )


def test_age_out_of_range_raises_error():
    """Age must be between 0 and 120."""
    with pytest.raises(ValidationError):
        NotifiableDiseaseCase(
            disease_name="Measles",
            diagnosis_status=DiagnosisStatus.CONFIRMED,
            report_date="2026-07-01",
            region="Giza",
            patient_age=200,
        )
