"""
FastAPI Dependency Injection.

Shared dependencies for all API routes.
"""

from __future__ import annotations

from typing import Generator

from sqlalchemy.orm import Session

from app.connectors.synthetic import SyntheticConnector
from app.db.database import SessionLocal
from app.services.case_service import CaseService


def get_db() -> Generator[Session, None, None]:
    """Provide a transactional DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Singleton instances (created once, reused per request)
_connector: SyntheticConnector | None = None
_service: CaseService | None = None
_simulator_service = None


def get_connector() -> SyntheticConnector:
    """Provide the data connector (synthetic for MVP)."""
    global _connector
    if _connector is None:
        _connector = SyntheticConnector()
    return _connector


def get_case_service() -> CaseService:
    """Provide the case orchestration service."""
    global _service
    if _service is None:
        _service = CaseService(connector=get_connector())
    return _service


def get_simulator_service():
    """Provide the dispute simulation service."""
    global _simulator_service
    if _simulator_service is None:
        from app.services.simulator_service import SimulatorService
        _simulator_service = SimulatorService()
    return _simulator_service

