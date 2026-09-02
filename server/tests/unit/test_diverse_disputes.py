"""Tests for Phase 9: Diverse dispute types end-to-end.

Tests verify the dynamic system handles different dispute types correctly:
- Evidence tools return valid structures for all cases
- Dynamic checklist produces reasonable weights for different claim types
- Deterministic pipeline produces valid assessments regardless of reason code
- The system does not crash or produce invalid output for any dispute type
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.agent.agent import (
    _format_dispute,
    get_device_session,
    get_policy_terms,
    get_service_logs,
    submit_investigation,
    get_investigation_output,
    _investigation_outputs,
)
from app.core.schemas import Evidence, InvestigationOutput
from app.core.types import EvidenceCategory, EvidenceStatus
from app.pipeline.analysis import build_dynamic_checklist, check_completeness


CASES_DIR = Path(__file__).parent.parent.parent / "data" / "synthetic" / "cases"


def _load_case(case_id: str) -> dict:
    """Load a synthetic case JSON file."""
    path = CASES_DIR / f"{case_id}.json"
    with open(path) as f:
        return json.load(f)


def _make_evidence(category: str, status: str = "available") -> Evidence:
    return Evidence(
        evidence_id=f"ev_{category}_test",
        case_id="CASE-TEST",
        category=EvidenceCategory(category),
        status=EvidenceStatus(status),
        source_system="test",
        source_record_id=f"rec_{category}",
        observed_at=datetime.now(timezone.utc),
        summary=f"Test {category}",
    )


# ═══════════════════════════════════════════════════════════════
#  Diverse Case File Tests
# ═══════════════════════════════════════════════════════════════


class TestDiverseCaseFiles:
    """Verify the new synthetic cases load and have correct structure."""

    @pytest.mark.parametrize("case_id", [
        "CASE-00051", "CASE-00052", "CASE-00053",
        "CASE-00054", "CASE-00055", "CASE-00056", "CASE-00057",
    ])
    def test_case_loads_and_has_required_fields(self, case_id: str):
        """Each diverse case has all required fields."""
        case = _load_case(case_id)
        assert case["case_id"] == case_id
        assert "razorpay_dispute" in case
        assert "razorpay_payment" in case
        assert "merchant_data" in case
        assert "expected" in case

    @pytest.mark.parametrize("case_id,expected_reason", [
        ("CASE-00051", "unauthorized_transaction"),
        ("CASE-00052", "unauthorized_transaction"),
        ("CASE-00053", "product_not_as_described"),
        ("CASE-00054", "duplicate_transaction"),
        ("CASE-00055", "service_not_rendered"),
        ("CASE-00056", "general"),
        ("CASE-00057", "processing_error_4837"),
    ])
    def test_diverse_reason_codes(self, case_id: str, expected_reason: str):
        """Each case has the correct non-receipt reason code."""
        case = _load_case(case_id)
        assert case["razorpay_dispute"]["reason_code"] == expected_reason

    def test_unauthorized_has_no_shipping(self):
        """Unauthorized transaction with digital service has no shipping."""
        case = _load_case("CASE-00051")
        assert case["merchant_data"]["shipping"] is None

    def test_duplicate_has_refund(self):
        """Duplicate charge case has refund evidence."""
        case = _load_case("CASE-00054")
        assert len(case["merchant_data"]["refunds"]) > 0

    def test_service_has_no_delivery(self):
        """Digital service case has no delivery evidence."""
        case = _load_case("CASE-00055")
        assert case["merchant_data"]["delivery"] is None

    def test_unknown_has_empty_description(self):
        """Unknown reason code has empty description."""
        case = _load_case("CASE-00057")
        assert case["razorpay_dispute"]["reason_description"] == ""

    def test_compound_claim_description(self):
        """Compound claim mentions both unauthorized and not delivered."""
        case = _load_case("CASE-00056")
        desc = case["razorpay_dispute"]["reason_description"].lower()
        assert "authorize" in desc
        assert "deliver" in desc


# ═══════════════════════════════════════════════════════════════
#  Format Dispute Tests
# ═══════════════════════════════════════════════════════════════


class TestFormatDispute:
    """Verify _format_dispute uses actual claim text."""

    def test_unauthorized_claim_text(self):
        """Unauthorized dispute shows actual claim, not 'Product not received'."""
        case = _load_case("CASE-00051")
        dispute = case["razorpay_dispute"]
        formatted = _format_dispute(dispute)
        assert "did not authorize" in formatted
        assert "Product not received" not in formatted

    def test_quality_claim_text(self):
        """Quality dispute shows the actual complaint."""
        case = _load_case("CASE-00053")
        dispute = case["razorpay_dispute"]
        formatted = _format_dispute(dispute)
        assert "different from what was advertised" in formatted

    def test_empty_description_falls_back_to_reason_code(self):
        """When description is empty, falls back to reason_code."""
        case = _load_case("CASE-00057")
        dispute = case["razorpay_dispute"]
        formatted = _format_dispute(dispute)
        assert "processing_error_4837" in formatted


# ═══════════════════════════════════════════════════════════════
#  Dynamic Relevance + Checklist for Different Dispute Types
# ═══════════════════════════════════════════════════════════════


class TestDynamicRelevanceByDisputeType:
    """Test that different relevance maps produce correct checklists."""

    def test_unauthorized_prioritizes_auth(self):
        """For unauthorized claims, auth should have highest weight."""
        evidence = [
            _make_evidence("payment"),
            _make_evidence("authentication"),
            _make_evidence("delivery"),
            _make_evidence("device", "missing"),
        ]
        relevance = {
            "authentication": "critical",
            "device": "critical",
            "payment": "supporting",
            "delivery": "irrelevant",
        }
        checklist, missing = build_dynamic_checklist(evidence, relevance)

        auth = next(i for i in checklist if i.category == "authentication")
        assert auth.weight == 0.30
        assert auth.required is True

        delivery = next(i for i in checklist if i.category == "delivery")
        assert delivery.weight == 0.00
        assert delivery.status == "not_applicable"

        device = next(i for i in checklist if i.category == "device")
        assert "Device" in missing  # Critical but missing

    def test_duplicate_prioritizes_refund(self):
        """For duplicate claims, refund evidence should be critical."""
        evidence = [
            _make_evidence("payment"),
            _make_evidence("refund"),
            _make_evidence("delivery"),
        ]
        relevance = {
            "refund": "critical",
            "payment": "critical",
            "delivery": "contextual",
        }
        checklist, missing = build_dynamic_checklist(evidence, relevance)

        refund = next(i for i in checklist if i.category == "refund")
        assert refund.weight == 0.30
        assert refund.required is True
        assert refund.status == "available"
        assert missing == []

    def test_service_prioritizes_service_logs(self):
        """For service disputes, service logs should be critical."""
        evidence = [
            _make_evidence("payment"),
            _make_evidence("service", "missing"),
            _make_evidence("communication"),
        ]
        relevance = {
            "service": "critical",
            "communication": "critical",
            "payment": "supporting",
        }
        checklist, missing = build_dynamic_checklist(evidence, relevance)

        service = next(i for i in checklist if i.category == "service")
        assert service.weight == 0.30
        assert service.required is True
        assert "Service" in missing  # Critical but missing

    def test_compound_has_multiple_critical(self):
        """Compound claims can have multiple critical categories."""
        evidence = [
            _make_evidence("authentication"),
            _make_evidence("delivery"),
            _make_evidence("payment"),
        ]
        relevance = {
            "authentication": "critical",
            "delivery": "critical",
            "payment": "supporting",
        }
        checklist, _ = build_dynamic_checklist(evidence, relevance)

        auth = next(i for i in checklist if i.category == "authentication")
        delivery = next(i for i in checklist if i.category == "delivery")
        assert auth.weight == 0.30
        assert delivery.weight == 0.30
        assert auth.required is True
        assert delivery.required is True

    def test_unknown_reason_uses_equal_weights(self):
        """Unknown reason with no relevance → equal weights."""
        evidence = [
            _make_evidence("payment"),
            _make_evidence("delivery"),
            _make_evidence("authentication"),
        ]
        checklist, _ = build_dynamic_checklist(evidence, None)

        weights = {i.weight for i in checklist}
        assert len(weights) == 1  # All equal
        expected = 1.0 / 3
        assert abs(checklist[0].weight - expected) < 0.001


# ═══════════════════════════════════════════════════════════════
#  Submit Investigation for Different Dispute Types
# ═══════════════════════════════════════════════════════════════


class TestSubmitInvestigationDiverse:
    """Test submit_investigation works for various dispute types."""

    def setup_method(self):
        _investigation_outputs.clear()

    def test_unauthorized_investigation(self):
        """Agent can submit analysis for unauthorized transaction."""
        result = submit_investigation(
            case_id="CASE-00051",
            claim_summary="Customer claims unauthorized card usage",
            defense_goal="Prove the cardholder authenticated the transaction",
            evidence_relevance={
                "authentication": "critical",
                "device": "critical",
                "payment": "supporting",
                "delivery": "irrelevant",
            },
            key_findings=["3DS v2 verified", "Known device from 12 prior transactions"],
            noted_gaps=["No device session logs available"],
            noted_contradictions=[],
            response_draft="The transaction was verified via [authentication] with 3DS v2.",
            agent_confidence="high",
            reasoning="Strong auth + known device = cardholder authorized.",
        )
        assert result["status"] == "recorded"
        output = get_investigation_output("CASE-00051")
        assert output["evidence_relevance"]["authentication"] == "critical"
        assert output["evidence_relevance"]["delivery"] == "irrelevant"

    def test_service_investigation(self):
        """Agent can submit analysis for service not rendered."""
        result = submit_investigation(
            case_id="CASE-00055",
            claim_summary="Customer claims no access to online course",
            defense_goal="Prove the customer received access credentials",
            evidence_relevance={
                "service": "critical",
                "communication": "critical",
                "authentication": "contextual",
                "payment": "supporting",
            },
            key_findings=["Credentials sent via email"],
            noted_gaps=["No service access logs to prove usage"],
            noted_contradictions=[],
            response_draft="Access credentials were sent via [communication].",
            agent_confidence="medium",
            reasoning="Credentials sent but no proof of usage.",
        )
        assert result["status"] == "recorded"
        output = get_investigation_output("CASE-00055")
        assert output["evidence_relevance"]["service"] == "critical"

    def test_unknown_reason_investigation(self):
        """Agent can submit analysis even for unknown reason codes."""
        result = submit_investigation(
            case_id="CASE-00057",
            claim_summary="Dispute filed under unknown processing error code",
            defense_goal="Present all available evidence since claim is unclear",
            evidence_relevance={
                "payment": "supporting",
                "delivery": "supporting",
                "authentication": "supporting",
            },
            key_findings=["All evidence available but claim is unclear"],
            noted_gaps=["Reason code is non-standard, cannot determine priority"],
            noted_contradictions=[],
            response_draft="",
            agent_confidence="low",
            reasoning="Cannot determine specific defense without clear claim.",
        )
        assert result["status"] == "recorded"
        output = get_investigation_output("CASE-00057")
        assert output["agent_confidence"] == "low"
