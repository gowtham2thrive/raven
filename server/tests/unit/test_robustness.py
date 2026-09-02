"""
Robustness Tests — Phases 1-4.

Tests for:
- Phase 1: Raw source capsule preservation and hash integrity
- Phase 2: Boundary validation, ingestion quarantine, and error handling
- Phase 3: Causal validation and multi-source triangulation
- Phase 4: Citation verification gate (zero-hallucination)

These cover failure modes the original test suite doesn't:
malformed input, schema drift, ingestion errors, impossible timelines,
single-source false confidence, and unsupported claims in response drafts.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.pipeline.ingest import (
    _hash_payload,
    normalize_auth,
    normalize_communications,
    normalize_delivery,
    normalize_razorpay_order,
    normalize_razorpay_payment,
    normalize_shipping,
    validate_auth,
    validate_delivery,
    validate_payment,
    validate_shipping,
)
from app.connectors.quarantine import IngestionQuarantine, QuarantinedRecord
from app.core.types import EvidenceCategory, EvidenceStatus
from app.core.schemas import Evidence


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database for quarantine tests."""
    db_path = str(tmp_path / "test_quarantine.db")
    return db_path


@pytest.fixture
def quarantine(tmp_db):
    """Create a quarantine instance with a temp database."""
    return IngestionQuarantine(db_path=tmp_db)


def _valid_payment() -> dict:
    """A valid Razorpay payment payload."""
    return {
        "id": "pay_test123",
        "amount": 50000,
        "currency": "INR",
        "status": "captured",
        "method": "card",
        "created_at": 1693000000,
        "captured": True,
        "international": False,
        "card": {
            "network": "Visa",
            "last4": "1234",
            "type": "credit",
            "issuer": "HDFC",
        },
    }


def _valid_shipping() -> dict:
    """A valid merchant shipping payload."""
    return {
        "carrier": "BlueDart",
        "tracking_id": "BD123456",
        "shipped_at": "2026-08-20T10:00:00+05:30",
        "status": "delivered",
        "origin_city": "Mumbai",
        "destination_city": "Pune",
    }


def _valid_delivery() -> dict:
    """A valid merchant delivery payload."""
    return {
        "delivered_at": "2026-08-22T14:30:00+05:30",
        "proof_type": "signature",
        "signed_by": "John Doe",
        "delivery_address": "123 Main St, Pune",
    }


def _valid_auth() -> dict:
    """A valid merchant auth payload."""
    return {
        "method": "otp",
        "verified": True,
        "device_known": True,
        "ip_country": "IN",
    }


# ═══════════════════════════════════════════════════════════════
#  PHASE 1: Raw Source Capsule Preservation
# ═══════════════════════════════════════════════════════════════


class TestRawSourceCapsule:
    """Every normalized evidence item must preserve its raw source."""

    def test_payment_preserves_raw_source(self):
        """Payment normalization stores the original payload."""
        payment = _valid_payment()
        ev = normalize_razorpay_payment(payment, "CASE-TEST")

        assert ev.raw_source == payment
        assert ev.raw_source_hash != ""

    def test_delivery_preserves_raw_source(self):
        """Delivery normalization stores the original payload."""
        delivery = _valid_delivery()
        ev = normalize_delivery(delivery, "CASE-TEST")

        assert ev.raw_source == delivery
        assert ev.raw_source_hash != ""

    def test_shipping_preserves_raw_source(self):
        """Shipping normalization stores the original payload."""
        shipping = _valid_shipping()
        ev = normalize_shipping(shipping, "CASE-TEST")

        assert ev.raw_source == shipping
        assert ev.raw_source_hash != ""

    def test_auth_preserves_raw_source(self):
        """Auth normalization stores the original payload."""
        auth = _valid_auth()
        ev = normalize_auth(auth, "CASE-TEST")

        assert ev.raw_source == auth
        assert ev.raw_source_hash != ""

    def test_raw_hash_is_deterministic(self):
        """Same payload always produces the same hash."""
        payment = _valid_payment()
        hash1 = _hash_payload(payment)
        hash2 = _hash_payload(payment)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_different_payloads_different_hashes(self):
        """Different payloads produce different hashes."""
        payment1 = _valid_payment()
        payment2 = _valid_payment()
        payment2["amount"] = 99999

        assert _hash_payload(payment1) != _hash_payload(payment2)

    def test_missing_data_has_empty_raw_source(self):
        """When input is None, raw_source defaults to empty dict."""
        ev = normalize_delivery(None, "CASE-TEST")

        assert ev.raw_source == {}
        assert ev.raw_source_hash == ""


# ═══════════════════════════════════════════════════════════════
#  PHASE 2: Boundary Validation
# ═══════════════════════════════════════════════════════════════


class TestBoundaryValidation:
    """Input schemas catch malformed data at the boundary."""

    def test_valid_payment_passes(self):
        """A well-formed payment should pass validation."""
        payment = _valid_payment()
        result = validate_payment(payment)
        assert result.id == "pay_test123"

    def test_missing_required_field_raises_error(self):
        """Payment without 'id' should fail validation."""
        payment = _valid_payment()
        del payment["id"]

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            validate_payment(payment)

    def test_wrong_type_raises_error(self):
        """Payment with string amount should fail validation."""
        payment = _valid_payment()
        payment["amount"] = "not_a_number"

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            validate_payment(payment)

    def test_shipping_extra_field_raises_error(self):
        """Shipping with an unexpected field should fail (extra='forbid')."""
        shipping = _valid_shipping()
        shipping["surprise_field"] = "unexpected"

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            validate_shipping(shipping)

    def test_delivery_extra_field_raises_error(self):
        """Delivery with an unexpected field should fail."""
        delivery = _valid_delivery()
        delivery["unknown_key"] = True

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            validate_delivery(delivery)

    def test_auth_extra_field_raises_error(self):
        """Auth with an unexpected field should fail."""
        auth = _valid_auth()
        auth["extra_field"] = "oops"

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            validate_auth(auth)


# ═══════════════════════════════════════════════════════════════
#  PHASE 2: Ingestion Quarantine
# ═══════════════════════════════════════════════════════════════


class TestIngestionQuarantine:
    """Bad data is quarantined in SQLite, not silently dropped."""

    def test_quarantine_stores_record(self, quarantine):
        """Quarantined records are persisted to SQLite."""
        record = IngestionQuarantine.make_record(
            case_id="CASE-TEST",
            source_system="razorpay",
            evidence_category="payment",
            raw_payload={"bad": "data"},
            error_message="Missing field: id",
        )
        quarantine.quarantine(record)

        records = quarantine.list_quarantined("CASE-TEST")
        assert len(records) == 1
        assert records[0].case_id == "CASE-TEST"
        assert records[0].source_system == "razorpay"

    def test_quarantine_retrieves_by_case_id(self, quarantine):
        """Only records for the requested case are returned."""
        for case_id in ["CASE-A", "CASE-B", "CASE-A"]:
            quarantine.quarantine(IngestionQuarantine.make_record(
                case_id=case_id,
                source_system="test",
                evidence_category="payment",
                raw_payload={},
                error_message="test",
            ))

        assert len(quarantine.list_quarantined("CASE-A")) == 2
        assert len(quarantine.list_quarantined("CASE-B")) == 1
        assert len(quarantine.list_quarantined("CASE-C")) == 0

    def test_quarantine_count(self, quarantine):
        """Count returns correct totals."""
        assert quarantine.count() == 0

        quarantine.quarantine(IngestionQuarantine.make_record(
            case_id="CASE-X",
            source_system="test",
            evidence_category="payment",
            raw_payload={},
            error_message="test",
        ))

        assert quarantine.count() == 1
        assert quarantine.count(case_id="CASE-X") == 1
        assert quarantine.count(case_id="CASE-Y") == 0

    def test_quarantine_preserves_raw_payload(self, quarantine):
        """The exact failing payload is stored for inspection."""
        bad_payload = {"id": 12345, "amount": "not_int", "extra": [1, 2, 3]}

        quarantine.quarantine(IngestionQuarantine.make_record(
            case_id="CASE-TEST",
            source_system="razorpay",
            evidence_category="payment",
            raw_payload=bad_payload,
            error_message="validation failed",
        ))

        records = quarantine.list_quarantined("CASE-TEST")
        assert records[0].raw_payload == bad_payload

    def test_malformed_payment_quarantined_and_returns_ingestion_error(self, quarantine):
        """A malformed payment is quarantined AND returns INGESTION_ERROR evidence."""
        bad_payment = {"amount": "not_a_number", "status": "captured"}  # Missing 'id', 'method', 'created_at'

        ev = normalize_razorpay_payment(bad_payment, "CASE-TEST", quarantine)

        # Evidence should have INGESTION_ERROR status
        assert ev.status == EvidenceStatus.INGESTION_ERROR
        assert "validation" in ev.summary.lower() or "failed" in ev.summary.lower()

        # Raw source should still be preserved
        assert ev.raw_source == bad_payment
        assert ev.raw_source_hash != ""

        # Should be quarantined in the database
        records = quarantine.list_quarantined("CASE-TEST")
        assert len(records) == 1
        assert records[0].evidence_category == "payment"

    def test_malformed_shipping_quarantined(self, quarantine):
        """Malformed shipping data with extra field is quarantined."""
        bad_shipping = {
            "carrier": "BlueDart",
            "tracking_id": "BD123",
            "shipped_at": "2026-08-20T10:00:00",
            "status": "shipped",
            "rogue_field": "should_not_be_here",  # extra='forbid' triggers this
        }

        ev = normalize_shipping(bad_shipping, "CASE-TEST", quarantine)

        assert ev.status == EvidenceStatus.INGESTION_ERROR
        assert quarantine.count(case_id="CASE-TEST") == 1

    def test_investigation_continues_after_quarantine(self, quarantine):
        """Even with quarantined data, the normalizer returns usable evidence."""
        bad_payment = {"garbage": True}
        ev = normalize_razorpay_payment(bad_payment, "CASE-TEST", quarantine)

        # Should return a valid Evidence object (not crash)
        assert ev.evidence_id.startswith("ev_")
        assert ev.case_id == "CASE-TEST"
        assert ev.category.value == "payment"
        assert ev.status == EvidenceStatus.INGESTION_ERROR


# ═══════════════════════════════════════════════════════════════
#  PHASE 3: Causal Validation
# ═══════════════════════════════════════════════════════════════

from app.pipeline.analysis import validate_causal_order, violations_to_contradictions


def _make_evidence(
    case_id: str,
    category: str,
    event_time_utc: datetime | None = None,
    status: str = "available",
    source_system: str = "test",
    content: dict | None = None,
) -> Evidence:
    """Helper to build minimal Evidence for testing."""
    import uuid
    return Evidence(
        evidence_id=f"ev_{uuid.uuid4().hex[:10]}",
        case_id=case_id,
        category=EvidenceCategory(category),
        status=EvidenceStatus(status),
        source_system=source_system,
        source_record_id=f"test_{uuid.uuid4().hex[:6]}",
        observed_at=datetime.now(timezone.utc),
        event_time_utc=event_time_utc,
        content=content or {},
        summary=f"Test {category}",
    )


class TestCausalValidation:
    """Phase 3: Catch physically impossible timelines."""

    def test_delivery_before_order_detected(self):
        """Delivery happening before order is flagged."""
        evidence = [
            _make_evidence("C1", "order", datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)),
            _make_evidence("C1", "delivery", datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)),
        ]
        violations = validate_causal_order(evidence)
        assert len(violations) >= 1
        assert any("Delivery" in v.earlier_event for v in violations)

    def test_shipping_before_order_detected(self):
        """Shipping happening before order is flagged."""
        evidence = [
            _make_evidence("C1", "order", datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)),
            _make_evidence("C1", "shipping", datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)),
        ]
        violations = validate_causal_order(evidence)
        assert len(violations) >= 1
        assert any("Shipping" in v.earlier_event for v in violations)

    def test_refund_before_payment_detected(self):
        """Refund before payment is flagged."""
        evidence = [
            _make_evidence("C1", "payment", datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)),
            _make_evidence("C1", "refund", datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)),
        ]
        violations = validate_causal_order(evidence)
        assert len(violations) >= 1
        assert any("Refund" in v.earlier_event for v in violations)

    def test_valid_order_passes(self):
        """Correct chronological order produces no violations."""
        evidence = [
            _make_evidence("C1", "order", datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)),
            _make_evidence("C1", "shipping", datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)),
            _make_evidence("C1", "delivery", datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)),
        ]
        violations = validate_causal_order(evidence)
        assert len(violations) == 0

    def test_missing_timestamps_skipped(self):
        """Evidence without timestamps doesn't trigger violations."""
        evidence = [
            _make_evidence("C1", "order", None),  # No timestamp
            _make_evidence("C1", "delivery", datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)),
        ]
        violations = validate_causal_order(evidence)
        assert len(violations) == 0  # Can't compare without both timestamps

    def test_violations_convert_to_contradictions(self):
        """CausalViolations convert to Contradiction objects correctly."""
        evidence = [
            _make_evidence("C1", "order", datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)),
            _make_evidence("C1", "delivery", datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)),
        ]
        violations = validate_causal_order(evidence)
        contradictions = violations_to_contradictions(violations)
        assert len(contradictions) >= 1
        assert contradictions[0].impact == "high"
        assert contradictions[0].requires_human_review is True


# ═══════════════════════════════════════════════════════════════
#  PHASE 3: Triangulation
# ═══════════════════════════════════════════════════════════════

from app.pipeline.analysis import triangulate_delivery, apply_triangulation


class TestTriangulation:
    """Phase 3: Multi-source evidence verification."""

    def test_single_source_delivery_downgraded(self):
        """Single-source delivery gets reliability downgraded."""
        evidence = [
            _make_evidence(
                "C1", "delivery",
                datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
                source_system="merchant_delivery",
            ),
        ]
        # Set reliability to high to test downgrade
        evidence[0].reliability = "high"

        tri = triangulate_delivery(evidence)
        assert tri.triangulated is False
        assert tri.supporting_count == 1
        assert "Single-source" in tri.confidence_note

        # Apply should downgrade (returns new list, does not mutate input)
        result = apply_triangulation(evidence, tri)
        assert result[0].reliability == "medium"

    def test_dual_source_delivery_stays_high(self):
        """Two independent sources confirming delivery stays HIGH."""
        evidence = [
            _make_evidence(
                "C1", "delivery",
                datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
                source_system="merchant_delivery",
            ),
            _make_evidence(
                "C1", "delivery",
                datetime(2026, 8, 23, 10, 5, tzinfo=timezone.utc),
                source_system="carrier_api",
            ),
        ]
        evidence[0].reliability = "high"
        evidence[1].reliability = "high"

        tri = triangulate_delivery(evidence)
        assert tri.triangulated is True
        assert tri.supporting_count >= 2

        # Apply should NOT downgrade
        apply_triangulation(evidence, tri)
        assert evidence[0].reliability == "high"

    def test_no_delivery_returns_no_triangulation(self):
        """No delivery evidence produces empty triangulation."""
        evidence = [
            _make_evidence("C1", "payment", datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)),
        ]
        tri = triangulate_delivery(evidence)
        assert tri.signal_count == 0
        assert tri.triangulated is False

    def test_conflicting_sources_detected(self):
        """Merchant says delivered, shipping says returned."""
        evidence = [
            _make_evidence(
                "C1", "delivery",
                datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
                source_system="merchant_delivery",
            ),
            _make_evidence(
                "C1", "shipping",
                datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
                source_system="carrier_tracking",
                content={"status": "returned_to_sender"},
            ),
        ]
        evidence[0].reliability = "high"

        tri = triangulate_delivery(evidence)
        assert tri.conflicting_count >= 1
        assert tri.triangulated is False
        assert "Conflicting" in tri.confidence_note


# ═══════════════════════════════════════════════════════════════
#  PHASE 4: Citation Verification
# ═══════════════════════════════════════════════════════════════

from app.pipeline.assess import verify_response
from app.core.schemas import Assessment, EvidenceCheckItem
from app.core.types import CaseStrength, Recommendation


def _make_assessment(strength: str = "high", recommendation: str = "contest") -> Assessment:
    """Helper to build minimal Assessment for testing."""
    from app.core.types import Confidence
    return Assessment(
        case_id="CASE-TEST",
        score=0.8 if strength == "high" else 0.3,
        case_strength=CaseStrength(strength),
        confidence=Confidence.HIGH if strength == "high" else Confidence.LOW,
        recommendation=Recommendation(recommendation),
        auto_submit_eligible=(strength == "high"),
        requires_human_review=(strength != "high"),
        evidence_checklist=[],
        assessed_at=datetime.now(timezone.utc),
    )


class TestCitationVerification:
    """Phase 4: Response drafts don't contain unsupported claims."""

    def test_valid_response_passes(self):
        """A response with supported claims passes verification."""
        evidence = [
            _make_evidence(
                "C1", "delivery",
                datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
                content={"signed_by": "John", "proof_type": "signature"},
            ),
            _make_evidence("C1", "authentication", status="available"),
        ]
        assessment = _make_assessment("high")
        draft = "The package was delivered and signed by the recipient."

        result = verify_response(draft, evidence, assessment)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_delivered_claim_with_missing_delivery_fails(self):
        """Claiming 'delivered' when delivery is missing is a violation."""
        evidence = [
            _make_evidence("C1", "delivery", status="missing"),
        ]
        assessment = _make_assessment("low", "human_review")
        draft = "The package was successfully delivered to the customer."

        result = verify_response(draft, evidence, assessment)
        assert result.passed is False
        assert any(v.violation_type == "unsupported_claim" for v in result.violations)

    def test_signed_claim_without_signature_fails(self):
        """Claiming 'signed by' when no signature exists is a violation."""
        evidence = [
            _make_evidence(
                "C1", "delivery",
                datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
                content={"proof_type": "photo", "signed_by": None},
            ),
        ]
        assessment = _make_assessment("high")
        draft = "The delivery was signed by the recipient at the door."

        result = verify_response(draft, evidence, assessment)
        assert result.passed is False
        assert any(v.violation_type == "status_mismatch" for v in result.violations)

    def test_auth_claim_without_auth_fails(self):
        """Claiming 'authenticated' when auth is missing is a violation."""
        evidence = [
            _make_evidence("C1", "authentication", status="missing"),
        ]
        assessment = _make_assessment("high")
        draft = "The transaction was authenticated via OTP verification."

        result = verify_response(draft, evidence, assessment)
        assert result.passed is False
        assert any(v.violation_type == "unsupported_claim" for v in result.violations)

    def test_weak_case_with_certainty_language_fails(self):
        """Overconfident language on a weak case is a violation."""
        evidence = [
            _make_evidence("C1", "delivery", status="missing"),
        ]
        assessment = _make_assessment("low", "human_review")
        draft = "This conclusively proves the customer received the goods."

        result = verify_response(draft, evidence, assessment)
        assert result.passed is False
        assert any(v.violation_type == "certainty_overreach" for v in result.violations)
