"""
Tests for deterministic analysis modules.

Pure function tests — no LLM, no DB, no external calls.
"""

import pytest
from datetime import datetime, timezone

from app.pipeline.analysis import check_completeness, detect_contradictions, build_timeline, PRODUCT_NOT_RECEIVED_REQUIREMENTS
from app.pipeline.ingest import (
    normalize_auth,
    normalize_communications,
    normalize_delivery,
    normalize_razorpay_order,
    normalize_razorpay_payment,
    normalize_razorpay_refunds,
    normalize_shipping,
)
from app.core.types import EvidenceCategory, EvidenceStatus
from app.core.schemas import Evidence, EvidenceCheckItem, Contradiction
from app.pipeline.assess import assess_case, _calculate_score
from data.synthetic.razorpay_mock import mock_payment, mock_order


# ═══════════════════════════════════════════════════════════════
#  NORMALIZER TESTS
# ═══════════════════════════════════════════════════════════════


class TestNormalizer:
    def test_normalize_payment(self):
        """Payment normalizer produces AVAILABLE evidence with content."""
        payment = mock_payment(amount=849900)
        ev = normalize_razorpay_payment(payment, "CASE-TEST")

        assert ev.category == EvidenceCategory.PAYMENT
        assert ev.status == EvidenceStatus.AVAILABLE
        assert ev.source_system == "razorpay"
        assert ev.content["amount"] == 849900
        assert ev.content["card_last4"] == "4242"
        assert ev.timezone_confident is True

    def test_normalize_order(self):
        """Order normalizer produces AVAILABLE evidence."""
        order = mock_order(receipt="ORD-TEST")
        ev = normalize_razorpay_order(order, "CASE-TEST")

        assert ev.category == EvidenceCategory.ORDER
        assert ev.status == EvidenceStatus.AVAILABLE
        assert ev.content["receipt"] == "ORD-TEST"

    def test_normalize_shipping_present(self):
        """Shipping normalizer with data produces AVAILABLE."""
        shipping = {
            "carrier": "BlueDart",
            "tracking_id": "BLU123456",
            "shipped_at": "2024-08-21T14:30:00+05:30",
            "status": "delivered",
        }
        ev = normalize_shipping(shipping, "CASE-TEST")

        assert ev.category == EvidenceCategory.SHIPPING
        assert ev.status == EvidenceStatus.AVAILABLE
        assert ev.content["carrier"] == "BlueDart"

    def test_normalize_shipping_none(self):
        """Shipping normalizer with None produces MISSING."""
        ev = normalize_shipping(None, "CASE-TEST")

        assert ev.category == EvidenceCategory.SHIPPING
        assert ev.status == EvidenceStatus.MISSING

    def test_normalize_delivery_with_signature(self):
        """Delivery with signature is AVAILABLE with high reliability."""
        delivery = {
            "delivered_at": "2024-08-23T16:15:00+05:30",
            "signed_by": "A. Mehta",
            "proof_type": "signature",
            "photo_proof": True,
        }
        ev = normalize_delivery(delivery, "CASE-TEST")

        assert ev.category == EvidenceCategory.DELIVERY
        assert ev.status == EvidenceStatus.AVAILABLE
        assert ev.reliability == "high"
        assert "A. Mehta" in ev.summary

    def test_normalize_delivery_left_at_door(self):
        """Delivery without signature is UNVERIFIED."""
        delivery = {
            "delivered_at": "2024-08-23T16:15:00",
            "signed_by": None,
            "proof_type": "left_at_door",
            "photo_proof": False,
        }
        ev = normalize_delivery(delivery, "CASE-TEST")

        assert ev.status == EvidenceStatus.UNVERIFIED
        assert ev.reliability == "medium"

    def test_normalize_delivery_none(self):
        """No delivery data produces MISSING evidence."""
        ev = normalize_delivery(None, "CASE-TEST")

        assert ev.status == EvidenceStatus.MISSING

    def test_normalize_refund_none(self):
        """No refunds produces NOT_APPLICABLE evidence."""
        ev = normalize_razorpay_refunds([], "CASE-TEST", "pay_xxx")

        assert ev is not None
        assert ev.status == EvidenceStatus.NOT_APPLICABLE

    def test_normalize_refund_present(self):
        """Refund present produces AVAILABLE evidence."""
        refunds = [{"id": "rfnd_001", "amount": 849900, "status": "processed", "created_at": 1724400000}]
        ev = normalize_razorpay_refunds(refunds, "CASE-TEST", "pay_xxx")

        assert ev is not None
        assert ev.status == EvidenceStatus.AVAILABLE
        assert ev.content["refund_count"] == 1

    def test_normalize_auth_verified(self):
        """Auth verified produces AVAILABLE evidence."""
        auth = {"method": "OTP", "verified": True, "device_known": True, "ip_country": "IN"}
        ev = normalize_auth(auth, "CASE-TEST")

        assert ev.status == EvidenceStatus.AVAILABLE

    def test_normalize_comms_empty(self):
        """No communications produces NOT_APPLICABLE."""
        ev = normalize_communications([], "CASE-TEST")

        assert ev.status == EvidenceStatus.NOT_APPLICABLE


# ═══════════════════════════════════════════════════════════════
#  TIMELINE TESTS
# ═══════════════════════════════════════════════════════════════


class TestTimeline:
    def _make_evidence(self, category: str, time_utc: datetime, **kwargs) -> Evidence:
        return Evidence(
            evidence_id=f"ev_{category}",
            case_id="CASE-TEST",
            category=EvidenceCategory(category),
            status=kwargs.get("status", EvidenceStatus.AVAILABLE),
            source_system=kwargs.get("source", "test"),
            source_record_id="test_001",
            event_time=time_utc,
            event_time_utc=time_utc,
            timezone_confident=kwargs.get("tz_confident", True),
            observed_at=datetime.now(timezone.utc),
            content=kwargs.get("content", {}),
            summary=kwargs.get("summary", ""),
        )

    def test_builds_chronological_timeline(self):
        """Timeline should be sorted chronologically."""
        ev1 = self._make_evidence("payment", datetime(2024, 8, 20, 10, 41, tzinfo=timezone.utc))
        ev2 = self._make_evidence("order", datetime(2024, 8, 20, 10, 42, tzinfo=timezone.utc))
        ev3 = self._make_evidence("delivery", datetime(2024, 8, 23, 16, 15, tzinfo=timezone.utc))

        timeline = build_timeline([ev3, ev1, ev2])  # Pass out of order
        assert len(timeline) == 3
        assert timeline[0].category == "payment"
        assert timeline[1].category == "order"
        assert timeline[2].category == "delivery"

    def test_skips_evidence_without_timestamp(self):
        """Evidence without event_time_utc should not appear in timeline."""
        ev1 = self._make_evidence("payment", datetime(2024, 8, 20, 10, 41, tzinfo=timezone.utc))
        ev2 = Evidence(
            evidence_id="ev_no_time",
            case_id="CASE-TEST",
            category=EvidenceCategory.AUTHENTICATION,
            source_system="test",
            source_record_id="test_002",
            observed_at=datetime.now(timezone.utc),
        )

        timeline = build_timeline([ev1, ev2])
        assert len(timeline) == 1

    def test_skips_missing_evidence(self):
        """Missing evidence should not appear in timeline."""
        ev = self._make_evidence(
            "delivery",
            datetime(2024, 8, 23, tzinfo=timezone.utc),
            status=EvidenceStatus.MISSING,
        )
        timeline = build_timeline([ev])
        assert len(timeline) == 0

    def test_flags_uncertain_timezone(self):
        """Events with uncertain timezone should be flagged."""
        ev = self._make_evidence(
            "delivery",
            datetime(2024, 8, 23, 14, 30, tzinfo=timezone.utc),
            tz_confident=False,
        )
        timeline = build_timeline([ev])
        assert len(timeline) == 1
        assert timeline[0].timezone_confident is False

    def test_links_events_to_source_evidence(self):
        """Each timeline event should reference its source evidence."""
        ev = self._make_evidence("payment", datetime(2024, 8, 20, tzinfo=timezone.utc))
        timeline = build_timeline([ev])
        assert timeline[0].source_evidence_id == "ev_payment"


# ═══════════════════════════════════════════════════════════════
#  CONTRADICTION TESTS
# ═══════════════════════════════════════════════════════════════


class TestContradictions:
    def _delivery_ev(self, **kwargs) -> Evidence:
        return Evidence(
            evidence_id="ev_delivery",
            case_id="CASE-TEST",
            category=EvidenceCategory.DELIVERY,
            status=EvidenceStatus.AVAILABLE,
            source_system="merchant_delivery",
            source_record_id="del_001",
            observed_at=datetime.now(timezone.utc),
            content=kwargs.get("content", {}),
            summary=kwargs.get("summary", "Delivery confirmed"),
        )

    def _shipping_ev(self, status: str = "delivered") -> Evidence:
        return Evidence(
            evidence_id="ev_shipping",
            case_id="CASE-TEST",
            category=EvidenceCategory.SHIPPING,
            status=EvidenceStatus.AVAILABLE,
            source_system="merchant_shipping",
            source_record_id="ship_001",
            observed_at=datetime.now(timezone.utc),
            content={"status": status},
            summary=f"Shipping status: {status}",
        )

    def test_detects_delivery_vs_shipping_conflict(self):
        """Delivered delivery + returned_to_sender shipping = contradiction."""
        delivery = self._delivery_ev()
        shipping = self._shipping_ev(status="returned_to_sender")

        contradictions = detect_contradictions([delivery, shipping])
        assert len(contradictions) >= 1
        assert contradictions[0].impact == "high"

    def test_no_contradiction_on_consistent_evidence(self):
        """Delivered delivery + delivered shipping = no contradiction."""
        delivery = self._delivery_ev()
        shipping = self._shipping_ev(status="delivered")

        contradictions = detect_contradictions([delivery, shipping])
        # Should not have delivery-vs-shipping contradiction
        delivery_vs_ship = [
            c for c in contradictions
            if "ev_delivery" in c.evidence_a_id or "ev_shipping" in c.evidence_a_id
        ]
        assert len(delivery_vs_ship) == 0

    def test_detects_customer_vs_support_conflict(self):
        """Support log showing confirmed receipt should contradict dispute claim."""
        comms = Evidence(
            evidence_id="ev_comms",
            case_id="CASE-TEST",
            category=EvidenceCategory.COMMUNICATION,
            status=EvidenceStatus.AVAILABLE,
            source_system="merchant_crm",
            source_record_id="",
            observed_at=datetime.now(timezone.utc),
            content={
                "tickets": [
                    {"summary": "Customer confirmed receipt in support chat"}
                ]
            },
        )

        contradictions = detect_contradictions([comms])
        assert len(contradictions) >= 1
        assert any("confirmed receipt" in c.description.lower() for c in contradictions)

    def test_detects_refund_already_issued(self):
        """Existing refund should flag potential double recovery."""
        refund = Evidence(
            evidence_id="ev_refund",
            case_id="CASE-TEST",
            category=EvidenceCategory.REFUND,
            status=EvidenceStatus.AVAILABLE,
            source_system="razorpay",
            source_record_id="pay_xxx",
            observed_at=datetime.now(timezone.utc),
            content={"refund_count": 1, "total_refunded": 849900},
        )

        contradictions = detect_contradictions([refund])
        assert len(contradictions) >= 1
        assert any("refund" in c.description.lower() for c in contradictions)

    def test_detects_timeline_anomaly(self):
        """Delivery before order = impossible, should be flagged."""
        order = Evidence(
            evidence_id="ev_order",
            case_id="CASE-TEST",
            category=EvidenceCategory.ORDER,
            status=EvidenceStatus.AVAILABLE,
            source_system="razorpay",
            source_record_id="order_xxx",
            event_time_utc=datetime(2024, 8, 23, tzinfo=timezone.utc),
            observed_at=datetime.now(timezone.utc),
        )
        delivery = Evidence(
            evidence_id="ev_delivery",
            case_id="CASE-TEST",
            category=EvidenceCategory.DELIVERY,
            status=EvidenceStatus.AVAILABLE,
            source_system="merchant",
            source_record_id="del_xxx",
            event_time_utc=datetime(2024, 8, 20, tzinfo=timezone.utc),  # BEFORE order!
            timezone_confident=False,
            observed_at=datetime.now(timezone.utc),
        )

        contradictions = detect_contradictions([order, delivery])
        assert len(contradictions) >= 1
        assert any("before" in c.description.lower() for c in contradictions)


# ═══════════════════════════════════════════════════════════════
#  COMPLETENESS TESTS
# ═══════════════════════════════════════════════════════════════


class TestCompleteness:
    def _make_evidence(self, category: str, status: EvidenceStatus = EvidenceStatus.AVAILABLE) -> Evidence:
        return Evidence(
            evidence_id=f"ev_{category}",
            case_id="CASE-TEST",
            category=EvidenceCategory(category),
            status=status,
            source_system="test",
            source_record_id="test_001",
            observed_at=datetime.now(timezone.utc),
        )

    def test_all_present_returns_full_checklist(self):
        """All evidence present = no missing required."""
        evidence = [
            self._make_evidence("payment"),
            self._make_evidence("order"),
            self._make_evidence("shipping"),
            self._make_evidence("delivery"),
            self._make_evidence("authentication"),
            self._make_evidence("communication"),
            self._make_evidence("refund"),
        ]
        checklist, missing = check_completeness(evidence)

        assert len(missing) == 0
        assert all(i.status == "available" for i in checklist)

    def test_missing_delivery_flags_gap(self):
        """Missing delivery should appear in missing_labels."""
        evidence = [
            self._make_evidence("payment"),
            self._make_evidence("order"),
            self._make_evidence("shipping"),
            # No delivery!
        ]
        checklist, missing = check_completeness(evidence)

        assert "Delivery confirmation" in missing
        delivery_item = next(i for i in checklist if i.category == "delivery")
        assert delivery_item.status == "missing"

    def test_weights_sum_approximately_to_one(self):
        """All weights should sum to ~1.0."""
        from app.pipeline.analysis import PRODUCT_NOT_RECEIVED_REQUIREMENTS
        total = sum(r.weight for r in PRODUCT_NOT_RECEIVED_REQUIREMENTS)
        assert abs(total - 1.0) < 0.01

    def test_unverified_evidence_marked_correctly(self):
        """Unverified evidence should show as 'unverified' in checklist."""
        evidence = [
            self._make_evidence("payment"),
            self._make_evidence("order"),
            self._make_evidence("shipping"),
            self._make_evidence("delivery", EvidenceStatus.UNVERIFIED),
        ]
        checklist, missing = check_completeness(evidence)

        delivery_item = next(i for i in checklist if i.category == "delivery")
        assert delivery_item.status == "unverified"
        # Unverified is not "missing required" — it exists, just unverified
        assert "Delivery confirmation" not in missing


# ═══════════════════════════════════════════════════════════════
#  DECISION ENGINE TESTS
# ═══════════════════════════════════════════════════════════════


class TestDecisionEngine:
    def _make_checklist(self, statuses: dict[str, str]) -> list[EvidenceCheckItem]:
        """Build a checklist with specified statuses."""
        from app.pipeline.analysis import PRODUCT_NOT_RECEIVED_REQUIREMENTS
        from copy import deepcopy

        checklist = deepcopy(PRODUCT_NOT_RECEIVED_REQUIREMENTS)
        for item in checklist:
            if item.category in statuses:
                item.status = statuses[item.category]
                if statuses[item.category] == "available":
                    item.evidence_id = f"ev_{item.category}"
        return checklist

    def test_high_score_recommends_contest(self):
        """All available = high score = CONTEST."""
        checklist = self._make_checklist({
            "payment": "available",
            "order": "available",
            "shipping": "available",
            "delivery": "available",
            "authentication": "available",
            "communication": "available",
            "refund": "not_applicable",
        })
        assessment = assess_case("CASE-TEST", checklist, [], [])

        assert assessment.score >= 0.80
        assert assessment.recommendation.value == "contest"
        assert assessment.auto_submit_eligible is True

    def test_low_score_recommends_accept(self):
        """Everything missing = low score = ACCEPT_LOSS."""
        checklist = self._make_checklist({
            "payment": "available",
            "order": "available",
            "shipping": "missing",
            "delivery": "missing",
            "authentication": "missing",
            "communication": "missing",
            "refund": "not_applicable",
        })
        assessment = assess_case(
            "CASE-TEST", checklist, [],
            ["Shipping dispatched", "Delivery confirmation"],
        )

        assert assessment.score < 0.40
        assert assessment.recommendation.value in ("accept_loss", "escalate")

    def test_contradictions_prevent_auto_submit(self):
        """Even high score should not auto-submit with contradictions."""
        from app.core.schemas import Contradiction

        checklist = self._make_checklist({
            "payment": "available",
            "order": "available",
            "shipping": "available",
            "delivery": "available",
            "authentication": "available",
            "communication": "available",
            "refund": "not_applicable",
        })
        contradiction = Contradiction(
            contradiction_id="c_test",
            case_id="CASE-TEST",
            evidence_a_id="ev_delivery",
            evidence_a_claim="Delivered",
            evidence_b_id="ev_shipping",
            evidence_b_claim="Returned",
            impact="high",
            description="Conflict",
            detected_at=datetime.now(timezone.utc),
        )
        assessment = assess_case("CASE-TEST", checklist, [contradiction], [])

        assert assessment.auto_submit_eligible is False
        assert assessment.requires_human_review is True

    def test_missing_required_lowers_confidence(self):
        """Missing required evidence should lower confidence."""
        checklist = self._make_checklist({
            "payment": "available",
            "order": "available",
            "shipping": "available",
            "delivery": "missing",  # Key evidence missing
            "authentication": "available",
        })
        assessment = assess_case(
            "CASE-TEST", checklist, [],
            ["Delivery confirmation"],
        )

        assert assessment.confidence.value != "high"

    def test_score_reproducible(self):
        """Same inputs should always produce the same score."""
        checklist = self._make_checklist({
            "payment": "available",
            "order": "available",
            "shipping": "available",
            "delivery": "unverified",
        })

        score1 = _calculate_score(checklist)
        score2 = _calculate_score(checklist)
        assert score1 == score2
