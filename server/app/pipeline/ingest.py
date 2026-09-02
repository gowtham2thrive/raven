"""
Evidence Ingestion Pipeline — Validation + Normalization.

THE boundary where business-specific data becomes business-agnostic
canonical evidence. This module:

1. Validates raw data from external sources against strict Pydantic schemas
2. Converts valid data into canonical Evidence objects
3. Quarantines malformed data instead of silently coercing it

Merchant-specific logic lives here — never in analysis or agent layers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.connectors.quarantine import IngestionQuarantine
from app.core.types import EvidenceCategory, EvidenceStatus
from app.core.schemas import Evidence

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  VALIDATION SCHEMAS — Boundary Input Models
# ═══════════════════════════════════════════════════════════════
# Strict Pydantic models for each external data source.
# Uses extra="forbid" for controlled schemas (merchant connectors)
# and extra="allow" for vendor APIs (Razorpay may add fields).


class RazorpayCardInput(BaseModel):
    """Card details nested within a payment."""
    model_config = ConfigDict(extra="allow")
    network: str | None = None
    last4: str | None = None
    type: str | None = None
    issuer: str | None = None


class RazorpayPaymentInput(BaseModel):
    """Expected shape of a Razorpay payment API response."""
    model_config = ConfigDict(extra="allow")
    id: str
    amount: int
    currency: str = "INR"
    status: str
    method: str
    created_at: int | float
    captured: bool = False
    international: bool = False
    email: str | None = None
    contact: str | None = None
    card: RazorpayCardInput | dict | None = None


class RazorpayOrderInput(BaseModel):
    """Expected shape of a Razorpay order API response."""
    model_config = ConfigDict(extra="allow")
    id: str
    amount: int
    status: str
    created_at: int | float
    receipt: str | None = None
    notes: dict | None = None


class RazorpayRefundInput(BaseModel):
    """Expected shape of a single Razorpay refund."""
    model_config = ConfigDict(extra="allow")
    id: str
    amount: int
    status: str
    created_at: int | float


class ShippingInput(BaseModel):
    """Expected shape of merchant shipping data."""
    model_config = ConfigDict(extra="forbid")
    carrier: str
    tracking_id: str
    shipped_at: str | int | float
    status: str
    origin_city: str | None = None
    destination_city: str | None = None
    timezone: str | None = None
    events: list[dict] | None = None


class DeliveryInput(BaseModel):
    """Expected shape of merchant delivery proof."""
    model_config = ConfigDict(extra="forbid")
    delivered_at: str | int | float
    proof_type: str = "unknown"
    signed_by: str | None = None
    delivery_address: str | None = None
    photo_proof: bool = False
    tracking_id: str | None = None
    source: str = "merchant"
    timezone: str | None = None


class AuthInput(BaseModel):
    """Expected shape of authentication event data."""
    model_config = ConfigDict(extra="forbid")
    method: str
    verified: bool
    device_known: bool = False
    ip_country: str | None = None
    ip_address: str | None = None
    device_fingerprint: str | None = None
    previous_transactions: int | None = None


class CommunicationInput(BaseModel):
    """Expected shape of a single customer communication record."""
    model_config = ConfigDict(extra="forbid")
    type: str
    timestamp: str
    summary: str
    channel: str | None = None
    direction: str | None = None


# ── Validation Functions ──────────────────────────────────────

def validate_payment(data: dict) -> RazorpayPaymentInput:
    return RazorpayPaymentInput.model_validate(data)

def validate_order(data: dict) -> RazorpayOrderInput:
    return RazorpayOrderInput.model_validate(data)

def validate_refund(data: dict) -> RazorpayRefundInput:
    return RazorpayRefundInput.model_validate(data)

def validate_shipping(data: dict) -> ShippingInput:
    return ShippingInput.model_validate(data)

def validate_delivery(data: dict) -> DeliveryInput:
    return DeliveryInput.model_validate(data)

def validate_auth(data: dict) -> AuthInput:
    return AuthInput.model_validate(data)

def validate_communication(data: dict) -> CommunicationInput:
    return CommunicationInput.model_validate(data)


# ═══════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════


def _make_id() -> str:
    return f"ev_{uuid.uuid4().hex[:10]}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_payload(payload: dict) -> str:
    """SHA-256 hash of the raw source payload for tamper detection."""
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a timestamp from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError):
            return None
    return None


def _format_amount(paise: int | None) -> str:
    """Format paise to rupee string."""
    if paise is None:
        return "unknown"
    rupees = paise / 100
    return f"Rs.{rupees:,.2f}"


def _make_ingestion_error(
    payload: dict,
    case_id: str,
    category: EvidenceCategory,
    source_system: str,
    error: ValidationError,
    quarantine: IngestionQuarantine | None = None,
) -> Evidence:
    """Create an INGESTION_ERROR evidence item and quarantine the bad data."""
    error_msg = str(error)

    if quarantine:
        quarantine.quarantine(
            IngestionQuarantine.make_record(
                case_id=case_id,
                source_system=source_system,
                evidence_category=category.value,
                raw_payload=payload,
                error_message=error_msg,
            )
        )

    logger.warning(
        f"Ingestion error for {source_system}/{category.value} "
        f"in case {case_id}: {error_msg[:100]}"
    )

    return Evidence(
        evidence_id=_make_id(),
        case_id=case_id,
        category=category,
        status=EvidenceStatus.INGESTION_ERROR,
        source_system=source_system,
        source_record_id=payload.get("id", ""),
        observed_at=_utc_now(),
        summary=f"Data failed validation: {error_msg[:100]}",
        raw_source=payload,
        raw_source_hash=_hash_payload(payload),
    )


# ═══════════════════════════════════════════════════════════════
#  NORMALIZERS — Razorpay Data → Canonical Evidence
# ═══════════════════════════════════════════════════════════════


def normalize_razorpay_payment(
    payment: dict, case_id: str, quarantine: IngestionQuarantine | None = None,
) -> Evidence:
    """Convert Razorpay payment API response to canonical Evidence."""
    try:
        validate_payment(payment)
    except ValidationError as e:
        return _make_ingestion_error(
            payment, case_id, EvidenceCategory.PAYMENT, "razorpay", e, quarantine,
        )

    created = _parse_timestamp(payment.get("created_at"))
    card = payment.get("card", {}) or {}

    return Evidence(
        evidence_id=_make_id(),
        case_id=case_id,
        category=EvidenceCategory.PAYMENT,
        status=EvidenceStatus.AVAILABLE,
        source_system="razorpay",
        source_record_id=payment.get("id", ""),
        source_url=f"/v1/payments/{payment.get('id', '')}",
        event_time=created,
        event_timezone="UTC",
        event_time_utc=created,
        timezone_confident=True,
        observed_at=_utc_now(),
        content={
            "payment_id": payment.get("id"),
            "amount": payment.get("amount"),
            "currency": payment.get("currency", "INR"),
            "status": payment.get("status"),
            "method": payment.get("method"),
            "card_network": card.get("network"),
            "card_last4": card.get("last4"),
            "card_type": card.get("type"),
            "card_issuer": card.get("issuer"),
            "international": payment.get("international", False),
            "email": payment.get("email"),
            "contact": payment.get("contact"),
            "captured": payment.get("captured", False),
        },
        summary=(
            f"Payment of {_format_amount(payment.get('amount', 0))} "
            f"via {payment.get('method', 'unknown')} "
            f"({card.get('network', '')} ending {card.get('last4', '????')}), "
            f"status: {payment.get('status', 'unknown')}"
        ),
        relevance="high",
        reliability="high",
        raw_source=payment,
        raw_source_hash=_hash_payload(payment),
    )


def normalize_razorpay_order(
    order: dict, case_id: str, quarantine: IngestionQuarantine | None = None,
) -> Evidence:
    """Convert Razorpay order API response to canonical Evidence."""
    try:
        validate_order(order)
    except ValidationError as e:
        return _make_ingestion_error(
            order, case_id, EvidenceCategory.ORDER, "razorpay", e, quarantine,
        )

    created = _parse_timestamp(order.get("created_at"))
    notes = order.get("notes", {}) or {}

    return Evidence(
        evidence_id=_make_id(),
        case_id=case_id,
        category=EvidenceCategory.ORDER,
        status=EvidenceStatus.AVAILABLE,
        source_system="razorpay",
        source_record_id=order.get("id", ""),
        source_url=f"/v1/orders/{order.get('id', '')}",
        event_time=created,
        event_timezone="UTC",
        event_time_utc=created,
        timezone_confident=True,
        observed_at=_utc_now(),
        content={
            "order_id": order.get("id"),
            "amount": order.get("amount"),
            "receipt": order.get("receipt"),
            "status": order.get("status"),
            "item": notes.get("item", ""),
            "quantity": notes.get("quantity", ""),
        },
        summary=(
            f"Order {order.get('receipt', order.get('id', ''))} — "
            f"{notes.get('item', 'item details unavailable')}, "
            f"amount: {_format_amount(order.get('amount', 0))}"
        ),
        relevance="high",
        reliability="high",
        raw_source=order,
        raw_source_hash=_hash_payload(order),
    )


def normalize_razorpay_refunds(
    refunds: list[dict], case_id: str, payment_id: str
) -> Evidence | None:
    """Convert Razorpay refund data to canonical Evidence.

    Returns Evidence with NOT_APPLICABLE if no refunds exist.
    """
    if not refunds:
        return Evidence(
            evidence_id=_make_id(),
            case_id=case_id,
            category=EvidenceCategory.REFUND,
            status=EvidenceStatus.NOT_APPLICABLE,
            source_system="razorpay",
            source_record_id=payment_id,
            observed_at=_utc_now(),
            summary="No refunds issued for this payment",
            relevance="medium",
            reliability="high",
        )

    total_refunded = sum(r.get("amount", 0) for r in refunds)
    latest = max(refunds, key=lambda r: r.get("created_at", 0))
    latest_time = _parse_timestamp(latest.get("created_at"))

    refunds_payload = {"payment_id": payment_id, "refunds": refunds}
    return Evidence(
        evidence_id=_make_id(),
        case_id=case_id,
        category=EvidenceCategory.REFUND,
        status=EvidenceStatus.AVAILABLE,
        source_system="razorpay",
        source_record_id=payment_id,
        event_time=latest_time,
        event_timezone="UTC",
        event_time_utc=latest_time,
        timezone_confident=True,
        observed_at=_utc_now(),
        content={
            "refund_count": len(refunds),
            "total_refunded": total_refunded,
            "refunds": [
                {
                    "id": r.get("id"),
                    "amount": r.get("amount"),
                    "status": r.get("status"),
                    "created_at": r.get("created_at"),
                }
                for r in refunds
            ],
        },
        summary=f"{len(refunds)} refund(s) totaling {_format_amount(total_refunded)}",
        relevance="high",
        reliability="high",
        raw_source=refunds_payload,
        raw_source_hash=_hash_payload(refunds_payload),
    )


# ═══════════════════════════════════════════════════════════════
#  NORMALIZERS — Merchant Data → Canonical Evidence
# ═══════════════════════════════════════════════════════════════


def normalize_shipping(
    shipping: dict | None, case_id: str, quarantine: IngestionQuarantine | None = None,
) -> Evidence:
    """Convert merchant shipping data to canonical Evidence."""
    if shipping is None:
        return Evidence(
            evidence_id=_make_id(),
            case_id=case_id,
            category=EvidenceCategory.SHIPPING,
            status=EvidenceStatus.MISSING,
            source_system="merchant_shipping",
            source_record_id="",
            observed_at=_utc_now(),
            summary="No shipping records found",
            relevance="high",
            reliability="unknown",
        )

    try:
        validate_shipping(shipping)
    except ValidationError as e:
        return _make_ingestion_error(
            shipping, case_id, EvidenceCategory.SHIPPING, "merchant_shipping", e, quarantine,
        )

    shipped_at = _parse_timestamp(shipping.get("shipped_at"))

    return Evidence(
        evidence_id=_make_id(),
        case_id=case_id,
        category=EvidenceCategory.SHIPPING,
        status=EvidenceStatus.AVAILABLE,
        source_system="merchant_shipping",
        source_record_id=shipping.get("tracking_id", ""),
        event_time=shipped_at,
        event_timezone=shipping.get("timezone"),
        event_time_utc=shipped_at,
        timezone_confident=shipping.get("timezone") is not None,
        observed_at=_utc_now(),
        content={
            "carrier": shipping.get("carrier"),
            "tracking_id": shipping.get("tracking_id"),
            "status": shipping.get("status"),
            "origin_city": shipping.get("origin_city"),
            "destination_city": shipping.get("destination_city"),
        },
        summary=(
            f"Shipped via {shipping.get('carrier', 'unknown')} "
            f"(tracking: {shipping.get('tracking_id', 'N/A')}), "
            f"status: {shipping.get('status', 'unknown')}"
        ),
        relevance="high",
        reliability="medium",
        raw_source=shipping,
        raw_source_hash=_hash_payload(shipping),
    )


def normalize_delivery(
    delivery: dict | None, case_id: str, quarantine: IngestionQuarantine | None = None,
) -> Evidence:
    """Convert merchant delivery data to canonical Evidence."""
    if delivery is None:
        return Evidence(
            evidence_id=_make_id(),
            case_id=case_id,
            category=EvidenceCategory.DELIVERY,
            status=EvidenceStatus.MISSING,
            source_system="merchant_delivery",
            source_record_id="",
            observed_at=_utc_now(),
            summary="No delivery records found",
            relevance="critical",
            reliability="unknown",
        )

    try:
        validate_delivery(delivery)
    except ValidationError as e:
        return _make_ingestion_error(
            delivery, case_id, EvidenceCategory.DELIVERY, "merchant_delivery", e, quarantine,
        )

    delivered_at = _parse_timestamp(delivery.get("delivered_at"))
    tz = delivery.get("timezone")
    tz_confident = tz is not None

    has_signature = delivery.get("signed_by") is not None
    signed_by_name = delivery.get("signed_by", "")
    has_photo = delivery.get("photo_proof", False)
    proof_type = delivery.get("proof_type", "unknown")

    if has_signature:
        status = EvidenceStatus.AVAILABLE
        reliability = "high"
    elif proof_type in ("left_at_door", "mailbox"):
        status = EvidenceStatus.UNVERIFIED
        reliability = "medium"
    else:
        status = EvidenceStatus.UNVERIFIED
        reliability = "low"

    return Evidence(
        evidence_id=_make_id(),
        case_id=case_id,
        category=EvidenceCategory.DELIVERY,
        status=status,
        source_system="merchant_delivery",
        source_record_id=delivery.get("tracking_id", ""),
        event_time=delivered_at,
        event_timezone=tz,
        event_time_utc=delivered_at,
        timezone_confident=tz_confident,
        observed_at=_utc_now(),
        content={
            "delivered_at": str(delivered_at) if delivered_at else None,
            "signed_by": delivery.get("signed_by"),
            "delivery_address": delivery.get("delivery_address"),
            "proof_type": proof_type,
            "photo_proof": has_photo,
            "source": delivery.get("source", "merchant"),
        },
        summary=(
            f"Delivery {'confirmed' if has_signature else 'recorded'}"
            f"{f', signed by {signed_by_name}' if has_signature else ''}"
            f"{', with photo proof' if has_photo else ''}"
            f" (proof: {proof_type})"
        ),
        relevance="critical",
        reliability=reliability,
        raw_source=delivery,
        raw_source_hash=_hash_payload(delivery),
    )


def normalize_auth(
    auth: dict | None, case_id: str, quarantine: IngestionQuarantine | None = None,
) -> Evidence:
    """Convert authentication event to canonical Evidence."""
    if auth is None:
        return Evidence(
            evidence_id=_make_id(),
            case_id=case_id,
            category=EvidenceCategory.AUTHENTICATION,
            status=EvidenceStatus.MISSING,
            source_system="merchant_auth",
            source_record_id="",
            observed_at=_utc_now(),
            summary="No authentication records found",
            relevance="medium",
            reliability="unknown",
        )

    try:
        validate_auth(auth)
    except ValidationError as e:
        return _make_ingestion_error(
            auth, case_id, EvidenceCategory.AUTHENTICATION, "merchant_auth", e, quarantine,
        )

    verified = auth.get("verified", False)
    method = str(auth.get("method", "")).strip()

    if not verified and method in ("None", "none", "", "null", "undefined"):
        status = EvidenceStatus.MISSING
    elif verified:
        status = EvidenceStatus.AVAILABLE
    else:
        status = EvidenceStatus.UNVERIFIED

    return Evidence(
        evidence_id=_make_id(),
        case_id=case_id,
        category=EvidenceCategory.AUTHENTICATION,
        status=status,
        source_system="merchant_auth",
        source_record_id="",
        observed_at=_utc_now(),
        content={
            "method": auth.get("method"),
            "verified": verified,
            "device_known": auth.get("device_known", False),
            "ip_country": auth.get("ip_country"),
        },
        summary=(
            f"Authentication: {auth.get('method', 'unknown')} "
            f"({'verified' if verified else 'not verified'}), "
            f"device {'known' if auth.get('device_known') else 'new'}, "
            f"IP country: {auth.get('ip_country', 'unknown')}"
        ),
        relevance="medium",
        reliability="high" if verified else "low",
        raw_source=auth,
        raw_source_hash=_hash_payload(auth),
    )


def normalize_communications(
    comms: list[dict] | None, case_id: str, quarantine: IngestionQuarantine | None = None,
) -> Evidence:
    """Convert customer communications to canonical Evidence."""
    if not comms:
        return Evidence(
            evidence_id=_make_id(),
            case_id=case_id,
            category=EvidenceCategory.COMMUNICATION,
            status=EvidenceStatus.NOT_APPLICABLE,
            source_system="merchant_crm",
            source_record_id="",
            observed_at=_utc_now(),
            summary="No customer communications found",
            relevance="low",
            reliability="unknown",
        )

    latest = max(comms, key=lambda c: c.get("timestamp", ""))
    latest_time = _parse_timestamp(latest.get("timestamp"))

    comms_payload = {"communications": comms}
    return Evidence(
        evidence_id=_make_id(),
        case_id=case_id,
        category=EvidenceCategory.COMMUNICATION,
        status=EvidenceStatus.AVAILABLE,
        source_system="merchant_crm",
        source_record_id="",
        event_time=latest_time,
        event_time_utc=latest_time,
        observed_at=_utc_now(),
        content={
            "ticket_count": len(comms),
            "tickets": [
                {
                    "type": c.get("type"),
                    "timestamp": c.get("timestamp"),
                    "channel": c.get("channel"),
                    "summary": c.get("summary"),
                    "direction": c.get("direction"),
                }
                for c in comms
            ],
        },
        summary=(
            f"{len(comms)} communication(s): "
            f"{latest.get('summary', 'details available')}"
        ),
        relevance="medium",
        reliability="medium",
        raw_source=comms_payload,
        raw_source_hash=_hash_payload(comms_payload),
    )
