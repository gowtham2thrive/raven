"""
RAVEN Domain Schemas — All Pydantic models and data structures.

Contains:
- Evidence: The canonical evidence model
- Contradiction: Detected conflicts between evidence
- TimelineEvent: Reconstructed timeline entries
- EvidenceCheckItem / Assessment: Decision engine output
- RazorpayDisputeInfo / Case: Case lifecycle state
- AuditEntry / AuditTrail: Investigation audit recording
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime, timezone
from typing import Any, Generator

from pydantic import BaseModel, Field

from .types import (
    CaseStatus,
    CaseStrength,
    Confidence,
    DisputePhase,
    EvidenceCategory,
    EvidenceStatus,
    Recommendation,
    ReviewDecision,
)


# ═══════════════════════════════════════════════════════════════
#  EVIDENCE
# ═══════════════════════════════════════════════════════════════


class Evidence(BaseModel):
    """Single piece of evidence in the canonical model.

    Every evidence item carries its source traceability, temporal
    information (with timezone handling), and assessment metadata.
    """

    # ── Identity ──────────────────────────────────────────────
    evidence_id: str                                   # ev_001, ev_002, ...
    case_id: str                                       # Parent case ID

    # ── Classification ────────────────────────────────────────
    category: EvidenceCategory                         # What kind of evidence
    status: EvidenceStatus = EvidenceStatus.AVAILABLE   # Availability state

    # ── Source Traceability ───────────────────────────────────
    source_system: str                                 # "razorpay", "merchant_shipping", "carrier_api"
    source_record_id: str                              # Original ID in the source system
    source_url: str | None = None                      # API endpoint or reference URL

    # ── Temporal ──────────────────────────────────────────────
    event_time: datetime | None = None                 # When the event happened (original)
    event_timezone: str | None = None                  # Original timezone, e.g. "Asia/Kolkata"
    event_time_utc: datetime | None = None             # Normalized to UTC
    timezone_confident: bool = True                    # False if timezone was guessed
    observed_at: datetime                              # When RAVEN retrieved this evidence

    # ── Content ───────────────────────────────────────────────
    content: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""

    # ── Raw Source Preservation ────────────────────────────────
    raw_source: dict[str, Any] = Field(default_factory=dict)
    raw_source_hash: str = ""                          # SHA-256 of serialized raw payload

    # ── Assessment (filled by analysis tools) ─────────────────
    relevance: str = ""
    reliability: str = ""


class Contradiction(BaseModel):
    """A detected conflict between two or more evidence items.

    Contradictions are surfaced, never hidden.
    """

    contradiction_id: str
    case_id: str

    evidence_a_id: str
    evidence_a_claim: str
    evidence_b_id: str
    evidence_b_claim: str

    impact: str                                        # "high" | "medium" | "low"
    description: str
    requires_human_review: bool = True

    detected_at: datetime


# ═══════════════════════════════════════════════════════════════
#  TIMELINE
# ═══════════════════════════════════════════════════════════════


class TimelineEvent(BaseModel):
    """A single event in the reconstructed case timeline."""

    event_id: str
    case_id: str

    timestamp_utc: datetime
    timestamp_original: str | None = None
    timezone_original: str | None = None
    timezone_confident: bool = True

    label: str
    description: str = ""
    category: str = ""

    source_evidence_id: str = ""
    source_system: str = ""


# ═══════════════════════════════════════════════════════════════
#  ASSESSMENT
# ═══════════════════════════════════════════════════════════════


class EvidenceCheckItem(BaseModel):
    """One line in the evidence checklist used for scoring."""

    category: str
    label: str
    required: bool
    status: str
    evidence_id: str | None = None
    weight: float = 1.0
    notes: str = ""


class Assessment(BaseModel):
    """Output of the decision engine."""

    case_id: str

    case_strength: CaseStrength
    recommendation: Recommendation
    confidence: Confidence

    evidence_checklist: list[EvidenceCheckItem] = Field(default_factory=list)
    score: float
    score_methodology: str = "weighted_evidence_checklist_v1"
    reasons: list[str] = Field(default_factory=list)

    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradiction_count: int = 0
    missing_evidence_count: int = 0

    requires_human_review: bool = False
    auto_submit_eligible: bool = False

    assessed_at: datetime


class InvestigationOutput(BaseModel):
    """Structured output from the ADK agent's investigation.

    The agent calls submit_investigation() with this data after
    gathering evidence and reasoning about the customer's claim.
    Validated at the boundary before the deterministic pipeline
    consumes it.
    """

    # ── Claim Understanding ──────────────────────────────────
    claim_summary: str
    """One-line summary of what the customer is claiming."""

    defense_goal: str
    """What the merchant needs to prove to refute this claim."""

    # ── Evidence Relevance ───────────────────────────────────
    evidence_relevance: dict[str, str]
    """Map of evidence category → relevance level.

    Keys: evidence categories (e.g. "payment", "delivery").
    Values: "critical", "supporting", "contextual", "irrelevant".
    """

    # ── Key Findings ─────────────────────────────────────────
    key_findings: list[str] = Field(default_factory=list)
    """Most important observations from the evidence."""

    noted_gaps: list[str] = Field(default_factory=list)
    """Evidence that is missing and would strengthen the case."""

    noted_contradictions: list[str] = Field(default_factory=list)
    """Contradictions the agent noticed between evidence items."""

    # ── Response Draft ───────────────────────────────────────
    response_draft: str = ""
    """Draft response addressing the specific claim.

    Must cite evidence categories in [brackets], e.g. "[delivery]".
    """

    # ── Agent Confidence ─────────────────────────────────────
    agent_confidence: str = "medium"
    """Agent's own assessment: "high", "medium", "low"."""

    reasoning: str = ""
    """Brief explanation of the agent's reasoning."""


# ═══════════════════════════════════════════════════════════════
#  CASE
# ═══════════════════════════════════════════════════════════════


class RazorpayDisputeInfo(BaseModel):
    """Data received from Razorpay's dispute entity."""

    dispute_id: str
    payment_id: str
    order_id: str | None = None
    customer_id: str | None = None
    amount: int
    currency: str = "INR"
    reason_code: str
    reason_description: str = ""
    phase: DisputePhase = DisputePhase.CHARGEBACK
    respond_by: datetime
    status: str = "open"
    created_at: datetime


class Case(BaseModel):
    """Complete case state — RAVEN's structured memory for one investigation."""

    case_id: str
    dispute_reason: str = ""
    status: CaseStatus = CaseStatus.CREATED

    razorpay: RazorpayDisputeInfo

    evidence: list[Evidence] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)

    agent_actions: list[dict] = Field(default_factory=list)
    tool_calls_count: int = 0
    investigation_started_at: datetime | None = None
    investigation_completed_at: datetime | None = None
    investigation_error: str | None = None

    assessment: Assessment | None = None

    response_draft: str | None = None
    response_evidence_ids: list[str] = Field(default_factory=list)

    review_decision: ReviewDecision | None = None
    review_notes: str = ""
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None

    submitted_at: datetime | None = None
    razorpay_document_ids: list[str] = Field(default_factory=list)

    outcome: str | None = None
    outcome_at: datetime | None = None

    created_at: datetime
    updated_at: datetime


# ═══════════════════════════════════════════════════════════════
#  AUDIT TRAIL
# ═══════════════════════════════════════════════════════════════


@dataclass
class AuditEntry:
    """One recorded step in an investigation."""

    case_id: str
    timestamp: datetime
    action: str
    component: str
    details: dict[str, Any]
    evidence_ids: list[str]
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "component": self.component,
            "details": self.details,
            "evidence_ids": self.evidence_ids,
            "duration_ms": round(self.duration_ms, 2),
        }


class AuditTrail:
    """Thread-safe audit log for a single investigation.

    Usage:
        audit = AuditTrail("CASE-00001")

        with audit.step("evidence_gathered", "connector") as step:
            step.evidence_ids = ["ev_abc123"]
            step.details = {"source": "razorpay", "items": 3}

        result["audit_trail"] = audit.to_dict()
    """

    def __init__(self, case_id: str):
        self.case_id = case_id
        self._entries: list[AuditEntry] = []
        self._start_time = time.monotonic()

    def record(
        self,
        action: str,
        component: str,
        details: dict[str, Any] | None = None,
        evidence_ids: list[str] | None = None,
        duration_ms: float = 0.0,
    ) -> AuditEntry:
        entry = AuditEntry(
            case_id=self.case_id,
            timestamp=datetime.now(timezone.utc),
            action=action,
            component=component,
            details=details or {},
            evidence_ids=evidence_ids or [],
            duration_ms=duration_ms,
        )
        self._entries.append(entry)
        return entry

    @contextmanager
    def step(
        self, action: str, component: str
    ) -> Generator[AuditEntry, None, None]:
        """Context manager that records a step with automatic timing."""
        entry = AuditEntry(
            case_id=self.case_id,
            timestamp=datetime.now(timezone.utc),
            action=action,
            component=component,
            details={},
            evidence_ids=[],
        )
        start = time.monotonic()
        try:
            yield entry
        finally:
            entry.duration_ms = (time.monotonic() - start) * 1000
            self._entries.append(entry)

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    def total_duration_ms(self) -> float:
        if not self._entries:
            return 0.0
        return sum(e.duration_ms for e in self._entries)

    def entry_count(self) -> int:
        return len(self._entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "entry_count": len(self._entries),
            "total_duration_ms": round(self.total_duration_ms(), 2),
            "entries": [e.to_dict() for e in self._entries],
        }
