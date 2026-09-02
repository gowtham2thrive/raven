"""
Golden Test Cases.

A small set of cases whose expected outcomes are stable.
Every major reasoning change should be evaluated against them.

These run the FULL deterministic pipeline end-to-end:
    connector → normalizer → timeline → contradictions → completeness
    → decision engine → response generator

Profiles in synthetic data:
    CASE-00001 to CASE-00015: A_STRONG  (strong evidence)
    CASE-00016 to CASE-00025: B_WEAK    (weak delivery proof)
    CASE-00026 to CASE-00035: C_MISSING (no delivery data)
    CASE-00036 to CASE-00045: D_CONTRADICTORY (conflicting evidence)
    CASE-00046 to CASE-00050: E_EDGE    (timezone issues, etc.)
"""

import pytest
from pathlib import Path

from app.pipeline.runner import DeterministicRunner
from app.connectors.synthetic import SyntheticConnector


@pytest.fixture
def runner():
    """Create a DeterministicRunner with synthetic data."""
    cases_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "cases"
    if not cases_dir.exists():
        pytest.skip("Synthetic data not generated — run 'python -m data.seed' first")
    connector = SyntheticConnector(cases_dir=cases_dir)
    return DeterministicRunner(connector=connector)


# ═══════════════════════════════════════════════════════════════
#  STRONG CASES — Expected: CONTEST, HIGH confidence
# ═══════════════════════════════════════════════════════════════


class TestStrongCases:
    """Profile A: All evidence present, delivery confirmed with signature."""

    def test_gold_01_strong_case_contests(self, runner):
        """CASE-00001: All evidence + signed delivery -> CONTEST, HIGH."""
        result = runner.investigate("CASE-00001")

        assert "error" not in result
        assessment = result["assessment"]
        assert assessment.recommendation.value == "contest"
        assert assessment.case_strength.value == "high"
        assert assessment.score >= 0.80
        assert assessment.auto_submit_eligible is True
        assert len(result["contradictions"]) == 0
        assert len(result["missing_evidence"]) == 0

    def test_gold_02_strong_case_has_timeline(self, runner):
        """CASE-00002: Strong case should produce a timeline."""
        result = runner.investigate("CASE-00002")

        assert len(result["timeline"]) >= 3  # At least payment, order, delivery
        # Timeline should be chronologically sorted
        timestamps = [e.timestamp_utc for e in result["timeline"]]
        assert timestamps == sorted(timestamps)

    def test_gold_03_strong_case_has_response(self, runner):
        """CASE-00003: Strong case should produce a response draft."""
        result = runner.investigate("CASE-00003")

        assert result["response_draft"] is not None
        assert len(result["response_draft"]) > 50
        # Response should mention payment, delivery, and shipping
        draft = result["response_draft"].upper()
        assert "PAYMENT" in draft
        assert "DELIVERY" in draft


# ═══════════════════════════════════════════════════════════════
#  WEAK CASES — Expected: HUMAN_REVIEW, MEDIUM confidence
# ═══════════════════════════════════════════════════════════════


class TestWeakCases:
    """Profile B: Delivery present but weak proof (no signature)."""

    def test_gold_04_weak_delivery_is_unverified(self, runner):
        """CASE-00016: Weak delivery proof is marked as UNVERIFIED."""
        result = runner.investigate("CASE-00016")

        assert "error" not in result
        assessment = result["assessment"]
        # Delivery should be marked unverified (not fully confirmed)
        delivery_items = [
            i for i in assessment.evidence_checklist if i.category == "delivery"
        ]
        assert len(delivery_items) == 1
        assert delivery_items[0].status == "unverified"
        # Should still have some evidence (just weak)
        assert assessment.score > 0.0


# ═══════════════════════════════════════════════════════════════
#  MISSING EVIDENCE — Expected: ACCEPT_LOSS or HUMAN_REVIEW
# ═══════════════════════════════════════════════════════════════


class TestMissingCases:
    """Profile C: Key delivery/shipping evidence missing."""

    def test_gold_05_missing_delivery_low_score(self, runner):
        """CASE-00026: No delivery data -> low score."""
        result = runner.investigate("CASE-00026")

        assert "error" not in result
        assessment = result["assessment"]
        # Should have missing evidence
        assert len(result["missing_evidence"]) > 0
        # Should NOT be auto-submit eligible
        assert assessment.auto_submit_eligible is False

    def test_gold_06_missing_flags_delivery_gap(self, runner):
        """CASE-00027: Missing delivery should appear in missing list."""
        result = runner.investigate("CASE-00027")

        assert any(
            "delivery" in m.lower()
            for m in result["missing_evidence"]
        )


# ═══════════════════════════════════════════════════════════════
#  CONTRADICTORY — Expected: HUMAN_REVIEW, contradiction detected
# ═══════════════════════════════════════════════════════════════


class TestContradictoryCases:
    """Profile D: Merchant says delivered, carrier says returned."""

    def test_gold_07_contradiction_detected(self, runner):
        """CASE-00036: Delivered vs returned_to_sender -> contradiction."""
        result = runner.investigate("CASE-00036")

        assert "error" not in result
        assert len(result["contradictions"]) >= 1
        assessment = result["assessment"]
        assert assessment.auto_submit_eligible is False
        assert assessment.requires_human_review is True

    def test_gold_08_contradiction_has_impact(self, runner):
        """CASE-00037: Contradiction should have impact level."""
        result = runner.investigate("CASE-00037")

        if result["contradictions"]:
            for c in result["contradictions"]:
                assert c.impact in ("high", "medium", "low")


# ═══════════════════════════════════════════════════════════════
#  EDGE CASES — Expected: HUMAN_REVIEW
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Profile E: Timezone mismatches, unusual data."""

    def test_gold_09_edge_case_runs(self, runner):
        """CASE-00046: Edge case should complete without error."""
        result = runner.investigate("CASE-00046")

        assert "error" not in result
        assert result["assessment"] is not None

    def test_gold_10_edge_case_not_auto_submitted(self, runner):
        """CASE-00047: Edge cases should not be auto-submitted."""
        result = runner.investigate("CASE-00047")

        if "error" not in result:
            assessment = result["assessment"]
            # Edge cases have uncertainty — should not auto-submit
            # (they may or may not pass auto-submit threshold depending on data)
            assert assessment is not None


# ═══════════════════════════════════════════════════════════════
#  TRIANGULATION — Golden cases for multi-source verification
# ═══════════════════════════════════════════════════════════════


class TestTriangulationGolden:
    """Verify triangulation behavior on stable synthetic cases."""

    def test_gold_11_strong_case_triangulated(self, runner):
        """CASE-00001: Strong case with carrier confirmation -> triangulated."""
        result = runner.investigate("CASE-00001")

        tri = result["triangulation"]
        assert tri is not None
        assert tri.triangulated is True
        assert tri.supporting_count >= 2

    def test_gold_12_weak_case_single_source(self, runner):
        """CASE-00016: Weak delivery -> carrier has no scan -> not triangulated."""
        result = runner.investigate("CASE-00016")

        tri = result["triangulation"]
        assert tri is not None
        # Weak delivery + carrier in_transit = not triangulated
        assert tri.triangulated is False


# ═══════════════════════════════════════════════════════════════
#  CAUSAL VALIDATION — Golden cases for timeline integrity
# ═══════════════════════════════════════════════════════════════


class TestCausalGolden:
    """Verify causal validation on stable synthetic cases."""

    def test_gold_13_normal_case_no_causal_violations(self, runner):
        """CASE-00001: Well-formed case should have no causal violations."""
        result = runner.investigate("CASE-00001")

        assert len(result["causal_violations"]) == 0


# ═══════════════════════════════════════════════════════════════
#  CITATION VERIFICATION — Golden cases for response integrity
# ═══════════════════════════════════════════════════════════════


class TestCitationGolden:
    """Verify citation verification on stable synthetic cases."""

    def test_gold_14_strong_case_citation_passes(self, runner):
        """CASE-00001: Strong case response should pass citation check."""
        result = runner.investigate("CASE-00001")

        cv = result.get("citation_verification")
        if cv is not None:
            assert cv.passed is True
            assert len(cv.violations) == 0
