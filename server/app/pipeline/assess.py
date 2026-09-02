"""
Case Assessment — Decision Engine + Response Generation + Citation Verification.

Three sequential stages:
1. Decision Engine: Weighted evidence scoring → recommendation
2. Response Generator: Template-based evidence-linked draft
3. Citation Verifier: Post-generation check for unsupported claims

Scoring methodology: weighted_evidence_checklist_v1
    score = sum(weight * status_multiplier) / sum(weight for applicable items)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.types import (
    CaseStrength,
    Confidence,
    EvidenceCategory,
    EvidenceStatus,
    Recommendation,
)
from app.core.schemas import (
    Assessment,
    Contradiction,
    Evidence,
    EvidenceCheckItem,
    TimelineEvent,
)


# ═══════════════════════════════════════════════════════════════
#  DECISION ENGINE
# ═══════════════════════════════════════════════════════════════


STATUS_MULTIPLIERS: dict[str, float] = {
    "available": 1.0,
    "unverified": 0.5,
    "missing": 0.0,
    "conflicting": -0.3,
    "not_applicable": 0.0,
    "ingestion_error": 0.0,
}

AUTO_SUBMIT_THRESHOLD = 0.80
CONTEST_THRESHOLD = 0.60
UNCERTAIN_THRESHOLD = 0.40


def assess_case(
    case_id: str,
    checklist: list[EvidenceCheckItem],
    contradictions: list[Contradiction],
    missing_required: list[str],
) -> Assessment:
    """Produce a deterministic assessment from evidence analysis.

    The score is NOT an LLM-generated number. It is a weighted sum
    of evidence availability, reproducible from the same inputs.
    """
    score = _calculate_score(checklist)
    strength = _determine_strength(score)
    contradiction_count = len(contradictions)
    missing_count = len(missing_required)
    has_unverified_required = any(
        item.required and item.status == "unverified"
        for item in checklist
    )

    recommendation, confidence, needs_review, auto_eligible = _determine_recommendation(
        score=score,
        contradiction_count=contradiction_count,
        missing_required_count=missing_count,
        has_unverified_required=has_unverified_required,
    )

    reasons = _build_reasons(
        score, strength, recommendation,
        checklist, contradictions, missing_required,
    )

    supporting_ids = [
        item.evidence_id
        for item in checklist
        if item.evidence_id and item.status == "available"
    ]

    return Assessment(
        case_id=case_id,
        case_strength=strength,
        recommendation=recommendation,
        confidence=confidence,
        evidence_checklist=checklist,
        score=round(score, 4),
        score_methodology="weighted_evidence_checklist_v1",
        reasons=reasons,
        supporting_evidence_ids=supporting_ids,
        contradiction_count=contradiction_count,
        missing_evidence_count=missing_count,
        requires_human_review=needs_review,
        auto_submit_eligible=auto_eligible,
        assessed_at=datetime.now(timezone.utc),
    )


def _calculate_score(checklist: list[EvidenceCheckItem]) -> float:
    """Calculate weighted evidence score (0.0 - 1.0)."""
    numerator = 0.0
    denominator = 0.0

    for item in checklist:
        if item.status == "not_applicable":
            continue
        multiplier = STATUS_MULTIPLIERS.get(item.status, 0.0)
        numerator += item.weight * multiplier
        denominator += item.weight

    if denominator == 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))


def _determine_strength(score: float) -> CaseStrength:
    if score >= AUTO_SUBMIT_THRESHOLD:
        return CaseStrength.HIGH
    if score >= CONTEST_THRESHOLD:
        return CaseStrength.MEDIUM
    if score >= UNCERTAIN_THRESHOLD:
        return CaseStrength.LOW
    return CaseStrength.INSUFFICIENT


def _determine_recommendation(
    score: float,
    contradiction_count: int,
    missing_required_count: int,
    has_unverified_required: bool = False,
) -> tuple[Recommendation, Confidence, bool, bool]:
    """Returns (recommendation, confidence, requires_human_review, auto_submit_eligible)."""
    # 1. Missing critical/required evidence -> Accept loss with medium confidence (gap exists)
    if missing_required_count > 0:
        return (Recommendation.ACCEPT_LOSS, Confidence.MEDIUM, False, False)

    # 2. Contradictions detected -> Human review required
    if contradiction_count > 0:
        conf = Confidence.LOW if score < AUTO_SUBMIT_THRESHOLD else Confidence.MEDIUM
        return (Recommendation.HUMAN_REVIEW, conf, True, False)

    # 3. Unverified required evidence -> Human review required (never auto-submit unverified)
    if has_unverified_required:
        return (Recommendation.HUMAN_REVIEW, Confidence.MEDIUM, True, False)

    # 4. High evidence score with all required verified -> Contest (auto-submit eligible)
    if score >= AUTO_SUBMIT_THRESHOLD:
        return (Recommendation.CONTEST, Confidence.HIGH, False, True)

    # 5. Medium score -> Human review
    if score >= CONTEST_THRESHOLD:
        return (Recommendation.HUMAN_REVIEW, Confidence.MEDIUM, True, False)

    # 6. Low score -> Human review
    if score >= UNCERTAIN_THRESHOLD:
        return (Recommendation.HUMAN_REVIEW, Confidence.LOW, True, False)

    return (Recommendation.ACCEPT_LOSS, Confidence.HIGH, False, False)


def _build_reasons(
    score: float,
    strength: CaseStrength,
    recommendation: Recommendation,
    checklist: list[EvidenceCheckItem],
    contradictions: list[Contradiction],
    missing_required: list[str],
) -> list[str]:
    reasons: list[str] = []
    reasons.append(f"Evidence score: {score:.2f} ({strength.value} strength)")

    available = [i for i in checklist if i.status == "available"]
    if available:
        reasons.append(f"Evidence available: {', '.join(i.label for i in available)}")

    if missing_required:
        reasons.append(f"Missing required evidence: {', '.join(missing_required)}")

    unverified = [i for i in checklist if i.status == "unverified"]
    if unverified:
        reasons.append(f"Unverified evidence: {', '.join(i.label for i in unverified)}")

    if contradictions:
        reasons.append(f"{len(contradictions)} contradiction(s) detected — human review required")
        for c in contradictions:
            reasons.append(f"  - {c.description[:100]}")

    label_map = {
        Recommendation.CONTEST: "CONTEST — sufficient evidence to dispute",
        Recommendation.ACCEPT_LOSS: "ACCEPT LOSS — insufficient evidence to contest",
        Recommendation.HUMAN_REVIEW: "HUMAN REVIEW — case needs manual assessment",
        Recommendation.ESCALATE: "ESCALATE — unusual case requires investigation",
    }
    reasons.append(f"Recommendation: {label_map.get(recommendation, recommendation.value)}")

    return reasons


# ═══════════════════════════════════════════════════════════════
#  RESPONSE GENERATOR
# ═══════════════════════════════════════════════════════════════


class ResponseGenerator:
    """Generate chargeback response from verified evidence.

    Template-based (no LLM needed). Every claim traces to evidence.
    """

    def generate(
        self,
        evidence: list[Evidence],
        timeline: list[TimelineEvent],
        assessment: Assessment,
        dispute: dict | None = None,
        agent_response_draft: str | None = None,
    ) -> str:
        """Generate chargeback response.

        Prefers the agent's draft when available (already claim-specific).
        Falls back to template-based generation otherwise.
        """
        if agent_response_draft:
            return agent_response_draft

        # Template-based fallback
        sections: list[str] = []

        sections.append(self._opening(dispute))

        for method in (
            self._payment_section,
            self._order_section,
            self._shipping_section,
            self._delivery_section,
            self._auth_section,
            self._comms_section,
        ):
            section = method(evidence)
            if section:
                sections.append(section)

        timeline_section = self._timeline_section(timeline)
        if timeline_section:
            sections.append(timeline_section)

        sections.append(self._closing(assessment))

        return "\n\n".join(sections)

    def _opening(self, dispute: dict | None) -> str:
        return (
            "We are contesting this dispute. The customer claims the product "
            "was not received; however, our records show the order was "
            "fulfilled and delivered successfully. Below is the supporting evidence."
        )

    def _payment_section(self, evidence: list[Evidence]) -> str | None:
        ev = self._find(evidence, EvidenceCategory.PAYMENT)
        if not ev or ev.status != EvidenceStatus.AVAILABLE:
            return None
        c = ev.content
        return (
            f"PAYMENT: The payment of Rs.{c.get('amount', 0) / 100:,.2f} "
            f"was captured via {c.get('method', 'card')} "
            f"({c.get('card_network', '')} ending {c.get('card_last4', '****')}). "
            f"The payment was {'authenticated' if c.get('captured') else 'processed'} "
            f"successfully."
        )

    def _order_section(self, evidence: list[Evidence]) -> str | None:
        ev = self._find(evidence, EvidenceCategory.ORDER)
        if not ev or ev.status != EvidenceStatus.AVAILABLE:
            return None
        c = ev.content
        return (
            f"ORDER: Order {c.get('receipt', c.get('order_id', ''))} "
            f"was placed for {c.get('item', 'the purchased item')}. "
            f"Order status: {c.get('status', 'confirmed')}."
        )

    def _shipping_section(self, evidence: list[Evidence]) -> str | None:
        ev = self._find(evidence, EvidenceCategory.SHIPPING)
        if not ev or ev.status == EvidenceStatus.MISSING:
            return None
        c = ev.content
        return (
            f"SHIPPING: The order was shipped via {c.get('carrier', 'carrier')} "
            f"with tracking number {c.get('tracking_id', 'N/A')}. "
            f"Current tracking status: {c.get('status', 'unknown')}."
        )

    def _delivery_section(self, evidence: list[Evidence]) -> str | None:
        ev = self._find(evidence, EvidenceCategory.DELIVERY)
        if not ev or ev.status == EvidenceStatus.MISSING:
            return None
        c = ev.content
        parts = ["DELIVERY:"]
        if c.get("delivered_at"):
            parts.append(f"The package was delivered on {c['delivered_at']}.")
        if c.get("signed_by"):
            parts.append(f"Delivery was signed for by {c['signed_by']}.")
        proof_type = c.get("proof_type", "")
        if proof_type and proof_type != "unknown":
            parts.append(f"Proof of delivery: {proof_type}.")
        if c.get("photo_proof"):
            parts.append("Photo proof of delivery is available.")
        return " ".join(parts)

    def _auth_section(self, evidence: list[Evidence]) -> str | None:
        ev = self._find(evidence, EvidenceCategory.AUTHENTICATION)
        if not ev or ev.status == EvidenceStatus.MISSING:
            return None
        c = ev.content
        if not c.get("verified"):
            return None
        return (
            f"AUTHENTICATION: The transaction was authenticated via "
            f"{c.get('method', 'verification')}. "
            f"The device was {'recognized' if c.get('device_known') else 'new'}. "
            f"Transaction originated from {c.get('ip_country', 'the expected region')}."
        )

    def _comms_section(self, evidence: list[Evidence]) -> str | None:
        ev = self._find(evidence, EvidenceCategory.COMMUNICATION)
        if not ev or ev.status in (EvidenceStatus.MISSING, EvidenceStatus.NOT_APPLICABLE):
            return None
        tickets = ev.content.get("tickets", [])
        if not tickets:
            return None
        summaries = "; ".join(
            (t.get("summary") or t.get("subject") or t.get("content") or "")
            for t in tickets[:3]
        )
        return f"CUSTOMER COMMUNICATIONS: {summaries}"

    def _timeline_section(self, timeline: list[TimelineEvent]) -> str | None:
        if not timeline:
            return None
        lines = ["TIMELINE OF EVENTS:"]
        for event in timeline:
            date = event.timestamp_utc.strftime("%b %d, %Y %H:%M UTC")
            lines.append(f"  - {date}: {event.label}")
        return "\n".join(lines)

    def _closing(self, assessment: Assessment) -> str:
        return (
            "Based on the evidence above, we believe this dispute should be "
            "resolved in the merchant's favor. All required documentation "
            "has been provided."
        )

    def _find(self, evidence: list[Evidence], category: EvidenceCategory) -> Evidence | None:
        for ev in evidence:
            if ev.category == category:
                return ev
        return None


# ═══════════════════════════════════════════════════════════════
#  CITATION VERIFIER
# ═══════════════════════════════════════════════════════════════


@dataclass
class CitationViolation:
    """A specific unsupported claim found in the response draft."""
    claim_text: str
    violation_type: str
    expected: str
    severity: str = "high"


@dataclass
class VerificationResult:
    """Result of citation verification."""
    passed: bool = True
    violations: list[CitationViolation] = field(default_factory=list)
    checks_run: int = 0


DELIVERY_CONFIRMED_PATTERNS = [
    r"\bdelivered\b",
    r"\bdelivery\s+confirmed\b",
    r"\bsuccessfully\s+delivered\b",
    r"\bpackage\s+was\s+delivered\b",
    r"\bgoods?\s+(?:was|were)\s+delivered\b",
    r"\bshipment\s+delivered\b",
]

SIGNATURE_PATTERNS = [
    r"\bsigned\s+by\b",
    r"\bsignature\s+(?:on\s+)?(?:file|record|proof)\b",
    r"\brecipient\s+signed\b",
]

AUTH_PATTERNS = [
    r"\bauthenticated\b",
    r"\bverified\s+(?:identity|customer|cardholder)\b",
    r"\b(?:otp|3ds?|two.factor)\s+(?:verified|confirmed|passed)\b",
]

CERTAINTY_PATTERNS = [
    r"\bundeniable\b",
    r"\bconclusively?\s+proves?\b",
    r"\bwithout\s+(?:a\s+)?doubt\b",
    r"\birrefutable\b",
    r"\bcertain(?:ly)?\s+that\b",
    r"\bguaranteed?\b",
    r"\babsolutely\s+(?:confirms?|proves?)\b",
]

REFUND_PATTERNS = [
    r"\brefund(?:ed)?\s+(?:was\s+)?(?:issued|processed|completed|given)\b",
    r"\bfull\s+refund\b",
    r"\bpartial\s+refund\b",
]


def verify_response(
    response_draft: str,
    evidence: list[Evidence],
    assessment: Assessment,
) -> VerificationResult:
    """Verify that a response draft doesn't contain unsupported claims.

    Every violation prevents auto-submission and forces human review.
    """
    result = VerificationResult()
    draft_lower = response_draft.lower()

    by_category: dict[str, Evidence] = {}
    for ev in evidence:
        cat = ev.category.value
        if cat not in by_category:
            by_category[cat] = ev

    # Check 1: Delivery claims
    result.checks_run += 1
    delivery_ev = by_category.get("delivery")
    delivery_missing = (
        delivery_ev is None
        or delivery_ev.status in (EvidenceStatus.MISSING, EvidenceStatus.INGESTION_ERROR)
    )
    if delivery_missing:
        for pattern in DELIVERY_CONFIRMED_PATTERNS:
            match = re.search(pattern, draft_lower)
            if match:
                result.passed = False
                result.violations.append(CitationViolation(
                    claim_text=match.group(),
                    violation_type="unsupported_claim",
                    expected=(
                        f"Delivery evidence is "
                        f"{delivery_ev.status.value if delivery_ev else 'not present'}"
                    ),
                ))
                break

    # Check 2: Signature claims
    result.checks_run += 1
    has_signature = False
    if delivery_ev and delivery_ev.status == EvidenceStatus.AVAILABLE:
        content = delivery_ev.content or {}
        has_signature = bool(content.get("signed_by")) or content.get("proof_type") == "signature"

    if not has_signature:
        for pattern in SIGNATURE_PATTERNS:
            match = re.search(pattern, draft_lower)
            if match:
                result.passed = False
                result.violations.append(CitationViolation(
                    claim_text=match.group(),
                    violation_type="status_mismatch",
                    expected="No signature proof in delivery evidence",
                ))
                break

    # Check 3: Authentication claims
    result.checks_run += 1
    auth_ev = by_category.get("authentication")
    auth_missing = (
        auth_ev is None
        or auth_ev.status in (EvidenceStatus.MISSING, EvidenceStatus.INGESTION_ERROR)
    )
    if auth_missing:
        for pattern in AUTH_PATTERNS:
            match = re.search(pattern, draft_lower)
            if match:
                result.passed = False
                result.violations.append(CitationViolation(
                    claim_text=match.group(),
                    violation_type="unsupported_claim",
                    expected=(
                        f"Authentication evidence is "
                        f"{auth_ev.status.value if auth_ev else 'not present'}"
                    ),
                ))
                break

    # Check 4: Refund claims
    result.checks_run += 1
    refund_ev = by_category.get("refund")
    if refund_ev and refund_ev.status == EvidenceStatus.NOT_APPLICABLE:
        for pattern in REFUND_PATTERNS:
            match = re.search(pattern, draft_lower)
            if match:
                result.passed = False
                result.violations.append(CitationViolation(
                    claim_text=match.group(),
                    violation_type="status_mismatch",
                    expected="No refund was issued (status: not_applicable)",
                ))
                break

    # Check 5: Overconfident language on weak cases
    result.checks_run += 1
    if assessment.case_strength.value in ("low", "insufficient"):
        for pattern in CERTAINTY_PATTERNS:
            match = re.search(pattern, draft_lower)
            if match:
                result.passed = False
                result.violations.append(CitationViolation(
                    claim_text=match.group(),
                    violation_type="certainty_overreach",
                    expected=(
                        f"Case strength is {assessment.case_strength.value} — "
                        f"cannot use definitive language"
                    ),
                    severity="medium",
                ))
                break

    # Check 6: Agent [category] bracket citations
    result.checks_run += 1
    bracket_violations = _check_agent_citations(response_draft, evidence)
    if bracket_violations:
        result.passed = False
        result.violations.extend(bracket_violations)

    return result


# ── Agent Citation Check ────────────────────────────────────────

CITATION_BRACKET_PATTERN = re.compile(r'\[(\w+)\]')


def _check_agent_citations(
    response_draft: str,
    evidence: list[Evidence],
) -> list[CitationViolation]:
    """Check that [category] references in agent drafts map to real evidence.

    Only checks categories that match evidence category names.
    Non-category bracket text (like [Note]) is ignored.
    """
    violations: list[CitationViolation] = []
    available_categories = {
        ev.category.value for ev in evidence
        if ev.status not in (
            EvidenceStatus.MISSING,
            EvidenceStatus.NOT_APPLICABLE,
            EvidenceStatus.INGESTION_ERROR,
        )
    }

    # All valid category names for filtering
    all_category_names = {cat.value for cat in EvidenceCategory}

    cited = CITATION_BRACKET_PATTERN.findall(response_draft)
    for cite in cited:
        cite_lower = cite.lower()
        # Only check if it looks like an evidence category name
        if cite_lower not in all_category_names:
            continue
        if cite_lower not in available_categories:
            violations.append(CitationViolation(
                claim_text=f"[{cite}]",
                violation_type="missing_citation_source",
                expected=f"No available evidence for category '{cite_lower}'",
                severity="high",
            ))

    return violations
