"""
Tests for core schemas — evidence model, case state, assessment.

Verifies that the canonical evidence model validates correctly,
rejects invalid data, and serializes to/from JSON.
"""

import pytest
from datetime import datetime, timezone

from app.core.types import (
    CaseStatus,
    CaseStrength,
    Confidence,
    DisputePhase,
    EvidenceCategory,
    EvidenceStatus,
    Recommendation,
    validate_transition,
)
from app.core.schemas import (
    Assessment,
    Case,
    Contradiction,
    Evidence,
    EvidenceCheckItem,
    RazorpayDisputeInfo,
    TimelineEvent,
)


# ── Evidence Model Tests ──────────────────────────────────────

class TestEvidence:
    def test_creates_with_required_fields(self):
        """Evidence with all required fields should be valid."""
        ev = Evidence(
            evidence_id="ev_001",
            case_id="CASE-00001",
            category=EvidenceCategory.PAYMENT,
            source_system="razorpay",
            source_record_id="pay_abc123",
            observed_at=datetime.now(timezone.utc),
        )
        assert ev.evidence_id == "ev_001"
        assert ev.category == EvidenceCategory.PAYMENT
        assert ev.status == EvidenceStatus.AVAILABLE  # default

    def test_default_status_is_available(self):
        """Default evidence status should be AVAILABLE."""
        ev = Evidence(
            evidence_id="ev_002",
            case_id="CASE-00001",
            category=EvidenceCategory.DELIVERY,
            source_system="carrier_api",
            source_record_id="track_123",
            observed_at=datetime.now(timezone.utc),
        )
        assert ev.status == EvidenceStatus.AVAILABLE

    def test_accepts_all_status_types(self):
        """All five evidence status types should be valid."""
        for status in EvidenceStatus:
            ev = Evidence(
                evidence_id=f"ev_{status.value}",
                case_id="CASE-00001",
                category=EvidenceCategory.DELIVERY,
                status=status,
                source_system="test",
                source_record_id="test_123",
                observed_at=datetime.now(timezone.utc),
            )
            assert ev.status == status

    def test_content_defaults_to_empty_dict(self):
        """Evidence content should default to empty dict."""
        ev = Evidence(
            evidence_id="ev_003",
            case_id="CASE-00001",
            category=EvidenceCategory.ORDER,
            source_system="razorpay",
            source_record_id="order_123",
            observed_at=datetime.now(timezone.utc),
        )
        assert ev.content == {}

    def test_serializes_to_json(self):
        """Evidence should serialize to JSON-compatible dict."""
        ev = Evidence(
            evidence_id="ev_004",
            case_id="CASE-00001",
            category=EvidenceCategory.SHIPPING,
            source_system="carrier_api",
            source_record_id="ship_456",
            observed_at=datetime.now(timezone.utc),
            content={"tracking_id": "BLU123456", "status": "delivered"},
            summary="Package delivered via BlueDart",
        )
        data = ev.model_dump()
        assert data["evidence_id"] == "ev_004"
        assert data["content"]["tracking_id"] == "BLU123456"

    def test_timezone_fields(self):
        """Evidence should store timezone information."""
        ev = Evidence(
            evidence_id="ev_005",
            case_id="CASE-00001",
            category=EvidenceCategory.DELIVERY,
            source_system="carrier_api",
            source_record_id="del_789",
            event_time=datetime(2024, 8, 23, 14, 30, tzinfo=timezone.utc),
            event_timezone="Asia/Kolkata",
            event_time_utc=datetime(2024, 8, 23, 14, 30, tzinfo=timezone.utc),
            timezone_confident=True,
            observed_at=datetime.now(timezone.utc),
        )
        assert ev.event_timezone == "Asia/Kolkata"
        assert ev.timezone_confident is True


class TestContradiction:
    def test_creates_contradiction(self):
        """Contradiction should capture conflicting claims."""
        c = Contradiction(
            contradiction_id="contra_001",
            case_id="CASE-00001",
            evidence_a_id="ev_001",
            evidence_a_claim="Product delivered",
            evidence_b_id="ev_002",
            evidence_b_claim="Returned to sender",
            impact="high",
            description="Merchant system says delivered but carrier says RTS",
            detected_at=datetime.now(timezone.utc),
        )
        assert c.impact == "high"
        assert c.requires_human_review is True  # default


# ── Case Model Tests ──────────────────────────────────────────

class TestCase:
    def _make_razorpay_info(self) -> RazorpayDisputeInfo:
        return RazorpayDisputeInfo(
            dispute_id="disp_test001",
            payment_id="pay_test001",
            amount=849900,
            reason_code="product_not_received",
            respond_by=datetime(2024, 8, 30, tzinfo=timezone.utc),
            created_at=datetime(2024, 8, 25, tzinfo=timezone.utc),
        )

    def test_default_status_is_created(self):
        """New case should start in CREATED status."""
        case = Case(
            case_id="CASE-00001",
            dispute_reason="product_not_received",
            razorpay=self._make_razorpay_info(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert case.status == CaseStatus.CREATED

    def test_case_has_evidence_list(self):
        """Case should initialize with empty evidence list."""
        case = Case(
            case_id="CASE-00002",
            dispute_reason="product_not_received",
            razorpay=self._make_razorpay_info(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert case.evidence == []
        assert case.contradictions == []
        assert case.timeline == []

    def test_razorpay_info_parses_amount(self):
        """RazorpayDisputeInfo should store amount in paise."""
        info = self._make_razorpay_info()
        assert info.amount == 849900
        assert info.currency == "INR"


# ── Assessment Tests ──────────────────────────────────────────

class TestAssessment:
    def test_assessment_score_stored(self):
        """Assessment should store score as float."""
        a = Assessment(
            case_id="CASE-00001",
            case_strength=CaseStrength.HIGH,
            recommendation=Recommendation.CONTEST,
            confidence=Confidence.HIGH,
            score=0.92,
            reasons=["All evidence present", "Delivery confirmed with signature"],
            assessed_at=datetime.now(timezone.utc),
        )
        assert 0.0 <= a.score <= 1.0
        assert a.case_strength == CaseStrength.HIGH
        assert a.auto_submit_eligible is False  # default

    def test_checklist_item(self):
        """EvidenceCheckItem should capture category, weight, status."""
        item = EvidenceCheckItem(
            category="delivery",
            label="Delivery confirmation",
            required=True,
            status="available",
            evidence_id="ev_003",
            weight=0.30,
        )
        assert item.weight == 0.30
        assert item.required is True


# ── Timeline Tests ────────────────────────────────────────────

class TestTimeline:
    def test_timeline_event_creates(self):
        """TimelineEvent should store timestamp and source."""
        ev = TimelineEvent(
            event_id="tl_001",
            case_id="CASE-00001",
            timestamp_utc=datetime(2024, 8, 20, 10, 41, tzinfo=timezone.utc),
            label="Payment captured",
            description="₹8,499 via card ending 4242",
            category="payment",
            source_system="razorpay",
        )
        assert ev.label == "Payment captured"
        assert ev.timezone_confident is True  # default

    def test_timezone_uncertain(self):
        """Timeline event with unknown timezone should flag uncertainty."""
        ev = TimelineEvent(
            event_id="tl_002",
            case_id="CASE-00001",
            timestamp_utc=datetime(2024, 8, 23, 14, 30, tzinfo=timezone.utc),
            timezone_original=None,
            timezone_confident=False,
            label="Delivery recorded",
            source_system="carrier_api",
        )
        assert ev.timezone_confident is False


# ── State Transition Tests ────────────────────────────────────

class TestStateTransitions:
    def test_valid_transition_created_to_investigating(self):
        assert validate_transition(CaseStatus.CREATED, CaseStatus.INVESTIGATING) is True

    def test_valid_transition_assessed_to_draft_ready(self):
        assert validate_transition(CaseStatus.ASSESSED, CaseStatus.DRAFT_READY) is True

    def test_invalid_transition_created_to_submitted(self):
        assert validate_transition(CaseStatus.CREATED, CaseStatus.SUBMITTED) is False

    def test_invalid_transition_closed_to_investigating(self):
        assert validate_transition(CaseStatus.CLOSED, CaseStatus.INVESTIGATING) is False

    def test_escalation_always_valid(self):
        """Escalation should be valid from most states."""
        escalatable = [
            CaseStatus.CREATED,
            CaseStatus.INVESTIGATING,
            CaseStatus.EVIDENCE_GATHERED,
            CaseStatus.ASSESSED,
            CaseStatus.DRAFT_READY,
            CaseStatus.UNDER_REVIEW,
            CaseStatus.APPROVED,
        ]
        for status in escalatable:
            assert validate_transition(status, CaseStatus.ESCALATED) is True

    def test_submitted_can_win_or_lose(self):
        assert validate_transition(CaseStatus.SUBMITTED, CaseStatus.WON) is True
        assert validate_transition(CaseStatus.SUBMITTED, CaseStatus.LOST) is True
