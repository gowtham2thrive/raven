"""
RAVEN Database Models (SQLAlchemy ORM).

Tables:
    cases              — One row per chargeback case
    evidence_items     — Canonical evidence records
    contradictions     — Detected contradictions between evidence
    timeline_events    — Reconstructed timeline entries
    agent_runs         — One row per investigation attempt (supports re-investigation)
    audit_logs         — Full audit trail for every case action
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship

from .database import Base


def _generate_id(prefix: str = "") -> str:
    """Generate a short unique ID with an optional prefix."""
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════
#  CASES
# ═══════════════════════════════════════════════════════════════

class CaseModel(Base):
    __tablename__ = "cases"

    # ── Identity ──────────────────────────────────────────────
    id = Column(String(32), primary_key=True, default=lambda: _generate_id("CASE-"))
    status = Column(String(32), nullable=False, default="created")
    dispute_reason = Column(Text, nullable=False)

    # ── Razorpay Dispute Data ─────────────────────────────────
    rzp_dispute_id = Column(String(64), unique=True, index=True)
    rzp_payment_id = Column(String(64), index=True)
    rzp_order_id = Column(String(64), nullable=True)
    rzp_customer_id = Column(String(64), nullable=True)
    amount = Column(Integer, nullable=False)                       # In paise
    currency = Column(String(8), default="INR")
    reason_code = Column(String(64), nullable=False)
    reason_description = Column(Text, default="")
    dispute_phase = Column(String(32), default="chargeback")
    respond_by = Column(DateTime(timezone=True), nullable=False)
    rzp_dispute_status = Column(String(32), default="open")
    rzp_created_at = Column(DateTime(timezone=True), nullable=True)

    # ── Investigation Tracking ────────────────────────────────
    investigation_started_at = Column(DateTime(timezone=True), nullable=True)
    investigation_completed_at = Column(DateTime(timezone=True), nullable=True)
    investigation_error = Column(Text, nullable=True)

    # ── Assessment ────────────────────────────────────────────
    case_strength = Column(String(16), nullable=True)
    recommendation = Column(String(32), nullable=True)
    confidence = Column(String(16), nullable=True)
    assessment_score = Column(Float, nullable=True)
    assessment_data = Column(JSON, nullable=True)

    # ── Response ──────────────────────────────────────────────
    response_draft = Column(Text, nullable=True)
    response_evidence_ids = Column(JSON, default=list)

    # ── Human Review ──────────────────────────────────────────
    review_decision = Column(String(16), nullable=True)
    review_notes = Column(Text, default="")
    reviewed_by = Column(String(128), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # ── Razorpay Submission ───────────────────────────────────
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    rzp_document_ids = Column(JSON, default=list)

    # ── Outcome ───────────────────────────────────────────────
    outcome = Column(String(16), nullable=True)                    # won | lost
    outcome_at = Column(DateTime(timezone=True), nullable=True)

    # ── Metadata ──────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    # ── Relationships ─────────────────────────────────────────
    evidence_items = relationship(
        "EvidenceModel", back_populates="case", cascade="all, delete-orphan",
        order_by="EvidenceModel.observed_at",
    )
    contradictions = relationship(
        "ContradictionModel", back_populates="case", cascade="all, delete-orphan",
    )
    timeline_events = relationship(
        "TimelineEventModel", back_populates="case", cascade="all, delete-orphan",
        order_by="TimelineEventModel.timestamp_utc",
    )
    agent_runs = relationship(
        "AgentRunModel", back_populates="case", cascade="all, delete-orphan",
        order_by="AgentRunModel.started_at.desc()",
    )
    audit_logs = relationship(
        "AuditLogModel", back_populates="case", cascade="all, delete-orphan",
        order_by="AuditLogModel.timestamp",
    )

    __table_args__ = (
        Index("ix_cases_status", "status"),
        Index("ix_cases_created_at", "created_at"),
        Index("ix_cases_respond_by", "respond_by"),
        Index("ix_cases_recommendation", "recommendation"),
        Index("ix_cases_outcome", "outcome"),
    )

    def __repr__(self) -> str:
        return f"<Case {self.id} [{self.status}] {self.reason_code}>"


# ═══════════════════════════════════════════════════════════════
#  EVIDENCE
# ═══════════════════════════════════════════════════════════════

class EvidenceModel(Base):
    __tablename__ = "evidence_items"

    id = Column(String(32), primary_key=True, default=lambda: _generate_id("ev_"))
    case_id = Column(String(32), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    # ── Classification ────────────────────────────────────────
    category = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="available")

    # ── Source Traceability ───────────────────────────────────
    source_system = Column(String(64), nullable=False)
    source_record_id = Column(String(128), nullable=False)
    source_url = Column(String(512), nullable=True)

    # ── Temporal ──────────────────────────────────────────────
    event_time = Column(DateTime(timezone=True), nullable=True)
    event_timezone = Column(String(64), nullable=True)
    event_time_utc = Column(DateTime(timezone=True), nullable=True)
    timezone_confident = Column(Boolean, default=True)
    observed_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    # ── Content ───────────────────────────────────────────────
    content = Column(JSON, default=dict)
    summary = Column(Text, default="")
    relevance = Column(String(32), default="")
    reliability = Column(String(32), default="")

    # ── Relationships ─────────────────────────────────────────
    case = relationship("CaseModel", back_populates="evidence_items")

    __table_args__ = (
        Index("ix_evidence_category", "category"),
        Index("ix_evidence_case_category", "case_id", "category"),
    )

    def __repr__(self) -> str:
        return f"<Evidence {self.id} [{self.category}:{self.status}]>"


# ═══════════════════════════════════════════════════════════════
#  CONTRADICTIONS
# ═══════════════════════════════════════════════════════════════

class ContradictionModel(Base):
    __tablename__ = "contradictions"

    id = Column(String(32), primary_key=True, default=lambda: _generate_id("contra_"))
    case_id = Column(String(32), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    evidence_a_id = Column(String(64), nullable=False)
    evidence_a_claim = Column(Text, nullable=False)
    evidence_b_id = Column(String(64), nullable=False)
    evidence_b_claim = Column(Text, nullable=False)

    impact = Column(String(16), nullable=False)                    # high | medium | low
    description = Column(Text, nullable=False)
    requires_human_review = Column(Boolean, default=True)
    detected_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    case = relationship("CaseModel", back_populates="contradictions")

    def __repr__(self) -> str:
        return f"<Contradiction {self.id} [impact:{self.impact}]>"


# ═══════════════════════════════════════════════════════════════
#  TIMELINE
# ═══════════════════════════════════════════════════════════════

class TimelineEventModel(Base):
    __tablename__ = "timeline_events"

    id = Column(String(32), primary_key=True, default=lambda: _generate_id("tl_"))
    case_id = Column(String(32), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    timestamp_utc = Column(DateTime(timezone=True), nullable=False)
    timestamp_original = Column(String(64), nullable=True)
    timezone_original = Column(String(64), nullable=True)
    timezone_confident = Column(Boolean, default=True)

    label = Column(String(256), nullable=False)
    description = Column(Text, default="")
    category = Column(String(32), default="")
    source_evidence_id = Column(String(32), default="")
    source_system = Column(String(64), default="")

    case = relationship("CaseModel", back_populates="timeline_events")

    __table_args__ = (
        Index("ix_timeline_case_time", "case_id", "timestamp_utc"),
    )

    def __repr__(self) -> str:
        return f"<TimelineEvent {self.id} [{self.label}]>"


# ═══════════════════════════════════════════════════════════════
#  AGENT RUNS
# ═══════════════════════════════════════════════════════════════

class AgentRunModel(Base):
    """One row per investigation attempt.

    Re-investigation is safe:
    - Each attempt gets its own run record
    - Previously gathered evidence is reused unless invalidated
    - The audit trail records each attempt
    """
    __tablename__ = "agent_runs"

    id = Column(String(32), primary_key=True, default=lambda: _generate_id("run_"))
    case_id = Column(String(32), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    started_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), default="running")               # running | completed | failed | budget_exceeded
    tool_calls_count = Column(Integer, default=0)
    model_used = Column(String(64), default="")
    total_tokens = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    actions = Column(JSON, default=list)                         # List of tool call records

    case = relationship("CaseModel", back_populates="agent_runs")

    def __repr__(self) -> str:
        return f"<AgentRun {self.id} [{self.status}] calls={self.tool_calls_count}>"


# ═══════════════════════════════════════════════════════════════
#  AUDIT LOGS
# ═══════════════════════════════════════════════════════════════

class AuditLogModel(Base):
    """Full audit trail — what did RAVEN know, retrieve, conclude, and authorize?

    Every investigation should have a traceable case ID and record:
    tool calls, tool outcomes, evidence IDs accessed, model used,
    latency, errors, recommendation, human decision, final outcome.
    """
    __tablename__ = "audit_logs"

    id = Column(String(32), primary_key=True, default=lambda: _generate_id("audit_"))
    case_id = Column(String(32), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)

    timestamp = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    action = Column(String(64), nullable=False)                  # "webhook_received", "investigation_started", etc.
    actor = Column(String(128), default="system")                # "system", "agent", "human:user@email"
    details = Column(JSON, default=dict)                         # Action-specific payload

    case = relationship("CaseModel", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_case_time", "case_id", "timestamp"),
        Index("ix_audit_action", "action"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.id} [{self.action}]>"


# ═══════════════════════════════════════════════════════════════
#  INTEGRATIONS
# ═══════════════════════════════════════════════════════════════

class IntegrationModel(Base):
    """Reusable data source integration configuration.

    Each row defines a connection to an external merchant system
    (REST API, database, uploaded file, webhook). Not tied to a
    specific case — integrations feed evidence into any investigation.
    """
    __tablename__ = "integrations"

    id = Column(String(32), primary_key=True, default=lambda: _generate_id("intg_"))

    # ── Identity ──────────────────────────────────────────────
    name = Column(String(256), nullable=False)
    description = Column(Text, default="")
    integration_type = Column(String(32), nullable=False)        # IntegrationType enum value
    evidence_category = Column(String(32), nullable=False)       # EvidenceCategory enum value
    status = Column(String(16), nullable=False, default="inactive")  # IntegrationStatus enum value

    # ── Configuration ─────────────────────────────────────────
    config = Column(JSON, nullable=False, default=dict)
    """Type-specific config (RestApiConfig, DatabaseConfig, etc.) serialized as JSON."""

    # ── Sync State ────────────────────────────────────────────
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    sync_count = Column(Integer, default=0)

    # ── Metadata ──────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    # ── Relationships ─────────────────────────────────────────
    field_mappings = relationship(
        "IntegrationFieldMappingModel",
        back_populates="integration",
        cascade="all, delete-orphan",
        order_by="IntegrationFieldMappingModel.target_field",
    )

    __table_args__ = (
        Index("ix_integrations_type", "integration_type"),
        Index("ix_integrations_status", "status"),
        Index("ix_integrations_category", "evidence_category"),
    )

    def __repr__(self) -> str:
        return f"<Integration {self.id} [{self.integration_type}:{self.status}] {self.name}>"


class IntegrationFieldMappingModel(Base):
    """Maps a source field to a RAVEN canonical evidence field.

    Each row is one field-level mapping within an integration.
    """
    __tablename__ = "integration_field_mappings"

    id = Column(String(32), primary_key=True, default=lambda: _generate_id("fmap_"))
    integration_id = Column(
        String(32),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_field = Column(String(256), nullable=False)
    """Field name or path in the source data (e.g., 'shipment.tracking_number')."""

    target_field = Column(String(256), nullable=False)
    """Canonical evidence content field (e.g., 'tracking_id')."""

    transform = Column(String(128), nullable=True)
    """Optional transform function name (e.g., 'parse_date', 'to_lowercase')."""

    is_required = Column(Boolean, default=False)
    """Whether this mapping is required for valid evidence."""

    default_value = Column(String(512), nullable=True)
    """Fallback value if source field is absent."""

    integration = relationship("IntegrationModel", back_populates="field_mappings")

    __table_args__ = (
        Index("ix_fmap_integration", "integration_id"),
    )

    def __repr__(self) -> str:
        return f"<FieldMapping {self.source_field} → {self.target_field}>"


# ═══════════════════════════════════════════════════════════════
#  SYSTEM SETTINGS
# ═══════════════════════════════════════════════════════════════

class SystemSettingModel(Base):
    """Key-value store for persistent system configuration.

    Each row holds one configuration namespace (e.g., 'guardrails').
    The value column stores structured JSON so settings can evolve
    without schema migrations.
    """
    __tablename__ = "system_settings"

    key = Column(String(128), primary_key=True)
    value = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    def __repr__(self) -> str:
        return f"<SystemSetting {self.key}>"
