"""
Structured schema for an Immunization Report.

System-agnostic by design: fields map to international vaccine/coding
standards (CVX-style vaccine codes), not any single country's registry.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InjectionRoute(str, Enum):
    IM = "intramuscular"
    SC = "subcutaneous"
    ORAL = "oral"
    INTRANASAL = "intranasal"
    INTRADERMAL = "intradermal"
    UNKNOWN = "unknown"


class AdverseEventSeverity(str, Enum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class ImmunizationRecord(BaseModel):
    """One structured vaccination event extracted from an immunization report."""

    vaccine_name: str = Field(
        ..., description="Vaccine name as stated or normalized, e.g. 'MMR', 'BCG'"
    )
    vaccine_code: Optional[str] = Field(
        None, description="Standardized vaccine code once terminology normalization is added"
    )
    dose_number: Optional[int] = Field(
        None, ge=1, le=20, description="Dose number in the series, if stated"
    )
    lot_number: Optional[str] = Field(None, description="Manufacturer lot/batch number")

    administration_date: date = Field(..., description="Date the vaccine was administered")
    route: InjectionRoute = InjectionRoute.UNKNOWN

    patient_age: Optional[int] = Field(None, ge=0, le=120)
    patient_age_months: Optional[int] = Field(
        None, ge=0, le=24,
        description=(
            "Age in months, for infants — most of the immunization schedule "
            "(birth through 18 months) happens before a child's first or "
            "second birthday, where patient_age in whole years is nearly "
            "meaningless (mostly 0). Populated alongside patient_age when "
            "the child is under 2; left unset once whole-year age is the "
            "natural way to state it (boosters at 2y, 3.5y, 10-12y, 16-18y)."
        ),
    )
    region: str = Field(..., description="Governorate / health district of the administering facility")
    facility_name: Optional[str] = None

    adverse_event_reported: bool = Field(
        False, description="Whether an adverse event following immunization (AEFI) was reported"
    )
    adverse_event_severity: AdverseEventSeverity = AdverseEventSeverity.NONE
    adverse_event_description: Optional[str] = None

    source_excerpt: Optional[str] = Field(
        None, description="Short excerpt of the original text for human review"
    )
