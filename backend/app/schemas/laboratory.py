"""
Structured schema for a Laboratory Report feeding public health surveillance.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TestResult(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    INDETERMINATE = "indeterminate"
    PENDING = "pending"


class LaboratoryReport(BaseModel):
    """One structured laboratory result relevant to surveillance."""

    test_name: str = Field(..., description="e.g. 'PCR - Influenza A', 'Blood Culture'")
    test_code: Optional[str] = Field(
        None, description="LOINC code once terminology normalization is added"
    )
    specimen_type: Optional[str] = Field(None, description="e.g. 'Nasopharyngeal swab', 'Blood'")

    result: TestResult
    pathogen_identified: Optional[str] = Field(
        None, description="Organism/pathogen name if the result identifies one"
    )

    specimen_collection_date: Optional[date] = None
    result_date: date = Field(..., description="Date the result was finalized")

    patient_age: Optional[int] = Field(None, ge=0, le=120)
    region: str = Field(..., description="Governorate / health district of the reporting lab")
    facility_name: Optional[str] = None

    source_excerpt: Optional[str] = None
