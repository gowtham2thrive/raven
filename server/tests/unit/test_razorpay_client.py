"""
Tests for Razorpay client — webhook parsing, mock response parsing.

These tests use mock data to verify RAVEN correctly parses
Razorpay's API response format without making real API calls.
"""

import pytest
from datetime import datetime, timezone

from app.core.schemas import RazorpayDisputeInfo
from app.connectors.razorpay import DisputeService, WebhookParser, DISPUTE_EVENTS
from data.synthetic.razorpay_mock import (
    mock_dispute,
    mock_payment,
    mock_order,
    mock_customer,
    mock_webhook_dispute_created,
    mock_webhook_dispute_won,
)


# ── Mock Response Parsing ─────────────────────────────────────

class TestDisputeParsing:
    def test_parse_dispute_from_mock(self):
        """DisputeService should parse mock dispute into typed model."""
        raw = mock_dispute(
            dispute_id="disp_test001",
            payment_id="pay_test001",
            amount=500000,
        )
        info = DisputeService._parse_dispute(raw)

        assert isinstance(info, RazorpayDisputeInfo)
        assert info.dispute_id == "disp_test001"
        assert info.payment_id == "pay_test001"
        assert info.amount == 500000
        assert info.currency == "INR"
        assert info.reason_code == "product_not_received"
        assert info.status == "open"

    def test_parse_dispute_respond_by_is_datetime(self):
        """respond_by should be parsed as a UTC datetime."""
        raw = mock_dispute(respond_by=1719830400)
        info = DisputeService._parse_dispute(raw)

        assert isinstance(info.respond_by, datetime)
        assert info.respond_by.tzinfo is not None

    def test_parse_dispute_handles_unknown_phase(self):
        """Unknown phase should default to CHARGEBACK."""
        raw = mock_dispute()
        raw["phase"] = "unknown_phase"
        info = DisputeService._parse_dispute(raw)

        assert info.phase.value == "chargeback"


# ── Webhook Parsing ───────────────────────────────────────────

class TestWebhookParsing:
    def test_parse_dispute_created_event(self):
        """Parser should extract dispute info from payment.dispute.created."""
        raw = mock_webhook_dispute_created(
            dispute_id="disp_webhook001",
            payment_id="pay_webhook001",
            amount=750000,
        )
        event = WebhookParser.parse(raw)

        assert event.event == "payment.dispute.created"
        assert WebhookParser.is_dispute_event(event) is True

        info = WebhookParser.extract_dispute_info(event)
        assert info is not None
        assert info.dispute_id == "disp_webhook001"
        assert info.payment_id == "pay_webhook001"
        assert info.amount == 750000

    def test_parse_dispute_won_event(self):
        """Parser should extract dispute info from payment.dispute.won."""
        raw = mock_webhook_dispute_won(
            dispute_id="disp_won001",
            payment_id="pay_won001",
        )
        event = WebhookParser.parse(raw)

        assert event.event == "payment.dispute.won"
        assert WebhookParser.is_dispute_event(event) is True

        info = WebhookParser.extract_dispute_info(event)
        assert info is not None
        assert info.status == "won"

    def test_extract_payment_id_from_webhook(self):
        """Parser should extract payment ID from webhook payload."""
        raw = mock_webhook_dispute_created(payment_id="pay_extract001")
        event = WebhookParser.parse(raw)

        payment_id = WebhookParser.extract_payment_id(event)
        assert payment_id == "pay_extract001"

    def test_non_dispute_event_returns_false(self):
        """Non-dispute events should not be identified as dispute events."""
        event = WebhookParser.parse({
            "event": "payment.captured",
            "payload": {},
        })
        assert WebhookParser.is_dispute_event(event) is False

    def test_malformed_payload_returns_none(self):
        """Malformed webhook payload should return None, not crash."""
        event = WebhookParser.parse({
            "event": "payment.dispute.created",
            "payload": {"dispute": {}},  # Missing 'entity' key
        })
        info = WebhookParser.extract_dispute_info(event)
        assert info is None

    def test_all_dispute_events_recognized(self):
        """All 6 dispute event types should be in DISPUTE_EVENTS set."""
        expected = {
            "payment.dispute.created",
            "payment.dispute.action_required",
            "payment.dispute.won",
            "payment.dispute.lost",
            "payment.dispute.closed",
            "payment.dispute.under_review",
        }
        assert DISPUTE_EVENTS == expected


# ── Mock Data Consistency ─────────────────────────────────────

class TestMockDataConsistency:
    def test_mock_payment_has_all_fields(self):
        """Mock payment should have all fields RAVEN needs."""
        p = mock_payment()
        assert "id" in p
        assert "amount" in p
        assert "order_id" in p
        assert "customer_id" in p
        assert "method" in p
        assert "email" in p
        assert "card" in p
        assert p["card"]["last4"] == "4242"

    def test_mock_order_has_all_fields(self):
        """Mock order should have receipt and notes."""
        o = mock_order()
        assert "id" in o
        assert "receipt" in o
        assert "notes" in o
        assert o["status"] == "paid"

    def test_mock_customer_has_all_fields(self):
        """Mock customer should have name, email, contact."""
        c = mock_customer()
        assert c["name"] == "Arjun Mehta"
        assert c["email"] == "arjun@example.com"
        assert c["contact"].startswith("+91")

    def test_mock_dispute_default_reason(self):
        """Default mock dispute should be product_not_received."""
        d = mock_dispute()
        assert d["reason_code"] == "product_not_received"
        assert d["phase"] == "chargeback"
        assert d["status"] == "open"

    def test_webhook_payload_structure(self):
        """Webhook mock should match Razorpay's nested structure."""
        raw = mock_webhook_dispute_created()
        assert raw["event"] == "payment.dispute.created"
        assert "payment" in raw["payload"]
        assert "dispute" in raw["payload"]
        assert "entity" in raw["payload"]["dispute"]
        assert "entity" in raw["payload"]["payment"]
