"""
RAVEN Domain Types — Enums and Exceptions.

All state machines, classification values, and error hierarchy
for the investigation pipeline.
"""

from __future__ import annotations

from enum import Enum


# ═══════════════════════════════════════════════════════════════
#  ENUMS
# ═══════════════════════════════════════════════════════════════


class DisputeReason(str, Enum):
    """MVP: one dispute type. Expand as needed."""

    PRODUCT_NOT_RECEIVED = "product_not_received"


class DisputePhase(str, Enum):
    """Razorpay dispute lifecycle phases."""

    CHARGEBACK = "chargeback"
    PRE_ARBITRATION = "pre_arbitration"
    ARBITRATION = "arbitration"
    FRAUD = "fraud"


class CaseStatus(str, Enum):
    """Case lifecycle states (AGENTS.md Section IX)."""

    CREATED = "created"
    INVESTIGATING = "investigating"
    EVIDENCE_GATHERED = "evidence_gathered"
    ASSESSED = "assessed"
    DRAFT_READY = "draft_ready"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    SUBMITTED = "submitted"
    WON = "won"
    LOST = "lost"
    CLOSED = "closed"


class EvidenceCategory(str, Enum):
    """Canonical evidence categories (AGENTS.md Section V)."""

    PAYMENT = "payment"
    ORDER = "order"
    SHIPPING = "shipping"
    DELIVERY = "delivery"
    AUTHENTICATION = "authentication"
    COMMUNICATION = "communication"
    REFUND = "refund"
    SERVICE = "service"
    POLICY = "policy"
    DEVICE = "device"
    OTHER = "other"


class EvidenceRelevance(str, Enum):
    """How relevant an evidence item is to the specific dispute claim.

    Determined by the ADK agent based on the customer's claim text.
    Used to dynamically weight evidence for scoring — replaces
    the need for fixed per-type weight tables.
    """

    CRITICAL = "critical"
    SUPPORTING = "supporting"
    CONTEXTUAL = "contextual"
    IRRELEVANT = "irrelevant"


RELEVANCE_WEIGHTS: dict[EvidenceRelevance, float] = {
    EvidenceRelevance.CRITICAL: 0.30,
    EvidenceRelevance.SUPPORTING: 0.15,
    EvidenceRelevance.CONTEXTUAL: 0.05,
    EvidenceRelevance.IRRELEVANT: 0.00,
}


class EvidenceStatus(str, Enum):
    """Evidence availability states (AGENTS.md Section V)."""

    AVAILABLE = "available"
    MISSING = "missing"
    CONFLICTING = "conflicting"
    UNVERIFIED = "unverified"
    NOT_APPLICABLE = "not_applicable"
    INGESTION_ERROR = "ingestion_error"


class CaseStrength(str, Enum):
    """Assessment strength levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class Recommendation(str, Enum):
    """Agent recommendation outcomes."""

    CONTEST = "contest"
    ACCEPT_LOSS = "accept_loss"
    HUMAN_REVIEW = "human_review"
    ESCALATE = "escalate"


class Confidence(str, Enum):
    """Confidence must be proportional to evidence (AGENTS.md XIII)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ReviewDecision(str, Enum):
    """Human review actions (AGENTS.md Section IX)."""

    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"


# ── State Machine ─────────────────────────────────────────────

VALID_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.CREATED: {CaseStatus.INVESTIGATING, CaseStatus.ESCALATED},
    CaseStatus.INVESTIGATING: {
        CaseStatus.EVIDENCE_GATHERED,
        CaseStatus.ASSESSED,
        CaseStatus.DRAFT_READY,
        CaseStatus.UNDER_REVIEW,
        CaseStatus.APPROVED,
        CaseStatus.SUBMITTED,
        CaseStatus.CREATED,
        CaseStatus.ESCALATED,
    },
    CaseStatus.EVIDENCE_GATHERED: {
        CaseStatus.ASSESSED,
        CaseStatus.INVESTIGATING,
        CaseStatus.ESCALATED,
    },
    CaseStatus.ASSESSED: {
        CaseStatus.DRAFT_READY,
        CaseStatus.UNDER_REVIEW,
        CaseStatus.APPROVED,
        CaseStatus.REJECTED,
        CaseStatus.INVESTIGATING,
        CaseStatus.ESCALATED,
    },
    CaseStatus.DRAFT_READY: {
        CaseStatus.UNDER_REVIEW,
        CaseStatus.APPROVED,
        CaseStatus.REJECTED,
        CaseStatus.SUBMITTED,
        CaseStatus.INVESTIGATING,
        CaseStatus.ESCALATED,
    },
    CaseStatus.UNDER_REVIEW: {
        CaseStatus.APPROVED,
        CaseStatus.REJECTED,
        CaseStatus.ESCALATED,
    },
    CaseStatus.APPROVED: {
        CaseStatus.SUBMITTED,
        CaseStatus.UNDER_REVIEW,
        CaseStatus.ESCALATED,
    },
    CaseStatus.SUBMITTED: {
        CaseStatus.WON,
        CaseStatus.LOST,
        CaseStatus.CLOSED,
    },
    CaseStatus.REJECTED: {CaseStatus.CLOSED},
    CaseStatus.ESCALATED: {
        CaseStatus.UNDER_REVIEW,
        CaseStatus.CLOSED,
    },
    CaseStatus.WON: {CaseStatus.CLOSED},
    CaseStatus.LOST: {CaseStatus.CLOSED},
    CaseStatus.CLOSED: set(),
}


def validate_transition(current: CaseStatus, target: CaseStatus) -> bool:
    """Check whether a state transition is allowed."""
    allowed = VALID_TRANSITIONS.get(current, set())
    return target in allowed


# ═══════════════════════════════════════════════════════════════
#  EXCEPTIONS
# ═══════════════════════════════════════════════════════════════


class RavenError(Exception):
    """Base exception for all RAVEN errors."""


# ── Evidence Errors ───────────────────────────────────────────

class EvidenceNotFoundError(RavenError):
    """Requested evidence does not exist."""


class EvidenceValidationError(RavenError):
    """Evidence data failed schema validation at the boundary."""

    def __init__(self, source: str, category: str, details: str):
        self.source = source
        self.category = category
        self.details = details
        super().__init__(
            f"Validation failed for {source}/{category}: {details}"
        )


# ── Razorpay Errors ───────────────────────────────────────────

class RazorpayAPIError(RavenError):
    """Razorpay API call failed."""

    def __init__(self, status_code: int, message: str, endpoint: str = ""):
        self.status_code = status_code
        self.endpoint = endpoint
        super().__init__(
            f"Razorpay API error ({status_code}) on {endpoint}: {message}"
        )


class RazorpayRateLimitError(RazorpayAPIError):
    """Razorpay rate limit exceeded — retryable."""

    def __init__(self, endpoint: str = "", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(429, f"Rate limited. Retry after {retry_after}s", endpoint)


class WebhookSignatureError(RavenError):
    """Webhook signature verification failed."""


# ── Investigation Errors ──────────────────────────────────────

class InvestigationBudgetExceeded(RavenError):
    """Agent exceeded max tool calls or latency."""

    def __init__(self, limit_type: str, limit: int, actual: int):
        self.limit_type = limit_type
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Budget exceeded: {limit_type} limit={limit}, actual={actual}"
        )


# ── Case Errors ───────────────────────────────────────────────

class CaseStateTransitionError(RavenError):
    """Invalid case state transition attempted."""

    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot transition from '{current}' to '{target}'"
        )


class CaseNotFoundError(RavenError):
    """Case does not exist."""


class PolicyViolationError(RavenError):
    """Operation violates a safety policy."""
