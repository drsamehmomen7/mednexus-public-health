"""
Structured schemas for Syndromic Surveillance and Outbreak/Cluster reports.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class SyndromicReport(BaseModel):
    """One structured symptom-based report used for early outbreak detection."""

    chief_complaint: str = Field(..., description="Primary presenting symptom(s) as stated")
    syndrome_category: Optional[str] = Field(
        None, description="e.g. 'Influenza-like illness', 'Acute gastroenteritis'"
    )

    visit_date: date = Field(..., description="Date of the healthcare encounter")
    patient_age: Optional[int] = Field(None, ge=0, le=120)
    region: str = Field(..., description="Governorate / health district of the reporting facility")
    facility_name: Optional[str] = None

    source_excerpt: Optional[str] = None


class OutbreakReport(BaseModel):
    """One structured group-level report covering a detected outbreak event."""

    disease_or_syndrome: str = Field(..., description="Suspected or confirmed cause of the cluster")
    case_count: int = Field(..., ge=1, description="Number of cases in this cluster/outbreak")
    date_range_start: date = Field(..., description="Earliest case onset date in the cluster")
    date_range_end: Optional[date] = Field(None, description="Latest case onset date, if the cluster is closed")

    region: str = Field(..., description="Governorate / health district where the outbreak occurred")
    affected_facilities: Optional[List[str]] = Field(
        None, description="Facilities reporting cases within this outbreak"
    )

    source_excerpt: Optional[str] = None
