"""Tests for Phase 1 foundation types: EvidenceRelevance and InvestigationOutput."""

import pytest
from pydantic import ValidationError

from app.core.types import EvidenceRelevance, RELEVANCE_WEIGHTS
from app.core.schemas import InvestigationOutput


# ═══════════════════════════════════════════════════════════════
#  EvidenceRelevance Enum
# ═══════════════════════════════════════════════════════════════


class TestEvidenceRelevance:
    """Tests for the EvidenceRelevance enum."""

    def test_has_four_values(self):
        """EvidenceRelevance must have exactly 4 levels."""
        assert len(EvidenceRelevance) == 4

    def test_values(self):
        """Each relevance level has the correct string value."""
        assert EvidenceRelevance.CRITICAL == "critical"
        assert EvidenceRelevance.SUPPORTING == "supporting"
        assert EvidenceRelevance.CONTEXTUAL == "contextual"
        assert EvidenceRelevance.IRRELEVANT == "irrelevant"

    def test_from_string(self):
        """Can construct from string value."""
        assert EvidenceRelevance("critical") == EvidenceRelevance.CRITICAL
        assert EvidenceRelevance("supporting") == EvidenceRelevance.SUPPORTING

    def test_invalid_value_raises(self):
        """Invalid string raises ValueError."""
        with pytest.raises(ValueError):
            EvidenceRelevance("invalid_value")


# ═══════════════════════════════════════════════════════════════
#  RELEVANCE_WEIGHTS Mapping
# ═══════════════════════════════════════════════════════════════


class TestRelevanceWeights:
    """Tests for the RELEVANCE_WEIGHTS mapping."""

    def test_maps_all_relevance_levels(self):
        """Every EvidenceRelevance value must have a weight."""
        for relevance in EvidenceRelevance:
            assert relevance in RELEVANCE_WEIGHTS

    def test_critical_has_highest_weight(self):
        """Critical evidence must have the highest weight."""
        assert RELEVANCE_WEIGHTS[EvidenceRelevance.CRITICAL] > RELEVANCE_WEIGHTS[EvidenceRelevance.SUPPORTING]
        assert RELEVANCE_WEIGHTS[EvidenceRelevance.SUPPORTING] > RELEVANCE_WEIGHTS[EvidenceRelevance.CONTEXTUAL]
        assert RELEVANCE_WEIGHTS[EvidenceRelevance.CONTEXTUAL] > RELEVANCE_WEIGHTS[EvidenceRelevance.IRRELEVANT]

    def test_irrelevant_is_zero(self):
        """Irrelevant evidence must have zero weight (excluded from scoring)."""
        assert RELEVANCE_WEIGHTS[EvidenceRelevance.IRRELEVANT] == 0.0

    def test_critical_weight_value(self):
        """Critical weight is 0.30."""
        assert RELEVANCE_WEIGHTS[EvidenceRelevance.CRITICAL] == 0.30

    def test_supporting_weight_value(self):
        """Supporting weight is 0.15."""
        assert RELEVANCE_WEIGHTS[EvidenceRelevance.SUPPORTING] == 0.15

    def test_contextual_weight_value(self):
        """Contextual weight is 0.05."""
        assert RELEVANCE_WEIGHTS[EvidenceRelevance.CONTEXTUAL] == 0.05


# ═══════════════════════════════════════════════════════════════
#  InvestigationOutput Schema
# ═══════════════════════════════════════════════════════════════


class TestInvestigationOutput:
    """Tests for the InvestigationOutput Pydantic model."""

    def _valid_data(self) -> dict:
        """Minimal valid data for InvestigationOutput."""
        return {
            "claim_summary": "Customer claims product was not received",
            "defense_goal": "Prove delivery occurred and was confirmed",
            "evidence_relevance": {
                "delivery": "critical",
                "shipping": "critical",
                "payment": "supporting",
                "auth": "contextual",
            },
        }

    def test_valid_minimal(self):
        """Validates with only required fields."""
        output = InvestigationOutput(**self._valid_data())
        assert output.claim_summary == "Customer claims product was not received"
        assert output.defense_goal == "Prove delivery occurred and was confirmed"
        assert output.evidence_relevance["delivery"] == "critical"

    def test_valid_full(self):
        """Validates with all fields."""
        data = self._valid_data()
        data.update({
            "key_findings": ["Delivery confirmed by carrier", "Signature on file"],
            "noted_gaps": ["No customer communication records"],
            "noted_contradictions": ["Carrier says delivered but customer says not"],
            "response_draft": "We contest this dispute. [delivery] confirms receipt.",
            "agent_confidence": "high",
            "reasoning": "Strong delivery evidence from multiple sources.",
        })
        output = InvestigationOutput(**data)
        assert len(output.key_findings) == 2
        assert len(output.noted_gaps) == 1
        assert output.agent_confidence == "high"

    def test_defaults(self):
        """Optional fields have correct defaults."""
        output = InvestigationOutput(**self._valid_data())
        assert output.key_findings == []
        assert output.noted_gaps == []
        assert output.noted_contradictions == []
        assert output.response_draft == ""
        assert output.agent_confidence == "medium"
        assert output.reasoning == ""

    def test_missing_claim_summary_raises(self):
        """claim_summary is required."""
        data = self._valid_data()
        del data["claim_summary"]
        with pytest.raises(ValidationError):
            InvestigationOutput(**data)

    def test_missing_defense_goal_raises(self):
        """defense_goal is required."""
        data = self._valid_data()
        del data["defense_goal"]
        with pytest.raises(ValidationError):
            InvestigationOutput(**data)

    def test_missing_evidence_relevance_raises(self):
        """evidence_relevance is required."""
        data = self._valid_data()
        del data["evidence_relevance"]
        with pytest.raises(ValidationError):
            InvestigationOutput(**data)

    def test_empty_evidence_relevance_allowed(self):
        """Empty evidence_relevance dict is valid (edge case)."""
        data = self._valid_data()
        data["evidence_relevance"] = {}
        output = InvestigationOutput(**data)
        assert output.evidence_relevance == {}

    def test_serialization_roundtrip(self):
        """model_dump and reconstruction produce identical output."""
        original = InvestigationOutput(**self._valid_data())
        dumped = original.model_dump()
        reconstructed = InvestigationOutput(**dumped)
        assert original == reconstructed
