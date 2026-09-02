# RAVEN API Reference

> Complete REST API documentation for the chargeback investigation system.
>
> Interactive OpenAPI docs available at: `http://localhost:8000/docs`

---

## Base URL

| Environment | URL |
|---|---|
| Development | `http://localhost:8000` |
| Docker | `http://localhost:8000` |

---

## Authentication

The MVP does not enforce API authentication. In production, all endpoints should be protected with appropriate authentication and authorization.

---

## Endpoints Overview

### Cases & Core

| # | Method | Endpoint | Purpose | Tags |
|---|---|---|---|---|
| 1 | `GET` | `/health` | Service health check | System |
| 2 | `POST` | `/webhooks/razorpay` | Receive Razorpay dispute webhooks | Webhooks |
| 3 | `GET` | `/cases/` | List cases with filters & pagination | Cases |
| 4 | `GET` | `/cases/{case_id}` | Full case detail with all relationships | Cases |
| 5 | `POST` | `/cases/{case_id}/investigate` | Trigger investigation pipeline | Cases |
| 6 | `GET` | `/cases/{case_id}/evidence` | Evidence items for a case | Cases |
| 7 | `GET` | `/cases/{case_id}/timeline` | Reconstructed timeline events | Cases |
| 8 | `GET` | `/cases/{case_id}/assessment` | Assessment score & recommendation | Cases |
| 9 | `GET` | `/cases/{case_id}/response` | Draft response for Razorpay submission | Cases |
| 10 | `GET` | `/cases/{case_id}/audit` | Full audit trail | Cases |
| 11 | `POST` | `/cases/{case_id}/review` | Human review decision | Cases |
| 12 | `POST` | `/cases/{case_id}/submit` | Submit contest to Razorpay | Cases |
| 13 | `POST` | `/cases/batch-investigate` | Batch investigate all pending cases | Cases |
| 14 | `POST` | `/cases/batch-submit` | Batch submit all approved cases | Cases |
| 15 | `DELETE` | `/cases/` | Clear all cases | Cases |
| 16 | `POST` | `/cases/clear` | Clear all cases (POST alias) | Cases |
| 17 | `GET` | `/cases/{case_id}/investigate/stream` | Live SSE investigation stream | Stream |
| 18 | `GET` | `/metrics/summary` | Dashboard stat card values | Metrics |
| 19 | `GET` | `/metrics/breakdown` | Status & recommendation breakdown | Metrics |
| 20 | `GET` | `/models/` | List available AI models | Models |

### Simulator

| # | Method | Endpoint | Purpose | Tags |
|---|---|---|---|---|
| 21 | `GET` | `/simulator/presets` | List simulation presets | Simulator |
| 22 | `POST` | `/simulator/generate` | Generate a simulated case | Simulator |
| 23 | `POST` | `/simulator/clear` | Purge all simulated cases | Simulator |

### Integrations

| # | Method | Endpoint | Purpose | Tags |
|---|---|---|---|---|
| 24 | `GET` | `/integrations` | List all integrations | Integrations |
| 25 | `POST` | `/integrations` | Create a new integration | Integrations |
| 26 | `POST` | `/integrations/upload` | File upload (CSV, Excel, PDF) | Integrations |
| 27 | `GET` | `/integrations/types/available` | List available integration types | Integrations |
| 28 | `GET` | `/integrations/categories/available` | List evidence categories | Integrations |
| 29 | `GET` | `/integrations/{id}` | Get integration detail | Integrations |
| 30 | `PUT` | `/integrations/{id}` | Update integration config | Integrations |
| 31 | `DELETE` | `/integrations/{id}` | Remove integration | Integrations |
| 32 | `POST` | `/integrations/{id}/test` | Test connectivity + sample | Integrations |
| 33 | `GET` | `/integrations/{id}/sample` | Preview with field mappings | Integrations |
| 34 | `PUT` | `/integrations/{id}/mappings` | Save field mappings | Integrations |
| 35 | `GET` | `/integrations/{id}/mappings` | Get field mappings | Integrations |
| 36 | `POST` | `/integrations/{id}/sync` | Manually trigger data fetch | Integrations |
| 37 | `POST` | `/integrations/{id}/activate` | Activate integration | Integrations |
| 38 | `POST` | `/integrations/{id}/deactivate` | Deactivate integration | Integrations |

### Settings

| # | Method | Endpoint | Purpose | Tags |
|---|---|---|---|---|
| 39 | `GET` | `/settings/credentials/status` | Masked credential status | Settings |
| 40 | `POST` | `/settings/credentials/validate` | Validate credentials against live APIs | Settings |
| 41 | `GET` | `/settings/guardrails` | Get auto-pilot guardrail config | Settings |
| 42 | `PUT` | `/settings/guardrails` | Update guardrail config | Settings |

---

## System

### `GET /health`

Service health check. Returns the current mode (ADK vs deterministic) and configured model.

**Response:**

```json
{
  "status": "ok",
  "service": "raven",
  "version": "0.1.0",
  "agent_mode": "adk",
  "agent_model": "gemini-3.6-flash"
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | Always `"ok"` if service is running |
| `agent_mode` | string | `"adk"` if Gemini API key configured, `"deterministic"` otherwise |
| `agent_model` | string\|null | Model name when ADK mode, `null` otherwise |

---

## Webhooks

### `POST /webhooks/razorpay`

Receive a Razorpay dispute webhook event. Creates a case and auto-triggers investigation.

**Request Body:**

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

**Response (201 Created):**

```json
{
  "status": "processed",
  "event": "payment.dispute.created",
  "case_id": "CASE-00001"
}
```

**Supported Events:**

| Event | Action |
|---|---|
| `payment.dispute.created` | Create case + auto-investigate |
| `payment.dispute.action_required` | Re-investigate |
| `payment.dispute.won` | Update outcome to "won" |
| `payment.dispute.lost` | Update outcome to "lost" |
| Other | Ignored |

**Idempotency:** Duplicate webhooks for the same `dispute_id` return the existing case without re-creating.

---

## Cases

### `GET /cases/`

List cases with optional filtering, sorting, and pagination.

**Query Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `status` | string | — | Filter by case status |
| `recommendation` | string | — | Filter by recommendation |
| `sort_by` | string | `created_at` | Sort column |
| `sort_dir` | string | `desc` | Sort direction: `asc` or `desc` |
| `page` | int | `1` | Page number (≥ 1) |
| `per_page` | int | `20` | Items per page (1–100) |

**Response:**

```json
{
  "cases": [
    {
      "case_id": "CASE-00001",
      "status": "approved",
      "dispute_reason": "product_not_received",
      "rzp_dispute_id": "disp_AYz...",
      "rzp_payment_id": "pay_BK7...",
      "rzp_order_id": "order_EK...",
      "amount": 849900,
      "currency": "INR",
      "reason_code": "chargeback",
      "reason_description": "Product not received",
      "dispute_phase": "chargeback",
      "respond_by": "2025-01-01T00:00:00+00:00",
      "case_strength": "high",
      "recommendation": "contest",
      "confidence": "high",
      "assessment_score": 1.0,
      "review_decision": null,
      "reviewed_by": null,
      "reviewed_at": null,
      "outcome": null,
      "created_at": "2025-12-30T10:00:00+00:00",
      "updated_at": "2025-12-30T10:01:00+00:00"
    }
  ],
  "total": 50,
  "page": 1,
  "per_page": 20
}
```

---

### `GET /cases/{case_id}`

Get full case details with all relationships (evidence, timeline, contradictions, assessment, audit trail).

**Path Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `case_id` | string | Case identifier (e.g., `CASE-00001`) |

**Response:**

```json
{
  "case": { "..." },
  "evidence": [
    {
      "evidence_id": "ev_abc123",
      "category": "payment",
      "status": "available",
      "source_system": "razorpay",
      "source_record_id": "pay_BK7...",
      "event_time_utc": "2025-12-30T10:41:00+00:00",
      "timezone_confident": true,
      "content": {
        "payment_id": "pay_BK7...",
        "amount": 849900,
        "method": "card",
        "card_network": "Visa",
        "card_last4": "4242",
        "status": "captured"
      },
      "summary": "Payment of Rs.8,499.00 via card (Visa ending 4242), status: captured",
      "relevance": "high",
      "reliability": "high"
    }
  ],
  "timeline": [
    {
      "event_id": "tl_abc123",
      "timestamp_utc": "2025-12-30T10:41:00+00:00",
      "timezone_confident": true,
      "label": "Payment captured (card)",
      "description": "Rs.8,499.00 via Visa ending 4242",
      "category": "payment",
      "source_system": "razorpay"
    }
  ],
  "contradictions": [
    {
      "contradiction_id": "contra_abc123",
      "evidence_a_id": "ev_001",
      "evidence_a_claim": "Delivery confirmed: ...",
      "evidence_b_id": "ev_002",
      "evidence_b_claim": "Carrier status: returned_to_sender",
      "impact": "high",
      "description": "Merchant delivery records show delivered, but carrier says returned.",
      "requires_human_review": true
    }
  ],
  "assessment": {
    "score": 0.85,
    "strength": "high",
    "recommendation": "contest",
    "confidence": "high",
    "data": {
      "methodology": "weighted_evidence_checklist_v1",
      "reasons": ["..."],
      "checklist": ["..."]
    }
  },
  "response_draft": "We are contesting this dispute...",
  "audit": [
    {
      "id": "audit_abc123",
      "timestamp": "2025-12-30T10:00:00+00:00",
      "action": "case_created",
      "actor": "system:webhook",
      "details": { "dispute_id": "disp_AYz..." }
    }
  ]
}
```

**Errors:**

| Status | Description |
|---|---|
| `404` | Case not found |

---

### `POST /cases/{case_id}/investigate`

Trigger the full investigation pipeline. Idempotent — re-investigating updates evidence, doesn't duplicate.

**Response:**

```json
{
  "case_id": "CASE-00001",
  "status": "investigated",
  "evidence_count": 7,
  "contradiction_count": 0,
  "timeline_event_count": 5,
  "score": 1.0,
  "recommendation": "contest",
  "auto_submit_eligible": true
}
```

**Errors:**

| Status | Description |
|---|---|
| `400` | Invalid state transition |
| `404` | Case not found |
| `500` | Investigation pipeline error |

---

### `GET /cases/{case_id}/evidence`

Get all evidence items gathered for a case.

**Response:**

```json
{
  "evidence": [
    {
      "evidence_id": "ev_abc123",
      "category": "payment",
      "status": "available",
      "source_system": "razorpay",
      "source_record_id": "pay_BK7...",
      "event_time_utc": "2025-12-30T10:41:00+00:00",
      "timezone_confident": true,
      "content": { "..." },
      "summary": "Payment of Rs.8,499.00 ...",
      "relevance": "high",
      "reliability": "high"
    }
  ]
}
```

---

### `GET /cases/{case_id}/timeline`

Get the reconstructed chronological timeline for a case.

**Response:**

```json
{
  "timeline": [
    {
      "event_id": "tl_abc123",
      "timestamp_utc": "2025-12-30T10:41:00+00:00",
      "timezone_confident": true,
      "label": "Payment captured (card)",
      "description": "Rs.8,499.00 via Visa ending 4242",
      "category": "payment",
      "source_system": "razorpay"
    }
  ]
}
```

---

### `GET /cases/{case_id}/assessment`

Get the case assessment (score, strength, recommendation).

**Response:**

```json
{
  "assessment": {
    "score": 1.0,
    "strength": "high",
    "recommendation": "contest",
    "confidence": "high",
    "auto_submit_eligible": true,
    "data": {
      "methodology": "weighted_evidence_checklist_v1",
      "reasons": [
        "Evidence score: 1.00 (high strength)",
        "Evidence available: Payment confirmation, Order details, ...",
        "Recommendation: CONTEST — sufficient evidence to dispute"
      ],
      "checklist": [
        {
          "category": "payment",
          "label": "Payment confirmation",
          "status": "available",
          "weight": 0.15,
          "required": true
        }
      ]
    }
  }
}
```

---

### `GET /cases/{case_id}/response`

Get the draft response generated for Razorpay submission.

**Response:**

```json
{
  "response_draft": "We are contesting this dispute. The customer claims...",
  "evidence_ids": ["ev_001", "ev_002", "ev_003"]
}
```

---

### `GET /cases/{case_id}/audit`

Get the full audit trail for a case.

**Response:**

```json
{
  "audit": [
    {
      "id": "audit_abc123",
      "timestamp": "2025-12-30T10:00:00+00:00",
      "action": "case_created",
      "actor": "system:webhook",
      "details": { "dispute_id": "disp_AYz...", "amount": 849900 }
    },
    {
      "id": "audit_def456",
      "timestamp": "2025-12-30T10:00:01+00:00",
      "action": "investigation_started",
      "actor": "system:runner",
      "details": {}
    },
    {
      "id": "audit_ghi789",
      "timestamp": "2025-12-30T10:00:02+00:00",
      "action": "investigation_completed",
      "actor": "system:runner",
      "details": {
        "evidence_count": 7,
        "contradiction_count": 0,
        "score": 1.0,
        "recommendation": "contest",
        "status": "approved"
      }
    }
  ]
}
```

---

## Review

### `POST /cases/{case_id}/review`

Apply a human review decision to a case.

**Request Body:**

```json
{
  "decision": "approve",
  "notes": "Evidence is conclusive. Approve for submission.",
  "reviewed_by": "analyst@raven.dev"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `decision` | string | ✅ | `"approve"`, `"reject"`, or `"escalate"` |
| `notes` | string | ❌ | Reviewer notes |
| `reviewed_by` | string | ❌ | Reviewer identifier (default: `analyst@raven.dev`) |

**Response:**

```json
{
  "case_id": "CASE-00001",
  "status": "approved",
  "decision": "approve",
  "reviewed_by": "analyst@raven.dev"
}
```

**Decision → Status Mapping:**

| Decision | Target Status | Next Action |
|---|---|---|
| `approve` | `APPROVED` | Eligible for submission |
| `reject` | `REJECTED` | Case closed (accept loss) |
| `escalate` | `ESCALATED` | Senior review required |

**Errors:**

| Status | Description |
|---|---|
| `400` | Invalid decision or state transition |
| `404` | Case not found |

---

### `POST /cases/{case_id}/submit`

Submit the contest to Razorpay. Level 4 action — requires explicit authorization.

**Precondition:** Case status must be `APPROVED`.

**Request Body:**

```json
{
  "confirmed": true
}
```

**Response:**

```json
{
  "case_id": "CASE-00001",
  "status": "submitted",
  "dispute_id": "disp_AYz...",
  "submitted_at": "2025-12-30T12:00:00+00:00",
  "note": "MVP: Submission simulated. In production, this contests via Razorpay Disputes API."
}
```

**Errors:**

| Status | Description |
|---|---|
| `400` | Case not in `APPROVED` status, or `confirmed` is false |
| `404` | Case not found |

---

## Stream

### `GET /cases/{case_id}/investigate/stream`

Live investigation stream via Server-Sent Events (SSE). Connect with `EventSource` in the browser.

**Response:** `text/event-stream`

**Event Types:**

| Event | Data | Description |
|---|---|---|
| `step` | `{tool, status, step, total}` | Tool being called |
| `evidence` | `{category, status, summary}` | Evidence item discovered |
| `thinking` | `{message}` | Agent reasoning message |
| `contradiction` | `{type, description, impact}` | Conflict detected |
| `result` | `{score, strength, recommendation, confidence, auto_submit, contradictions, missing_evidence, evidence_count}` | Final assessment |
| `error` | `{message}` | Error occurred |
| `done` | `{case_id, mode, result}` | Investigation complete |

**Example SSE Output:**

```
event: step
data: {"tool": "get_transaction", "status": "calling", "step": 1, "total": 7}

event: evidence
data: {"category": "payment", "status": "available", "summary": "Payment of Rs.8,499.00 via card"}

event: thinking
data: {"message": "Payment and order data retrieved. Checking delivery records..."}

event: result
data: {"score": 1.0, "strength": "high", "recommendation": "contest", "confidence": "high", "auto_submit": true}

event: done
data: {"case_id": "CASE-00001", "mode": "deterministic"}
```

---

## Metrics

### `GET /metrics/summary`

Dashboard stat card values.

**Response:**

```json
{
  "total_cases": 50,
  "open_cases": 35,
  "pending_review": 10,
  "submitted": 15,
  "won": 10,
  "lost": 5,
  "win_rate": 0.67,
  "avg_score": 0.72,
  "status_breakdown": {
    "created": 5,
    "approved": 15,
    "under_review": 10,
    "submitted": 10,
    "won": 5,
    "lost": 5
  },
  "recommendation_breakdown": {
    "contest": 25,
    "human_review": 15,
    "accept_loss": 10
  }
}
```

---

### `GET /metrics/breakdown`

Dispute breakdown by status and recommendation.

**Response:**

```json
{
  "status_breakdown": { "created": 5, "approved": 15, "..." },
  "recommendation_breakdown": { "contest": 25, "..." }
}
```

---

## Error Responses

All error responses follow a consistent format:

```json
{
  "detail": "Human-readable error message"
}
```

| Status Code | Meaning |
|---|---|
| `400` | Bad request — invalid input, invalid state transition |
| `404` | Resource not found |
| `500` | Internal server error |

---

## Case Status Values

| Status | Description |
|---|---|
| `created` | Case created, awaiting investigation |
| `investigating` | Investigation in progress |
| `evidence_gathered` | Evidence collected, no assessment yet |
| `assessed` | Assessment complete |
| `draft_ready` | Response draft generated |
| `under_review` | Awaiting human review |
| `approved` | Human approved, eligible for submission |
| `rejected` | Human rejected (accept loss) |
| `escalated` | Escalated for senior review |
| `submitted` | Contest submitted to Razorpay |
| `won` | Dispute resolved in merchant's favor |
| `lost` | Dispute resolved against merchant |
| `closed` | Case closed |

---

## Evidence Categories

| Category | Description |
|---|---|
| `payment` | Payment transaction details |
| `order` | Order details (receipt, items) |
| `shipping` | Shipping carrier, tracking |
| `delivery` | Delivery proof (signature, photo) |
| `authentication` | OTP/3DS verification |
| `communication` | Customer support tickets |
| `refund` | Refund history |

## Evidence Statuses

| Status | Description |
|---|---|
| `available` | Evidence found and retrieved |
| `missing` | Expected evidence not found |
| `conflicting` | Multiple sources disagree |
| `unverified` | Evidence exists but not independently verified |
| `not_applicable` | This evidence type doesn't apply |
| `ingestion_error` | Evidence retrieval or parsing failed |

---

## Models

### `GET /models/`

List available LLM models for investigation. Returns models fetched from Google API with pricing and speed info.

**Response:**

```json
{
  "models": [
    {
      "id": "gemini-3.6-flash",
      "name": "Gemini 3.6 Flash",
      "tier": "Free / Economy",
      "price": "Free Tier / $0.10 per 1M",
      "speed": "⚡ Ultra Fast (~1.5s)",
      "badge": "Recommended",
      "description": "Optimal balance of dispute reasoning speed and cost efficiency.",
      "is_default": true
    }
  ],
  "default": "gemini-3.6-flash",
  "llm_configured": true
}
```

---

## Simulator

### `GET /simulator/presets`

List available dispute simulation presets (evidence profiles for case generation).

**Response:**

```json
{
  "presets": [
    {
      "id": "strong_defense",
      "name": "Strong Defense",
      "description": "All evidence present, signed delivery, verified auth"
    }
  ]
}
```

---

### `POST /simulator/generate`

Generate a new simulated dispute case from a preset profile.

**Request Body:**

```json
{
  "preset_id": "strong_defense",
  "auto_investigate": true
}
```

**Response:** Created case object with investigation results (if `auto_investigate` is true).

---

### `POST /simulator/clear`

Purge all cases and related records from the database.

**Response:**

```json
{
  "status": "success",
  "deleted_count": 50,
  "message": "Successfully purged 50 cases from database."
}
```

---

## Batch Operations

### `POST /cases/batch-investigate`

Auto-investigate all pending (status=`created`) cases in one request.

**Response:**

```json
{
  "processed_count": 10,
  "successful_count": 9,
  "results": [
    {
      "case_id": "CASE-00001",
      "status": "success",
      "score": 1.0,
      "recommendation": "contest",
      "auto_submit_eligible": true
    }
  ]
}
```

---

### `POST /cases/batch-submit`

Auto-submit all approved cases to Razorpay in one request.

**Response:**

```json
{
  "submitted_count": 5,
  "results": [
    { "case_id": "CASE-00001", "status": "submitted" }
  ]
}
```

---

### `DELETE /cases/` · `POST /cases/clear`

Purge all cases and related records. Supports both DELETE and POST methods.

**Response:**

```json
{
  "status": "success",
  "deleted_count": 50,
  "message": "Successfully purged 50 cases from database."
}
```

---

## Integrations

### `GET /integrations`

List all configured data source integrations.

**Response:**

```json
{
  "integrations": [
    {
      "id": "intg_abc123",
      "name": "Shipping API",
      "integration_type": "rest_api",
      "evidence_category": "shipping",
      "status": "active",
      "last_sync_at": "2026-01-15T10:00:00+00:00",
      "sync_count": 42
    }
  ]
}
```

---

### `POST /integrations`

Create a new integration. Configuration schema varies by integration type.

**Integration Types:** `rest_api`, `database`, `file_upload`, `webhook`, `carrier`

---

### `POST /integrations/upload`

Upload a file (CSV, Excel, PDF) as an evidence source.

---

### `GET /integrations/types/available`

List supported integration types.

---

### `GET /integrations/categories/available`

List all evidence categories that integrations can map to.

---

### `GET /integrations/{id}`

Get full integration detail including configuration and sync state.

---

### `PUT /integrations/{id}`

Update integration configuration.

---

### `DELETE /integrations/{id}`

Remove an integration and its field mappings.

---

### `POST /integrations/{id}/test`

Test connectivity to the integration source. Returns a sample record if successful.

---

### `GET /integrations/{id}/sample`

Preview data with current field mappings applied.

---

### `PUT /integrations/{id}/mappings`

Save field mappings that translate source fields to canonical evidence fields.

---

### `GET /integrations/{id}/mappings`

Get current field mappings for an integration.

---

### `POST /integrations/{id}/sync`

Manually trigger a data fetch from the integration source.

---

### `POST /integrations/{id}/activate`

Activate an integration so it participates in evidence gathering.

---

### `POST /integrations/{id}/deactivate`

Deactivate an integration without deleting it.

---

## Settings

### `GET /settings/credentials/status`

Return which credentials are configured, with masked previews. Does not expose actual values.

**Response:**

```json
{
  "gemini_api_key": {
    "label": "Gemini API Key",
    "configured": true,
    "masked_value": "AIza••••••••••••••ey"
  },
  "razorpay_key_id": {
    "label": "Razorpay Key ID",
    "configured": true,
    "masked_value": "rzp_••••••••••••••st"
  }
}
```

---

### `POST /settings/credentials/validate`

Validate configured credentials against live APIs (Gemini, Razorpay).

---

### `GET /settings/guardrails`

Get current auto-pilot guardrail configuration.

---

### `PUT /settings/guardrails`

Update guardrail thresholds (auto-submit score, max contradictions, etc.).
