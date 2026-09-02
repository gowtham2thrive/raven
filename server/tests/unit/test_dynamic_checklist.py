"""Tests for Phase 4: Dynamic checklist builder."""

import pytest
from datetime import datetime, timezone

from app.core.schemas import Evidence, EvidenceCheckItem
from app.core.types import EvidenceCategory, EvidenceStatus
from app.pipeline.analysis import (
    build_dynamic_checklist,
    check_completeness,
)


def _make_evidence(
    case_id: str, category: str, status: str = "available",
) -> Evidence:
    """Create a test evidence item."""
    return Evidence(
        evidence_id=f"ev_{category}_{case_id[-5:]}",
        case_id=case_id,
        category=EvidenceCategory(category),
        status=EvidenceStatus(status),
        source_system="test",
        source_record_id=f"rec_{category}",
        observed_at=datetime.now(timezone.utc),
        summary=f"Test {category} evidence",
    )


def _standard_evidence(case_id: str = "CASE-00001") -> list[Evidence]:
    """Create a standard set of 7 evidence items (all available)."""
    return [
        _make_evidence(case_id, "payment"),
        _make_evidence(case_id, "order"),
        _make_evidence(case_id, "shipping"),
        _make_evidence(case_id, "delivery"),
        _make_evidence(case_id, "authentication"),
        _make_evidence(case_id, "communication"),
        _make_evidence(case_id, "refund"),
    ]


class TestCheckCompletenessBackwardCompat:
    """check_completeness without evidence_relevance must behave exactly as before."""

    def test_existing_behavior_unchanged(self):
        """Without evidence_relevance, uses fixed weight table."""
        evidence = _standard_evidence()
        checklist, missing = check_completeness(evidence)
        assert len(checklist) == 7
        assert missing == []
        # Verify specific weights from the fixed table
        delivery_item = next(i for i in checklist if i.category == "delivery")
        assert delivery_item.weight == 0.30
        assert delivery_item.status == "available"

    def test_missing_delivery_flagged(self):
        """Missing delivery is flagged as required-missing."""
        evidence = _standard_evidence()
        evidence[3] = _make_evidence("CASE-00001", "delivery", "missing")
        checklist, missing = check_completeness(evidence)
        assert "Delivery confirmation" in missing

    def test_with_evidence_relevance_uses_dynamic(self):
        """When evidence_relevance is provided, uses dynamic weights."""
        evidence = _standard_evidence()
        relevance = {"delivery": "critical", "payment": "supporting"}
        checklist, missing = check_completeness(
            evidence, evidence_relevance=relevance,
        )
        # Dynamic checklist should have all 7 categories
        delivery_item = next(i for i in checklist if i.category == "delivery")
        assert delivery_item.weight == 0.30  # critical weight
        assert delivery_item.required is True  # critical = required


class TestBuildDynamicChecklist:
    """Tests for the dynamic checklist builder."""

    def test_none_relevance_uses_equal_weights(self):
        """None relevance → equal weights for all evidence."""
        evidence = _standard_evidence()
        checklist, missing = build_dynamic_checklist(evidence, None)
        assert len(checklist) == 7
        # All weights should be equal
        weights = {item.weight for item in checklist}
        assert len(weights) == 1  # All same weight
        expected_weight = 1.0 / 7
        assert abs(checklist[0].weight - expected_weight) < 0.001

    def test_relevance_weighted_critical(self):
        """Critical evidence gets weight 0.30."""
        evidence = _standard_evidence()
        relevance = {
            "delivery": "critical",
            "payment": "supporting",
            "order": "contextual",
            "authentication": "irrelevant",
        }
        checklist, missing = build_dynamic_checklist(evidence, relevance)

        delivery = next(i for i in checklist if i.category == "delivery")
        assert delivery.weight == 0.30
        assert delivery.required is True

        payment = next(i for i in checklist if i.category == "payment")
        assert payment.weight == 0.15
        assert payment.required is False

        order = next(i for i in checklist if i.category == "order")
        assert order.weight == 0.05

        auth = next(i for i in checklist if i.category == "authentication")
        assert auth.weight == 0.00
        assert auth.status == "not_applicable"

    def test_irrelevant_excluded_from_scoring(self):
        """Irrelevant evidence has weight 0 and status not_applicable."""
        evidence = _standard_evidence()
        relevance = {"shipping": "irrelevant"}
        checklist, _ = build_dynamic_checklist(evidence, relevance)
        shipping = next(i for i in checklist if i.category == "shipping")
        assert shipping.weight == 0.00
        assert shipping.status == "not_applicable"

    def test_missing_critical_evidence_flagged(self):
        """Missing critical evidence appears in missing list."""
        evidence = [
            _make_evidence("CASE-00001", "delivery", "missing"),
            _make_evidence("CASE-00001", "payment", "available"),
        ]
        relevance = {"delivery": "critical", "payment": "supporting"}
        checklist, missing = build_dynamic_checklist(evidence, relevance)
        assert "Delivery" in missing

    def test_available_critical_evidence_not_in_missing(self):
        """Available critical evidence is NOT in missing list."""
        evidence = [
            _make_evidence("CASE-00001", "delivery", "available"),
            _make_evidence("CASE-00001", "payment", "available"),
        ]
        relevance = {"delivery": "critical", "payment": "supporting"}
        _, missing = build_dynamic_checklist(evidence, relevance)
        assert missing == []

    def test_unknown_relevance_defaults_to_supporting(self):
        """Categories not in relevance map default to supporting weight."""
        evidence = [_make_evidence("CASE-00001", "refund")]
        relevance = {}  # Empty — no relevance specified
        checklist, _ = build_dynamic_checklist(evidence, relevance)
        assert checklist[0].weight == 0.15  # supporting weight

    def test_invalid_relevance_string_defaults_to_supporting(self):
        """Invalid relevance string defaults to supporting."""
        evidence = [_make_evidence("CASE-00001", "payment")]
        relevance = {"payment": "very_important"}
        checklist, _ = build_dynamic_checklist(evidence, relevance)
        assert checklist[0].weight == 0.15

    def test_deduplicates_categories(self):
        """Multiple evidence items in same category produce one checklist item."""
        evidence = [
            _make_evidence("CASE-00001", "payment", "available"),
            _make_evidence("CASE-00001", "payment", "unverified"),
        ]
        relevance = {"payment": "critical"}
        checklist, _ = build_dynamic_checklist(evidence, relevance)
        payment_items = [i for i in checklist if i.category == "payment"]
        assert len(payment_items) == 1
        # Should prefer AVAILABLE over UNVERIFIED
        assert payment_items[0].status == "available"

    def test_empty_evidence_list(self):
        """Empty evidence list produces empty checklist."""
        checklist, missing = build_dynamic_checklist([], {"delivery": "critical"})
        assert checklist == []
        assert missing == []
