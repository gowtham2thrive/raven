# Canonical Evidence Model

> Schema reference for RAVEN's business-agnostic evidence system.
>
> Source: [`schemas.py`](file:///c:/Users/gowth/Desktop/raven/server/app/core/schemas.py) · [`types.py`](file:///c:/Users/gowth/Desktop/raven/server/app/core/types.py) · [`ingest.py`](file:///c:/Users/gowth/Desktop/raven/server/app/pipeline/ingest.py)

---

## Design Principle

RAVEN normalizes all source data into a canonical evidence model at the boundary. The investigation engine operates on canonical evidence — never on any single merchant's database structure.

```
Business A                          Business B
order.shipped_at                    service.completed_at
order.delivered_at                  customer.confirmed_at
        │                                   │
        ▼                                   ▼
Canonical Fulfillment Evidence      Canonical Service Evidence
```

Merchant-specific logic belongs at the **boundary** (normalizer/connector layer). It never leaks into the analysis, agent, or decision layers.

---

## Evidence Schema

Every evidence item carries these fields:

```python
class Evidence(BaseModel):
    # ── Identity ──────────────────────────────────────────
    evidence_id: str          # ev_001, ev_002, ...
    case_id: str              # Parent case ID

    # ── Classification ────────────────────────────────────
    category: EvidenceCategory       # What kind of evidence
    status: EvidenceStatus           # Availability state

    # ── Source Traceability ───────────────────────────────
    source_system: str               # "razorpay", "merchant_shipping"
    source_record_id: str            # Original ID in the source system
    source_url: str | None           # API endpoint or reference URL

    # ── Temporal ──────────────────────────────────────────
    event_time: datetime | None      # When the event happened (original)
    event_timezone: str | None       # Original timezone, e.g. "Asia/Kolkata"
    event_time_utc: datetime | None  # Normalized to UTC
    timezone_confident: bool         # False if timezone was guessed
    observed_at: datetime            # When RAVEN retrieved this evidence

    # ── Content ───────────────────────────────────────────
    content: dict[str, Any]          # Structured evidence data
    summary: str                     # Human-readable one-liner

    # ── Assessment ────────────────────────────────────────
    relevance: str                   # How relevant to this dispute type
    reliability: str                 # How reliable is this source
```

### Key Design Decisions

1. **Source traceability** — Every evidence item records WHERE it came from (`source_system`, `source_record_id`). The question "which source record supports this claim?" is always answerable.

2. **Timezone handling** — All timestamps are normalized to UTC while preserving the original timezone. A 12-hour timezone error can make a legitimate delivery appear to happen before the order.

3. **Status is not binary** — Evidence is not yes/no. RAVEN tracks six distinct availability states.

4. **Reliability scoring** — Each evidence item has a reliability assessment based on the strength of the source.

5. **Relevance classification** — Each evidence item is classified by relevance to the specific dispute claim (critical, supporting, contextual, irrelevant), used for dynamic scoring weights.

---

## Evidence Categories

| Category | Enum Value | Description | Source (MVP) |
|---|---|---|---|
| Payment | `PAYMENT` | Payment transaction details | Razorpay Payment API |
| Order | `ORDER` | Order details and items | Razorpay Order API |
| Shipping | `SHIPPING` | Carrier tracking data | Merchant shipping |
| Delivery | `DELIVERY` | Delivery proof | Merchant/carrier |
| Authentication | `AUTHENTICATION` | OTP/3DS verification | Merchant auth service |
| Communication | `COMMUNICATION` | Support tickets, emails | Merchant CRM |
| Refund | `REFUND` | Refund history | Razorpay Refunds API |
| Service | `SERVICE` | Digital service / access logs | Merchant platform |
| Policy | `POLICY` | Applicable policies and terms | Merchant legal |
| Device | `DEVICE` | Device fingerprint, session data | Merchant analytics |
| Other | `OTHER` | Any additional evidence | Various |

### MVP Evidence (Active)

For `PRODUCT_NOT_RECEIVED`, 7 categories are actively gathered:

```
PAYMENT  ·  ORDER  ·  SHIPPING  ·  DELIVERY  ·  AUTHENTICATION  ·  COMMUNICATION  ·  REFUND
```

---

## Evidence Statuses

| Status | Enum Value | Meaning | Score Impact |
|---|---|---|---|
| Available | `AVAILABLE` | Evidence found and retrieved | ×1.0 (full credit) |
| Missing | `MISSING` | Expected evidence not found | ×0.0 (no credit) |
| Conflicting | `CONFLICTING` | Multiple sources disagree | ×-0.3 (penalty) |
| Unverified | `UNVERIFIED` | Evidence exists but not independently verified | ×0.5 (half credit) |
| Not Applicable | `NOT_APPLICABLE` | This evidence type doesn't apply | Excluded |
| Ingestion Error | `INGESTION_ERROR` | Evidence retrieval or parsing failed | ×0.0 (no credit) |

### Evidence Relevance

Each evidence item is classified by relevance to the specific dispute claim. The ADK agent determines relevance based on the customer's claim text. Relevance dynamically weights evidence for scoring.

| Relevance | Enum Value | Scoring Weight |
|---|---|---|
| Critical | `CRITICAL` | 0.30 |
| Supporting | `SUPPORTING` | 0.15 |
| Contextual | `CONTEXTUAL` | 0.05 |
| Irrelevant | `IRRELEVANT` | 0.00 |

### Status Determination Logic

```
Evidence is NULL?
    └── YES → MISSING

Evidence data exists?
    └── YES → Check quality:
        ├── Has independent verification (signature, OTP) → AVAILABLE
        ├── Exists but unverified (left at door, no sig) → UNVERIFIED
        ├── Multiple sources disagree → CONFLICTING
        └── Not relevant to case → NOT_APPLICABLE
```

---

## Evidence Category Details

### Payment Evidence

**Source:** Razorpay Payment API
**Normalizer:** `normalize_razorpay_payment()`

```json
{
  "category": "payment",
  "status": "available",
  "source_system": "razorpay",
  "content": {
    "payment_id": "pay_BK7...",
    "amount": 849900,
    "currency": "INR",
    "status": "captured",
    "method": "card",
    "card_network": "Visa",
    "card_last4": "4242",
    "card_type": "credit",
    "card_issuer": "HDFC",
    "international": false,
    "email": "customer@email.com",
    "contact": "+91...",
    "captured": true
  },
  "summary": "Payment of Rs.8,499.00 via card (Visa ending 4242), status: captured",
  "relevance": "high",
  "reliability": "high"
}
```

### Order Evidence

**Source:** Razorpay Order API
**Normalizer:** `normalize_razorpay_order()`

```json
{
  "category": "order",
  "status": "available",
  "source_system": "razorpay",
  "content": {
    "order_id": "order_EK...",
    "amount": 849900,
    "receipt": "ORD-2025-001",
    "status": "paid",
    "item": "Samsung Galaxy Watch 6",
    "quantity": "1"
  },
  "summary": "Order ORD-2025-001 — Samsung Galaxy Watch 6, amount: Rs.8,499.00",
  "relevance": "high",
  "reliability": "high"
}
```

### Shipping Evidence

**Source:** Merchant shipping system
**Normalizer:** `normalize_shipping()`

```json
{
  "category": "shipping",
  "status": "available",
  "source_system": "merchant_shipping",
  "content": {
    "carrier": "Delhivery",
    "tracking_id": "DLV2025001234",
    "status": "delivered",
    "origin_city": "Mumbai",
    "destination_city": "Bangalore"
  },
  "summary": "Shipped via Delhivery (tracking: DLV2025001234), status: delivered",
  "relevance": "high",
  "reliability": "medium"
}
```

When shipping data is `null`:

```json
{
  "category": "shipping",
  "status": "missing",
  "summary": "No shipping records found",
  "reliability": "unknown"
}
```

### Delivery Evidence

**Source:** Merchant delivery system
**Normalizer:** `normalize_delivery()`

This is the **highest-weighted** evidence for `PRODUCT_NOT_RECEIVED` disputes (weight: 0.30).

**Reliability determination:**

| Condition | Status | Reliability |
|---|---|---|
| Signed by recipient | `available` | `high` |
| Left at door / mailbox | `unverified` | `medium` |
| Other proof type | `unverified` | `low` |
| No delivery data | `missing` | `unknown` |

```json
{
  "category": "delivery",
  "status": "available",
  "source_system": "merchant_delivery",
  "content": {
    "delivered_at": "2025-12-31T14:30:00",
    "signed_by": "Amit Kumar",
    "delivery_address": "HSR Layout, Bangalore",
    "proof_type": "signature",
    "photo_proof": true,
    "source": "merchant"
  },
  "summary": "Delivery confirmed, signed by Amit Kumar, with photo proof (proof: signature)",
  "relevance": "critical",
  "reliability": "high"
}
```

### Authentication Evidence

**Source:** Merchant auth service
**Normalizer:** `normalize_auth()`

```json
{
  "category": "authentication",
  "status": "available",
  "source_system": "merchant_auth",
  "content": {
    "method": "OTP",
    "verified": true,
    "device_known": true,
    "ip_country": "IN"
  },
  "summary": "Authentication: OTP (verified), device known, IP country: IN",
  "relevance": "medium",
  "reliability": "high"
}
```

### Communication Evidence

**Source:** Merchant CRM
**Normalizer:** `normalize_communications()`

```json
{
  "category": "communication",
  "status": "available",
  "source_system": "merchant_crm",
  "content": {
    "ticket_count": 2,
    "tickets": [
      {
        "type": "complaint",
        "timestamp": "2025-12-31T16:00:00",
        "channel": "email",
        "summary": "Customer asked about delivery status",
        "direction": "inbound"
      }
    ]
  },
  "summary": "2 communication(s): Customer asked about delivery status",
  "relevance": "medium",
  "reliability": "medium"
}
```

### Refund Evidence

**Source:** Razorpay Refunds API
**Normalizer:** `normalize_razorpay_refunds()`

When refunds exist (potential double recovery):

```json
{
  "category": "refund",
  "status": "available",
  "content": {
    "refund_count": 1,
    "total_refunded": 849900,
    "refunds": [
      {
        "id": "rfnd_...",
        "amount": 849900,
        "status": "processed",
        "created_at": 1735603200
      }
    ]
  },
  "summary": "1 refund(s) totaling Rs.8,499.00"
}
```

When no refunds exist:

```json
{
  "category": "refund",
  "status": "not_applicable",
  "summary": "No refunds issued for this payment"
}
```

---

## Contradiction Schema

Detected conflicts between evidence items:

```python
class Contradiction(BaseModel):
    contradiction_id: str          # contra_001
    case_id: str                   # Parent case ID

    evidence_a_id: str             # First conflicting evidence
    evidence_a_claim: str          # What evidence A says
    evidence_b_id: str             # Second conflicting evidence
    evidence_b_claim: str          # What evidence B says

    impact: str                    # "high" | "medium" | "low"
    description: str               # Human-readable explanation
    requires_human_review: bool    # Should a human look at this?

    detected_at: datetime
```

---

## Database Storage

Evidence is stored in the `evidence_items` table with these columns:

| Column | Type | Description |
|---|---|---|
| `id` | String(32) | Primary key (e.g., `ev_abc123`) |
| `case_id` | String(32) | Foreign key to `cases` |
| `category` | String(32) | Evidence category |
| `status` | String(16) | Evidence status |
| `source_system` | String(64) | Source identifier |
| `source_record_id` | String(128) | Original record ID |
| `source_url` | String(512) | API endpoint reference |
| `event_time` | DateTime | Original event time |
| `event_timezone` | String(64) | Original timezone |
| `event_time_utc` | DateTime | Normalized UTC time |
| `timezone_confident` | Boolean | Timezone certainty flag |
| `observed_at` | DateTime | When RAVEN retrieved this |
| `content` | JSON | Structured evidence data |
| `summary` | Text | Human-readable summary |
| `relevance` | String(32) | Relevance assessment |
| `reliability` | String(32) | Reliability assessment |

### Indexes

| Index | Columns | Purpose |
|---|---|---|
| `ix_evidence_category` | `category` | Filter by category |
| `ix_evidence_case_category` | `case_id`, `category` | Case-specific category lookup |
