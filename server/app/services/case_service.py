"""
Case Orchestration Service.

Manages the case lifecycle:
    webhook received -> case created -> investigation triggered ->
    evidence gathered -> assessed -> draft ready -> reviewed ->
    submitted/accepted -> outcome recorded

This service:
- Validates state transitions
- Calls the investigation runner
- Saves results to DB
- Creates audit log entries
- Routes to human review vs auto-submit
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.connectors.synthetic import SyntheticConnector
from app.core.types import (
    CaseNotFoundError,
    CaseStateTransitionError,
    CaseStatus,
    ReviewDecision,
    validate_transition,
)
from app.core.schemas import Assessment
from app.db.models import (
    AgentRunModel,
    AuditLogModel,
    CaseModel,
    ContradictionModel,
    EvidenceModel,
    TimelineEventModel,
)
from app.pipeline.runner import DeterministicRunner

logger = logging.getLogger(__name__)


class CaseService:
    """Orchestrates the full case lifecycle."""

    def __init__(self, connector: SyntheticConnector | None = None):
        self._connector = connector or SyntheticConnector()
        self._runner = DeterministicRunner(connector=self._connector)

    # ── Create ────────────────────────────────────────────────

    def create_from_webhook(
        self,
        dispute_id: str,
        payment_id: str,
        amount: int,
        currency: str,
        reason_code: str,
        reason_description: str,
        phase: str,
        respond_by: datetime,
        status: str,
        created_at: datetime,
        order_id: str | None = None,
        customer_id: str | None = None,
        db: Session | None = None,
    ) -> CaseModel:
        """Create a case from a Razorpay webhook event.

        Idempotent: if dispute_id already exists, returns existing case.
        """
        # Check for duplicate
        existing = db.query(CaseModel).filter_by(rzp_dispute_id=dispute_id).first()
        if existing:
            logger.info(f"Duplicate webhook for dispute {dispute_id}, returning existing case {existing.id}")
            return existing

        # Generate case ID
        count = db.query(func.count(CaseModel.id)).scalar() or 0
        case_id = f"CASE-{count + 1:05d}"

        case = CaseModel(
            id=case_id,
            status="created",
            dispute_reason=reason_description or reason_code,
            rzp_dispute_id=dispute_id,
            rzp_payment_id=payment_id,
            rzp_order_id=order_id,
            rzp_customer_id=customer_id,
            amount=amount,
            currency=currency,
            reason_code=reason_code,
            reason_description=reason_description,
            dispute_phase=phase,
            respond_by=respond_by,
            rzp_dispute_status=status,
            rzp_created_at=created_at,
        )
        db.add(case)

        # Audit log
        self._audit(db, case_id, "case_created", "system:webhook", {
            "dispute_id": dispute_id,
            "amount": amount,
            "reason_code": reason_code,
        })

        db.commit()
        db.refresh(case)
        logger.info(f"Created case {case_id} from dispute {dispute_id}")
        return case

    # ── Investigate ───────────────────────────────────────────

    def investigate(self, case_id: str, db: Session) -> dict:
        """Run investigation pipeline and save results to DB.

        Returns the investigation result dict.
        """
        case = self._get_case(case_id, db)

        # Validate state transition
        current = CaseStatus(case.status)
        if current not in (CaseStatus.CREATED, CaseStatus.INVESTIGATING, CaseStatus.EVIDENCE_GATHERED):
            # Allow re-investigation from early states
            if not validate_transition(current, CaseStatus.INVESTIGATING):
                raise CaseStateTransitionError(case.status, "investigating")

        # Update status
        case.status = "investigating"
        case.investigation_started_at = datetime.now(timezone.utc)
        self._audit(db, case_id, "investigation_started", "system:runner")
        db.commit()

        # Run investigation
        result = self._runner.investigate(case_id, db_session=db)

        if "error" in result:
            case.status = "created"  # Revert on error
            case.investigation_error = result["error"]
            self._audit(db, case_id, "investigation_failed", "system:runner", {
                "error": result["error"],
            })
            db.commit()
            return result

        # Save results
        self._save_results(case, result, db)

        return result

    def _save_results(self, case: CaseModel, result: dict, db: Session) -> None:
        """Persist investigation results to database."""
        case_id = case.id

        # Clear existing evidence (safe re-investigation)
        db.query(EvidenceModel).filter_by(case_id=case_id).delete()
        db.query(ContradictionModel).filter_by(case_id=case_id).delete()
        db.query(TimelineEventModel).filter_by(case_id=case_id).delete()

        # Save evidence
        for ev in result.get("evidence", []):
            db.add(EvidenceModel(
                id=ev.evidence_id,
                case_id=case_id,
                category=ev.category.value,
                status=ev.status.value,
                source_system=ev.source_system,
                source_record_id=ev.source_record_id,
                source_url=ev.source_url,
                event_time=ev.event_time,
                event_timezone=ev.event_timezone,
                event_time_utc=ev.event_time_utc,
                timezone_confident=ev.timezone_confident,
                observed_at=ev.observed_at,
                content=ev.content,
                summary=ev.summary,
                relevance=ev.relevance,
                reliability=ev.reliability,
            ))

        # Save contradictions
        for c in result.get("contradictions", []):
            db.add(ContradictionModel(
                id=c.contradiction_id,
                case_id=case_id,
                evidence_a_id=c.evidence_a_id,
                evidence_a_claim=c.evidence_a_claim,
                evidence_b_id=c.evidence_b_id,
                evidence_b_claim=c.evidence_b_claim,
                impact=c.impact,
                description=c.description,
                requires_human_review=c.requires_human_review,
                detected_at=c.detected_at,
            ))

        # Save timeline
        for tl in result.get("timeline", []):
            db.add(TimelineEventModel(
                id=tl.event_id,
                case_id=case_id,
                timestamp_utc=tl.timestamp_utc,
                timestamp_original=tl.timestamp_original,
                timezone_original=tl.timezone_original,
                timezone_confident=tl.timezone_confident,
                label=tl.label,
                description=tl.description,
                category=tl.category,
                source_evidence_id=tl.source_evidence_id,
                source_system=tl.source_system,
            ))

        # Save assessment
        assessment: Assessment | None = result.get("assessment")
        if assessment:
            case.case_strength = assessment.case_strength.value
            case.recommendation = assessment.recommendation.value
            case.confidence = assessment.confidence.value
            case.assessment_score = assessment.score
            case.assessment_data = {
                "methodology": assessment.score_methodology,
                "reasons": assessment.reasons,
                "checklist": [
                    {
                        "category": i.category,
                        "label": i.label,
                        "status": i.status,
                        "weight": i.weight,
                        "required": i.required,
                    }
                    for i in assessment.evidence_checklist
                ],
            }

        # Save response draft
        case.response_draft = result.get("response_draft")
        case.response_evidence_ids = [
            ev.evidence_id for ev in result.get("evidence", [])
            if ev.status.value == "available"
        ]

        # Update status based on assessment + guardrail-based auto-submission
        if assessment:
            if self._passes_auto_submit_guardrails(assessment, case, db):
                # All guardrail criteria met — auto-submit
                case.status = "submitted"
                case.review_decision = "auto_approved"
                case.reviewed_by = "system:guardrails"
                case.reviewed_at = datetime.now(timezone.utc)
                case.submitted_at = datetime.now(timezone.utc)
                self._audit(db, case_id, "auto_submitted", "system:guardrails", {
                    "score": assessment.score,
                    "recommendation": assessment.recommendation.value,
                    "reason": "All guardrail criteria met",
                })
            else:
                case.status = "under_review"
        else:
            case.status = "evidence_gathered"

        case.investigation_completed_at = datetime.now(timezone.utc)

        # Agent run record
        db.add(AgentRunModel(
            case_id=case_id,
            status="completed",
            tool_calls_count=len(result.get("evidence", [])),
            model_used="deterministic_v1",
        ))

        self._audit(db, case_id, "investigation_completed", "system:runner", {
            "evidence_count": len(result.get("evidence", [])),
            "contradiction_count": len(result.get("contradictions", [])),
            "score": assessment.score if assessment else None,
            "recommendation": assessment.recommendation.value if assessment else None,
            "status": case.status,
        })

        db.commit()

    # ── Guardrail-Based Auto-Submission ────────────────────────

    def _passes_auto_submit_guardrails(
        self,
        assessment: Assessment,
        case: CaseModel,
        db: Session,
    ) -> bool:
        """Check if a case qualifies for automatic submission based on guardrail settings.

        All of the following must be true:
        1. auto_contest_enabled is True
        2. Recommendation is 'contest'
        3. Assessment is auto_submit_eligible (no contradictions, no missing evidence)
        4. Confidence score >= min_confidence_threshold
        5. Dispute amount <= max_dispute_amount (or no cap)
        6. Dispute amount <= require_human_review_above (or threshold disabled)
        """
        from app.db.models import SystemSettingModel
        from app.api.settings_routes import DEFAULT_GUARDRAILS

        # Load guardrail config from DB, falling back to defaults
        row = db.query(SystemSettingModel).filter_by(key="guardrails").first()
        if row and row.value:
            guardrails = {**DEFAULT_GUARDRAILS, **row.value}
        else:
            guardrails = {**DEFAULT_GUARDRAILS}

        # 1. Auto-contest must be enabled
        if not guardrails.get("auto_contest_enabled", False):
            return False

        # 2. Recommendation must be contest
        if assessment.recommendation.value != "contest":
            return False

        # 3. Assessment must be auto-submit eligible
        if not assessment.auto_submit_eligible:
            return False

        # 4. Confidence score must meet threshold
        confidence_score = int(assessment.score * 100)
        min_threshold = guardrails.get("min_confidence_threshold", 80)
        if confidence_score < min_threshold:
            return False

        # 5. Dispute amount must be within max limit
        max_amount = guardrails.get("max_dispute_amount")
        if max_amount is not None and (case.amount or 0) > max_amount:
            return False

        # 6. Dispute amount must be below human review threshold
        review_above = guardrails.get("require_human_review_above")
        if review_above is not None and (case.amount or 0) > review_above:
            return False

        logger.info(
            "Case %s passes all guardrail criteria — auto-submitting "
            "(score=%d%%, amount=%s, recommendation=%s)",
            case.id, confidence_score, case.amount,
            assessment.recommendation.value,
        )
        return True

    # ── Review ────────────────────────────────────────────────

    def review(
        self,
        case_id: str,
        decision: str,
        notes: str,
        reviewed_by: str,
        db: Session,
    ) -> CaseModel:
        """Apply human review decision."""
        case = self._get_case(case_id, db)

        # Map decision to target status
        target_map = {
            "approve": CaseStatus.APPROVED,
            "reject": CaseStatus.REJECTED,
            "escalate": CaseStatus.ESCALATED,
        }
        target = target_map.get(decision)
        if not target:
            raise ValueError(f"Invalid review decision: {decision}")

        current = CaseStatus(case.status)
        if current != target and not validate_transition(current, target):
            raise CaseStateTransitionError(case.status, target.value)

        case.status = target.value
        case.review_decision = decision
        case.review_notes = notes
        case.reviewed_by = reviewed_by
        case.reviewed_at = datetime.now(timezone.utc)

        self._audit(db, case_id, f"review_{decision}", f"human:{reviewed_by}", {
            "decision": decision,
            "notes": notes,
        })

        db.commit()
        db.refresh(case)
        return case

    # ── Outcome ───────────────────────────────────────────────

    def update_outcome(
        self, case_id: str, outcome: str, db: Session
    ) -> CaseModel:
        """Update case with dispute outcome (won/lost)."""
        case = self._get_case(case_id, db)

        target = CaseStatus.WON if outcome == "won" else CaseStatus.LOST
        current = CaseStatus(case.status)

        if not validate_transition(current, target):
            raise CaseStateTransitionError(case.status, target.value)

        case.status = target.value
        case.outcome = outcome
        case.outcome_at = datetime.now(timezone.utc)

        self._audit(db, case_id, f"outcome_{outcome}", "system:webhook", {
            "outcome": outcome,
        })

        db.commit()
        db.refresh(case)
        return case

    # ── Metrics ───────────────────────────────────────────────

    def get_metrics(self, db: Session) -> dict:
        """Calculate dashboard metrics."""
        total = db.query(func.count(CaseModel.id)).scalar() or 0

        open_statuses = [
            "created", "investigating", "evidence_gathered",
            "assessed", "draft_ready", "under_review", "approved",
        ]
        open_cases = (
            db.query(func.count(CaseModel.id))
            .filter(CaseModel.status.in_(open_statuses))
            .scalar() or 0
        )

        pending = (
            db.query(func.count(CaseModel.id))
            .filter(CaseModel.status == "under_review")
            .scalar() or 0
        )

        won = db.query(func.count(CaseModel.id)).filter(CaseModel.outcome == "won").scalar() or 0
        lost = db.query(func.count(CaseModel.id)).filter(CaseModel.outcome == "lost").scalar() or 0

        submitted = (
            db.query(func.count(CaseModel.id))
            .filter(CaseModel.status.in_(["submitted", "won", "lost"]))
            .scalar() or 0
        )

        now = datetime.now(timezone.utc)
        urgent_cutoff = now + timedelta(hours=24)

        # Amount at risk (sum of open cases amount in paise)
        amount_at_risk_paise = (
            db.query(func.sum(CaseModel.amount))
            .filter(CaseModel.status.in_(open_statuses))
            .scalar() or 0
        )

        # Protected value (sum of won or submitted or approved cases)
        protected_value_paise = (
            db.query(func.sum(CaseModel.amount))
            .filter(CaseModel.status.in_(["submitted", "won", "approved"]))
            .scalar() or 0
        )

        # Urgent cases (< 24h deadline)
        urgent_count = (
            db.query(func.count(CaseModel.id))
            .filter(CaseModel.status.in_(open_statuses))
            .filter(CaseModel.respond_by <= urgent_cutoff)
            .scalar() or 0
        )

        avg_score = db.query(func.avg(CaseModel.assessment_score)).scalar() or 0.0

        # Status breakdown
        status_counts = (
            db.query(CaseModel.status, func.count(CaseModel.id))
            .group_by(CaseModel.status)
            .all()
        )

        # Recommendation breakdown
        rec_counts = (
            db.query(CaseModel.recommendation, func.count(CaseModel.id))
            .filter(CaseModel.recommendation.isnot(None))
            .group_by(CaseModel.recommendation)
            .all()
        )

        # Recovered revenue (sum of won cases in paise)
        recovered_revenue_paise = (
            db.query(func.sum(CaseModel.amount))
            .filter(CaseModel.outcome == "won")
            .scalar() or 0
        )

        # Arbitration fees saved (cases where merchant avoided losing arbitration penalties)
        rejected_count = (
            db.query(func.count(CaseModel.id))
            .filter(
                (CaseModel.review_decision == "reject") |
                (CaseModel.status == "rejected") |
                ((CaseModel.recommendation == "accept_loss") & (CaseModel.status == "approved"))
            )
            .scalar() or 0
        )
        fees_saved = float(rejected_count * 1500)  # ₹1,500 standard chargeback penalty per dispute saved

        # Win rate
        total_resolved = won + lost
        win_rate = round(won / total_resolved, 2) if total_resolved > 0 else 0.0

        return {
            "total_cases": total,
            "open_cases": open_cases,
            "pending_review": pending,
            "submitted": submitted,
            "won": won,
            "lost": lost,
            "amount_at_risk": round(amount_at_risk_paise / 100.0, 2),
            "protected_value": round(protected_value_paise / 100.0, 2),
            "recovered_revenue": round(recovered_revenue_paise / 100.0, 2),
            "fees_saved": fees_saved,
            "urgent_count": urgent_count,
            "win_rate": win_rate,
            "avg_score": round(float(avg_score), 2),
            "status_breakdown": {s: c for s, c in status_counts},
            "recommendation_breakdown": {r: c for r, c in rec_counts},
            "evaluation": {
                "synthetic_placeholder": True,
                "note": "These are placeholder values. Real evaluation requires golden case results.",
                "cases_evaluated": 0,
                "precision": 0.0,
                "recall": 0.0,
                "false_positive_rate": 0.0,
                "contest_count": 0,
                "accept_count": 0,
                "human_review_count": 0,
                "estimated_protected_value": 0,
                "cost_of_fp_saved": 0,
                "test_suite_passed": 0,
            },
        }

    # ── Helpers ───────────────────────────────────────────────

    def _get_case(self, case_id: str, db: Session) -> CaseModel:
        case = db.query(CaseModel).filter_by(id=case_id).first()
        if not case:
            raise CaseNotFoundError(f"Case {case_id} not found")
        return case

    def _audit(
        self,
        db: Session,
        case_id: str,
        action: str,
        actor: str = "system",
        details: dict | None = None,
    ) -> None:
        db.add(AuditLogModel(
            case_id=case_id,
            action=action,
            actor=actor,
            details=details or {},
        ))
