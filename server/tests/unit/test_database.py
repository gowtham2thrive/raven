"""
Tests for database models — table creation, insertion, relationships.

Uses an in-memory SQLite database for speed.
"""

import pytest
from datetime import datetime, timezone

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import (
    AuditLogModel,
    CaseModel,
    ContradictionModel,
    EvidenceModel,
    TimelineEventModel,
    AgentRunModel,
)


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ── Table Creation ────────────────────────────────────────────

class TestTableCreation:
    def test_all_tables_created(self, db_session):
        """All 6 tables should exist."""
        tables = Base.metadata.tables.keys()
        expected = {
            "cases", "evidence_items", "contradictions",
            "timeline_events", "agent_runs", "audit_logs",
        }
        assert expected.issubset(tables)


# ── Case Model ────────────────────────────────────────────────

class TestCaseModel:
    def test_insert_and_retrieve(self, db_session):
        """CaseModel should insert and retrieve correctly."""
        case = CaseModel(
            id="CASE-00001",
            status="created",
            dispute_reason="product_not_received",
            rzp_dispute_id="disp_test001",
            rzp_payment_id="pay_test001",
            amount=849900,
            reason_code="product_not_received",
            respond_by=datetime(2024, 8, 30, tzinfo=timezone.utc),
        )
        db_session.add(case)
        db_session.commit()

        retrieved = db_session.query(CaseModel).filter_by(id="CASE-00001").first()
        assert retrieved is not None
        assert retrieved.amount == 849900
        assert retrieved.status == "created"
        assert retrieved.rzp_dispute_id == "disp_test001"

    def test_default_status_is_created(self, db_session):
        """New case should default to 'created' status."""
        case = CaseModel(
            id="CASE-00002",
            dispute_reason="product_not_received",
            rzp_dispute_id="disp_test002",
            rzp_payment_id="pay_test002",
            amount=500000,
            reason_code="product_not_received",
            respond_by=datetime(2024, 8, 30, tzinfo=timezone.utc),
        )
        db_session.add(case)
        db_session.commit()

        assert case.status == "created"

    def test_unique_dispute_id(self, db_session):
        """Duplicate rzp_dispute_id should raise."""
        case1 = CaseModel(
            id="CASE-DUP1",
            dispute_reason="product_not_received",
            rzp_dispute_id="disp_duplicate",
            rzp_payment_id="pay_dup1",
            amount=100000,
            reason_code="product_not_received",
            respond_by=datetime(2024, 8, 30, tzinfo=timezone.utc),
        )
        case2 = CaseModel(
            id="CASE-DUP2",
            dispute_reason="product_not_received",
            rzp_dispute_id="disp_duplicate",  # Same dispute ID
            rzp_payment_id="pay_dup2",
            amount=200000,
            reason_code="product_not_received",
            respond_by=datetime(2024, 8, 30, tzinfo=timezone.utc),
        )
        db_session.add(case1)
        db_session.commit()
        db_session.add(case2)

        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()


# ── Evidence Model ────────────────────────────────────────────

class TestEvidenceModel:
    def _make_case(self, db_session, case_id="CASE-EV001") -> CaseModel:
        case = CaseModel(
            id=case_id,
            dispute_reason="product_not_received",
            rzp_dispute_id=f"disp_{case_id}",
            rzp_payment_id=f"pay_{case_id}",
            amount=849900,
            reason_code="product_not_received",
            respond_by=datetime(2024, 8, 30, tzinfo=timezone.utc),
        )
        db_session.add(case)
        db_session.commit()
        return case

    def test_insert_evidence(self, db_session):
        """Evidence should insert and link to case."""
        case = self._make_case(db_session)
        ev = EvidenceModel(
            id="ev_001",
            case_id=case.id,
            category="payment",
            status="available",
            source_system="razorpay",
            source_record_id="pay_test001",
            content={"amount": 849900, "method": "card"},
            summary="Payment of ₹8,499 via Visa card",
        )
        db_session.add(ev)
        db_session.commit()

        assert len(case.evidence_items) == 1
        assert case.evidence_items[0].category == "payment"

    def test_cascade_delete(self, db_session):
        """Deleting a case should cascade-delete its evidence."""
        case = self._make_case(db_session, "CASE-CASCADE")
        ev = EvidenceModel(
            id="ev_cascade",
            case_id=case.id,
            category="delivery",
            source_system="carrier_api",
            source_record_id="del_123",
        )
        db_session.add(ev)
        db_session.commit()

        db_session.delete(case)
        db_session.commit()

        remaining = db_session.query(EvidenceModel).filter_by(id="ev_cascade").first()
        assert remaining is None


# ── Audit Log Model ───────────────────────────────────────────

class TestAuditLogModel:
    def test_insert_audit_log(self, db_session):
        """Audit log should record case actions."""
        case = CaseModel(
            id="CASE-AUDIT",
            dispute_reason="product_not_received",
            rzp_dispute_id="disp_audit",
            rzp_payment_id="pay_audit",
            amount=100000,
            reason_code="product_not_received",
            respond_by=datetime(2024, 8, 30, tzinfo=timezone.utc),
        )
        db_session.add(case)
        db_session.commit()

        log = AuditLogModel(
            id="audit_001",
            case_id=case.id,
            action="webhook_received",
            actor="system",
            details={"event": "payment.dispute.created"},
        )
        db_session.add(log)
        db_session.commit()

        assert len(case.audit_logs) == 1
        assert case.audit_logs[0].action == "webhook_received"


# ── Agent Run Model ───────────────────────────────────────────

class TestAgentRunModel:
    def test_insert_agent_run(self, db_session):
        """Agent run should track tool calls and status."""
        case = CaseModel(
            id="CASE-AGENT",
            dispute_reason="product_not_received",
            rzp_dispute_id="disp_agent",
            rzp_payment_id="pay_agent",
            amount=500000,
            reason_code="product_not_received",
            respond_by=datetime(2024, 8, 30, tzinfo=timezone.utc),
        )
        db_session.add(case)
        db_session.commit()

        run = AgentRunModel(
            id="run_001",
            case_id=case.id,
            status="completed",
            tool_calls_count=8,
            model_used="gemini-2.5-flash",
            total_tokens=3500,
            latency_ms=4200,
        )
        db_session.add(run)
        db_session.commit()

        assert case.agent_runs[0].tool_calls_count == 8
        assert case.agent_runs[0].model_used == "gemini-2.5-flash"
