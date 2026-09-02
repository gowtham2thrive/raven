"""
RAVEN API Routes — All endpoints in one module.

Merged from: cases.py, webhooks.py, review.py, metrics.py, stream.py

Endpoints:
    GET    /cases                       — List with filters + pagination
    GET    /cases/:id                   — Full case detail
    POST   /cases/:id/investigate       — Trigger investigation
    GET    /cases/:id/evidence          — Evidence items
    GET    /cases/:id/timeline          — Timeline events
    GET    /cases/:id/assessment        — Assessment result
    GET    /cases/:id/response          — Response draft
    GET    /cases/:id/audit             — Audit trail
    POST   /cases/:id/review            — Human review decision
    POST   /cases/:id/submit            — Submit contest to Razorpay
    POST   /webhooks/razorpay           — Razorpay webhook receiver
    GET    /metrics/summary             — Dashboard stats
    GET    /metrics/breakdown           — Status/recommendation breakdown
    GET    /cases/:id/investigate/stream — SSE live investigation
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import asc, desc, func
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.api.deps import get_case_service, get_db, get_simulator_service
from app.core.types import CaseNotFoundError, CaseStateTransitionError
from app.db.models import (
    AuditLogModel,
    CaseModel,
    ContradictionModel,
    EvidenceModel,
    TimelineEventModel,
)
from app.services.case_service import CaseService
from app.services.simulator_service import SimulateCaseRequest, SimulatorService

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  ROUTERS
# ═══════════════════════════════════════════════════════════════

cases_router = APIRouter()
webhooks_router = APIRouter()
metrics_router = APIRouter()
models_router = APIRouter()
simulator_router = APIRouter()
stream_router = APIRouter(tags=["stream"])


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════


def _case_to_dict(case: CaseModel, contradiction_count: int = 0) -> dict:
    return {
        "case_id": case.id,
        "status": case.status,
        "dispute_reason": case.dispute_reason,
        "rzp_dispute_id": case.rzp_dispute_id,
        "rzp_payment_id": case.rzp_payment_id,
        "rzp_order_id": case.rzp_order_id,
        "amount": case.amount,
        "currency": case.currency,
        "reason_code": case.reason_code,
        "reason_description": case.reason_description,
        "dispute_phase": case.dispute_phase,
        "respond_by": case.respond_by.isoformat() if case.respond_by else None,
        "case_strength": case.case_strength,
        "recommendation": case.recommendation,
        "confidence": case.confidence,
        "assessment_score": case.assessment_score,
        "review_decision": case.review_decision,
        "reviewed_by": case.reviewed_by,
        "reviewed_at": case.reviewed_at.isoformat() if case.reviewed_at else None,
        "outcome": case.outcome,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        "contradiction_count": contradiction_count,
    }


def _evidence_to_dict(ev: EvidenceModel) -> dict:
    return {
        "evidence_id": ev.id,
        "category": ev.category,
        "status": ev.status,
        "source_system": ev.source_system,
        "source_record_id": ev.source_record_id,
        "event_time_utc": ev.event_time_utc.isoformat() if ev.event_time_utc else None,
        "timezone_confident": ev.timezone_confident,
        "content": ev.content,
        "summary": ev.summary,
        "relevance": ev.relevance,
        "reliability": ev.reliability,
    }


def _timeline_to_dict(tl: TimelineEventModel) -> dict:
    return {
        "event_id": tl.id,
        "timestamp_utc": tl.timestamp_utc.isoformat() if tl.timestamp_utc else None,
        "timezone_confident": tl.timezone_confident,
        "label": tl.label,
        "description": tl.description,
        "category": tl.category,
        "source_system": tl.source_system,
    }


def _contradiction_to_dict(c: ContradictionModel) -> dict:
    return {
        "contradiction_id": c.id,
        "evidence_a_id": c.evidence_a_id,
        "evidence_a_claim": c.evidence_a_claim,
        "evidence_b_id": c.evidence_b_id,
        "evidence_b_claim": c.evidence_b_claim,
        "impact": c.impact,
        "description": c.description,
        "requires_human_review": c.requires_human_review,
    }


def _audit_to_dict(a: AuditLogModel) -> dict:
    return {
        "id": a.id,
        "timestamp": a.timestamp.isoformat() if a.timestamp else None,
        "action": a.action,
        "actor": a.actor,
        "details": a.details,
    }


# ═══════════════════════════════════════════════════════════════
#  CASES ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@cases_router.get("")
@cases_router.get("/")
async def list_cases(
    status: str | None = None,
    recommendation: str | None = None,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List cases with optional filters and pagination."""
    query = db.query(CaseModel)

    if status:
        query = query.filter(CaseModel.status == status)
    if recommendation:
        query = query.filter(CaseModel.recommendation == recommendation)

    sort_column = getattr(CaseModel, sort_by, CaseModel.created_at)
    if sort_dir == "asc":
        query = query.order_by(asc(sort_column))
    else:
        query = query.order_by(desc(sort_column))

    total = query.count()
    cases = query.offset((page - 1) * per_page).limit(per_page).all()

    # Batch-load contradiction counts to avoid N+1 queries
    case_ids = [c.id for c in cases]
    contradiction_counts: dict[str, int] = {}
    if case_ids:
        counts = (
            db.query(ContradictionModel.case_id, func.count(ContradictionModel.id))
            .filter(ContradictionModel.case_id.in_(case_ids))
            .group_by(ContradictionModel.case_id)
            .all()
        )
        contradiction_counts = {cid: cnt for cid, cnt in counts}

    return {
        "cases": [
            _case_to_dict(c, contradiction_count=contradiction_counts.get(c.id, 0))
            for c in cases
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@cases_router.get("/{case_id}")
async def get_case(case_id: str, db: Session = Depends(get_db)):
    """Get full case details with all relationships."""
    case = db.query(CaseModel).filter_by(id=case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    evidence = db.query(EvidenceModel).filter_by(case_id=case_id).all()
    timeline = (
        db.query(TimelineEventModel)
        .filter_by(case_id=case_id)
        .order_by(TimelineEventModel.timestamp_utc)
        .all()
    )
    contradictions = db.query(ContradictionModel).filter_by(case_id=case_id).all()
    audit = (
        db.query(AuditLogModel)
        .filter_by(case_id=case_id)
        .order_by(AuditLogModel.timestamp)
        .all()
    )

    return {
        "case": _case_to_dict(case),
        "evidence": [_evidence_to_dict(e) for e in evidence],
        "timeline": [_timeline_to_dict(t) for t in timeline],
        "contradictions": [_contradiction_to_dict(c) for c in contradictions],
        "assessment": {
            "score": case.assessment_score,
            "strength": case.case_strength,
            "recommendation": case.recommendation,
            "confidence": case.confidence,
            "data": case.assessment_data,
        } if case.assessment_score is not None else None,
        "response_draft": case.response_draft,
        "audit": [_audit_to_dict(a) for a in audit],
    }


@cases_router.post("/batch-investigate")
async def batch_investigate(
    db: Session = Depends(get_db),
    service: CaseService = Depends(get_case_service),
):
    """Auto-investigate all pending (created) cases in batch without manual clicking."""
    cases = db.query(CaseModel).filter_by(status="created").all()
    results = []
    for c in cases:
        try:
            res = service.investigate(c.id, db)
            assessment = res.get("assessment")
            results.append({
                "case_id": c.id,
                "status": "success",
                "score": assessment.score if assessment else None,
                "recommendation": assessment.recommendation.value if assessment else None,
                "auto_submit_eligible": assessment.auto_submit_eligible if assessment else False,
            })
        except Exception as e:
            results.append({"case_id": c.id, "status": "error", "message": str(e)})

    return {
        "processed_count": len(results),
        "successful_count": sum(1 for r in results if r["status"] == "success"),
        "results": results,
    }


@cases_router.post("/batch-submit")
async def batch_submit(
    db: Session = Depends(get_db),
    service: CaseService = Depends(get_case_service),
):
    """Auto-submit all approved/auto-submit eligible cases to Razorpay in 1-click."""
    cases = db.query(CaseModel).filter_by(status="approved").all()
    results = []
    for c in cases:
        try:
            c.status = "submitted"
            c.submitted_at = datetime.now(timezone.utc)
            db.add(AuditLogModel(
                case_id=c.id,
                action="submitted_to_razorpay",
                actor="system:batch_submit",
                details={"dispute_id": c.rzp_dispute_id, "batch": True},
            ))
            results.append({"case_id": c.id, "status": "submitted"})
        except Exception as e:
            results.append({"case_id": c.id, "status": "error", "message": str(e)})

    db.commit()
    return {
        "submitted_count": len(results),
        "results": results,
    }


@cases_router.delete("")
@cases_router.delete("/")
@cases_router.post("/clear")
async def clear_all_cases(
    db: Session = Depends(get_db),
    simulator: SimulatorService = Depends(get_simulator_service),
):
    """Purge all cases and related records from database."""
    count = simulator.clear_all_cases(db)
    return {
        "status": "success",
        "deleted_count": count,
        "message": f"Successfully purged {count} cases from database.",
    }


@cases_router.post("/{case_id}/investigate")
async def investigate_case(
    case_id: str,
    model: str | None = Query(None, description="LLM model override"),
    db: Session = Depends(get_db),
    service: CaseService = Depends(get_case_service),
):
    """Trigger investigation for a case."""
    try:
        result = service.investigate(case_id, db)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    except CaseStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    assessment = result.get("assessment")
    return {
        "case_id": case_id,
        "status": "investigated",
        "evidence_count": len(result.get("evidence", [])),
        "contradiction_count": len(result.get("contradictions", [])),
        "timeline_event_count": len(result.get("timeline", [])),
        "score": assessment.score if assessment else None,
        "recommendation": assessment.recommendation.value if assessment else None,
        "auto_submit_eligible": assessment.auto_submit_eligible if assessment else False,
    }


@cases_router.get("/{case_id}/evidence")
async def get_evidence(case_id: str, db: Session = Depends(get_db)):
    """Get all gathered evidence for a case."""
    case = db.query(CaseModel).filter_by(id=case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    evidence = db.query(EvidenceModel).filter_by(case_id=case_id).all()
    return {"evidence": [_evidence_to_dict(e) for e in evidence]}


@cases_router.get("/{case_id}/timeline")
async def get_timeline(case_id: str, db: Session = Depends(get_db)):
    """Get reconstructed timeline for a case."""
    case = db.query(CaseModel).filter_by(id=case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    timeline = (
        db.query(TimelineEventModel)
        .filter_by(case_id=case_id)
        .order_by(TimelineEventModel.timestamp_utc)
        .all()
    )
    return {"timeline": [_timeline_to_dict(t) for t in timeline]}


@cases_router.get("/{case_id}/assessment")
async def get_assessment(case_id: str, db: Session = Depends(get_db)):
    """Get case assessment."""
    case = db.query(CaseModel).filter_by(id=case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    if case.assessment_score is None:
        return {"assessment": None, "message": "Case not yet assessed"}
    return {
        "assessment": {
            "score": case.assessment_score,
            "strength": case.case_strength,
            "recommendation": case.recommendation,
            "confidence": case.confidence,
            "auto_submit_eligible": case.status == "approved" and case.recommendation == "contest",
            "data": case.assessment_data,
        }
    }


@cases_router.get("/{case_id}/response")
async def get_response(case_id: str, db: Session = Depends(get_db)):
    """Get draft response for a case."""
    case = db.query(CaseModel).filter_by(id=case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return {"response_draft": case.response_draft, "evidence_ids": case.response_evidence_ids}


@cases_router.get("/{case_id}/audit")
async def get_audit(case_id: str, db: Session = Depends(get_db)):
    """Get full audit trail for a case."""
    case = db.query(CaseModel).filter_by(id=case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    audit = (
        db.query(AuditLogModel)
        .filter_by(case_id=case_id)
        .order_by(AuditLogModel.timestamp)
        .all()
    )
    return {"audit": [_audit_to_dict(a) for a in audit]}


# ═══════════════════════════════════════════════════════════════
#  REVIEW ENDPOINTS
# ═══════════════════════════════════════════════════════════════


class ReviewRequest(BaseModel):
    decision: str
    notes: str = ""
    reviewed_by: str = "analyst@raven.dev"


class SubmitRequest(BaseModel):
    confirmed: bool = True


@cases_router.post("/{case_id}/review")
async def review_case(
    case_id: str,
    review: ReviewRequest,
    db: Session = Depends(get_db),
    service: CaseService = Depends(get_case_service),
):
    """Apply human review decision."""
    if review.decision not in ("approve", "reject", "escalate"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid decision: {review.decision}. Must be: approve, reject, escalate",
        )
    try:
        case = service.review(
            case_id=case_id,
            decision=review.decision,
            notes=review.notes,
            reviewed_by=review.reviewed_by,
            db=db,
        )
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    except CaseStateTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "case_id": case.id,
        "status": case.status,
        "decision": review.decision,
        "reviewed_by": review.reviewed_by,
    }


@cases_router.post("/{case_id}/submit")
async def submit_to_razorpay(
    case_id: str,
    request: SubmitRequest,
    db: Session = Depends(get_db),
    service: CaseService = Depends(get_case_service),
):
    """Submit case contest to Razorpay. Level 4 action."""
    case = db.query(CaseModel).filter_by(id=case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    if case.status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit case in status '{case.status}'. Must be 'approved'.",
        )
    if not request.confirmed:
        raise HTTPException(status_code=400, detail="Submission not confirmed")

    case.status = "submitted"
    case.submitted_at = datetime.now(timezone.utc)

    db.add(AuditLogModel(
        case_id=case_id,
        action="submitted_to_razorpay",
        actor="system:submit",
        details={
            "dispute_id": case.rzp_dispute_id,
            "simulated": True,
        },
    ))
    db.commit()

    return {
        "case_id": case.id,
        "status": "submitted",
        "dispute_id": case.rzp_dispute_id,
        "submitted_at": case.submitted_at.isoformat(),
        "note": "MVP: Submission simulated. In production, this contests via Razorpay Disputes API.",
    }


# ═══════════════════════════════════════════════════════════════
#  WEBHOOK ENDPOINT
# ═══════════════════════════════════════════════════════════════


@webhooks_router.post("/razorpay", status_code=200)
async def receive_webhook(
    request: Request,
    db: Session = Depends(get_db),
    service: CaseService = Depends(get_case_service),
):
    """Receive a Razorpay dispute webhook event."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = body.get("event", "")
    payload = body.get("payload", {})
    dispute_entity = (
        payload.get("dispute", {}).get("entity", {})
        if isinstance(payload.get("dispute"), dict)
        else {}
    )

    if not dispute_entity:
        return {"status": "ignored", "reason": "no dispute entity"}

    dispute_id = dispute_entity.get("id", "")
    payment_id = dispute_entity.get("payment_id", "")
    amount = dispute_entity.get("amount", 0)
    currency = dispute_entity.get("currency", "INR")
    reason_code = dispute_entity.get("reason_code", "")
    reason_description = dispute_entity.get("reason_description", "")
    phase = dispute_entity.get("phase", "chargeback")
    status = dispute_entity.get("status", "open")
    respond_by = dispute_entity.get("respond_by_date")
    created_at_epoch = dispute_entity.get("created_at")

    if respond_by:
        if isinstance(respond_by, (int, float)):
            respond_by = datetime.fromtimestamp(respond_by, tz=timezone.utc)
        elif isinstance(respond_by, str):
            respond_by = datetime.fromisoformat(respond_by.replace("Z", "+00:00"))
    else:
        respond_by = datetime.now(timezone.utc)

    if created_at_epoch:
        if isinstance(created_at_epoch, (int, float)):
            created_at = datetime.fromtimestamp(created_at_epoch, tz=timezone.utc)
        else:
            created_at = datetime.now(timezone.utc)
    else:
        created_at = datetime.now(timezone.utc)

    if event in ("payment.dispute.created", "payment.dispute.action_required"):
        case = service.create_from_webhook(
            dispute_id=dispute_id,
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            reason_code=reason_code,
            reason_description=reason_description,
            phase=phase,
            respond_by=respond_by,
            status=status,
            created_at=created_at,
            db=db,
        )
        try:
            service.investigate(case.id, db)
        except Exception as e:
            logger.error(f"Investigation failed for {case.id}: {e}")
        return {"status": "processed", "event": event, "case_id": case.id}

    elif event == "payment.dispute.won":
        try:
            case = db.query(CaseModel).filter_by(rzp_dispute_id=dispute_id).first()
            if case:
                service.update_outcome(case.id, "won", db)
                return {"status": "processed", "event": event, "case_id": case.id}
        except Exception as e:
            logger.error(f"Failed to update outcome for {dispute_id}: {e}")
        return {"status": "skipped", "reason": "case not found"}

    elif event == "payment.dispute.lost":
        try:
            case = db.query(CaseModel).filter_by(rzp_dispute_id=dispute_id).first()
            if case:
                service.update_outcome(case.id, "lost", db)
                return {"status": "processed", "event": event, "case_id": case.id}
        except Exception as e:
            logger.error(f"Failed to update outcome for {dispute_id}: {e}")
        return {"status": "skipped", "reason": "case not found"}

    else:
        return {"status": "ignored", "event": event}


# ═══════════════════════════════════════════════════════════════
#  METRICS ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@metrics_router.get("/summary")
async def get_summary(
    db: Session = Depends(get_db),
    service: CaseService = Depends(get_case_service),
):
    """Dashboard stat card values."""
    return service.get_metrics(db)


@metrics_router.get("/breakdown")
async def get_breakdown(
    db: Session = Depends(get_db),
    service: CaseService = Depends(get_case_service),
):
    """Dispute breakdown by status and recommendation."""
    metrics = service.get_metrics(db)
    return {
        "status_breakdown": metrics.get("status_breakdown", {}),
        "recommendation_breakdown": metrics.get("recommendation_breakdown", {}),
    }


# ═══════════════════════════════════════════════════════════════
#  MODELS CATALOG ENDPOINT
# ═══════════════════════════════════════════════════════════════

models_router = APIRouter()


@models_router.get("")
@models_router.get("/")
async def get_models():
    """List available LLM models for investigation fetched live from Google API."""
    from app.config import settings
    from app.services.model_service import get_dynamic_available_models
    return {
        "models": get_dynamic_available_models(),
        "default": settings.agent_model,
        "llm_configured": bool(settings.gemini_api_key),
    }


# ═══════════════════════════════════════════════════════════════
#  SIMULATOR ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@simulator_router.get("/presets")
@simulator_router.get("/presets/")
async def list_simulation_presets(
    simulator: SimulatorService = Depends(get_simulator_service),
):
    """List available dispute simulation presets."""
    return {"presets": simulator.get_presets()}


@simulator_router.post("/generate")
@simulator_router.post("/generate/")
async def generate_simulated_case(
    request: SimulateCaseRequest,
    db: Session = Depends(get_db),
    case_service: CaseService = Depends(get_case_service),
    simulator: SimulatorService = Depends(get_simulator_service),
):
    """Simulate a new realistic dispute case."""
    return simulator.generate_case(
        request=request,
        db=db,
        case_service=case_service,
    )


@simulator_router.post("/clear")
@simulator_router.post("/clear/")
async def clear_simulated_cases(
    db: Session = Depends(get_db),
    simulator: SimulatorService = Depends(get_simulator_service),
):
    """Purge all cases and related records from database."""
    count = simulator.clear_all_cases(db)
    return {
        "status": "success",
        "deleted_count": count,
        "message": f"Successfully purged {count} cases from database.",
    }



# ═══════════════════════════════════════════════════════════════
#  SSE STREAMING ENDPOINT
# ═══════════════════════════════════════════════════════════════


@stream_router.get("/cases/{case_id}/investigate/stream")
async def stream_investigation(
    case_id: str,
    model: str | None = Query(None, description="LLM model override for investigation"),
    db: Session = Depends(get_db),
    service: CaseService = Depends(get_case_service),
):
    """Stream live investigation events as SSE."""
    from app.agent.agent import InvestigationAgent

    # Load dispute context from DB so the agent sees the actual claim
    case = db.query(CaseModel).filter_by(id=case_id).first()
    dispute: dict | None = None
    if case:
        dispute = {
            "id": case.rzp_dispute_id,
            "payment_id": case.rzp_payment_id,
            "amount": case.amount,
            "reason_code": case.reason_code,
            "reason_description": case.reason_description or "",
            "phase": case.dispute_phase,
        }

    agent = InvestigationAgent()

    async def event_generator():
        try:
            async for event in agent.investigate_streaming(case_id, dispute, model=model):
                data = json.dumps(event.data, default=str)
                yield f"event: {event.type.value}\ndata: {data}\n\n"

            # Persist results via the DI-provided service (runs the deterministic
            # pipeline once to save to DB). This is a single run, not a duplicate.
            try:
                service.investigate(case_id, db)
            except Exception as save_err:
                logger.debug(f"DB sync after stream for {case_id}: {save_err}")
        except Exception as e:
            error_data = json.dumps({"message": str(e)})
            yield f"event: error\ndata: {error_data}\n\n"
            yield f"event: done\ndata: {json.dumps({'case_id': case_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
