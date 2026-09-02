"""
Mock Razorpay API Responses.

These match the exact JSON structure returned by Razorpay's live API,
so RAVEN's Razorpay client code works identically with mock and real data.

All IDs use Razorpay's naming conventions:
    Disputes:  disp_xxx
    Payments:  pay_xxx
    Orders:    order_xxx
    Customers: cust_xxx
    Refunds:   rfnd_xxx
    Documents: doc_xxx
"""

from __future__ import annotations

import time


def mock_dispute(
    dispute_id: str = "disp_AHfqOvkldwsbqt",
    payment_id: str = "pay_EsyWjHrfzb59eR",
    amount: int = 849900,
    reason_code: str = "product_not_received",
    reason_description: str | None = None,
    respond_by: int | None = None,
    status: str = "open",
    phase: str = "chargeback",
    created_at: int | None = None,
) -> dict:
    """Mock Razorpay dispute entity matching /v1/disputes/:id response."""
    if respond_by is None:
        respond_by = int(time.time()) + (3 * 24 * 3600)  # 3 days from now
    if created_at is None:
        created_at = int(time.time()) - (1 * 24 * 3600)  # 1 day ago
    if reason_description is None:
        desc_map = {
            "product_not_received": "Customer claims the product was not received.",
            "unauthorized_transaction": "Customer claims they did not authorize the transaction.",
            "service_not_rendered": "Customer claims the service or digital subscription was not provided.",
            "product_not_as_described": "Customer claims the product was materially defective or not as described.",
            "duplicate_transaction": "Customer claims they were charged multiple times for the same order.",
        }
        reason_description = desc_map.get(reason_code, "Customer claims the product was not received.")

    return {
        "id": dispute_id,
        "entity": "dispute",
        "payment_id": payment_id,
        "amount": amount,
        "currency": "INR",
        "amount_deducted": 0,
        "reason_code": reason_code,
        "reason_description": reason_description,
        "respond_by": respond_by,
        "status": status,
        "phase": phase,
        "created_at": created_at,
        "evidence": {
            "amount": amount,
            "summary": None,
            "shipping_proof": [],
            "billing_proof": [],
            "cancellation_proof": [],
            "customer_communication": [],
            "proof_of_service": [],
            "explanation_letter": [],
            "refund_confirmation": [],
            "access_activity_log": [],
            "submitted_at": None,
        },
    }


def mock_payment(
    payment_id: str = "pay_EsyWjHrfzb59eR",
    order_id: str = "order_DBJOWzybf0sJbb",
    amount: int = 849900,
    method: str = "card",
    status: str = "captured",
    customer_id: str = "cust_1Aa00000000004",
    email: str = "arjun@example.com",
    contact: str = "+919876543210",
    international: bool = False,
    created_at: int | None = None,
    name: str | None = None,
    card_name: str | None = None,
) -> dict:
    """Mock Razorpay payment entity matching /v1/payments/:id response."""
    if created_at is None:
        created_at = int(time.time()) - (6 * 24 * 3600)

    holder_name = card_name or name or "Arjun Mehta"

    return {
        "id": payment_id,
        "entity": "payment",
        "amount": amount,
        "currency": "INR",
        "status": status,
        "order_id": order_id,
        "method": method,
        "description": "Order #1234",
        "card_id": "card_DZBt9VnTASbv3f",
        "card": {
            "id": "card_DZBt9VnTASbv3f",
            "name": holder_name,
            "network": "Visa",
            "last4": "4242",
            "type": "credit",
            "issuer": "HDFC",
            "international": international,
            "emi": None,
        },
        "bank": None,
        "wallet": None,
        "vpa": None,
        "email": email,
        "contact": contact,
        "customer_id": customer_id,
        "captured": status == "captured",
        "international": international,
        "amount_refunded": 0,
        "refund_status": None,
        "created_at": created_at,
        "notes": {},
    }


def mock_order(
    order_id: str = "order_DBJOWzybf0sJbb",
    amount: int = 849900,
    status: str = "paid",
    receipt: str = "ORD-1234",
    created_at: int | None = None,
    item: str = "Wireless Headphones (Sony WH-1000XM5)",
    quantity: str = "1",
) -> dict:
    """Mock Razorpay order entity matching /v1/orders/:id response."""
    if created_at is None:
        created_at = int(time.time()) - (6 * 24 * 3600)

    return {
        "id": order_id,
        "entity": "order",
        "amount": amount,
        "amount_paid": amount,
        "amount_due": 0,
        "currency": "INR",
        "receipt": receipt,
        "status": status,
        "notes": {
            "item": item,
            "quantity": quantity,
        },
        "created_at": created_at,
    }


def mock_customer(
    customer_id: str = "cust_1Aa00000000004",
    name: str = "Arjun Mehta",
    email: str = "arjun@example.com",
    contact: str = "+919876543210",
    created_at: int | None = None,
) -> dict:
    """Mock Razorpay customer entity matching /v1/customers/:id response."""
    if created_at is None:
        created_at = int(time.time()) - (90 * 24 * 3600)

    return {
        "id": customer_id,
        "entity": "customer",
        "name": name,
        "email": email,
        "contact": contact,
        "gstin": None,
        "notes": {},
        "created_at": created_at,
    }


def mock_refund(
    refund_id: str = "rfnd_FgR09UxRiEwYon",
    payment_id: str = "pay_EsyWjHrfzb59eR",
    amount: int = 849900,
    status: str = "processed",
    created_at: int | None = None,
) -> dict:
    """Mock Razorpay refund entity matching /v1/refunds/:id response."""
    if created_at is None:
        created_at = int(time.time()) - (1 * 24 * 3600)

    return {
        "id": refund_id,
        "entity": "refund",
        "amount": amount,
        "currency": "INR",
        "payment_id": payment_id,
        "status": status,
        "speed_processed": "normal",
        "speed_requested": "normal",
        "created_at": created_at,
        "notes": {},
    }


def mock_webhook_dispute_created(
    dispute_id: str = "disp_AHfqOvkldwsbqt",
    payment_id: str = "pay_EsyWjHrfzb59eR",
    amount: int = 849900,
) -> dict:
    """Mock Razorpay webhook payload for payment.dispute.created event."""
    return {
        "entity": "event",
        "account_id": "acc_BFQ7uGkUGKwZFj",
        "event": "payment.dispute.created",
        "contains": ["payment", "dispute"],
        "created_at": int(time.time()),
        "payload": {
            "payment": {
                "entity": mock_payment(payment_id=payment_id, amount=amount),
            },
            "dispute": {
                "entity": mock_dispute(
                    dispute_id=dispute_id,
                    payment_id=payment_id,
                    amount=amount,
                ),
            },
        },
    }


def mock_webhook_dispute_won(
    dispute_id: str = "disp_AHfqOvkldwsbqt",
    payment_id: str = "pay_EsyWjHrfzb59eR",
) -> dict:
    """Mock webhook payload for payment.dispute.won."""
    return {
        "entity": "event",
        "account_id": "acc_BFQ7uGkUGKwZFj",
        "event": "payment.dispute.won",
        "contains": ["payment", "dispute"],
        "created_at": int(time.time()),
        "payload": {
            "payment": {
                "entity": mock_payment(payment_id=payment_id),
            },
            "dispute": {
                "entity": mock_dispute(
                    dispute_id=dispute_id,
                    payment_id=payment_id,
                    status="won",
                ),
            },
        },
    }
