"""
Error & Edge Case Tests.

Covers failure modes from AGENTS.md §XVIII that the main suite doesn't test:
- Connector failures (empty/partial data)
- Duplicate events
- Re-investigation safety
- Large cases
- Timestamp edge cases
- Full pipeline integration with Phase 3+4 features
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.pipeline.ingest import (
    normalize_delivery,
    normalize_razorpay_payment,
    normalize_shipping,
)
from app.connectors.quarantine import IngestionQuarantine
from app.connectors.synthetic import SyntheticConnector
from app.core.types import EvidenceCategory, EvidenceStatus
from app.core.schemas import Evidence
from app.pipeline.runner import DeterministicRunner


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def runner(tmp_path):
    """Create a DeterministicRunner with synthetic data and temp DB."""
    cases_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "cases"
    if not cases_dir.exists():
        pytest.skip("Synthetic data not generated")
    connector = SyntheticConnector(cases_dir=cases_dir)
    return DeterministicRunner(
        connector=connector,
        db_path=str(tmp_path / "test.db"),
    )


# ═══════════════════════════════════════════════════════════════
#  CONNECTOR FAILURES
# ═══════════════════════════════════════════════════════════════


class TestConnectorFailures:
    """What happens when external sources return empty/partial data?"""

    def test_nonexistent_case_returns_error(self, runner):
        """Investigating a case that doesn't exist returns an error dict."""
        result = runner.investigate("CASE-99999")
        assert "error" in result

    def test_investigation_with_missing_shipping(self, runner):
        """Cases with no shipping data still complete investigation."""
        # C_MISSING profile cases (26-35) have no delivery data
        result = runner.investigate("CASE-00026")
        assert "error" not in result
        assert result["assessment"] is not None

    def test_investigation_with_minimal_evidence(self, runner):
        """Even with sparse evidence, pipeline completes without crash."""
        result = runner.investigate("CASE-00026")
        assert "error" not in result
        # Should have some evidence (at least payment + order)
        assert len(result["evidence"]) >= 2
        # Should have missing evidence flagged
        assert len(result["missing_evidence"]) > 0


# ═══════════════════════════════════════════════════════════════
#  DUPLICATE EVENTS
# ═══════════════════════════════════════════════════════════════


class TestDuplicateEvents:
    """De-duplication and idempotency."""

    def test_duplicate_delivery_produces_unique_evidence_ids(self):
        """Two normalize calls produce different evidence IDs."""
        delivery = {
            "delivered_at": "2026-08-22T14:30:00+05:30",
            "proof_type": "signature",
            "signed_by": "Test",
        }
        ev1 = normalize_delivery(delivery, "CASE-DUP")
        ev2 = normalize_delivery(delivery, "CASE-DUP")

        # Different evidence IDs (no collision)
        assert ev1.evidence_id != ev2.evidence_id
        # But same content
        assert ev1.raw_source_hash == ev2.raw_source_hash

    def test_duplicate_payment_produces_unique_evidence_ids(self):
        """Two normalize calls for same payment produce different IDs."""
        payment = {
            "id": "pay_dup123",
            "amount": 50000,
            "currency": "INR",
            "status": "captured",
            "method": "card",
            "created_at": 1693000000,
        }
        ev1 = normalize_razorpay_payment(payment, "CASE-DUP")
        ev2 = normalize_razorpay_payment(payment, "CASE-DUP")

        assert ev1.evidence_id != ev2.evidence_id
        assert ev1.raw_source_hash == ev2.raw_source_hash


# ═══════════════════════════════════════════════════════════════
#  RE-INVESTIGATION SAFETY
# ═══════════════════════════════════════════════════════════════


class TestReInvestigation:
    """AGENTS.md §IX: Re-investigating same case must be safe."""

    def test_reinvestigation_produces_consistent_assessment(self, runner):
        """Running investigation twice yields same recommendation."""
        result1 = runner.investigate("CASE-00001")
        result2 = runner.investigate("CASE-00001")

        assert result1["assessment"].recommendation == result2["assessment"].recommendation
        assert result1["assessment"].case_strength == result2["assessment"].case_strength

    def test_reinvestigation_score_is_reproducible(self, runner):
        """Score should be deterministic across runs."""
        result1 = runner.investigate("CASE-00001")
        result2 = runner.investigate("CASE-00001")

        assert result1["assessment"].score == result2["assessment"].score

    def test_reinvestigation_does_not_duplicate_quarantine(self, runner):
        """Re-investigating doesn't create duplicate quarantine records."""
        # Run twice on a case that should have no quarantine issues
        runner.investigate("CASE-00001")
        runner.investigate("CASE-00001")

        # No quarantined records for a clean case
        records = runner._quarantine.list_quarantined("CASE-00001")
        assert len(records) == 0


# ═══════════════════════════════════════════════════════════════
#  TIMESTAMP EDGE CASES
# ═══════════════════════════════════════════════════════════════


class TestEdgeCaseTimestamps:
    """Timestamp edge cases that could corrupt timelines."""

    def test_null_timestamps_produce_missing_timeline(self):
        """Evidence with no timestamps still normalizes correctly."""
        delivery = {
            "delivered_at": None,
            "proof_type": "unknown",
        }
        ev = normalize_delivery(delivery, "CASE-NULL")
        assert ev.event_time_utc is None

    def test_epoch_zero_timestamp(self):
        """Epoch 0 (1970-01-01) is parsed but produces old date."""
        payment = {
            "id": "pay_epoch",
            "amount": 1000,
            "currency": "INR",
            "status": "captured",
            "method": "card",
            "created_at": 0,
        }
        ev = normalize_razorpay_payment(payment, "CASE-EPOCH")
        assert ev.event_time_utc is not None
        assert ev.event_time_utc.year == 1970

    def test_string_timestamp_parsed(self):
        """ISO string timestamps are parsed correctly."""
        shipping = {
            "carrier": "Test",
            "tracking_id": "T123",
            "shipped_at": "2026-08-20T10:00:00+05:30",
            "status": "shipped",
        }
        ev = normalize_shipping(shipping, "CASE-STR")
        assert ev.event_time_utc is not None
        assert ev.event_time_utc.year == 2026


# ═══════════════════════════════════════════════════════════════
#  END-TO-END PIPELINE (with Phase 3+4 features)
# ═══════════════════════════════════════════════════════════════


class TestEndToEndPipeline:
    """Full pipeline integration verifying new features work end-to-end."""

    def test_strong_case_has_triangulation_result(self, runner):
        """Strong case (CASE-00001) should have triangulation data."""
        result = runner.investigate("CASE-00001")
        assert "triangulation" in result
        tri = result["triangulation"]
        assert tri is not None
        assert tri.signal_count > 0

    def test_strong_case_is_triangulated(self, runner):
        """Strong case with carrier confirmation should be triangulated."""
        result = runner.investigate("CASE-00001")
        tri = result["triangulation"]
        # Mock carrier confirms for cases 1-15
        assert tri.triangulated is True
        assert tri.supporting_count >= 2

    def test_contradictory_case_has_causal_check(self, runner):
        """Contradictory case should have causal_violations in result."""
        result = runner.investigate("CASE-00036")
        assert "causal_violations" in result

    def test_strong_case_citation_passes(self, runner):
        """Strong case response draft should pass citation verification."""
        result = runner.investigate("CASE-00001")
        if result.get("citation_verification"):
            assert result["citation_verification"].passed is True

    def test_missing_case_no_auto_submit(self, runner):
        """Missing evidence case should never be auto-submittable."""
        result = runner.investigate("CASE-00026")
        assert result["assessment"].auto_submit_eligible is False

    def test_pipeline_returns_all_expected_keys(self, runner):
        """Investigation result has all expected keys."""
        result = runner.investigate("CASE-00001")
        expected_keys = {
            "case_id", "evidence", "timeline", "contradictions",
            "checklist", "missing_evidence", "assessment",
            "response_draft", "triangulation", "causal_violations",
            "citation_verification",
        }
        assert expected_keys.issubset(set(result.keys()))
