"""
Database engine and session setup.

Connection string comes from the DATABASE_URL environment variable — never
hardcode credentials here. Local Postgres example:
    postgresql://mednexus:mednexus@localhost:5432/mednexus_public_health

Loaded from two places, in order of priority:
1. An actual shell environment variable ($env:DATABASE_URL), if set —
   always wins, matches how this worked before.
2. A .env file in backend/ (see .env.example) — read automatically via
   python-dotenv, so DATABASE_URL doesn't need retyping every session.
   Never commit the real .env file; only .env.example is tracked in git.

On Render, DATABASE_URL is provided automatically when you attach a
Postgres instance to the service — no code change needed there.
"""

from os import environ

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Does nothing if DATABASE_URL is already set in the real environment —
# never overrides an explicit $env:DATABASE_URL, only fills the gap when
# nothing else provided one.
load_dotenv()

DATABASE_URL = environ.get(
    "DATABASE_URL",
    "postgresql://mednexus:mednexus@localhost:5432/mednexus_public_health",
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a session, always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Create all tables that don't exist yet.

    Fine for this prototype phase (no data to lose yet). Once real data
    exists, switch to Alembic migrations instead of calling this blindly —
    noted here so it isn't forgotten later.
    """
    from app.db_models import NotifiableDiseaseRecord  # noqa: F401 (registers the model)
    Base.metadata.create_all(bind=engine)
