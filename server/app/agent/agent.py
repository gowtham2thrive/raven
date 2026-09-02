"""
RAVEN Investigation Agent — Streaming Orchestrator.

This module contains only the orchestration logic. Tools, callbacks,
and agent creation are in their own focused modules:
- agent.tools:     Evidence-gathering tool functions
- agent.callbacks: Budget enforcement and evidence accumulation
- agent.factory:   ADK agent creation with full configuration

Two investigation modes:
1. ADK mode: Uses Google ADK agent with callbacks, output_schema,
   and session state for intelligent evidence gathering
2. Deterministic mode: Calls all tools in fixed order (fallback)

Scoring and assessment are ALWAYS deterministic regardless of mode.
The agent is an enhancement, not a requirement.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator

from app.config import settings
from app.connectors.synthetic import SyntheticConnector
from app.core.schemas import Evidence
from app.core.types import EvidenceCategory, EvidenceStatus
from app.pipeline.ingest import (
    normalize_auth,
    normalize_communications,
    normalize_delivery,
    normalize_razorpay_order,
    normalize_razorpay_payment,
    normalize_razorpay_refunds,
    normalize_shipping,
)
from app.pipeline.analysis import (
    build_timeline,
    check_completeness,
    detect_contradictions,
)
from app.pipeline.assess import (
    ResponseGenerator,
    assess_case,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  STREAMING EVENT TYPES
# ═══════════════════════════════════════════════════════════════


class EventType(str, Enum):
    STEP = "step"
    EVIDENCE = "evidence"
    THINKING = "thinking"
    CONTRADICTION = "contradiction"
    RESULT = "result"
    ERROR = "error"
    DONE = "done"


@dataclass
class InvestigationEvent:
    """A single event emitted during investigation."""
    type: EventType
    data: dict


# ═══════════════════════════════════════════════════════════════
#  INVESTIGATION AGENT — Streaming Orchestrator
# ═══════════════════════════════════════════════════════════════


class InvestigationAgent:
    """Agentic investigation with tool calling and streaming.

    Two modes:
    1. ADK mode: Uses Google ADK agent for intelligent tool selection
    2. Deterministic mode: Calls all tools in fixed order (fallback)

    Scoring and assessment are ALWAYS deterministic regardless of mode.
    """

    def __init__(self):
        self._connector = SyntheticConnector()
        self._response_gen = ResponseGenerator()

    @property
    def _llm_available(self) -> bool:
        return bool(settings.gemini_api_key)

    async def investigate_streaming(
        self,
        case_id: str,
        dispute: dict | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[InvestigationEvent, None]:
        """Run investigation and yield events as they happen."""
        if self._llm_available:
            try:
                async for event in self._adk_investigate(case_id, dispute, model=model):
                    yield event
                return
            except Exception as e:
                logger.warning(f"ADK agent failed: {e}, falling back to deterministic")
                yield InvestigationEvent(
                    type=EventType.THINKING,
                    data={"message": f"LLM unavailable ({e}), using deterministic pipeline"},
                )

        async for event in self._deterministic_investigate(case_id, dispute):
            yield event

    # ── ADK-Powered Investigation ─────────────────────────────

    async def _adk_investigate(
        self,
        case_id: str,
        dispute: dict | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[InvestigationEvent, None]:
        """LLM-powered investigation using Google ADK.

        Uses proper ADK features:
        - before_tool_callback for budget enforcement
        - after_tool_callback for evidence accumulation
        - output_schema for structured InvestigationOutput
        - output_key for session state storage
        - Session state replaces the old global _investigation_outputs dict
        """
        try:
            import os
            if settings.gemini_api_key:
                os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
                os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key

            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService
            from google.genai import types
        except ImportError:
            yield InvestigationEvent(
                type=EventType.THINKING,
                data={"message": "google-adk not installed, using deterministic pipeline"},
            )
            async for event in self._deterministic_investigate(case_id, dispute):
                yield event
            return

        from app.agent.factory import create_investigation_agent, format_dispute, INVESTIGATION_OUTPUT_KEY
        from app.agent.callbacks import (
            STATE_BUDGET_CALLS_USED,
            STATE_BUDGET_MAX_CALLS,
            STATE_BUDGET_START_TIME,
            STATE_BUDGET_MAX_LATENCY,
            STATE_GATHERED_EVIDENCE,
            STATE_AUDIT_LOG,
        )

        active_model = model or settings.agent_model
        dispute_context = format_dispute(dispute) if dispute else ""
        agent = create_investigation_agent(case_id, dispute_context, model=active_model)

        session_service = InMemorySessionService()
        runner = Runner(agent=agent, session_service=session_service, app_name="raven")
        session = await session_service.create_session(
            app_name="raven", user_id="system"
        )

        # Initialize budget state in the session so callbacks can enforce limits
        session.state[STATE_BUDGET_CALLS_USED] = 0
        session.state[STATE_BUDGET_MAX_CALLS] = settings.agent_max_tool_calls
        session.state[STATE_BUDGET_START_TIME] = time.time()
        session.state[STATE_BUDGET_MAX_LATENCY] = settings.agent_max_latency_seconds
        session.state[STATE_GATHERED_EVIDENCE] = []
        session.state[STATE_AUDIT_LOG] = []

        yield InvestigationEvent(
            type=EventType.THINKING,
            data={"message": f"Starting AI-powered investigation (model: {active_model})..."},
        )

        content = types.Content(
            role="user",
            parts=[types.Part(text=f"Investigate chargeback case {case_id}. Gather all evidence.")],
        )

        step = 0

        try:
            async for adk_event in runner.run_async(
                session_id=session.id, user_id="system", new_message=content
            ):
                # Process function calls (tool invocations)
                fn_calls = adk_event.get_function_calls()
                if fn_calls:
                    for fc in fn_calls:
                        step += 1
                        yield InvestigationEvent(
                            type=EventType.STEP,
                            data={"tool": fc.name, "status": "calling", "step": step, "total": "?"},
                        )

                # Process function responses (tool results with evidence)
                fn_responses = adk_event.get_function_responses()
                if fn_responses:
                    for fr in fn_responses:
                        response_data = fr.response if hasattr(fr, 'response') else {}
                        if isinstance(response_data, dict):
                            for ev_dict in response_data.get("evidence", []):
                                yield InvestigationEvent(
                                    type=EventType.EVIDENCE,
                                    data={
                                        "category": ev_dict.get("category", "unknown"),
                                        "status": ev_dict.get("status", "unknown"),
                                        "summary": ev_dict.get("summary", ""),
                                    },
                                )

                # Process text content (agent thinking)
                if adk_event.content and adk_event.content.parts:
                    for part in adk_event.content.parts:
                        if hasattr(part, 'text') and part.text and not getattr(adk_event, 'partial', False):
                            yield InvestigationEvent(
                                type=EventType.THINKING,
                                data={"message": part.text[:500]},
                            )

        except Exception as e:
            logger.warning(f"ADK agent error during execution: {e}")
            yield InvestigationEvent(
                type=EventType.ERROR,
                data={"message": f"LLM error: {str(e)}. Falling back to deterministic."},
            )
            async for event in self._deterministic_investigate(case_id, dispute):
                yield event
            return

        # ── Deterministic Assessment (ALWAYS runs, never LLM) ──
        yield InvestigationEvent(
            type=EventType.THINKING,
            data={"message": "Running deterministic assessment..."},
        )

        # Use evidence accumulated by after_tool_callback in session state
        # instead of re-fetching from connectors
        gathered_evidence_dicts = session.state.get(STATE_GATHERED_EVIDENCE, [])
        investigation_output = session.state.get(INVESTIGATION_OUTPUT_KEY)

        # Convert gathered evidence dicts back to Evidence objects
        evidence_all = _dicts_to_evidence(gathered_evidence_dicts, case_id)

        # If the agent gathered no evidence via callbacks (edge case),
        # fall back to direct connector fetch
        if not evidence_all:
            logger.warning(
                f"No evidence in session state for {case_id}, "
                "falling back to connector fetch"
            )
            evidence_all = self._fetch_all_evidence(case_id)

        # Extract agent's relevance classification from structured output
        evidence_relevance = None
        if isinstance(investigation_output, dict):
            evidence_relevance = investigation_output.get("evidence_relevance")
        elif isinstance(investigation_output, str):
            # output_schema may return JSON string — try to parse
            try:
                import json
                parsed = json.loads(investigation_output)
                evidence_relevance = parsed.get("evidence_relevance")
            except (json.JSONDecodeError, AttributeError):
                logger.debug(f"Could not parse investigation output as JSON for {case_id}")

        # Determine dispute type for analysis
        rzp_data = self._connector.get_razorpay_data(case_id)
        dispute_info = {}
        if rzp_data:
            dispute_info = rzp_data.get("dispute") or dispute or {}
        else:
            dispute_info = dispute or {}
        reason_code = dispute_info.get("reason_code", "product_not_received")

        checklist, missing = check_completeness(
            evidence_all,
            dispute_type=reason_code,
            evidence_relevance=evidence_relevance,
        )
        contradictions = detect_contradictions(
            evidence_all,
            dispute_reason=reason_code,
        )
        timeline = build_timeline(evidence_all)

        for c in contradictions:
            yield InvestigationEvent(
                type=EventType.CONTRADICTION,
                data={"description": c.description, "impact": c.impact},
            )

        assessment = assess_case(
            case_id=case_id,
            checklist=checklist,
            contradictions=contradictions,
            missing_required=missing,
        )

        yield InvestigationEvent(
            type=EventType.RESULT,
            data={
                "score": assessment.score,
                "strength": assessment.case_strength.value,
                "recommendation": assessment.recommendation.value,
                "confidence": assessment.confidence.value,
                "auto_submit": assessment.auto_submit_eligible,
                "contradictions": len(contradictions),
                "missing_evidence": missing,
                "evidence_count": len(evidence_all),
            },
        )

        yield InvestigationEvent(
            type=EventType.DONE,
            data={"case_id": case_id, "mode": "adk", "model": active_model},
        )

    # ── Helper: Fetch all evidence from connectors ────────────

    def _fetch_all_evidence(self, case_id: str) -> list[Evidence]:
        """Fetch all evidence directly from connectors.

        Used as fallback when session state has no accumulated evidence,
        and always used by the deterministic pipeline.
        """
        evidence: list[Evidence] = []

        rzp_data = self._connector.get_razorpay_data(case_id)
        if not rzp_data:
            return evidence

        payment = rzp_data.get("payment")
        if payment:
            evidence.append(normalize_razorpay_payment(payment, case_id))

        order = rzp_data.get("order")
        if order:
            evidence.append(normalize_razorpay_order(order, case_id))

        refund_data = self._connector.get_refunds(case_id)
        payment_id = payment.get("id", "") if payment else ""
        refund_ev = normalize_razorpay_refunds(refund_data, case_id, payment_id)
        if refund_ev:
            evidence.append(refund_ev)

        evidence.append(normalize_shipping(self._connector.get_shipping(case_id), case_id))
        evidence.append(normalize_delivery(self._connector.get_delivery(case_id), case_id))
        evidence.append(normalize_auth(self._connector.get_auth(case_id), case_id))
        evidence.append(normalize_communications(self._connector.get_communications(case_id), case_id))

        return evidence

    # ── Deterministic Investigation (Fallback) ────────────────

    async def _deterministic_investigate(
        self, case_id: str, dispute: dict | None = None,
    ) -> AsyncGenerator[InvestigationEvent, None]:
        """Deterministic pipeline with streaming events."""
        evidence: list[Evidence] = []

        # Step 1: Transaction data
        yield InvestigationEvent(
            type=EventType.STEP,
            data={"tool": "get_transaction", "status": "calling", "step": 1, "total": 7},
        )
        await asyncio.sleep(0.3)

        rzp_data = self._connector.get_razorpay_data(case_id)
        if not rzp_data or not rzp_data.get("dispute"):
            yield InvestigationEvent(type=EventType.ERROR, data={"message": f"Case {case_id} not found"})
            yield InvestigationEvent(type=EventType.DONE, data={"case_id": case_id})
            return

        payment = rzp_data.get("payment")
        if payment:
            ev = normalize_razorpay_payment(payment, case_id)
            evidence.append(ev)
            yield InvestigationEvent(
                type=EventType.EVIDENCE,
                data={"category": "payment", "status": ev.status.value, "summary": ev.summary},
            )

        order = rzp_data.get("order")
        if order:
            ev = normalize_razorpay_order(order, case_id)
            evidence.append(ev)
            yield InvestigationEvent(
                type=EventType.EVIDENCE,
                data={"category": "order", "status": ev.status.value, "summary": ev.summary},
            )

        yield InvestigationEvent(
            type=EventType.THINKING,
            data={"message": "Payment and order data retrieved. Checking delivery records..."},
        )

        # Step 2: Delivery evidence
        yield InvestigationEvent(
            type=EventType.STEP,
            data={"tool": "get_delivery_evidence", "status": "calling", "step": 2, "total": 7},
        )
        await asyncio.sleep(0.4)

        shipping = self._connector.get_shipping(case_id)
        ev = normalize_shipping(shipping, case_id)
        evidence.append(ev)
        yield InvestigationEvent(
            type=EventType.EVIDENCE,
            data={"category": "shipping", "status": ev.status.value, "summary": ev.summary},
        )

        delivery = self._connector.get_delivery(case_id)
        ev = normalize_delivery(delivery, case_id)
        evidence.append(ev)
        yield InvestigationEvent(
            type=EventType.EVIDENCE,
            data={"category": "delivery", "status": ev.status.value, "summary": ev.summary},
        )

        if ev.status.value == "available":
            yield InvestigationEvent(
                type=EventType.THINKING,
                data={"message": "Delivery evidence found. Verifying authentication and checking for refunds..."},
            )
        elif ev.status.value == "missing":
            yield InvestigationEvent(
                type=EventType.THINKING,
                data={"message": "WARNING: No delivery evidence found. This weakens the case significantly."},
            )

        # Step 3: Refunds
        yield InvestigationEvent(
            type=EventType.STEP,
            data={"tool": "get_refund_history", "status": "calling", "step": 3, "total": 7},
        )
        await asyncio.sleep(0.2)

        refund_data = self._connector.get_refunds(case_id)
        payment_id = payment.get("id", "") if payment else ""
        refund_ev = normalize_razorpay_refunds(refund_data, case_id, payment_id)
        if refund_ev:
            evidence.append(refund_ev)
            yield InvestigationEvent(
                type=EventType.EVIDENCE,
                data={"category": "refund", "status": refund_ev.status.value, "summary": refund_ev.summary},
            )

        # Step 4: Authentication
        yield InvestigationEvent(
            type=EventType.STEP,
            data={"tool": "get_authentication_events", "status": "calling", "step": 4, "total": 7},
        )
        await asyncio.sleep(0.2)

        auth = self._connector.get_auth(case_id)
        ev = normalize_auth(auth, case_id)
        evidence.append(ev)
        yield InvestigationEvent(
            type=EventType.EVIDENCE,
            data={"category": "authentication", "status": ev.status.value, "summary": ev.summary},
        )

        # Step 5: Communications
        yield InvestigationEvent(
            type=EventType.STEP,
            data={"tool": "get_customer_communications", "status": "calling", "step": 5, "total": 7},
        )
        await asyncio.sleep(0.2)

        comms = self._connector.get_communications(case_id)
        ev = normalize_communications(comms, case_id)
        evidence.append(ev)
        yield InvestigationEvent(
            type=EventType.EVIDENCE,
            data={"category": "communication", "status": ev.status.value, "summary": ev.summary},
        )

        yield InvestigationEvent(
            type=EventType.THINKING,
            data={"message": "All evidence gathered. Running analysis..."},
        )

        # Step 6: Contradiction detection
        yield InvestigationEvent(
            type=EventType.STEP,
            data={"tool": "detect_contradictions", "status": "calling", "step": 6, "total": 7},
        )
        await asyncio.sleep(0.3)

        dispute_info = rzp_data.get("dispute") or dispute or {}
        reason_code = dispute_info.get("reason_code", "product_not_received")

        contradictions = detect_contradictions(
            evidence,
            dispute_reason=reason_code,
        )
        for c in contradictions:
            yield InvestigationEvent(
                type=EventType.CONTRADICTION,
                data={"description": c.description, "impact": c.impact},
            )

        if contradictions:
            yield InvestigationEvent(
                type=EventType.THINKING,
                data={"message": f"Found {len(contradictions)} contradiction(s). This will require human review."},
            )
        else:
            yield InvestigationEvent(
                type=EventType.THINKING,
                data={"message": "No contradictions detected. Evidence is consistent."},
            )

        # Step 7: Assessment
        yield InvestigationEvent(
            type=EventType.STEP,
            data={"tool": "assess_case", "status": "calling", "step": 7, "total": 7},
        )
        await asyncio.sleep(0.3)

        checklist, missing = check_completeness(
            evidence,
            dispute_type=reason_code,
            evidence_relevance=None,
        )
        timeline = build_timeline(evidence)

        assessment = assess_case(
            case_id=case_id,
            checklist=checklist,
            contradictions=contradictions,
            missing_required=missing,
        )

        # Generate response draft
        response_draft = None
        if assessment.recommendation.value in ("contest", "human_review"):
            response_draft = self._response_gen.generate(
                evidence=evidence,
                timeline=timeline,
                assessment=assessment,
                dispute=rzp_data.get("dispute", {}),
            )

        yield InvestigationEvent(
            type=EventType.RESULT,
            data={
                "score": assessment.score,
                "strength": assessment.case_strength.value,
                "recommendation": assessment.recommendation.value,
                "confidence": assessment.confidence.value,
                "auto_submit": assessment.auto_submit_eligible,
                "contradictions": len(contradictions),
                "missing_evidence": missing,
                "evidence_count": len(evidence),
            },
        )

        final_msg = (
            f"Investigation complete. Score: {assessment.score:.2f}, "
            f"Recommendation: {assessment.recommendation.value.upper()}"
        )
        if assessment.auto_submit_eligible:
            final_msg += " -- Auto-submit eligible."
        else:
            final_msg += " -- Requires human review."

        yield InvestigationEvent(type=EventType.THINKING, data={"message": final_msg})

        yield InvestigationEvent(
            type=EventType.DONE,
            data={
                "case_id": case_id,
                "mode": "deterministic",
                "result": {
                    "evidence_count": len(evidence),
                    "timeline_count": len(timeline),
                    "contradictions": len(contradictions),
                    "score": assessment.score,
                    "recommendation": assessment.recommendation.value,
                },
            },
        )


# ═══════════════════════════════════════════════════════════════
#  EVIDENCE CONVERSION — Dict ↔ Evidence object boundary
# ═══════════════════════════════════════════════════════════════


def _dicts_to_evidence(
    evidence_dicts: list[dict], case_id: str,
) -> list[Evidence]:
    """Convert evidence dicts (from session state) back to Evidence objects.

    The after_tool_callback stores evidence as dicts in session state
    (JSON-serializable). The assessment pipeline needs Evidence objects.
    This is the boundary conversion.
    """
    from datetime import datetime, timezone

    evidence_list: list[Evidence] = []
    for ev_dict in evidence_dicts:
        try:
            category_raw = ev_dict.get("category", "")
            status_raw = ev_dict.get("status", "available")

            # Handle both string and enum values from serialization
            category_str = category_raw.value if hasattr(category_raw, 'value') else str(category_raw)
            status_str = status_raw.value if hasattr(status_raw, 'value') else str(status_raw)

            evidence_list.append(Evidence(
                evidence_id=ev_dict.get("evidence_id", f"ev_gathered_{len(evidence_list)}"),
                case_id=case_id,
                category=EvidenceCategory(category_str),
                status=EvidenceStatus(status_str),
                source_system=ev_dict.get("source_system", "unknown"),
                source_record_id=ev_dict.get("evidence_id", ""),
                observed_at=datetime.now(timezone.utc),
                summary=ev_dict.get("summary", ""),
                content=ev_dict.get("content", {}),
                relevance=ev_dict.get("relevance", ""),
                reliability=ev_dict.get("reliability", ""),
            ))
        except (ValueError, KeyError) as e:
            logger.warning(f"Could not convert evidence dict to Evidence: {e}")
            continue

    return evidence_list


# ═══════════════════════════════════════════════════════════════
#  BACKWARD-COMPATIBLE RE-EXPORTS
# ═══════════════════════════════════════════════════════════════
#
# Existing tests and code import from app.agent.agent.
# These re-exports maintain backward compatibility while the
# canonical location moves to the new modules.


from app.agent.tools import (  # noqa: E402, F401
    _evidence_to_dict,
    _make_missing_evidence,
    get_transaction,
    get_delivery_evidence,
    get_authentication_events,
    get_customer_communications,
    get_refund_history,
    get_device_session,
    get_service_logs,
    get_policy_terms,
    get_external_integrations,
)
from app.agent.factory import format_dispute as _format_dispute  # noqa: E402, F401


# Legacy submit_investigation support — kept for backward compatibility
# with existing tests. New code should use output_schema instead.


_investigation_outputs: dict[str, dict] = {}


def submit_investigation(
    case_id: str,
    claim_summary: str,
    defense_goal: str,
    evidence_relevance: dict[str, str],
    key_findings: list[str],
    noted_gaps: list[str],
    noted_contradictions: list[str],
    response_draft: str,
    agent_confidence: str,
    reasoning: str,
) -> dict:
    """Submit investigation analysis — LEGACY compatibility.

    In the new ADK architecture, this function is no longer called
    by the agent (output_schema replaces it). It is kept solely
    for backward compatibility with existing tests.
    """
    from app.core.schemas import InvestigationOutput

    valid_relevance = {"critical", "supporting", "contextual", "irrelevant"}
    sanitized_relevance: dict[str, str] = {}
    for key, value in evidence_relevance.items():
        lower_value = value.lower().strip()
        if lower_value in valid_relevance:
            sanitized_relevance[key] = lower_value
        else:
            logger.warning(
                f"Invalid relevance '{value}' for '{key}', defaulting to 'supporting'"
            )
            sanitized_relevance[key] = "supporting"

    valid_confidence = {"high", "medium", "low"}
    sanitized_confidence = (
        agent_confidence.lower().strip()
        if agent_confidence.lower().strip() in valid_confidence
        else "medium"
    )

    output = InvestigationOutput(
        claim_summary=claim_summary,
        defense_goal=defense_goal,
        evidence_relevance=sanitized_relevance,
        key_findings=key_findings or [],
        noted_gaps=noted_gaps or [],
        noted_contradictions=noted_contradictions or [],
        response_draft=response_draft or "",
        agent_confidence=sanitized_confidence,
        reasoning=reasoning or "",
    )

    _investigation_outputs[case_id] = output.model_dump()
    logger.info(
        f"Investigation output recorded for {case_id}: "
        f"{len(sanitized_relevance)} categories classified, "
        f"confidence={sanitized_confidence}"
    )

    return {
        "status": "recorded",
        "case_id": case_id,
        "categories_classified": len(sanitized_relevance),
        "message": "Investigation analysis recorded. Deterministic scoring will follow.",
    }


def get_investigation_output(case_id: str) -> dict | None:
    """Retrieve and clear stored investigation output — LEGACY compatibility.

    In the new ADK architecture, investigation output comes from
    session state via output_key, not from this global dict.
    """
    return _investigation_outputs.pop(case_id, None)
