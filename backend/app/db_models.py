"""
SQLAlchemy ORM models for the "reviewed and trusted" record stores —
saved AFTER human review confirms them, not raw extraction logs. Any BI
tool (dashboard, Metabase) reads from these tables, not from extraction
output directly.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class NotifiableDiseaseRecord(Base):
    __tablename__ = "notifiable_disease_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    disease_name: Mapped[str] = mapped_column(String, nullable=False)
    icd10_code: Mapped[str] = mapped_column(String, nullable=True)
    diagnosis_status: Mapped[str] = mapped_column(String, nullable=False)

    # onset_date is nullable because reports often omit it, but where present
    # it's the better basis for an epidemic curve than report_date.
    onset_date: Mapped[date] = mapped_column(Date, nullable=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)

    patient_age: Mapped[int] = mapped_column(Integer, nullable=True)
    patient_sex: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    occupation: Mapped[str] = mapped_column(String, nullable=True)

    region: Mapped[str] = mapped_column(String, nullable=False)
    facility_name: Mapped[str] = mapped_column(String, nullable=True)

    # None = not stated in the report, which is different from "no travel".
    travel_related: Mapped[bool] = mapped_column(Boolean, nullable=True)
    travel_country: Mapped[str] = mapped_column(String, nullable=True)

    vaccination_status: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    outcome: Mapped[str] = mapped_column(String, nullable=False, default="unknown")

    lab_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lab_test_type: Mapped[str] = mapped_column(String, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(String, nullable=True)

    # Full confidence report kept for audit — lets anyone re-check exactly
    # what the model was sure/unsure about at save time.
    confidence: Mapped[dict] = mapped_column(JSON, nullable=True)

    # Denormalized on purpose: computed once at save time from the
    # confidence dict, so a BI tool can filter/aggregate on this without
    # needing to parse JSON in every query.
    needed_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Which named batch/cohort this record belongs to, if any. NULL means
    # "original bulk load" — the initial 500-report dataset, never
    # explicitly batched. A reviewer chooses a batch at save time (new or
    # existing) so a dashboard can be filtered to just that cohort — e.g.
    # a specific outbreak period or region under active review — without
    # disturbing the baseline data. See docs/decisions-log.md.
    batch_label: Mapped[str] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SavedImmunizationRecord(Base):
    """
    The persisted (reviewed and trusted) store — named differently from
    the Pydantic ImmunizationRecord schema (app/schemas/immunization.py)
    on purpose, so both can be imported in the same file without aliasing,
    the same way NotifiableDiseaseCase/NotifiableDiseaseRecord are
    distinct names above.
    """
    __tablename__ = "immunization_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    vaccine_name: Mapped[str] = mapped_column(String, nullable=False)
    vaccine_code: Mapped[str] = mapped_column(String, nullable=True)
    dose_number: Mapped[int] = mapped_column(Integer, nullable=True)
    lot_number: Mapped[str] = mapped_column(String, nullable=True)

    administration_date: Mapped[date] = mapped_column(Date, nullable=False)
    route: Mapped[str] = mapped_column(String, nullable=False, default="unknown")

    patient_age: Mapped[int] = mapped_column(Integer, nullable=True)
    # See ImmunizationRecord (Pydantic schema) for why this exists
    # alongside patient_age: most of the schedule is stated in months for
    # children under 2, where a whole-year age is nearly meaningless.
    patient_age_months: Mapped[int] = mapped_column(Integer, nullable=True)

    region: Mapped[str] = mapped_column(String, nullable=False)
    facility_name: Mapped[str] = mapped_column(String, nullable=True)

    adverse_event_reported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    adverse_event_severity: Mapped[str] = mapped_column(String, nullable=False, default="none")
    adverse_event_description: Mapped[str] = mapped_column(String, nullable=True)

    source_excerpt: Mapped[str] = mapped_column(String, nullable=True)

    # Full confidence report kept for audit — lets anyone re-check exactly
    # what the model was sure/unsure about at save time.
    confidence: Mapped[dict] = mapped_column(JSON, nullable=True)

    # Denormalized on purpose: computed once at save time from the
    # confidence dict, so a BI tool can filter/aggregate on this without
    # needing to parse JSON in every query.
    needed_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Same batch/cohort concept as NotifiableDiseaseRecord above.
    batch_label: Mapped[str] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
