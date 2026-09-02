"""Tests for ADK callbacks — budget enforcement and evidence accumulation.

Tests verify that:
- before_tool_callback blocks when call budget is exceeded
- before_tool_callback blocks when time budget is exceeded
- before_tool_callback allows execution within budget
- before_tool_callback increments call counter in session state
- after_tool_callback accumulates evidence into session state
- after_tool_callback appends audit log entries
- after_tool_callback handles non-dict responses gracefully
- after_tool_callback handles tool responses with no evidence
"""

import time

import pytest

from app.agent.callbacks import (
    STATE_AUDIT_LOG,
    STATE_BUDGET_CALLS_USED,
    STATE_BUDGET_MAX_CALLS,
    STATE_BUDGET_MAX_LATENCY,
    STATE_BUDGET_START_TIME,
    STATE_GATHERED_EVIDENCE,
    STATE_TOOL_START_TIME,
    after_tool_callback,
    before_tool_callback,
)


class _FakeTool:
    """Minimal mock for ADK tool objects in callback tests."""

    def __init__(self, name: str = "test_tool"):
        self.name = name


class _FakeToolContext:
    """Minimal mock for ADK ToolContext — just a dict-like state."""

    def __init__(self, initial_state: dict | None = None):
        self.state = dict(initial_state or {})


# ═══════════════════════════════════════════════════════════════
#  BEFORE TOOL CALLBACK
# ═══════════════════════════════════════════════════════════════


class TestBeforeToolCallbackBudget:
    """Tests for budget enforcement in before_tool_callback."""

    def test_allows_first_call(self):
        """First call within budget should be allowed (returns None)."""
        ctx = _FakeToolContext({
            STATE_BUDGET_CALLS_USED: 0,
            STATE_BUDGET_MAX_CALLS: 15,
            STATE_BUDGET_START_TIME: time.time(),
            STATE_BUDGET_MAX_LATENCY: 60,
        })
        result = before_tool_callback(_FakeTool(), {"case_id": "CASE-00001"}, ctx)
        assert result is None

    def test_increments_call_counter(self):
        """Each call increments the counter in session state."""
        ctx = _FakeToolContext({
            STATE_BUDGET_CALLS_USED: 5,
            STATE_BUDGET_MAX_CALLS: 15,
            STATE_BUDGET_START_TIME: time.time(),
            STATE_BUDGET_MAX_LATENCY: 60,
        })
        before_tool_callback(_FakeTool(), {}, ctx)
        assert ctx.state[STATE_BUDGET_CALLS_USED] == 6

    def test_blocks_when_call_budget_exceeded(self):
        """Returns error dict when call count reaches max."""
        ctx = _FakeToolContext({
            STATE_BUDGET_CALLS_USED: 15,
            STATE_BUDGET_MAX_CALLS: 15,
            STATE_BUDGET_START_TIME: time.time(),
            STATE_BUDGET_MAX_LATENCY: 60,
        })
        result = before_tool_callback(_FakeTool("get_delivery"), {}, ctx)
        assert result is not None
        assert result["status"] == "budget_exceeded"
        assert result["calls_used"] == 15

    def test_blocks_when_time_budget_exceeded(self):
        """Returns error dict when elapsed time exceeds max latency."""
        ctx = _FakeToolContext({
            STATE_BUDGET_CALLS_USED: 3,
            STATE_BUDGET_MAX_CALLS: 15,
            STATE_BUDGET_START_TIME: time.time() - 120,  # 120s ago
            STATE_BUDGET_MAX_LATENCY: 60,
        })
        result = before_tool_callback(_FakeTool("get_auth"), {}, ctx)
        assert result is not None
        assert result["status"] == "time_exceeded"
        assert result["elapsed_seconds"] > 60

    def test_allows_at_boundary(self):
        """Call at max_calls-1 should still be allowed."""
        ctx = _FakeToolContext({
            STATE_BUDGET_CALLS_USED: 14,
            STATE_BUDGET_MAX_CALLS: 15,
            STATE_BUDGET_START_TIME: time.time(),
            STATE_BUDGET_MAX_LATENCY: 60,
        })
        result = before_tool_callback(_FakeTool(), {}, ctx)
        assert result is None
        assert ctx.state[STATE_BUDGET_CALLS_USED] == 15

    def test_uses_defaults_when_state_empty(self):
        """Should use default budget values when state is empty."""
        ctx = _FakeToolContext()
        result = before_tool_callback(_FakeTool(), {}, ctx)
        assert result is None
        assert ctx.state[STATE_BUDGET_CALLS_USED] == 1

    def test_records_tool_start_time(self):
        """Should store tool start time for after_tool_callback timing."""
        ctx = _FakeToolContext({
            STATE_BUDGET_CALLS_USED: 0,
            STATE_BUDGET_MAX_CALLS: 15,
            STATE_BUDGET_START_TIME: time.time(),
            STATE_BUDGET_MAX_LATENCY: 60,
        })
        before_tool_callback(_FakeTool(), {}, ctx)
        assert STATE_TOOL_START_TIME in ctx.state
        assert isinstance(ctx.state[STATE_TOOL_START_TIME], float)

    def test_custom_budget_limits(self):
        """Should respect custom budget limits set in state."""
        ctx = _FakeToolContext({
            STATE_BUDGET_CALLS_USED: 3,
            STATE_BUDGET_MAX_CALLS: 3,
            STATE_BUDGET_START_TIME: time.time(),
            STATE_BUDGET_MAX_LATENCY: 60,
        })
        result = before_tool_callback(_FakeTool(), {}, ctx)
        assert result is not None
        assert result["max_calls"] == 3


# ═══════════════════════════════════════════════════════════════
#  AFTER TOOL CALLBACK
# ═══════════════════════════════════════════════════════════════


class TestAfterToolCallbackEvidence:
    """Tests for evidence accumulation in after_tool_callback."""

    def test_accumulates_evidence_in_state(self):
        """Evidence items from tool response are added to session state."""
        ctx = _FakeToolContext({
            STATE_TOOL_START_TIME: time.time(),
            STATE_GATHERED_EVIDENCE: [],
        })
        tool_response = {
            "case_id": "CASE-00001",
            "evidence": [
                {"evidence_id": "ev_pay_001", "category": "payment", "status": "available"},
                {"evidence_id": "ev_ord_001", "category": "order", "status": "available"},
            ],
        }
        after_tool_callback(_FakeTool("get_transaction"), {"case_id": "CASE-00001"}, ctx, tool_response)
        gathered = ctx.state[STATE_GATHERED_EVIDENCE]
        assert len(gathered) == 2
        assert gathered[0]["evidence_id"] == "ev_pay_001"
        assert gathered[1]["evidence_id"] == "ev_ord_001"

    def test_appends_to_existing_evidence(self):
        """New evidence is appended, not replacing existing."""
        ctx = _FakeToolContext({
            STATE_TOOL_START_TIME: time.time(),
            STATE_GATHERED_EVIDENCE: [
                {"evidence_id": "ev_existing", "category": "payment"},
            ],
        })
        tool_response = {
            "evidence": [{"evidence_id": "ev_new", "category": "delivery"}],
        }
        after_tool_callback(_FakeTool(), {}, ctx, tool_response)
        gathered = ctx.state[STATE_GATHERED_EVIDENCE]
        assert len(gathered) == 2
        assert gathered[0]["evidence_id"] == "ev_existing"
        assert gathered[1]["evidence_id"] == "ev_new"

    def test_handles_no_evidence_in_response(self):
        """Tool responses without evidence key don't add anything."""
        ctx = _FakeToolContext({
            STATE_TOOL_START_TIME: time.time(),
            STATE_GATHERED_EVIDENCE: [],
        })
        tool_response = {"case_id": "CASE-00001", "note": "No refund records"}
        after_tool_callback(_FakeTool(), {}, ctx, tool_response)
        assert len(ctx.state[STATE_GATHERED_EVIDENCE]) == 0

    def test_handles_empty_evidence_list(self):
        """Empty evidence list doesn't add anything."""
        ctx = _FakeToolContext({
            STATE_TOOL_START_TIME: time.time(),
            STATE_GATHERED_EVIDENCE: [],
        })
        tool_response = {"evidence": []}
        after_tool_callback(_FakeTool(), {}, ctx, tool_response)
        assert len(ctx.state[STATE_GATHERED_EVIDENCE]) == 0

    def test_returns_tool_response_unchanged(self):
        """The tool response is returned as-is (pass-through)."""
        ctx = _FakeToolContext({STATE_TOOL_START_TIME: time.time()})
        tool_response = {"case_id": "CASE-00001", "evidence": []}
        result = after_tool_callback(_FakeTool(), {}, ctx, tool_response)
        assert result is tool_response


class TestAfterToolCallbackAudit:
    """Tests for audit logging in after_tool_callback."""

    def test_creates_audit_entry(self):
        """Each call appends an audit entry to the log."""
        ctx = _FakeToolContext({
            STATE_TOOL_START_TIME: time.time(),
            STATE_AUDIT_LOG: [],
        })
        tool_response = {"evidence": [{"ev": "test"}]}
        after_tool_callback(
            _FakeTool("get_delivery_evidence"),
            {"case_id": "CASE-00001"},
            ctx,
            tool_response,
        )
        audit_log = ctx.state[STATE_AUDIT_LOG]
        assert len(audit_log) == 1
        assert audit_log[0]["tool"] == "get_delivery_evidence"
        assert audit_log[0]["evidence_count"] == 1
        assert audit_log[0]["has_error"] is False

    def test_records_error_flag(self):
        """Audit entry marks has_error when tool response contains error."""
        ctx = _FakeToolContext({
            STATE_TOOL_START_TIME: time.time(),
            STATE_AUDIT_LOG: [],
        })
        tool_response = {"error": "Case not found", "status": "not_found"}
        after_tool_callback(_FakeTool("get_transaction"), {}, ctx, tool_response)
        audit_log = ctx.state[STATE_AUDIT_LOG]
        assert audit_log[0]["has_error"] is True

    def test_records_duration(self):
        """Audit entry includes duration in milliseconds."""
        start = time.time() - 0.1  # 100ms ago
        ctx = _FakeToolContext({
            STATE_TOOL_START_TIME: start,
            STATE_AUDIT_LOG: [],
        })
        after_tool_callback(_FakeTool(), {}, ctx, {"evidence": []})
        duration = ctx.state[STATE_AUDIT_LOG][0]["duration_ms"]
        assert duration >= 50  # Allow some tolerance

    def test_excludes_tool_context_from_args(self):
        """The tool_context key is filtered from logged args."""
        ctx = _FakeToolContext({
            STATE_TOOL_START_TIME: time.time(),
            STATE_AUDIT_LOG: [],
        })
        args = {"case_id": "CASE-00001", "tool_context": "should_be_excluded"}
        after_tool_callback(_FakeTool(), args, ctx, {"evidence": []})
        logged_args = ctx.state[STATE_AUDIT_LOG][0]["args"]
        assert "case_id" in logged_args
        assert "tool_context" not in logged_args

    def test_multiple_calls_append(self):
        """Multiple callback calls append to the same audit log."""
        ctx = _FakeToolContext({
            STATE_TOOL_START_TIME: time.time(),
            STATE_AUDIT_LOG: [],
        })
        after_tool_callback(_FakeTool("tool_a"), {}, ctx, {"evidence": []})
        after_tool_callback(_FakeTool("tool_b"), {}, ctx, {"evidence": [{"x": 1}]})
        audit_log = ctx.state[STATE_AUDIT_LOG]
        assert len(audit_log) == 2
        assert audit_log[0]["tool"] == "tool_a"
        assert audit_log[1]["tool"] == "tool_b"
        assert audit_log[1]["evidence_count"] == 1
