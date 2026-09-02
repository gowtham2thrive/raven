"""Tests for Phase 3: New evidence tools (device, service, policy)."""

from app.agent.agent import (
    _make_missing_evidence,
    get_device_session,
    get_policy_terms,
    get_service_logs,
)
from app.core.types import EvidenceCategory, EvidenceStatus


class TestMakeMissingEvidence:
    """Tests for the _make_missing_evidence helper."""

    def test_creates_evidence_with_missing_status(self):
        ev = _make_missing_evidence("CASE-00001", "device", "merchant_analytics")
        assert ev.status == EvidenceStatus.MISSING

    def test_correct_category(self):
        ev = _make_missing_evidence("CASE-00001", "device", "merchant_analytics")
        assert ev.category == EvidenceCategory.DEVICE

    def test_correct_source_system(self):
        ev = _make_missing_evidence("CASE-00001", "device", "merchant_analytics")
        assert ev.source_system == "merchant_analytics"

    def test_evidence_id_contains_category_and_case(self):
        ev = _make_missing_evidence("CASE-00001", "service", "merchant_platform")
        assert "service" in ev.evidence_id
        assert "00001" in ev.evidence_id

    def test_summary_mentions_category(self):
        ev = _make_missing_evidence("CASE-00001", "policy", "merchant_legal")
        assert "policy" in ev.summary.lower()


class TestGetDeviceSession:
    """Tests for the get_device_session tool."""

    def test_returns_valid_structure(self):
        result = get_device_session("CASE-00001")
        assert result["case_id"] == "CASE-00001"
        assert "evidence" in result
        assert len(result["evidence"]) == 1

    def test_evidence_is_missing(self):
        result = get_device_session("CASE-00001")
        ev = result["evidence"][0]
        assert ev["status"] == EvidenceStatus.MISSING
        assert ev["category"] == EvidenceCategory.DEVICE


class TestGetServiceLogs:
    """Tests for the get_service_logs tool."""

    def test_returns_valid_structure(self):
        result = get_service_logs("CASE-00001")
        assert result["case_id"] == "CASE-00001"
        assert len(result["evidence"]) == 1

    def test_evidence_is_missing(self):
        result = get_service_logs("CASE-00001")
        ev = result["evidence"][0]
        assert ev["status"] == EvidenceStatus.MISSING
        assert ev["category"] == EvidenceCategory.SERVICE


class TestGetPolicyTerms:
    """Tests for the get_policy_terms tool."""

    def test_returns_valid_structure(self):
        result = get_policy_terms("CASE-00001")
        assert result["case_id"] == "CASE-00001"
        assert len(result["evidence"]) == 1

    def test_evidence_is_missing(self):
        result = get_policy_terms("CASE-00001")
        ev = result["evidence"][0]
        assert ev["status"] == EvidenceStatus.MISSING
        assert ev["category"] == EvidenceCategory.POLICY
