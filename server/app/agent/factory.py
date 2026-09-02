"""
RAVEN ADK Agent Factory — Creates properly configured investigation agents.

The factory wires together:
- Tools from agent.tools
- Callbacks from agent.callbacks
- output_schema for structured InvestigationOutput
- output_key for session state storage
- generate_content_config for temperature control

Agents are ephemeral — created per-investigation, never shared across cases.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.core.schemas import InvestigationOutput
from app.agent.tools import EVIDENCE_TOOLS
from app.agent.callbacks import (
    before_tool_callback,
    after_tool_callback,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  SESSION STATE KEY FOR INVESTIGATION OUTPUT
# ═══════════════════════════════════════════════════════════════

INVESTIGATION_OUTPUT_KEY = "investigation_output"


# ═══════════════════════════════════════════════════════════════
#  AGENT FACTORY
# ═══════════════════════════════════════════════════════════════


def create_investigation_agent(
    case_id: str,
    dispute_context: str = "",
    model: str | None = None,
):
    """Create an ADK agent fully configured for a single investigation.

    The agent is ephemeral — created per-investigation, not shared.
    It uses:
    - output_schema: Enforces InvestigationOutput structure on the final response
    - output_key: Stores the result in session state under INVESTIGATION_OUTPUT_KEY
    - before_tool_callback: Budget enforcement at the correct boundary
    - after_tool_callback: Evidence accumulation and audit logging
    - generate_content_config: Low temperature for deterministic reasoning
    """
    from google.adk.agents import Agent
    from google.genai import types

    active_model = model or settings.agent_model

    instruction = (
        "You are RAVEN, an evidence investigation agent for chargeback disputes.\n\n"
        f"## This Investigation\n"
        f"Case: {case_id}\n"
        f"{dispute_context}\n\n"
        "## Protocol\n"
        "1. Read the customer's claim carefully\n"
        "2. Gather evidence from ALL tools — call every one\n"
        f"3. Use case_id '{case_id}' for all tool calls\n"
        "4. Think about which evidence is relevant to THIS specific claim\n"
        "5. After gathering all evidence, provide your structured analysis as your final response\n\n"
        "## Evidence Relevance Classification\n"
        "For each evidence category, classify its relevance to THIS claim:\n"
        "  critical:   Directly addresses/refutes the customer's claim\n"
        "  supporting: Strengthens the merchant's case but not central\n"
        "  contextual: Provides background information\n"
        "  irrelevant: Not related to this specific claim\n\n"
        "## Rules\n"
        "- NEVER invent or fabricate evidence\n"
        "- If a tool returns no data, that is MISSING evidence — report it honestly\n"
        "- Think about what would REFUTE the customer's specific claim\n"
        "- In your response_draft, cite evidence categories in [brackets]\n"
        "- Be honest about gaps and contradictions\n\n"
        f"## Budget: Maximum {settings.agent_max_tool_calls} tool calls total\n"
    )

    return Agent(
        model=active_model,
        name="raven_investigator",
        description=(
            "Investigates chargeback disputes by gathering evidence "
            "and analyzing its relevance to the customer's specific claim."
        ),
        instruction=instruction,
        tools=EVIDENCE_TOOLS,
        output_schema=InvestigationOutput,
        output_key=INVESTIGATION_OUTPUT_KEY,
        before_tool_callback=before_tool_callback,
        after_tool_callback=after_tool_callback,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.2,
        ),
    )


# ═══════════════════════════════════════════════════════════════
#  DISPUTE CONTEXT FORMATTER
# ═══════════════════════════════════════════════════════════════


def format_dispute(dispute: dict | None) -> str:
    """Format dispute details for the agent's instruction context."""
    if not dispute:
        return ""
    amount = dispute.get("amount", 0) / 100
    reason = (
        dispute.get("reason_description", "")
        or dispute.get("reason_code", "unknown")
    )
    return (
        f"\nDispute details:\n"
        f"  Dispute ID: {dispute.get('id', 'unknown')}\n"
        f"  Amount: Rs.{amount:,.2f}\n"
        f"  Customer's claim: {reason}\n"
        f"  Reason code: {dispute.get('reason_code', 'unknown')}\n"
        f"  Phase: {dispute.get('phase', 'chargeback')}\n"
    )
