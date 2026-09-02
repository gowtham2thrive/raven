# Razorpay Integration Guide

## Overview

RAVEN integrates with Razorpay's Disputes API to receive chargeback notifications and respond with evidence.

## Webhook Setup

### 1. Register Webhook URL

In Razorpay Dashboard → Settings → Webhooks:
- **URL**: `https://your-domain.com/webhooks/razorpay`
- **Events**: Select all `payment.dispute.*` events

### 2. Supported Events

| Event | Action |
|---|---|
| `payment.dispute.created` | Create case + auto-investigate |
| `payment.dispute.won` | Update case outcome to "won" |
| `payment.dispute.lost` | Update case outcome to "lost" |
| `payment.dispute.closed` | Close case |
| `payment.dispute.under_review` | Update dispute status |
| `payment.dispute.action_required` | Flag for urgent review |

### 3. Webhook Payload

```json
{
  "event": "payment.dispute.created",
  "payload": {
    "dispute": {
      "entity": {
        "id": "disp_AYz...",
        "payment_id": "pay_BK7...",
        "amount": 849900,
        "currency": "INR",
        "reason_code": "chargeback",
        "reason_description": "Product not received",
        "phase": "chargeback",
        "status": "open",
        "respond_by_date": 1735689600,
        "created_at": 1735603200
      }
    }
  }
}
```

## API Flow

### Automated (MVP)

```
1. Webhook received
2. Case created (idempotent on dispute_id)
3. Investigation runs automatically
4. Evidence gathered from synthetic/mock data
5. Assessment scored
6. High-confidence cases auto-approved
7. Uncertain cases routed to human review
```

### Production (Future)

```
1. Webhook received
2. Case created
3. Fetch real data via Razorpay APIs:
   - GET /v1/payments/{id}
   - GET /v1/orders/{id}
   - GET /v1/customers/{id}
   - GET /v1/payments/{id}/refunds
4. Fetch merchant data (shipping, delivery, auth)
5. Investigation + assessment
6. Human approves
7. Upload evidence: POST /v1/documents
8. Contest dispute: PATCH /v1/disputes/{id}/contest
```

## API Keys

### Environment Variables

```env
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
```

### Test Mode vs Production

| Mode | Key Prefix | Behavior |
|---|---|---|
| Test | `rzp_test_` | Uses synthetic data, no real transactions |
| Live | `rzp_live_` | Real payments, real disputes |

## Idempotency

RAVEN handles duplicate webhooks safely:
- Each case is uniquely identified by `rzp_dispute_id`
- Duplicate webhooks for the same dispute return the existing case
- No double-investigation or duplicate evidence records

## Razorpay API Reference

- [Disputes API](https://razorpay.com/docs/api/disputes/)
- [Documents API](https://razorpay.com/docs/api/documents/)
- [Webhooks](https://razorpay.com/docs/webhooks/)
