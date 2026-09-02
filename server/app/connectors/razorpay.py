"""
Razorpay Integration — Client, Webhooks, and API Resources.

Unified module for all Razorpay interactions:
- Webhook signature verification and event parsing
- Typed API client with error handling
- Payment, Order, Customer, Refund, Document, and Dispute operations

The LLM is not the source of truth — Razorpay's API is.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import razorpay
from pydantic import BaseModel, Field

from app.config import Settings, settings
from app.core.types import (
    DisputePhase,
    RazorpayAPIError,
    WebhookSignatureError,
)
from app.core.schemas import RazorpayDisputeInfo

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  WEBHOOK EVENT MODELS
# ═══════════════════════════════════════════════════════════════


class WebhookEvent(BaseModel):
    """Parsed Razorpay webhook event."""
    event: str
    account_id: str = ""
    contains: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


DISPUTE_EVENTS = {
    "payment.dispute.created",
    "payment.dispute.action_required",
    "payment.dispute.won",
    "payment.dispute.lost",
    "payment.dispute.closed",
    "payment.dispute.under_review",
}


# ═══════════════════════════════════════════════════════════════
#  WEBHOOK PARSER
# ═══════════════════════════════════════════════════════════════


class WebhookParser:
    """Parse and validate Razorpay webhook payloads.

    External inputs are untrusted — reject or quarantine
    anything that doesn't match expected schema.
    """

    @staticmethod
    def parse(raw_payload: dict) -> WebhookEvent:
        """Parse a raw webhook JSON body into a structured event."""
        event_type = raw_payload.get("event", "")
        created_ts = raw_payload.get("created_at")

        return WebhookEvent(
            event=event_type,
            account_id=raw_payload.get("account_id", ""),
            contains=raw_payload.get("contains", []),
            created_at=(
                datetime.fromtimestamp(created_ts, tz=timezone.utc)
                if created_ts
                else None
            ),
            payload=raw_payload.get("payload", {}),
        )

    @staticmethod
    def is_dispute_event(event: WebhookEvent) -> bool:
        return event.event in DISPUTE_EVENTS

    @staticmethod
    def extract_dispute_info(event: WebhookEvent) -> RazorpayDisputeInfo | None:
        """Extract RazorpayDisputeInfo from a dispute webhook event."""
        try:
            dispute_entity = (
                event.payload
                .get("dispute", {})
                .get("entity", {})
            )

            if not dispute_entity or "id" not in dispute_entity:
                logger.warning(
                    f"Could not extract dispute entity from event {event.event}"
                )
                return None

            phase_str = dispute_entity.get("phase", "chargeback")
            try:
                phase = DisputePhase(phase_str)
            except ValueError:
                phase = DisputePhase.CHARGEBACK

            return RazorpayDisputeInfo(
                dispute_id=dispute_entity["id"],
                payment_id=dispute_entity.get("payment_id", ""),
                amount=dispute_entity.get("amount", 0),
                currency=dispute_entity.get("currency", "INR"),
                reason_code=dispute_entity.get("reason_code", "unknown"),
                reason_description=dispute_entity.get("reason_description", ""),
                phase=phase,
                respond_by=datetime.fromtimestamp(
                    dispute_entity.get("respond_by", 0), tz=timezone.utc
                ),
                status=dispute_entity.get("status", "open"),
                created_at=datetime.fromtimestamp(
                    dispute_entity.get("created_at", 0), tz=timezone.utc
                ),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Failed to parse dispute from webhook: {e}")
            return None

    @staticmethod
    def extract_payment_id(event: WebhookEvent) -> str | None:
        try:
            return (
                event.payload
                .get("payment", {})
                .get("entity", {})
                .get("id")
            )
        except (KeyError, TypeError):
            return None


# ═══════════════════════════════════════════════════════════════
#  API CLIENT
# ═══════════════════════════════════════════════════════════════


class RazorpayClient:
    """Central Razorpay API client.

    All Razorpay interactions go through this — never call the
    SDK directly from other modules.
    """

    def __init__(self, app_settings: Settings | None = None):
        s = app_settings or settings
        self._key_id = s.razorpay_key_id
        self._webhook_secret = s.razorpay_webhook_secret
        self.is_test_mode = s.is_test_mode

        if self._key_id:
            self._client = razorpay.Client(
                auth=(s.razorpay_key_id, s.razorpay_key_secret)
            )
        else:
            self._client = None
            logger.warning("Razorpay API keys not configured — running in mock mode")

    @property
    def client(self) -> razorpay.Client:
        if self._client is None:
            raise RazorpayAPIError(0, "Razorpay API keys not configured", "")
        return self._client

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def verify_webhook_signature(self, body: str, signature: str) -> bool:
        """Verify Razorpay webhook signature (HMAC-SHA256)."""
        if not self._webhook_secret:
            raise WebhookSignatureError("Webhook secret not configured")

        try:
            utility = self._client.utility if self._client is not None else razorpay.Utility(None)
            utility.verify_webhook_signature(
                body, signature, self._webhook_secret
            )
            return True
        except razorpay.errors.SignatureVerificationError as e:
            raise WebhookSignatureError(f"Invalid webhook signature: {e}") from e

    def _safe_call(self, method: str, *args: Any, **kwargs: Any) -> dict:
        """Execute a Razorpay API call with error handling."""
        try:
            func = getattr(self.client, method.split(".")[0])
            for attr in method.split(".")[1:]:
                func = getattr(func, attr)
            result = func(*args, **kwargs)
            return result
        except razorpay.errors.BadRequestError as e:
            raise RazorpayAPIError(400, str(e), method) from e
        except razorpay.errors.GatewayError as e:
            raise RazorpayAPIError(502, str(e), method) from e
        except razorpay.errors.ServerError as e:
            raise RazorpayAPIError(500, str(e), method) from e
        except Exception as e:
            raise RazorpayAPIError(0, str(e), method) from e

    # ── Payments ──────────────────────────────────────────────

    def fetch_payment(self, payment_id: str) -> dict:
        """Fetch payment details by ID."""
        logger.debug(f"Fetching payment {payment_id}")
        return self._safe_call("payment.fetch", payment_id)

    def fetch_payment_with_card(self, payment_id: str) -> dict:
        """Fetch payment with expanded card details."""
        logger.debug(f"Fetching payment {payment_id} with card details")
        return self._safe_call("payment.fetch", payment_id, {"expand[]": "card"})

    # ── Orders ────────────────────────────────────────────────

    def fetch_order(self, order_id: str) -> dict:
        """Fetch order details by ID."""
        logger.debug(f"Fetching order {order_id}")
        return self._safe_call("order.fetch", order_id)

    # ── Customers ─────────────────────────────────────────────

    def fetch_customer(self, customer_id: str) -> dict:
        """Fetch customer details by ID."""
        logger.debug(f"Fetching customer {customer_id}")
        return self._safe_call("customer.fetch", customer_id)

    # ── Refunds ───────────────────────────────────────────────

    def fetch_refunds(self, payment_id: str) -> list[dict]:
        """Fetch all refunds for a payment."""
        logger.debug(f"Fetching refunds for payment {payment_id}")
        result = self._safe_call("payment.fetch_refunds", payment_id)
        return result.get("items", []) if isinstance(result, dict) else []

    # ── Documents ─────────────────────────────────────────────

    def upload_document(
        self, file_path: Path | str, purpose: str = "dispute_evidence",
    ) -> str:
        """Upload a document for dispute evidence. Returns doc ID."""
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")

        logger.info(f"Uploading document {file_path.name} (purpose={purpose})")
        with open(file_path, "rb") as f:
            result = self.client.document.create(file=f, purpose=purpose)

        doc_id = result.get("id", "")
        logger.info(f"Document uploaded: {doc_id}")
        return doc_id

    # ── Disputes ──────────────────────────────────────────────

    def fetch_dispute(self, dispute_id: str) -> RazorpayDisputeInfo:
        """Fetch a single dispute and parse to typed model."""
        raw = self._safe_call("payment.fetch_dispute", dispute_id)
        return self._parse_dispute(raw)

    def fetch_all_disputes(self, status: str | None = "open") -> list[RazorpayDisputeInfo]:
        """Fetch all disputes, optionally filtered by status."""
        params: dict[str, Any] = {}
        if status:
            params["status"] = status
        raw = self._safe_call("payment.fetch_all_disputes", params)
        items = raw.get("items", [])
        return [self._parse_dispute(d) for d in items]

    def contest_dispute(
        self,
        dispute_id: str,
        summary: str,
        shipping_proof: list[str] | None = None,
        billing_proof: list[str] | None = None,
        customer_communication: list[str] | None = None,
        proof_of_service: list[str] | None = None,
        explanation_letter: list[str] | None = None,
        refund_confirmation: list[str] | None = None,
        access_activity_log: list[str] | None = None,
        submit: bool = True,
    ) -> dict:
        """Contest a dispute via Razorpay API."""
        payload: dict[str, Any] = {"summary": summary}

        if shipping_proof:
            payload["shipping_proof"] = shipping_proof
        if billing_proof:
            payload["billing_proof"] = billing_proof
        if customer_communication:
            payload["customer_communication"] = customer_communication
        if proof_of_service:
            payload["proof_of_service"] = proof_of_service
        if explanation_letter:
            payload["explanation_letter"] = explanation_letter
        if refund_confirmation:
            payload["refund_confirmation"] = refund_confirmation
        if access_activity_log:
            payload["access_activity_log"] = access_activity_log

        if submit:
            payload["action"] = "submit"

        logger.info(f"Contesting dispute {dispute_id} (submit={submit})")
        return self._safe_call("payment.contest_dispute", dispute_id, payload)

    def accept_dispute(self, dispute_id: str) -> dict:
        """Accept a dispute — merchant takes the loss. Irreversible."""
        logger.info(f"Accepting dispute {dispute_id} (loss)")
        return self._safe_call("payment.accept_dispute", dispute_id)

    @staticmethod
    def _parse_dispute(raw: dict) -> RazorpayDisputeInfo:
        """Parse raw Razorpay dispute response into typed model."""
        phase_str = raw.get("phase", "chargeback")
        try:
            phase = DisputePhase(phase_str)
        except ValueError:
            phase = DisputePhase.CHARGEBACK

        return RazorpayDisputeInfo(
            dispute_id=raw["id"],
            payment_id=raw["payment_id"],
            amount=raw["amount"],
            currency=raw.get("currency", "INR"),
            reason_code=raw.get("reason_code", "unknown"),
            reason_description=raw.get("reason_description", ""),
            phase=phase,
            respond_by=datetime.fromtimestamp(raw["respond_by"], tz=timezone.utc),
            status=raw.get("status", "open"),
            created_at=datetime.fromtimestamp(raw["created_at"], tz=timezone.utc),
        )


# Backward-compatible alias — old DisputeService was a thin wrapper
DisputeService = RazorpayClient

