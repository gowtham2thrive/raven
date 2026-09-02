# Decision Engine

> Scoring methodology, routing logic, and assessment specification.
>
> Source: [`assess.py`](file:///c:/Users/gowth/Desktop/raven/server/app/pipeline/assess.py) · [`analysis.py`](file:///c:/Users/gowth/Desktop/raven/server/app/pipeline/analysis.py)

---

## Core Principle

**The decision engine is always deterministic. The LLM never produces the score.**

A score should be reproducible from evidence and rules. The same evidence inputs always produce the same assessment output. This is not an LLM-generated number — it is a weighted sum of evidence availability.

---

## Scoring Methodology: `weighted_evidence_checklist_v1`

### Formula

```
         Σ (weight_i × multiplier_i)
score = ─────────────────────────────
              Σ (weight_i)

where i ∈ {items where status ≠ "not_applicable"}
```

- Only applicable items are included in both numerator and denominator
- Score is clamped to `[0.0, 1.0]`

### Status Multipliers

| Evidence Status | Multiplier | Rationale |
|---|---|---|
| `available` | **1.0** | Full credit — evidence found and verified |
| `unverified` | **0.5** | Half credit — evidence exists but not independently verified |
| `missing` | **0.0** | No credit — expected evidence not found |
| `conflicting` | **-0.3** | Penalty — sources disagree, weakens the case |
| `not_applicable` | excluded | Not counted in either numerator or denominator |

### Evidence Weights (PRODUCT_NOT_RECEIVED)

| # | Category | Label | Required | Weight | Rationale |
|---|---|---|---|---|---|
| 1 | `payment` | Payment confirmation | ✅ | **0.15** | Core transaction proof |
| 2 | `order` | Order details | ✅ | **0.10** | Establishes what was purchased |
| 3 | `shipping` | Shipping dispatched | ✅ | **0.15** | Shows merchant fulfilled order |
| 4 | `delivery` | Delivery confirmation | ✅ | **0.30** | **Highest weight — delivery proof is king** |
| 5 | `authentication` | Authentication (OTP/3DS) | ❌ | **0.15** | Establishes cardholder authorized |
| 6 | `communication` | Customer communication | ❌ | **0.10** | Contextual support history |
| 7 | `refund` | Refund history | ❌ | **0.05** | Double recovery check |

**Total weights: 1.00**

---

## Score Examples

### Example 1: Strong Case (Score = 1.00)

All evidence available, no contradictions.

```
Payment:        0.15 × 1.0 = 0.150  ✓ captured, Visa ending 4242
Order:          0.10 × 1.0 = 0.100  ✓ ORD-2025-001, Samsung Galaxy Watch
Shipping:       0.15 × 1.0 = 0.150  ✓ Delhivery, tracking DLV2025001234
Delivery:       0.30 × 1.0 = 0.300  ✓ signed by Amit Kumar
Authentication: 0.15 × 1.0 = 0.150  ✓ OTP verified, known device
Communication:  0.10 × 1.0 = 0.100  ✓ no complaints
Refund:         0.05 × 1.0 = 0.050  ✓ no refunds issued
──────────────────────────────────────
Score: 1.000 / 1.000 = 1.00

→ Strength: HIGH
→ Recommendation: CONTEST
→ Confidence: HIGH
→ Auto-submit: YES (score ≥ 0.80, 0 contradictions)
```

### Example 2: Weak Case (Score = 0.75)

Delivery unverified (left at door), missing communications.

```
Payment:        0.15 × 1.0 = 0.150  ✓ captured
Order:          0.10 × 1.0 = 0.100  ✓ confirmed
Shipping:       0.15 × 1.0 = 0.150  ✓ dispatched
Delivery:       0.30 × 0.5 = 0.150  ⚠ left at door, no signature
Authentication: 0.15 × 1.0 = 0.150  ✓ OTP verified
Communication:  0.10 × 0.0 = 0.000  ✗ no records found
Refund:         0.05 × 1.0 = 0.050  ✓ no refunds
──────────────────────────────────────
Score: 0.750 / 1.000 = 0.75

→ Strength: MEDIUM
→ Recommendation: HUMAN_REVIEW
→ Confidence: MEDIUM
→ Auto-submit: NO
```

### Example 3: Missing Delivery (Score = 0.45)

No delivery or shipping evidence.

```
Payment:        0.15 × 1.0 = 0.150  ✓ captured
Order:          0.10 × 1.0 = 0.100  ✓ confirmed
Shipping:       0.15 × 0.0 = 0.000  ✗ no shipping records
Delivery:       0.30 × 0.0 = 0.000  ✗ no delivery records
Authentication: 0.15 × 1.0 = 0.150  ✓ OTP verified
Communication:  0.10 × 0.0 = 0.000  ✗ no records
Refund:         0.05 × 1.0 = 0.050  ✓ no refunds
──────────────────────────────────────
Score: 0.450 / 1.000 = 0.45

→ Strength: LOW
→ Recommendation: HUMAN_REVIEW
→ Confidence: LOW
→ Auto-submit: NO
```

### Example 4: Contradictory Evidence (Score = 0.57)

Delivery evidence conflicts with carrier tracking.

```
Payment:        0.15 × 1.0 = 0.150  ✓ captured
Order:          0.10 × 1.0 = 0.100  ✓ confirmed
Shipping:       0.15 ×-0.3 =-0.045  ! carrier says "returned_to_sender"
Delivery:       0.30 × 1.0 = 0.300  ✓ merchant says "delivered"
Authentication: 0.15 × 1.0 = 0.150  ✓ OTP verified
Communication:  0.10 × 0.0 = 0.000  ✗ no records
Refund:         0.05 × 1.0 = 0.050  ✓ no refunds
──────────────────────────────────────
Score: 0.705 / 1.000 = 0.70

→ Strength: MEDIUM
→ Recommendation: HUMAN_REVIEW (contradictions present)
→ Confidence: MEDIUM
→ Auto-submit: NO (contradictions > 0)
```

---

## Routing Thresholds

```
                                    Auto-     Human
    Score Range     Strength       Submit?   Review?   Recommendation
    ─────────────   ───────────    ────────  ────────  ─────────────────
    ≥ 0.80          HIGH            YES*      NO       CONTEST
    ≥ 0.60          MEDIUM          NO        YES      HUMAN_REVIEW
    ≥ 0.40          LOW             NO        YES      HUMAN_REVIEW
    < 0.40          INSUFFICIENT    NO        NO       ACCEPT_LOSS / ESCALATE

    * Only if contradiction_count == 0
```

### Detailed Routing Logic

```
score ≥ 0.80 AND contradictions == 0
    → CONTEST, HIGH confidence, auto-submit eligible

score ≥ 0.80 AND contradictions > 0
    → HUMAN_REVIEW, MEDIUM confidence
    (High score but contradictions need human eyes)

score ≥ 0.60
    → HUMAN_REVIEW, MEDIUM confidence
    (Moderate evidence, lean toward contest)

score ≥ 0.40
    → HUMAN_REVIEW, LOW confidence
    (Uncertain, needs investigation)

score < 0.40 AND missing required evidence
    → ACCEPT_LOSS, HIGH confidence
    (Highly confident that evidence is insufficient)

score < 0.40 AND no missing evidence
    → ESCALATE, LOW confidence
    (Unusual case, requires investigation)
```

---

## Assessment Output

The decision engine produces an `Assessment` object:

```python
class Assessment(BaseModel):
    case_id: str

    # ── Verdict ───────────────────────────────────────
    case_strength: CaseStrength       # HIGH / MEDIUM / LOW / INSUFFICIENT
    recommendation: Recommendation    # CONTEST / ACCEPT_LOSS / HUMAN_REVIEW / ESCALATE
    confidence: Confidence            # HIGH / MEDIUM / LOW / UNKNOWN

    # ── Explainability ────────────────────────────────
    evidence_checklist: list[EvidenceCheckItem]   # Detailed breakdown
    score: float                                   # 0.0 – 1.0
    score_methodology: str                         # "weighted_evidence_checklist_v1"
    reasons: list[str]                             # Human-readable explanation

    # ── Supporting Data ───────────────────────────────
    supporting_evidence_ids: list[str]   # IDs of available evidence
    contradiction_count: int             # Number of conflicts
    missing_evidence_count: int          # Number of missing required items

    # ── Routing Flags ─────────────────────────────────
    requires_human_review: bool          # Should a human see this?
    auto_submit_eligible: bool           # Safe to auto-submit?

    assessed_at: datetime
```

### Reasons Output

The engine generates a list of human-readable reasons explaining the recommendation:

```
[
  "Evidence score: 1.00 (high strength)",
  "Evidence available: Payment confirmation, Order details, Shipping dispatched, Delivery confirmation, Authentication (OTP/3DS), Refund history",
  "Recommendation: CONTEST — sufficient evidence to dispute"
]
```

When contradictions exist:

```
[
  "Evidence score: 0.70 (medium strength)",
  "Evidence available: Payment confirmation, Order details, Delivery confirmation, ...",
  "1 contradiction(s) detected — human review required",
  "  - Merchant delivery records show delivered, but carrier says returned_to_sender...",
  "Recommendation: HUMAN REVIEW — case needs manual assessment"
]
```

When evidence is missing:

```
[
  "Evidence score: 0.45 (low strength)",
  "Evidence available: Payment confirmation, Order details, Authentication (OTP/3DS)",
  "Missing required evidence: Shipping dispatched, Delivery confirmation",
  "Recommendation: HUMAN REVIEW — case needs manual assessment"
]
```

---

## Case Strength Enum

| Value | Score Range | Meaning |
|---|---|---|
| `HIGH` | ≥ 0.80 | Strong evidence for contesting |
| `MEDIUM` | 0.60 – 0.79 | Moderate evidence, worth reviewing |
| `LOW` | 0.40 – 0.59 | Weak evidence, uncertain outcome |
| `INSUFFICIENT` | < 0.40 | Not enough evidence to contest |

---

## Recommendation Enum

| Value | Description | Auto-Submit? |
|---|---|---|
| `CONTEST` | Sufficient evidence to dispute | Yes (if no contradictions) |
| `HUMAN_REVIEW` | Case needs manual assessment | No |
| `ACCEPT_LOSS` | Insufficient evidence to contest | No |
| `ESCALATE` | Unusual case, requires investigation | No |

---

## Confidence Enum

| Value | Meaning |
|---|---|
| `HIGH` | Strong certainty in the recommendation |
| `MEDIUM` | Moderate certainty, some ambiguity |
| `LOW` | Uncertain, limited evidence or mixed signals |
| `UNKNOWN` | Cannot determine confidence |

---

## Future Extensibility

### Adding New Dispute Types

Each dispute type gets its own weight template in the analysis pipeline:

```python
REQUIREMENTS_BY_TYPE = {
    "product_not_received": PRODUCT_NOT_RECEIVED_REQUIREMENTS,
    # Future:
    # "unauthorized": UNAUTHORIZED_REQUIREMENTS,
    # "product_not_as_described": PRODUCT_QUALITY_REQUIREMENTS,
    # "duplicate": DUPLICATE_REQUIREMENTS,
}
```

Different dispute types will have different evidence weights. For example:
- **Unauthorized transaction** → Authentication weight is highest
- **Product quality** → Photos and return records are weighted highest
- **Duplicate charge** → Payment history comparison is critical

### Modifying Thresholds

Thresholds are defined as module-level constants in the assessment pipeline:

```python
AUTO_SUBMIT_THRESHOLD = 0.80
CONTEST_THRESHOLD = 0.60
UNCERTAIN_THRESHOLD = 0.40
```

These can be tuned based on real-world performance data.
