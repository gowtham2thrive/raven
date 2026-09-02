"""
Audit Trail Tests.

Verifies that the AuditTrail correctly records investigation steps
with timing, evidence IDs, and structured details.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from app.core.schemas import AuditEntry, AuditTrail


class TestAuditTrail:
    """Core audit trail functionality."""

    def test_records_entries(self):
        """Entries are recorded and retrievable."""
        audit = AuditTrail("CASE-TEST")
        audit.record(
            action="test_action",
            component="test_component",
            details={"key": "value"},
        )
        assert audit.entry_count() == 1
        assert audit.entries[0].action == "test_action"

    def test_entries_have_timestamps(self):
        """Each entry gets an automatic UTC timestamp."""
        audit = AuditTrail("CASE-TEST")
        audit.record(action="test", component="test")

        entry = audit.entries[0]
        assert entry.timestamp is not None
        assert entry.timestamp.tzinfo is not None

    def test_step_context_manager_records_duration(self):
        """The step() context manager records timing automatically."""
        audit = AuditTrail("CASE-TEST")

        with audit.step("slow_step", "test") as step:
            time.sleep(0.01)  # 10ms
            step.details = {"note": "test"}

        entry = audit.entries[0]
        assert entry.duration_ms >= 5  # At least 5ms (generous margin)
        assert entry.action == "slow_step"
        assert entry.details["note"] == "test"

    def test_step_records_evidence_ids(self):
        """Evidence IDs set inside step() are preserved."""
        audit = AuditTrail("CASE-TEST")

        with audit.step("gather", "normalizer") as step:
            step.evidence_ids = ["ev_001", "ev_002"]

        assert audit.entries[0].evidence_ids == ["ev_001", "ev_002"]

    def test_to_dict_serializable(self):
        """to_dict() produces JSON-serializable output."""
        audit = AuditTrail("CASE-TEST")
        audit.record(
            action="test",
            component="test",
            details={"count": 3},
            evidence_ids=["ev_abc"],
        )

        result = audit.to_dict()
        # Should not raise
        json_str = json.dumps(result)
        assert "CASE-TEST" in json_str
        assert result["entry_count"] == 1

    def test_total_duration_calculated(self):
        """Total duration is the sum of all entry durations."""
        audit = AuditTrail("CASE-TEST")

        with audit.step("step1", "test"):
            time.sleep(0.01)
        with audit.step("step2", "test"):
            time.sleep(0.01)

        assert audit.total_duration_ms() >= 10  # At least 10ms total

    def test_multiple_entries_ordered(self):
        """Entries are returned in chronological order."""
        audit = AuditTrail("CASE-TEST")
        audit.record(action="first", component="a")
        audit.record(action="second", component="b")
        audit.record(action="third", component="c")

        actions = [e.action for e in audit.entries]
        assert actions == ["first", "second", "third"]

    def test_empty_trail(self):
        """Empty trail has zero entries and zero duration."""
        audit = AuditTrail("CASE-TEST")
        assert audit.entry_count() == 0
        assert audit.total_duration_ms() == 0.0
        assert audit.to_dict()["entry_count"] == 0

    def test_case_id_propagated(self):
        """All entries inherit the trail's case_id."""
        audit = AuditTrail("CASE-00042")
        audit.record(action="test", component="test")

        with audit.step("step", "test"):
            pass

        for entry in audit.entries:
            assert entry.case_id == "CASE-00042"


class TestAuditEntry:
    """AuditEntry serialization."""

    def test_to_dict_includes_all_fields(self):
        """to_dict() includes every field."""
        entry = AuditEntry(
            case_id="CASE-TEST",
            timestamp=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
            action="evidence_gathered",
            component="normalizer",
            details={"count": 7},
            evidence_ids=["ev_001"],
            duration_ms=42.5,
        )
        d = entry.to_dict()
        assert d["case_id"] == "CASE-TEST"
        assert d["action"] == "evidence_gathered"
        assert d["component"] == "normalizer"
        assert d["details"] == {"count": 7}
        assert d["evidence_ids"] == ["ev_001"]
        assert d["duration_ms"] == 42.5
        assert "2026" in d["timestamp"]


class TestAuditInPipeline:
    """Verify audit trail is present in investigation results."""

    def test_investigation_includes_audit_trail(self, tmp_path):
        """Full investigation result includes audit_trail key."""
        from pathlib import Path
        from app.connectors.synthetic import SyntheticConnector
        from app.pipeline.runner import DeterministicRunner

        cases_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "cases"
        if not cases_dir.exists():
            import pytest
            pytest.skip("Synthetic data not generated")

        connector = SyntheticConnector(cases_dir=cases_dir)
        runner = DeterministicRunner(
            connector=connector,
            db_path=str(tmp_path / "audit_test.db"),
        )
        result = runner.investigate("CASE-00001")

        assert "audit_trail" in result
        trail = result["audit_trail"]
        assert trail["case_id"] == "CASE-00001"
        assert trail["entry_count"] >= 7  # At least 7 pipeline steps
        assert trail["total_duration_ms"] > 0

    def test_audit_trail_has_expected_steps(self, tmp_path):
        """Audit trail contains all major pipeline steps."""
        from pathlib import Path
        from app.connectors.synthetic import SyntheticConnector
        from app.pipeline.runner import DeterministicRunner

        cases_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "cases"
        if not cases_dir.exists():
            import pytest
            pytest.skip("Synthetic data not generated")

        connector = SyntheticConnector(cases_dir=cases_dir)
        runner = DeterministicRunner(
            connector=connector,
            db_path=str(tmp_path / "audit_test.db"),
        )
        result = runner.investigate("CASE-00001")

        actions = [e["action"] for e in result["audit_trail"]["entries"]]
        expected_actions = [
            "razorpay_data_fetched",
            "evidence_normalized",
            "carrier_data_fetched",
            "timeline_built",
            "causal_validation_complete",
            "triangulation_complete",
            "completeness_checked",
            "contradictions_detected",
            "assessment_produced",
        ]
        for expected in expected_actions:
            assert expected in actions, f"Missing audit step: {expected}"
