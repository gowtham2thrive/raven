"""
RAVEN Database Connection.

Uses SQLAlchemy 2.0 with the new DeclarativeBase.
SQLite for development, PostgreSQL for production — switchable via config.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ── Engine & Session Factory ──────────────────────────────────

is_sqlite = "sqlite" in settings.database_url

connect_args = {}
if is_sqlite:
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30

engine = create_engine(
    settings.database_url,
    echo=settings.debug and not settings.is_production,
    connect_args=connect_args,
    pool_pre_ping=True,
)

if is_sqlite:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # Enable WAL mode for file-based SQLite databases (allows concurrent read/write)
        if ":memory:" not in settings.database_url:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    class_=Session,
)


# ── Dependency ────────────────────────────────────────────────

def get_db():
    """FastAPI dependency — yields a DB session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables. Used for development and testing."""
    Base.metadata.create_all(bind=engine)


def drop_tables():
    """Drop all tables. Used for testing only."""
    Base.metadata.drop_all(bind=engine)
