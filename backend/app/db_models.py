"""
SQLAlchemy ORM model for a Notifiable Disease record, saved AFTER human
review confirms it — this table is the "reviewed and trusted" store that
Metabase (or any BI tool) will read from, not a raw extraction log.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class NotifiableDiseaseRecord(Base):
    __tablename__ = "notifiable_disease_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    disease_name: Mapped[str] = mapped_column(String, nullable=False)
    diagnosis_status: Mapped[str] = mapped_column(String, nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    patient_age: Mapped[int] = mapped_column(Integer, nullable=True)
    patient_sex: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    region: Mapped[str] = mapped_column(String, nullable=False)
    facility_name: Mapped[str] = mapped_column(String, nullable=True)
    lab_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_excerpt: Mapped[str] = mapped_column(String, nullable=True)

    # Full confidence report kept for audit — lets anyone re-check exactly
    # what the model was sure/unsure about at save time.
    confidence: Mapped[dict] = mapped_column(JSON, nullable=True)

    # Denormalized on purpose: computed once at save time from the
    # confidence dict, so a BI tool can filter/aggregate on this without
    # needing to parse JSON in every query.
    needed_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
