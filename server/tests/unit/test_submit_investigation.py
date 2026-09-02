"""Tests for Phase 2: submit_investigation tool and get_investigation_output."""

import pytest

from app.agent.agent import (
    _investigation_outputs,
    get_investigation_output,
    submit_investigation,
)


class TestSubmitInvestigation:
    """Tests for the submit_investigation agent tool."""

    def setup_method(self):
        """Clear stored outputs before each test."""
        _investigation_outputs.clear()

    def _valid_args(self) -> dict:
        return {
            "case_id": "CASE-99999",
            "claim_summary": "Customer claims unauthorized transaction",
            "defense_goal": "Prove cardholder authorized the payment",
            "evidence_relevance": {
                "authentication": "critical",
                "device": "critical",
                "payment": "supporting",
                "delivery": "contextual",
            },
            "key_findings": ["3DS verified", "Known device"],
            "noted_gaps": ["No customer communication"],
            "noted_contradictions": [],
            "response_draft": "Transaction was [authentication] verified.",
            "agent_confidence": "high",
            "reasoning": "Strong auth evidence.",
        }

    def test_valid_submission_returns_recorded(self):
        """Valid call returns status=recorded."""
        result = submit_investigation(**self._valid_args())
        assert result["status"] == "recorded"
        assert result["case_id"] == "CASE-99999"
        assert result["categories_classified"] == 4

    def test_stores_output(self):
        """Output is stored and retrievable."""
        submit_investigation(**self._valid_args())
        assert "CASE-99999" in _investigation_outputs
        output = _investigation_outputs["CASE-99999"]
        assert output["claim_summary"] == "Customer claims unauthorized transaction"
        assert output["evidence_relevance"]["authentication"] == "critical"

    def test_sanitizes_invalid_relevance(self):
        """Invalid relevance values are sanitized to 'supporting'."""
        args = self._valid_args()
        args["evidence_relevance"]["payment"] = "VERY_IMPORTANT"
        submit_investigation(**args)
        output = _investigation_outputs["CASE-99999"]
        assert output["evidence_relevance"]["payment"] == "supporting"

    def test_sanitizes_relevance_case_insensitive(self):
        """Relevance values are lowercased."""
        args = self._valid_args()
        args["evidence_relevance"]["authentication"] = "CRITICAL"
        submit_investigation(**args)
        output = _investigation_outputs["CASE-99999"]
        assert output["evidence_relevance"]["authentication"] == "critical"

    def test_sanitizes_invalid_confidence(self):
        """Invalid confidence defaults to 'medium'."""
        args = self._valid_args()
        args["agent_confidence"] = "very_sure"
        submit_investigation(**args)
        output = _investigation_outputs["CASE-99999"]
        assert output["agent_confidence"] == "medium"

    def test_sanitizes_confidence_case_insensitive(self):
        """Confidence is lowercased."""
        args = self._valid_args()
        args["agent_confidence"] = "HIGH"
        submit_investigation(**args)
        output = _investigation_outputs["CASE-99999"]
        assert output["agent_confidence"] == "high"

    def test_empty_lists_handled(self):
        """Empty or None lists are handled gracefully."""
        args = self._valid_args()
        args["key_findings"] = []
        args["noted_gaps"] = []
        args["noted_contradictions"] = []
        result = submit_investigation(**args)
        assert result["status"] == "recorded"

    def test_overwrites_previous_output(self):
        """Submitting for the same case_id overwrites the previous output."""
        submit_investigation(**self._valid_args())
        args = self._valid_args()
        args["claim_summary"] = "Updated claim"
        submit_investigation(**args)
        output = _investigation_outputs["CASE-99999"]
        assert output["claim_summary"] == "Updated claim"


class TestGetInvestigationOutput:
    """Tests for get_investigation_output retrieval."""

    def setup_method(self):
        _investigation_outputs.clear()

    def test_returns_and_clears(self):
        """Retrieves the output and removes it from storage."""
        submit_investigation(
            case_id="CASE-00001",
            claim_summary="Test claim",
            defense_goal="Test goal",
            evidence_relevance={"payment": "critical"},
            key_findings=[],
            noted_gaps=[],
            noted_contradictions=[],
            response_draft="",
            agent_confidence="medium",
            reasoning="",
        )
        output = get_investigation_output("CASE-00001")
        assert output is not None
        assert output["claim_summary"] == "Test claim"
        # Should be cleared now
        assert get_investigation_output("CASE-00001") is None

    def test_returns_none_for_unknown_case(self):
        """Returns None when no output exists for the case."""
        assert get_investigation_output("CASE-NONEXISTENT") is None

    def test_returns_none_after_consumed(self):
        """Returns None on second call (already consumed)."""
        submit_investigation(
            case_id="CASE-00002",
            claim_summary="Test",
            defense_goal="Test",
            evidence_relevance={},
            key_findings=[],
            noted_gaps=[],
            noted_contradictions=[],
            response_draft="",
            agent_confidence="low",
            reasoning="",
        )
        get_investigation_output("CASE-00002")
        assert get_investigation_output("CASE-00002") is None
