"""Tests for ADK agent factory and evidence dict conversion.

Tests verify that:
- format_dispute produces correct instruction context
- format_dispute handles edge cases (None, empty, missing fields)
- _dicts_to_evidence converts evidence dicts back to Evidence objects
- _dicts_to_evidence handles enum values (string and enum objects)
- _dicts_to_evidence skips invalid entries gracefully
- EVIDENCE_TOOLS registry contains all expected tools
"""

from datetime import datetime, timezone

import pytest

from app.agent.factory import format_dispute, INVESTIGATION_OUTPUT_KEY
from app.agent.tools import (
    EVIDENCE_TOOLS,
    get_authentication_events,
    get_customer_communications,
    get_delivery_evidence,
    get_device_session,
    get_external_integrations,
    get_policy_terms,
    get_refund_history,
    get_service_logs,
    get_transaction,
)
from app.agent.agent import _dicts_to_evidence
from app.core.types import EvidenceCategory, EvidenceStatus


# ═══════════════════════════════════════════════════════════════
#  FORMAT DISPUTE
# ═══════════════════════════════════════════════════════════════


class TestFormatDispute:
    """Tests for format_dispute instruction context formatting."""

    def test_returns_empty_for_none(self):
        """None dispute returns empty string."""
        assert format_dispute(None) == ""

    def test_returns_empty_for_empty_dict(self):
        """Empty dict returns empty string."""
        assert format_dispute({}) == ""

    def test_includes_dispute_id(self):
        """Output includes the dispute ID."""
        dispute = {"id": "disp_ABC123", "amount": 100000, "reason_code": "product_not_received"}
        result = format_dispute(dispute)
        assert "disp_ABC123" in result

    def test_formats_amount_in_rupees(self):
        """Amount is converted from paise to rupees."""
        dispute = {"amount": 849900, "reason_code": "product_not_received"}
        result = format_dispute(dispute)
        assert "8,499.00" in result

    def test_uses_reason_description_over_code(self):
        """Prefers reason_description when both are present."""
        dispute = {
            "amount": 100000,
            "reason_code": "product_not_received",
            "reason_description": "Customer says product never arrived",
        }
        result = format_dispute(dispute)
        assert "Customer says product never arrived" in result

    def test_falls_back_to_reason_code(self):
        """Uses reason_code when reason_description is empty."""
        dispute = {
            "amount": 100000,
            "reason_code": "unauthorized_transaction",
            "reason_description": "",
        }
        result = format_dispute(dispute)
        assert "unauthorized_transaction" in result

    def test_handles_missing_amount(self):
        """Missing amount defaults to 0."""
        dispute = {"reason_code": "product_not_received"}
        result = format_dispute(dispute)
        assert "0.00" in result

    def test_includes_phase(self):
        """Output includes dispute phase."""
        dispute = {"amount": 100000, "phase": "pre_arbitration"}
        result = format_dispute(dispute)
        assert "pre_arbitration" in result


# ═══════════════════════════════════════════════════════════════
#  EVIDENCE TOOLS REGISTRY
# ═══════════════════════════════════════════════════════════════


class TestEvidenceToolsRegistry:
    """Tests for the EVIDENCE_TOOLS list."""

    def test_contains_all_tools(self):
        """Registry contains all 9 evidence-gathering tools."""
        assert len(EVIDENCE_TOOLS) == 9

    def test_all_are_callable(self):
        """Every item in the registry is callable."""
        for tool in EVIDENCE_TOOLS:
            assert callable(tool)

    def test_expected_tools_present(self):
        """All expected tool functions are in the registry."""
        tool_names = {t.__name__ for t in EVIDENCE_TOOLS}
        expected = {
            "get_transaction",
            "get_delivery_evidence",
            "get_authentication_events",
            "get_customer_communications",
            "get_refund_history",
            "get_device_session",
            "get_service_logs",
            "get_policy_terms",
            "get_external_integrations",
        }
        assert tool_names == expected

    def test_submit_investigation_not_in_tools(self):
        """submit_investigation is NOT in the tools list (replaced by output_schema)."""
        tool_names = {t.__name__ for t in EVIDENCE_TOOLS}
        assert "submit_investigation" not in tool_names


# ═══════════════════════════════════════════════════════════════
#  INVESTIGATION OUTPUT KEY
# ═══════════════════════════════════════════════════════════════


class TestInvestigationOutputKey:
    """Tests for the output key constant."""

    def test_output_key_is_string(self):
        """The output key must be a non-empty string."""
        assert isinstance(INVESTIGATION_OUTPUT_KEY, str)
        assert len(INVESTIGATION_OUTPUT_KEY) > 0


# ═══════════════════════════════════════════════════════════════
#  DICTS TO EVIDENCE CONVERSION
# ═══════════════════════════════════════════════════════════════


class TestDictsToEvidence:
    """Tests for _dicts_to_evidence boundary conversion."""

    def test_converts_valid_dict(self):
        """Converts a valid evidence dict to an Evidence object."""
        dicts = [{
            "evidence_id": "ev_pay_001",
            "category": "payment",
            "status": "available",
            "source_system": "razorpay",
            "summary": "Payment of Rs.8,499.00 captured",
            "content": {"amount": 849900},
            "reliability": "high",
        }]
        result = _dicts_to_evidence(dicts, "CASE-00001")
        assert len(result) == 1
        ev = result[0]
        assert ev.evidence_id == "ev_pay_001"
        assert ev.category == EvidenceCategory.PAYMENT
        assert ev.status == EvidenceStatus.AVAILABLE
        assert ev.case_id == "CASE-00001"
        assert ev.summary == "Payment of Rs.8,499.00 captured"
        assert ev.content["amount"] == 849900

    def test_handles_enum_values(self):
        """Handles cases where category/status are already enum objects."""
        dicts = [{
            "evidence_id": "ev_del_001",
            "category": EvidenceCategory.DELIVERY,
            "status": EvidenceStatus.MISSING,
            "source_system": "merchant_delivery",
            "summary": "No delivery record",
        }]
        result = _dicts_to_evidence(dicts, "CASE-00001")
        assert len(result) == 1
        assert result[0].category == EvidenceCategory.DELIVERY
        assert result[0].status == EvidenceStatus.MISSING

    def test_converts_multiple_dicts(self):
        """Converts a list of evidence dicts."""
        dicts = [
            {"evidence_id": "ev_1", "category": "payment", "status": "available", "source_system": "razorpay"},
            {"evidence_id": "ev_2", "category": "delivery", "status": "missing", "source_system": "merchant"},
            {"evidence_id": "ev_3", "category": "authentication", "status": "unverified", "source_system": "merchant"},
        ]
        result = _dicts_to_evidence(dicts, "CASE-00001")
        assert len(result) == 3

    def test_skips_invalid_category(self):
        """Skips entries with invalid category values gracefully."""
        dicts = [
            {"evidence_id": "ev_1", "category": "payment", "status": "available", "source_system": "razorpay"},
            {"evidence_id": "ev_bad", "category": "nonexistent_category", "status": "available", "source_system": "x"},
        ]
        result = _dicts_to_evidence(dicts, "CASE-00001")
        assert len(result) == 1
        assert result[0].evidence_id == "ev_1"

    def test_empty_list_returns_empty(self):
        """Empty input returns empty output."""
        result = _dicts_to_evidence([], "CASE-00001")
        assert result == []

    def test_handles_missing_fields(self):
        """Handles dicts with missing optional fields."""
        dicts = [{
            "category": "payment",
            "status": "available",
        }]
        result = _dicts_to_evidence(dicts, "CASE-00001")
        assert len(result) == 1
        assert result[0].source_system == "unknown"

    def test_assigns_correct_case_id(self):
        """All converted evidence objects get the provided case_id."""
        dicts = [
            {"evidence_id": "ev_1", "category": "payment", "status": "available", "source_system": "x"},
            {"evidence_id": "ev_2", "category": "order", "status": "available", "source_system": "x"},
        ]
        result = _dicts_to_evidence(dicts, "CASE-12345")
        for ev in result:
            assert ev.case_id == "CASE-12345"
