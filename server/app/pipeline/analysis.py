"""
Evidence Analysis — All analytical operations on canonical evidence.

Contains:
- Completeness: Weighted evidence checklist per dispute type
- Contradiction Detection: 8 rules (5 original + 3 from causal)
- Timeline Construction: Chronological event reconstruction
- Multi-Source Triangulation: Cross-source delivery verification

All functions operate on `list[Evidence]` — pure analysis, no I/O.
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.types import (
    EvidenceCategory,
    EvidenceRelevance,
    EvidenceStatus,
    RELEVANCE_WEIGHTS,
)
from app.core.schemas import (
    Contradiction,
    Evidence,
    EvidenceCheckItem,
    TimelineEvent,
)


# ═══════════════════════════════════════════════════════════════
#  COMPLETENESS CHECK
# ═══════════════════════════════════════════════════════════════


PRODUCT_NOT_RECEIVED_REQUIREMENTS: list[EvidenceCheckItem] = [
    EvidenceCheckItem(
        category="payment", label="Payment confirmation",
        required=True, status="missing", weight=0.15,
    ),
    EvidenceCheckItem(
        category="order", label="Order details",
        required=True, status="missing", weight=0.10,
    ),
    EvidenceCheckItem(
        category="shipping", label="Shipping dispatched",
        required=True, status="missing", weight=0.15,
    ),
    EvidenceCheckItem(
        category="delivery", label="Delivery confirmation",
        required=True, status="missing", weight=0.30,
    ),
    EvidenceCheckItem(
        category="authentication", label="Authentication (OTP/3DS)",
        required=False, status="missing", weight=0.15,
    ),
    EvidenceCheckItem(
        category="communication", label="Customer communication",
        required=False, status="missing", weight=0.10,
    ),
    EvidenceCheckItem(
        category="refund", label="Refund history",
        required=False, status="missing", weight=0.05,
    ),
]

UNAUTHORIZED_TRANSACTION_REQUIREMENTS: list[EvidenceCheckItem] = [
    EvidenceCheckItem(
        category="authentication", label="Authentication (3DS/OTP/Device)",
        required=True, status="missing", weight=0.40,
    ),
    EvidenceCheckItem(
        category="payment", label="Payment confirmation",
        required=True, status="missing", weight=0.25,
    ),
    EvidenceCheckItem(
        category="order", label="Order details",
        required=True, status="missing", weight=0.15,
    ),
    EvidenceCheckItem(
        category="communication", label="Customer communication",
        required=False, status="missing", weight=0.10,
    ),
    EvidenceCheckItem(
        category="refund", label="Refund history",
        required=False, status="missing", weight=0.10,
    ),
]

SERVICE_NOT_RENDERED_REQUIREMENTS: list[EvidenceCheckItem] = [
    EvidenceCheckItem(
        category="communication", label="Customer communication / Usage logs",
        required=True, status="missing", weight=0.35,
    ),
    EvidenceCheckItem(
        category="authentication", label="Authentication / Access verification",
        required=True, status="missing", weight=0.25,
    ),
    EvidenceCheckItem(
        category="payment", label="Payment confirmation",
        required=True, status="missing", weight=0.20,
    ),
    EvidenceCheckItem(
        category="order", label="Order details",
        required=True, status="missing", weight=0.10,
    ),
    EvidenceCheckItem(
        category="refund", label="Refund history",
        required=False, status="missing", weight=0.10,
    ),
]

DUPLICATE_TRANSACTION_REQUIREMENTS: list[EvidenceCheckItem] = [
    EvidenceCheckItem(
        category="refund", label="Refund confirmation / Credit proof",
        required=True, status="missing", weight=0.40,
    ),
    EvidenceCheckItem(
        category="payment", label="Payment confirmation",
        required=True, status="missing", weight=0.25,
    ),
    EvidenceCheckItem(
        category="order", label="Order details",
        required=True, status="missing", weight=0.20,
    ),
    EvidenceCheckItem(
        category="communication", label="Customer communication",
        required=False, status="missing", weight=0.15,
    ),
]

PRODUCT_NOT_AS_DESCRIBED_REQUIREMENTS: list[EvidenceCheckItem] = [
    EvidenceCheckItem(
        category="communication", label="Customer communication / Warranty chat",
        required=True, status="missing", weight=0.30,
    ),
    EvidenceCheckItem(
        category="delivery", label="Delivery confirmation",
        required=True, status="missing", weight=0.25,
    ),
    EvidenceCheckItem(
        category="order", label="Order details / Product description",
        required=True, status="missing", weight=0.15,
    ),
    EvidenceCheckItem(
        category="payment", label="Payment confirmation",
        required=True, status="missing", weight=0.15,
    ),
    EvidenceCheckItem(
        category="shipping", label="Shipping dispatched",
        required=False, status="missing", weight=0.10,
    ),
    EvidenceCheckItem(
        category="refund", label="Refund history",
        required=False, status="missing", weight=0.05,
    ),
]

GENERAL_REQUIREMENTS: list[EvidenceCheckItem] = [
    EvidenceCheckItem(
        category="payment", label="Payment confirmation",
        required=True, status="missing", weight=0.30,
    ),
    EvidenceCheckItem(
        category="order", label="Order details",
        required=True, status="missing", weight=0.25,
    ),
    EvidenceCheckItem(
        category="authentication", label="Authentication (OTP/3DS)",
        required=False, status="missing", weight=0.25,
    ),
    EvidenceCheckItem(
        category="communication", label="Customer communication",
        required=False, status="missing", weight=0.20,
    ),
]

REQUIREMENTS_BY_TYPE: dict[str, list[EvidenceCheckItem]] = {
    "product_not_received": PRODUCT_NOT_RECEIVED_REQUIREMENTS,
    "unauthorized_transaction": UNAUTHORIZED_TRANSACTION_REQUIREMENTS,
    "service_not_rendered": SERVICE_NOT_RENDERED_REQUIREMENTS,
    "duplicate_transaction": DUPLICATE_TRANSACTION_REQUIREMENTS,
    "product_not_as_described": PRODUCT_NOT_AS_DESCRIBED_REQUIREMENTS,
    "general": GENERAL_REQUIREMENTS,
}


def check_completeness(
    evidence_items: list[Evidence],
    dispute_type: str = "product_not_received",
    evidence_relevance: dict[str, str] | None = None,
) -> tuple[list[EvidenceCheckItem], list[str]]:
    """Check which required evidence is present, missing, or conflicting.

    If evidence_relevance is provided (from the ADK agent's claim analysis),
    uses dynamic weights based on relevance classification. Otherwise falls
    back to fixed requirements by dispute_type.

    Returns:
        (checklist, missing_labels)
    """
    if evidence_relevance is not None:
        return build_dynamic_checklist(evidence_items, evidence_relevance)

    # Existing behavior — fixed weight table fallback
    template = REQUIREMENTS_BY_TYPE.get(
        dispute_type, PRODUCT_NOT_RECEIVED_REQUIREMENTS
    )
    checklist = deepcopy(template)

    # Build lookup — prefer AVAILABLE over others
    evidence_by_category: dict[str, Evidence] = {}
    for ev in evidence_items:
        cat = ev.category.value
        existing = evidence_by_category.get(cat)
        if existing is None or (
            ev.status == EvidenceStatus.AVAILABLE
            and existing.status != EvidenceStatus.AVAILABLE
        ):
            evidence_by_category[cat] = ev

    missing_labels: list[str] = []

    for item in checklist:
        ev = evidence_by_category.get(item.category)

        if ev is None:
            item.status = "missing"
            if item.required:
                missing_labels.append(item.label)
            continue

        if ev.status == EvidenceStatus.AVAILABLE:
            item.status = "available"
            item.evidence_id = ev.evidence_id
        elif ev.status == EvidenceStatus.CONFLICTING:
            item.status = "conflicting"
            item.evidence_id = ev.evidence_id
        elif ev.status == EvidenceStatus.UNVERIFIED:
            item.status = "unverified"
            item.evidence_id = ev.evidence_id
        elif ev.status == EvidenceStatus.MISSING:
            item.status = "missing"
            if item.required:
                missing_labels.append(item.label)
        elif ev.status == EvidenceStatus.NOT_APPLICABLE:
            item.status = "not_applicable"
            item.notes = "Not applicable for this case"
        elif ev.status == EvidenceStatus.INGESTION_ERROR:
            item.status = "missing"
            item.notes = "Data ingestion failed — source returned invalid data"
            if item.required:
                missing_labels.append(item.label)
        else:
            item.status = "missing"
            if item.required:
                missing_labels.append(item.label)

    return checklist, missing_labels


# ── Dynamic Checklist Builder ─────────────────────────────────


def build_dynamic_checklist(
    evidence_items: list[Evidence],
    evidence_relevance: dict[str, str] | None = None,
) -> tuple[list[EvidenceCheckItem], list[str]]:
    """Build evidence checklist with weights from agent's claim analysis.

    If evidence_relevance is None (agent unavailable), falls back to
    equal weights for all gathered evidence — conservative but safe.

    Args:
        evidence_items: All gathered canonical evidence.
        evidence_relevance: Map of category → relevance level from agent.
            If None, all evidence gets equal weight.

    Returns:
        (checklist, missing_required_labels)
    """
    if evidence_relevance is None:
        return _build_equal_weight_checklist(evidence_items)

    return _build_relevance_weighted_checklist(evidence_items, evidence_relevance)


def _build_equal_weight_checklist(
    evidence_items: list[Evidence],
) -> tuple[list[EvidenceCheckItem], list[str]]:
    """Fallback: all evidence gets equal weight."""
    checklist: list[EvidenceCheckItem] = []
    missing: list[str] = []

    equal_weight = 1.0 / max(len(set(e.category.value for e in evidence_items)), 1)

    seen_categories: set[str] = set()
    for ev in evidence_items:
        cat = ev.category.value
        if cat in seen_categories:
            continue
        seen_categories.add(cat)

        item = EvidenceCheckItem(
            category=cat,
            label=cat.replace("_", " ").title(),
            required=False,
            status=_map_evidence_status(ev),
            evidence_id=ev.evidence_id if ev.status == EvidenceStatus.AVAILABLE else None,
            weight=equal_weight,
        )
        checklist.append(item)
        if ev.status in (EvidenceStatus.MISSING, EvidenceStatus.INGESTION_ERROR):
            missing.append(item.label)

    return checklist, missing


def _build_relevance_weighted_checklist(
    evidence_items: list[Evidence],
    evidence_relevance: dict[str, str],
) -> tuple[list[EvidenceCheckItem], list[str]]:
    """Build checklist with agent-determined relevance weights."""
    checklist: list[EvidenceCheckItem] = []
    missing: list[str] = []

    # Deduplicate — keep best status per category
    evidence_by_category: dict[str, Evidence] = {}
    for ev in evidence_items:
        cat = ev.category.value
        existing = evidence_by_category.get(cat)
        if existing is None or (
            ev.status == EvidenceStatus.AVAILABLE
            and existing.status != EvidenceStatus.AVAILABLE
        ):
            evidence_by_category[cat] = ev

    for cat, ev in evidence_by_category.items():
        relevance_str = evidence_relevance.get(cat, "supporting")
        try:
            relevance = EvidenceRelevance(relevance_str)
        except ValueError:
            relevance = EvidenceRelevance.SUPPORTING

        weight = RELEVANCE_WEIGHTS.get(relevance, 0.15)
        is_critical = relevance == EvidenceRelevance.CRITICAL

        if relevance == EvidenceRelevance.IRRELEVANT:
            status = "not_applicable"
            evidence_id = None
        else:
            status = _map_evidence_status(ev)
            evidence_id = ev.evidence_id if status == "available" else None

        item = EvidenceCheckItem(
            category=cat,
            label=cat.replace("_", " ").title(),
            required=is_critical,
            status=status,
            evidence_id=evidence_id,
            weight=weight,
        )
        checklist.append(item)

        if is_critical and status in ("missing", "ingestion_error"):
            missing.append(item.label)

    return checklist, missing


def _map_evidence_status(ev: Evidence) -> str:
    """Map Evidence status to checklist status string."""
    if ev.status == EvidenceStatus.AVAILABLE:
        return "available"
    if ev.status == EvidenceStatus.CONFLICTING:
        return "conflicting"
    if ev.status == EvidenceStatus.UNVERIFIED:
        return "unverified"
    if ev.status == EvidenceStatus.NOT_APPLICABLE:
        return "not_applicable"
    if ev.status == EvidenceStatus.INGESTION_ERROR:
        return "missing"
    return "missing"



# ═══════════════════════════════════════════════════════════════
#  CONTRADICTION DETECTION — 8 Rules
# ═══════════════════════════════════════════════════════════════
#
# Rules 1-5: Original contradiction rules
# Rules 6-8: Merged from causal.py (physically impossible timelines)


def detect_contradictions(
    evidence_items: list[Evidence],
    dispute_created_at: datetime | None = None,
    dispute_reason: str = "",
) -> list[Contradiction]:
    """Run all contradiction detection rules against gathered evidence."""
    contradictions: list[Contradiction] = []

    by_category: dict[str, list[Evidence]] = {}
    for ev in evidence_items:
        by_category.setdefault(ev.category.value, []).append(ev)

    # Original rules
    contradictions.extend(_check_delivery_vs_shipping(by_category))
    contradictions.extend(_check_customer_vs_support(by_category))
    contradictions.extend(_check_delivery_after_dispute(evidence_items, dispute_created_at))
    contradictions.extend(_check_refund_exists(by_category, dispute_reason=dispute_reason))
    contradictions.extend(_check_timeline_anomaly(by_category))

    # Causal checks (shipping<order, delivery<shipping, refund<payment) are
    # handled by validate_causal_order() which the runner calls separately.
    # They are not duplicated here to avoid double-counting.

    return contradictions


def _make_contra_id() -> str:
    return f"contra_{uuid.uuid4().hex[:10]}"


def _get_timed_evidence(by_category: dict[str, list[Evidence]], category: str) -> Evidence | None:
    """Get first evidence item with a valid UTC timestamp for causal checks."""
    for ev in by_category.get(category, []):
        if ev.event_time_utc is not None and ev.status.value not in (
            "missing", "not_applicable", "ingestion_error"
        ):
            return ev
    return None


# ── Rule 1: Delivery vs Shipping Status ──────────────────────

def _check_delivery_vs_shipping(
    by_category: dict[str, list[Evidence]],
) -> list[Contradiction]:
    """Merchant says 'delivered' but carrier says 'returned_to_sender'."""
    results: list[Contradiction] = []

    for delivery in by_category.get("delivery", []):
        if delivery.status.value in ("missing", "not_applicable"):
            continue
        for shipping in by_category.get("shipping", []):
            if shipping.status.value in ("missing", "not_applicable"):
                continue
            ship_status = shipping.content.get("status", "").lower()
            if ship_status in {"returned_to_sender", "returned", "lost", "rts"}:
                results.append(Contradiction(
                    contradiction_id=_make_contra_id(),
                    case_id=delivery.case_id,
                    evidence_a_id=delivery.evidence_id,
                    evidence_a_claim=f"Delivery confirmed: {delivery.summary}",
                    evidence_b_id=shipping.evidence_id,
                    evidence_b_claim=f"Carrier status: {ship_status}",
                    impact="high",
                    description=(
                        f"Merchant delivery records show the package was delivered, "
                        f"but the carrier tracking status is '{ship_status}'. "
                        f"These records directly contradict each other."
                    ),
                    requires_human_review=True,
                    detected_at=datetime.now(timezone.utc),
                ))
    return results


# ── Rule 2: Customer Claim vs Support Log ─────────────────────

def _check_customer_vs_support(
    by_category: dict[str, list[Evidence]],
) -> list[Contradiction]:
    """Customer filed 'not received' but support shows confirmed receipt."""
    results: list[Contradiction] = []
    confirmed_phrases = [
        "confirmed receipt", "received the product", "received the item",
        "got the package", "product received", "item received",
        "delivery confirmed",
    ]

    for comm in by_category.get("communication", []):
        if comm.status.value in ("missing", "not_applicable"):
            continue
        for ticket in comm.content.get("tickets", []):
            summary = (ticket.get("summary") or "").lower()
            if any(phrase in summary for phrase in confirmed_phrases):
                results.append(Contradiction(
                    contradiction_id=_make_contra_id(),
                    case_id=comm.case_id,
                    evidence_a_id=comm.evidence_id,
                    evidence_a_claim=f"Customer support record: '{ticket.get('summary', '')}'",
                    evidence_b_id="dispute_claim",
                    evidence_b_claim="Customer filed dispute claiming product not received",
                    impact="high",
                    description=(
                        f"Customer contacted support and {ticket.get('summary', '')}, "
                        f"but then filed a chargeback claiming non-receipt. "
                        f"This may indicate friendly fraud."
                    ),
                    requires_human_review=True,
                    detected_at=datetime.now(timezone.utc),
                ))
    return results


# ── Rule 3: Delivery After Dispute ────────────────────────────

def _check_delivery_after_dispute(
    evidence_items: list[Evidence],
    dispute_created_at: datetime | None = None,
) -> list[Contradiction]:
    """Delivery recorded AFTER the dispute was opened."""
    results: list[Contradiction] = []
    if dispute_created_at is None:
        return results

    if dispute_created_at.tzinfo is None:
        dispute_created_at = dispute_created_at.replace(tzinfo=timezone.utc)

    for ev in evidence_items:
        if ev.category != EvidenceCategory.DELIVERY:
            continue
        if ev.status.value in ("missing", "not_applicable", "ingestion_error"):
            continue
        if ev.event_time_utc is None:
            continue
        if ev.event_time_utc > dispute_created_at:
            results.append(Contradiction(
                contradiction_id=_make_contra_id(),
                case_id=ev.case_id,
                evidence_a_id=ev.evidence_id,
                evidence_a_claim=f"Delivery recorded at {ev.event_time_utc.isoformat()}",
                evidence_b_id="dispute_claim",
                evidence_b_claim=f"Dispute opened at {dispute_created_at.isoformat()}",
                impact="high",
                description=(
                    f"Delivery was recorded at {ev.event_time_utc.isoformat()}, "
                    f"which is AFTER the dispute was opened at "
                    f"{dispute_created_at.isoformat()}. This delivery proof "
                    f"may not be valid for contesting this dispute."
                ),
                requires_human_review=True,
                detected_at=datetime.now(timezone.utc),
            ))
    return results


# ── Rule 4: Refund Already Exists ─────────────────────────────

def _check_refund_exists(
    by_category: dict[str, list[Evidence]],
    dispute_reason: str = "",
) -> list[Contradiction]:
    """Refund already processed — potential double recovery.

    Skipped for duplicate_transaction disputes where refund proof
    is the primary defense evidence confirming resolution.
    """
    if "duplicate" in dispute_reason.lower() or dispute_reason == "duplicate_transaction":
        return []

    results: list[Contradiction] = []

    for refund in by_category.get("refund", []):
        if refund.status != EvidenceStatus.AVAILABLE:
            continue
        refund_count = refund.content.get("refund_count", 0)
        if refund_count > 0:
            total = refund.content.get("total_refunded", 0)
            results.append(Contradiction(
                contradiction_id=_make_contra_id(),
                case_id=refund.case_id,
                evidence_a_id=refund.evidence_id,
                evidence_a_claim=(
                    f"Refund already processed: {refund_count} refund(s), "
                    f"total Rs.{total / 100:,.2f}"
                ),
                evidence_b_id="contest_attempt",
                evidence_b_claim="Merchant is considering contesting this dispute",
                impact="medium",
                description=(
                    f"A refund has already been issued for this payment. "
                    f"Contesting the dispute while a refund was processed "
                    f"could constitute a double recovery attempt."
                ),
                requires_human_review=True,
                detected_at=datetime.now(timezone.utc),
            ))
    return results


# ── Rule 5: Timezone Anomaly (Delivery Before Order) ──────────

def _check_timeline_anomaly(
    by_category: dict[str, list[Evidence]],
) -> list[Contradiction]:
    """Delivery appears before order — likely timezone error."""
    results: list[Contradiction] = []

    for order in by_category.get("order", []):
        if order.event_time_utc is None:
            continue
        for delivery in by_category.get("delivery", []):
            if delivery.event_time_utc is None:
                continue
            if delivery.status.value in ("missing", "not_applicable"):
                continue
            if delivery.event_time_utc < order.event_time_utc:
                results.append(Contradiction(
                    contradiction_id=_make_contra_id(),
                    case_id=order.case_id,
                    evidence_a_id=order.evidence_id,
                    evidence_a_claim=f"Order created at {order.event_time_utc.isoformat()}",
                    evidence_b_id=delivery.evidence_id,
                    evidence_b_claim=f"Delivery recorded at {delivery.event_time_utc.isoformat()}",
                    impact="medium",
                    description=(
                        f"Delivery timestamp ({delivery.event_time_utc.isoformat()}) "
                        f"is before order timestamp ({order.event_time_utc.isoformat()}). "
                        f"This is physically impossible and likely indicates a "
                        f"timezone parsing error. "
                        f"Delivery timezone confident: {delivery.timezone_confident}"
                    ),
                    requires_human_review=True,
                    detected_at=datetime.now(timezone.utc),
                ))
    return results


# ── Rule 6: Shipping Before Order (from causal.py) ───────────

def _check_shipping_before_order(
    by_category: dict[str, list[Evidence]],
) -> list[Contradiction]:
    """Shipping timestamp before order — physically impossible."""
    results: list[Contradiction] = []
    shipping_ev = _get_timed_evidence(by_category, "shipping")
    order_ev = _get_timed_evidence(by_category, "order")

    if shipping_ev and order_ev and shipping_ev.event_time_utc < order_ev.event_time_utc:
        results.append(Contradiction(
            contradiction_id=f"contra_causal_{uuid.uuid4().hex[:8]}",
            case_id=order_ev.case_id,
            evidence_a_id=shipping_ev.evidence_id,
            evidence_a_claim=f"Shipping at {shipping_ev.event_time_utc.isoformat()}",
            evidence_b_id=order_ev.evidence_id,
            evidence_b_claim=f"Order at {order_ev.event_time_utc.isoformat()}",
            impact="high",
            description=(
                f"Shipping ({shipping_ev.event_time_utc.isoformat()}) occurred "
                f"BEFORE order ({order_ev.event_time_utc.isoformat()}). "
                f"This is physically impossible."
            ),
            requires_human_review=True,
            detected_at=datetime.now(timezone.utc),
        ))
    return results


# ── Rule 7: Delivery Before Shipping (from causal.py) ────────

def _check_delivery_before_shipping(
    by_category: dict[str, list[Evidence]],
) -> list[Contradiction]:
    """Delivery timestamp before shipping — physically impossible."""
    results: list[Contradiction] = []
    delivery_ev = _get_timed_evidence(by_category, "delivery")
    shipping_ev = _get_timed_evidence(by_category, "shipping")

    if delivery_ev and shipping_ev and delivery_ev.event_time_utc < shipping_ev.event_time_utc:
        results.append(Contradiction(
            contradiction_id=f"contra_causal_{uuid.uuid4().hex[:8]}",
            case_id=shipping_ev.case_id,
            evidence_a_id=delivery_ev.evidence_id,
            evidence_a_claim=f"Delivery at {delivery_ev.event_time_utc.isoformat()}",
            evidence_b_id=shipping_ev.evidence_id,
            evidence_b_claim=f"Shipping at {shipping_ev.event_time_utc.isoformat()}",
            impact="high",
            description=(
                f"Delivery ({delivery_ev.event_time_utc.isoformat()}) occurred "
                f"BEFORE shipping ({shipping_ev.event_time_utc.isoformat()}). "
                f"This is physically impossible."
            ),
            requires_human_review=True,
            detected_at=datetime.now(timezone.utc),
        ))
    return results


# ── Rule 8: Refund Before Payment (from causal.py) ───────────

def _check_refund_before_payment(
    by_category: dict[str, list[Evidence]],
) -> list[Contradiction]:
    """Refund timestamp before payment — impossible data error."""
    results: list[Contradiction] = []
    refund_ev = _get_timed_evidence(by_category, "refund")
    payment_ev = _get_timed_evidence(by_category, "payment")

    if refund_ev and payment_ev and refund_ev.event_time_utc < payment_ev.event_time_utc:
        results.append(Contradiction(
            contradiction_id=f"contra_causal_{uuid.uuid4().hex[:8]}",
            case_id=payment_ev.case_id,
            evidence_a_id=refund_ev.evidence_id,
            evidence_a_claim=f"Refund at {refund_ev.event_time_utc.isoformat()}",
            evidence_b_id=payment_ev.evidence_id,
            evidence_b_claim=f"Payment at {payment_ev.event_time_utc.isoformat()}",
            impact="high",
            description=(
                f"Refund ({refund_ev.event_time_utc.isoformat()}) occurred "
                f"BEFORE payment ({payment_ev.event_time_utc.isoformat()}). "
                f"This is impossible — likely a data error."
            ),
            requires_human_review=True,
            detected_at=datetime.now(timezone.utc),
        ))
    return results


# ═══════════════════════════════════════════════════════════════
#  TIMELINE CONSTRUCTION
# ═══════════════════════════════════════════════════════════════


_CATEGORY_LABELS: dict[str, str] = {
    EvidenceCategory.PAYMENT.value: "Payment",
    EvidenceCategory.ORDER.value: "Order",
    EvidenceCategory.SHIPPING.value: "Shipping",
    EvidenceCategory.DELIVERY.value: "Delivery",
    EvidenceCategory.AUTHENTICATION.value: "Authentication",
    EvidenceCategory.COMMUNICATION.value: "Communication",
    EvidenceCategory.REFUND.value: "Refund",
}


def build_timeline(evidence_items: list[Evidence]) -> list[TimelineEvent]:
    """Construct a chronological timeline from evidence items.

    Only evidence with event_time_utc gets a timeline entry.
    Missing evidence is NOT included — no invented timestamps.
    """
    events: list[TimelineEvent] = []

    for ev in evidence_items:
        if ev.event_time_utc is None:
            continue
        if ev.status.value in ("missing", "not_applicable"):
            continue
        event = _evidence_to_timeline_event(ev)
        if event:
            events.append(event)

    events.sort(key=lambda e: e.timestamp_utc)
    return events


def _evidence_to_timeline_event(ev: Evidence) -> TimelineEvent | None:
    if ev.event_time_utc is None:
        return None

    return TimelineEvent(
        event_id=f"tl_{uuid.uuid4().hex[:10]}",
        case_id=ev.case_id,
        timestamp_utc=ev.event_time_utc,
        timestamp_original=str(ev.event_time) if ev.event_time else None,
        timezone_original=ev.event_timezone,
        timezone_confident=ev.timezone_confident,
        label=_build_label(ev),
        description=_build_description(ev),
        category=ev.category.value,
        source_evidence_id=ev.evidence_id,
        source_system=ev.source_system,
    )


def _build_label(ev: Evidence) -> str:
    category_name = _CATEGORY_LABELS.get(ev.category.value, ev.category.value.title())
    content = ev.content

    if ev.category == EvidenceCategory.PAYMENT:
        return f"Payment captured ({content.get('method', 'unknown')})"
    if ev.category == EvidenceCategory.ORDER:
        receipt = content.get("receipt", content.get("order_id", ""))
        return f"Order created ({receipt})"
    if ev.category == EvidenceCategory.SHIPPING:
        status = content.get("status", "dispatched")
        carrier = content.get("carrier", "")
        return f"Shipping {status}" + (f" ({carrier})" if carrier else "")
    if ev.category == EvidenceCategory.DELIVERY:
        signed = content.get("signed_by")
        if signed:
            return f"Delivery confirmed (signed by {signed})"
        return f"Delivery recorded ({content.get('proof_type', '')})"
    if ev.category == EvidenceCategory.AUTHENTICATION:
        method = content.get("method", "")
        verified = content.get("verified", False)
        return f"Auth: {method} {'verified' if verified else 'attempted'}"
    if ev.category == EvidenceCategory.COMMUNICATION:
        return f"Customer communication ({content.get('ticket_count', 0)} messages)"
    if ev.category == EvidenceCategory.REFUND:
        return f"Refund processed ({content.get('refund_count', 0)})"

    return f"{category_name} event"


def _build_description(ev: Evidence) -> str:
    content = ev.content

    if ev.category == EvidenceCategory.PAYMENT:
        amount = content.get("amount", 0)
        card = f"{content.get('card_network', '')} ending {content.get('card_last4', '????')}"
        return f"Rs.{amount / 100:,.2f} via {card}"
    if ev.category == EvidenceCategory.ORDER:
        return content.get("item", "") or "Order details available"
    if ev.category == EvidenceCategory.SHIPPING:
        tracking = content.get("tracking_id", "")
        return f"Tracking: {tracking}" if tracking else ""
    if ev.category == EvidenceCategory.DELIVERY:
        return content.get("delivery_address", "") or ""

    return ev.summary or ""


# ═══════════════════════════════════════════════════════════════
#  MULTI-SOURCE TRIANGULATION
# ═══════════════════════════════════════════════════════════════


@dataclass
class Signal:
    """An independent data point supporting a claim."""
    source_system: str
    evidence_id: str
    supports_claim: bool
    details: str = ""


@dataclass
class TriangulationResult:
    """Result of multi-source verification for a specific claim."""
    claim: str
    category: str
    signals: list[Signal] = field(default_factory=list)
    signal_count: int = 0
    supporting_count: int = 0
    conflicting_count: int = 0
    triangulated: bool = False
    confidence_note: str = ""


def triangulate_delivery(evidence_items: list[Evidence]) -> TriangulationResult:
    """Triangulate delivery evidence across independent sources.

    Checks how many independent systems confirm that delivery happened.
    """
    result = TriangulationResult(claim="Package was delivered", category="delivery")
    delivery_signals: list[Signal] = []
    seen_sources: set[str] = set()

    for ev in evidence_items:
        if ev.status.value in ("missing", "not_applicable", "ingestion_error"):
            continue

        if ev.category == EvidenceCategory.DELIVERY:
            if ev.source_system not in seen_sources:
                seen_sources.add(ev.source_system)
                delivery_signals.append(Signal(
                    source_system=ev.source_system,
                    evidence_id=ev.evidence_id,
                    supports_claim=ev.status == EvidenceStatus.AVAILABLE,
                    details=ev.summary,
                ))

        if ev.category == EvidenceCategory.SHIPPING:
            shipping_status = ev.content.get("status", "").lower()
            source_key = f"shipping_{ev.source_system}"
            if source_key not in seen_sources:
                if shipping_status in ("delivered", "completed"):
                    seen_sources.add(source_key)
                    delivery_signals.append(Signal(
                        source_system=ev.source_system,
                        evidence_id=ev.evidence_id,
                        supports_claim=True,
                        details=f"Carrier tracking status: {shipping_status}",
                    ))
                elif shipping_status in ("returned_to_sender", "returned", "lost", "rts"):
                    seen_sources.add(source_key)
                    delivery_signals.append(Signal(
                        source_system=ev.source_system,
                        evidence_id=ev.evidence_id,
                        supports_claim=False,
                        details=f"Carrier tracking status: {shipping_status}",
                    ))

        if ev.category == EvidenceCategory.COMMUNICATION:
            for ticket in ev.content.get("tickets", []):
                summary = (ticket.get("summary") or "").lower()
                confirmed = [
                    "confirmed receipt", "received the product", "received the item",
                    "got the package", "product received", "item received",
                ]
                denied = [
                    "not received", "never received", "didn't receive",
                    "did not receive", "haven't received",
                ]
                if any(p in summary for p in confirmed):
                    key = f"comm_confirm_{ev.source_system}"
                    if key not in seen_sources:
                        seen_sources.add(key)
                        delivery_signals.append(Signal(
                            source_system=ev.source_system,
                            evidence_id=ev.evidence_id,
                            supports_claim=True,
                            details=f"Customer support: {ticket.get('summary', '')}",
                        ))
                elif any(p in summary for p in denied):
                    key = f"comm_deny_{ev.source_system}"
                    if key not in seen_sources:
                        seen_sources.add(key)
                        delivery_signals.append(Signal(
                            source_system=ev.source_system,
                            evidence_id=ev.evidence_id,
                            supports_claim=False,
                            details=f"Customer support: {ticket.get('summary', '')}",
                        ))

    result.signals = delivery_signals
    result.signal_count = len(delivery_signals)
    result.supporting_count = sum(1 for s in delivery_signals if s.supports_claim)
    result.conflicting_count = sum(1 for s in delivery_signals if not s.supports_claim)

    if result.supporting_count >= 2:
        result.triangulated = True
        result.confidence_note = f"Delivery confirmed by {result.supporting_count} independent sources"
    elif result.supporting_count == 1 and result.conflicting_count == 0:
        result.confidence_note = "Single-source unconfirmed — delivery verified by only one source"
    elif result.conflicting_count > 0:
        result.confidence_note = (
            f"Conflicting signals: {result.supporting_count} confirm, "
            f"{result.conflicting_count} deny delivery"
        )
    else:
        result.confidence_note = "No delivery signals found"

    return result


def apply_triangulation(
    evidence_items: list[Evidence],
    triangulation: TriangulationResult,
) -> list[Evidence]:
    """Apply triangulation results to evidence items.

    Downgrades single-source delivery from HIGH to MEDIUM reliability.
    Returns a new list with modified copies — does not mutate inputs.
    """
    if triangulation.triangulated or triangulation.signal_count == 0:
        return evidence_items

    result: list[Evidence] = []
    for ev in evidence_items:
        if ev.category == EvidenceCategory.DELIVERY:
            ev_copy = deepcopy(ev)
            if ev_copy.status == EvidenceStatus.AVAILABLE and ev_copy.reliability == "high":
                if triangulation.conflicting_count > 0:
                    ev_copy.status = EvidenceStatus.CONFLICTING
                    ev_copy.summary = f"{ev_copy.summary} [Conflicting sources detected]"
                else:
                    ev_copy.reliability = "medium"
                    ev_copy.summary = f"{ev_copy.summary} [Single-source unconfirmed]"
            elif ev_copy.status == EvidenceStatus.UNVERIFIED:
                if triangulation.conflicting_count > 0:
                    ev_copy.summary = f"{ev_copy.summary} [No corroboration from carrier]"
                else:
                    ev_copy.summary = f"{ev_copy.summary} [Single-source unconfirmed]"
            result.append(ev_copy)
        else:
            result.append(ev)

    return result


# ═══════════════════════════════════════════════════════════════
#  CAUSAL VALIDATION — Standalone functions
# ═══════════════════════════════════════════════════════════════


@dataclass
class CausalViolation:
    """A physically impossible temporal relationship."""
    earlier_event: str
    later_event: str
    earlier_time: datetime
    later_time: datetime
    earlier_evidence_id: str
    later_evidence_id: str
    case_id: str
    description: str


def validate_causal_order(evidence_items: list[Evidence]) -> list[CausalViolation]:
    """Run all causal assertions against gathered evidence.

    Returns list of violations where the timeline is physically impossible.
    Skips checks when timestamps are missing (never invents timestamps).
    """
    violations: list[CausalViolation] = []

    by_category: dict[str, Evidence] = {}
    for ev in evidence_items:
        cat = ev.category.value
        if cat not in by_category and ev.event_time_utc is not None:
            if ev.status.value not in ("missing", "not_applicable", "ingestion_error"):
                by_category[cat] = ev

    order_ev = by_category.get("order")
    shipping_ev = by_category.get("shipping")
    delivery_ev = by_category.get("delivery")
    payment_ev = by_category.get("payment")
    refund_ev = by_category.get("refund")

    # Rule 1: Delivery MUST be after Order
    if delivery_ev and order_ev:
        if delivery_ev.event_time_utc < order_ev.event_time_utc:
            violations.append(CausalViolation(
                earlier_event="Delivery", later_event="Order",
                earlier_time=delivery_ev.event_time_utc,
                later_time=order_ev.event_time_utc,
                earlier_evidence_id=delivery_ev.evidence_id,
                later_evidence_id=order_ev.evidence_id,
                case_id=order_ev.case_id,
                description=(
                    f"Delivery ({delivery_ev.event_time_utc.isoformat()}) occurred "
                    f"BEFORE order ({order_ev.event_time_utc.isoformat()}). "
                    f"This is physically impossible — likely a timezone error."
                ),
            ))

    # Rule 2: Shipping MUST be after Order
    if shipping_ev and order_ev:
        if shipping_ev.event_time_utc < order_ev.event_time_utc:
            violations.append(CausalViolation(
                earlier_event="Shipping", later_event="Order",
                earlier_time=shipping_ev.event_time_utc,
                later_time=order_ev.event_time_utc,
                earlier_evidence_id=shipping_ev.evidence_id,
                later_evidence_id=order_ev.evidence_id,
                case_id=order_ev.case_id,
                description=(
                    f"Shipping ({shipping_ev.event_time_utc.isoformat()}) occurred "
                    f"BEFORE order ({order_ev.event_time_utc.isoformat()}). "
                    f"This is physically impossible."
                ),
            ))

    # Rule 3: Delivery MUST be after Shipping
    if delivery_ev and shipping_ev:
        if delivery_ev.event_time_utc < shipping_ev.event_time_utc:
            violations.append(CausalViolation(
                earlier_event="Delivery", later_event="Shipping",
                earlier_time=delivery_ev.event_time_utc,
                later_time=shipping_ev.event_time_utc,
                earlier_evidence_id=delivery_ev.evidence_id,
                later_evidence_id=shipping_ev.evidence_id,
                case_id=shipping_ev.case_id,
                description=(
                    f"Delivery ({delivery_ev.event_time_utc.isoformat()}) occurred "
                    f"BEFORE shipping ({shipping_ev.event_time_utc.isoformat()}). "
                    f"This is physically impossible."
                ),
            ))

    # Rule 4: Refund MUST be after Payment
    if refund_ev and payment_ev:
        if refund_ev.event_time_utc < payment_ev.event_time_utc:
            violations.append(CausalViolation(
                earlier_event="Refund", later_event="Payment",
                earlier_time=refund_ev.event_time_utc,
                later_time=payment_ev.event_time_utc,
                earlier_evidence_id=refund_ev.evidence_id,
                later_evidence_id=payment_ev.evidence_id,
                case_id=payment_ev.case_id,
                description=(
                    f"Refund ({refund_ev.event_time_utc.isoformat()}) occurred "
                    f"BEFORE payment ({payment_ev.event_time_utc.isoformat()}). "
                    f"This is impossible — likely a data error."
                ),
            ))

    return violations


def violations_to_contradictions(violations: list[CausalViolation]) -> list[Contradiction]:
    """Convert causal violations to Contradiction objects.

    All causal violations are HIGH impact — they indicate corrupted data
    that could invalidate the entire timeline.
    """
    return [
        Contradiction(
            contradiction_id=f"contra_causal_{uuid.uuid4().hex[:8]}",
            case_id=v.case_id,
            evidence_a_id=v.earlier_evidence_id,
            evidence_a_claim=f"{v.earlier_event} at {v.earlier_time.isoformat()}",
            evidence_b_id=v.later_evidence_id,
            evidence_b_claim=f"{v.later_event} at {v.later_time.isoformat()}",
            impact="high",
            description=v.description,
            requires_human_review=True,
            detected_at=datetime.now(timezone.utc),
        )
        for v in violations
    ]

