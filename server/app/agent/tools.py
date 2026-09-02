"""
RAVEN Agent Tools — Narrow, validated, read-only evidence-gathering functions.

Each tool fetches evidence from a specific source, normalizes it to
the canonical Evidence model, and returns a serializable dict.

Tools are pure functions with no dependency on ADK's ToolContext — they
are registered as plain callables with the ADK Agent. Callbacks handle
cross-cutting concerns (budget, audit, evidence accumulation).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as tz
from pathlib import Path

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

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════


def _get_connector() -> SyntheticConnector:
    """Get the synthetic data connector."""
    cases_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "cases"
    return SyntheticConnector(cases_dir=cases_dir)


def _evidence_to_dict(ev: Evidence) -> dict:
    """Convert Evidence to a serializable dict for the agent."""
    return {
        "evidence_id": ev.evidence_id,
        "category": ev.category,
        "status": ev.status,
        "source_system": ev.source_system,
        "summary": ev.summary,
        "reliability": ev.reliability,
        "event_time": ev.event_time,
        "content": ev.content,
    }


def _make_missing_evidence(
    case_id: str, category: str, source_system: str,
) -> Evidence:
    """Create a MISSING evidence item for categories without connectors yet."""
    return Evidence(
        evidence_id=f"ev_{category}_{case_id[-5:]}",
        case_id=case_id,
        category=EvidenceCategory(category),
        status=EvidenceStatus.MISSING,
        source_system=source_system,
        source_record_id="",
        observed_at=datetime.now(tz.utc),
        summary=f"No {category} records available",
        relevance="unknown",
        reliability="unknown",
    )


# ═══════════════════════════════════════════════════════════════
#  EVIDENCE-GATHERING TOOLS
# ═══════════════════════════════════════════════════════════════


def get_transaction(case_id: str) -> dict:
    """Fetch payment and order data for a case.

    Returns payment amount, method, status, and order details
    including product description and amount.
    """
    connector = _get_connector()
    rzp_data = connector.get_razorpay_data(case_id)
    if not rzp_data:
        return {"error": f"No data found for {case_id}", "status": "not_found"}

    result = {"case_id": case_id, "evidence": []}

    payment = rzp_data.get("payment")
    if payment:
        ev = normalize_razorpay_payment(payment, case_id)
        result["evidence"].append(_evidence_to_dict(ev))

    order = rzp_data.get("order")
    if order:
        ev = normalize_razorpay_order(order, case_id)
        result["evidence"].append(_evidence_to_dict(ev))

    return result


def get_delivery_evidence(case_id: str) -> dict:
    """Fetch shipping and delivery evidence for a case.

    Returns shipping carrier, tracking number, delivery status,
    proof type (signature/photo), and recipient name if available.
    """
    connector = _get_connector()
    result = {"case_id": case_id, "evidence": []}

    shipping = connector.get_shipping(case_id)
    ev = normalize_shipping(shipping, case_id)
    result["evidence"].append(_evidence_to_dict(ev))

    delivery = connector.get_delivery(case_id)
    ev = normalize_delivery(delivery, case_id)
    result["evidence"].append(_evidence_to_dict(ev))

    return result


def get_authentication_events(case_id: str) -> dict:
    """Fetch authentication and device verification data.

    Returns OTP/3DS verification status, device recognition,
    and IP country.
    """
    connector = _get_connector()
    auth = connector.get_auth(case_id)
    ev = normalize_auth(auth, case_id)
    return {"case_id": case_id, "evidence": [_evidence_to_dict(ev)]}


def get_customer_communications(case_id: str) -> dict:
    """Fetch customer support communication records.

    Returns any emails, chat logs, or support tickets
    between the customer and merchant.
    """
    connector = _get_connector()
    comms = connector.get_communications(case_id)
    ev = normalize_communications(comms, case_id)
    return {"case_id": case_id, "evidence": [_evidence_to_dict(ev)]}


def get_refund_history(case_id: str) -> dict:
    """Fetch refund records for the payment.

    Returns any refunds issued, their amounts, and dates.
    """
    connector = _get_connector()
    rzp_data = connector.get_razorpay_data(case_id)
    payment_id = ""
    if rzp_data and rzp_data.get("payment"):
        payment_id = rzp_data["payment"].get("id", "")

    refund_data = connector.get_refunds(case_id)
    ev = normalize_razorpay_refunds(refund_data, case_id, payment_id)

    if ev:
        return {"case_id": case_id, "evidence": [_evidence_to_dict(ev)]}
    return {"case_id": case_id, "evidence": [], "note": "No refund records found"}


def get_device_session(case_id: str) -> dict:
    """Fetch device fingerprint and session data.

    Returns device type, browser, IP address, session history,
    and whether this device was previously used by the customer.
    """
    ev = _make_missing_evidence(case_id, "device", "merchant_analytics")
    return {"case_id": case_id, "evidence": [_evidence_to_dict(ev)]}


def get_service_logs(case_id: str) -> dict:
    """Fetch digital service access logs.

    Returns login timestamps, feature usage, downloads,
    or streaming activity — proving the customer used the service.
    """
    ev = _make_missing_evidence(case_id, "service", "merchant_platform")
    return {"case_id": case_id, "evidence": [_evidence_to_dict(ev)]}


def get_policy_terms(case_id: str) -> dict:
    """Fetch applicable return policy and terms of service.

    Returns the refund policy, return window, terms the customer
    agreed to at purchase, and cancellation policy.
    """
    ev = _make_missing_evidence(case_id, "policy", "merchant_legal")
    return {"case_id": case_id, "evidence": [_evidence_to_dict(ev)]}


def get_external_integrations(case_id: str) -> dict:
    """Fetch evidence ingested from active external integrations.

    Returns records from connected REST APIs, SQL databases,
    uploaded CSV/Excel/PDF files, and webhooks.
    """
    try:
        from app.db.database import SessionLocal
        from app.services.integration_service import IntegrationService
        with SessionLocal() as db:
            service = IntegrationService()
            items = service.fetch_all_active_evidence(case_id, db)
            return {
                "case_id": case_id,
                "evidence": [_evidence_to_dict(ev) for ev in items],
                "count": len(items),
            }
    except Exception as e:
        logger.debug(f"Failed to fetch external integrations for {case_id}: {e}")
        return {"case_id": case_id, "evidence": [], "note": f"No active integrations or error: {str(e)}"}


# ═══════════════════════════════════════════════════════════════
#  TOOL REGISTRY — Ordered list of all evidence-gathering tools
# ═══════════════════════════════════════════════════════════════


EVIDENCE_TOOLS: list = [
    get_transaction,
    get_delivery_evidence,
    get_authentication_events,
    get_customer_communications,
    get_refund_history,
    get_device_session,
    get_service_logs,
    get_policy_terms,
    get_external_integrations,
]
