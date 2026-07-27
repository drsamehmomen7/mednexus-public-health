"""
Structured schema for a Notifiable Disease Case Report.

This defines the target shape of the data we want to extract from a raw
report (text, DOCX, PDF...) — before any AI/rules extraction logic exists.
Building the schema first lets us test "does this data make sense?"
independently of "did we extract it correctly?".

No AI is used here. This is pure data validation.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DiagnosisStatus(str, Enum):
    """How confirmed the case is, per standard surveillance case definitions."""
    SUSPECTED = "suspected"
    PROBABLE = "probable"
    CONFIRMED = "confirmed"


class PatientSex(str, Enum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class VaccinationStatus(str, Enum):
    """
    Vaccination status against the disease being reported (not vaccination
    in general). Standard forms ask this explicitly because it changes case
    interpretation — a measles case in a fully vaccinated patient is a very
    different signal from one in an unvaccinated patient.
    """
    VACCINATED = "vaccinated"
    PARTIALLY_VACCINATED = "partially_vaccinated"
    NOT_VACCINATED = "not_vaccinated"
    UNKNOWN = "unknown"


class CaseOutcome(str, Enum):
    """
    Outcome at the time of reporting. Needed to compute case fatality rate,
    which is one of the few indicators decision-makers ask for immediately.
    """
    RECOVERED = "recovered"
    RECOVERING = "recovering"
    HOSPITALIZED = "hospitalized"
    DIED = "died"
    UNKNOWN = "unknown"


class NotifiableDiseaseCase(BaseModel):
    """One structured case record extracted from a notifiable disease report."""

    # --- Core identification ---
    disease_name: str = Field(
        ..., description="Name of the disease as stated or normalized, e.g. 'Hepatitis C'"
    )
    icd10_code: Optional[str] = Field(
        None, description="ICD-10 code once terminology normalization is added"
    )
    diagnosis_status: DiagnosisStatus = Field(
        ..., description="Suspected, probable, or confirmed per case definition"
    )

    # --- Dates ---
    onset_date: Optional[date] = Field(
        None,
        description=(
            "Date symptoms began. Epidemiologically this matters more than "
            "report_date — epidemic curves are drawn by onset, not by when "
            "paperwork reached the authority."
        ),
    )
    report_date: date = Field(
        ..., description="Date the case was reported to the health authority"
    )

    # --- Patient context (already de-identified upstream — no direct identifiers here) ---
    patient_age: Optional[int] = Field(
        None, ge=0, le=120, description="Age in years, if stated"
    )
    patient_sex: PatientSex = PatientSex.UNKNOWN
    occupation: Optional[str] = Field(
        None,
        description=(
            "Recorded when relevant to transmission risk — food handling, "
            "healthcare, childcare, education. Standard forms ask for it "
            "because it drives contact tracing priority, not for demographics."
        ),
    )

    # --- Location and facility ---
    region: str = Field(
        ..., description="Governorate / health district where the case was reported"
    )
    facility_name: Optional[str] = Field(
        None, description="Reporting hospital or health unit name"
    )

    # --- Travel history ---
    travel_related: Optional[bool] = Field(
        None,
        description=(
            "Whether recent travel is considered relevant to this case. "
            "Separates imported from locally-acquired cases — a core "
            "surveillance classification. None means not stated."
        ),
    )
    travel_country: Optional[str] = Field(
        None, description="Country travelled to, if travel_related is true"
    )

    # --- Immunization and outcome ---
    vaccination_status: VaccinationStatus = VaccinationStatus.UNKNOWN
    outcome: CaseOutcome = CaseOutcome.UNKNOWN

    # --- Laboratory confirmation ---
    lab_confirmed: bool = Field(
        False, description="Whether a laboratory test confirmed the diagnosis"
    )
    lab_test_type: Optional[str] = Field(
        None, description="e.g. 'PCR', 'Culture', 'Rapid antigen test'"
    )

    # --- Traceability back to the source report ---
    source_excerpt: Optional[str] = Field(
        None,
        description=(
            "Short excerpt of the original text this record was extracted from, "
            "for human review. Not the full report."
        ),
    )
