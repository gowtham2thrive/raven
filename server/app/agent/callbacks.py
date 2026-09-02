"""
RAVEN ADK Callbacks — Budget enforcement, evidence accumulation, and audit logging.

Callbacks are the correct ADK mechanism for cross-cutting concerns that
apply to all tool calls. They execute at the right boundary — before/after
each tool invocation — rather than after-the-fact in the streaming loop.

before_tool_callback: Budget enforcement and pre-execution audit
after_tool_callback:  Evidence accumulation into session state and timing
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  SESSION STATE KEYS — Constants to avoid magic strings
# ═══════════════════════════════════════════════════════════════


STATE_BUDGET_CALLS_USED = "budget_calls_used"
STATE_BUDGET_MAX_CALLS = "budget_max_calls"
STATE_BUDGET_START_TIME = "budget_start_time"
STATE_BUDGET_MAX_LATENCY = "budget_max_latency_seconds"
STATE_GATHERED_EVIDENCE = "gathered_evidence"
STATE_AUDIT_LOG = "audit_log"
STATE_TOOL_START_TIME = "_tool_start_time"


# ═══════════════════════════════════════════════════════════════
#  BEFORE TOOL CALLBACK — Budget gate
# ═══════════════════════════════════════════════════════════════


def before_tool_callback(
    tool: Any, args: dict[str, Any], tool_context: Any,
) -> dict | None:
    """Enforce budget limits before each tool call.

    Returns None to allow execution. Returns a dict to block
    execution — the dict becomes the tool's response.

    Budget state is stored in the ADK session via tool_context.state,
    not in a module-level global. This is thread-safe and scoped
    to the individual investigation session.
    """
    calls_used = tool_context.state.get(STATE_BUDGET_CALLS_USED, 0)
    max_calls = tool_context.state.get(STATE_BUDGET_MAX_CALLS, 15)
    start_time = tool_context.state.get(STATE_BUDGET_START_TIME, time.time())
    max_latency = tool_context.state.get(STATE_BUDGET_MAX_LATENCY, 60)

    # Check call count budget
    if calls_used >= max_calls:
        logger.warning(
            f"Budget exceeded: {calls_used}/{max_calls} tool calls used. "
            f"Blocking {tool.name}."
        )
        return {
            "error": "Investigation budget exceeded",
            "status": "budget_exceeded",
            "calls_used": calls_used,
            "max_calls": max_calls,
            "message": "Maximum tool calls reached. Submit your analysis now.",
        }

    # Check time budget
    elapsed = time.time() - start_time
    if elapsed > max_latency:
        logger.warning(
            f"Time budget exceeded: {elapsed:.1f}s > {max_latency}s. "
            f"Blocking {tool.name}."
        )
        return {
            "error": "Investigation time budget exceeded",
            "status": "time_exceeded",
            "elapsed_seconds": round(elapsed, 1),
            "max_seconds": max_latency,
            "message": "Maximum investigation time reached. Submit your analysis now.",
        }

    # Increment call counter and record start time for this tool
    tool_context.state[STATE_BUDGET_CALLS_USED] = calls_used + 1
    tool_context.state[STATE_TOOL_START_TIME] = time.time()

    logger.debug(
        f"Tool {tool.name} starting (call {calls_used + 1}/{max_calls})"
    )

    return None  # Allow execution


# ═══════════════════════════════════════════════════════════════
#  AFTER TOOL CALLBACK — Evidence accumulation + audit
# ═══════════════════════════════════════════════════════════════


def after_tool_callback(
    tool: Any, args: dict[str, Any], tool_context: Any, tool_response: dict,
) -> dict | None:
    """Accumulate evidence into session state and log the tool call.

    Every evidence dict returned by a tool is appended to the
    session state's gathered_evidence list. This replaces the
    old pattern of re-fetching evidence from connectors after
    the agent finishes.

    The audit log captures tool name, args, timing, and result
    summary for the investigation audit trail.
    """
    tool_start = tool_context.state.get(STATE_TOOL_START_TIME, time.time())
    duration_ms = round((time.time() - tool_start) * 1000)

    # Accumulate evidence into session state
    if isinstance(tool_response, dict):
        evidence_items = tool_response.get("evidence", [])
        if evidence_items:
            gathered = tool_context.state.get(STATE_GATHERED_EVIDENCE, [])
            gathered.extend(evidence_items)
            tool_context.state[STATE_GATHERED_EVIDENCE] = gathered

    # Append to audit log
    evidence_count = (
        len(tool_response.get("evidence", []))
        if isinstance(tool_response, dict)
        else 0
    )
    has_error = (
        isinstance(tool_response, dict) and "error" in tool_response
    )

    audit_entry = {
        "tool": tool.name,
        "args": {k: v for k, v in args.items() if k != "tool_context"},
        "duration_ms": duration_ms,
        "evidence_count": evidence_count,
        "has_error": has_error,
    }

    audit_log = tool_context.state.get(STATE_AUDIT_LOG, [])
    audit_log.append(audit_entry)
    tool_context.state[STATE_AUDIT_LOG] = audit_log

    logger.debug(
        f"Tool {tool.name} completed in {duration_ms}ms "
        f"({evidence_count} evidence items)"
    )

    return tool_response
