"""
Investigation Runner — The Deterministic Pipeline Orchestrator.

Runs the full investigation WITHOUT an LLM agent. Used for:
- Testing the pipeline independently
- Fallback when agent fails or exceeds budget
- Baseline evaluation comparison
- CLI demonstration

Pipeline:
    1. Load case from DB (or synthetic data)
    2. Fetch Razorpay data (payment, order, customer, refunds)
    3. Fetch merchant data (shipping, delivery, auth, comms)
    4. Normalize all data to canonical evidence
    5. Build timeline
    6. Causal validation + triangulation
    7. Check completeness
    8. Detect contradictions
    9. Assess case strength
    10. Generate response draft + citation verification
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from app.core.schemas import Assessment, AuditTrail, Evidence
from app.connectors.carrier import MockCarrierConnector
from app.connectors.quarantine import IngestionQuarantine
from app.connectors.synthetic import SyntheticConnector
from app.pipeline.ingest import (
    _parse_timestamp,
    normalize_auth,
    normalize_communications,
    normalize_delivery,
    normalize_razorpay_order,
    normalize_razorpay_payment,
    normalize_razorpay_refunds,
    normalize_shipping,
)
from app.pipeline.analysis import (
    apply_triangulation,
    build_timeline,
    check_completeness,
    detect_contradictions,
    triangulate_delivery,
    validate_causal_order,
    violations_to_contradictions,
)
from app.pipeline.assess import (
    ResponseGenerator,
    assess_case,
    verify_response,
)


class DeterministicRunner:
    """Runs investigation without LLM — pure deterministic pipeline.

    Always calls all connectors, always runs all analysis.
    No tool selection intelligence — but 100% reproducible.
    """

    def __init__(
        self,
        connector: SyntheticConnector | None = None,
        db_path: str | None = None,
        carrier: MockCarrierConnector | None = None,
        db_session=None,
    ):
        self._connector = connector or SyntheticConnector()
        self._carrier = carrier or MockCarrierConnector()
        self._quarantine = IngestionQuarantine(db_path)
        self._response_gen = ResponseGenerator()
        self._db_session = db_session

    def investigate(self, case_id: str, db_session=None) -> dict:
        """Run full deterministic investigation.

        Returns a complete investigation result dict with:
            evidence, timeline, contradictions, checklist,
            missing, assessment, response_draft, audit_trail
        """
        audit = AuditTrail(case_id)
        active_db = db_session if db_session is not None else self._db_session

        # 1. Load Razorpay data from synthetic connector
        with audit.step("razorpay_data_fetched", "connector") as step:
            rzp_data = self._connector.get_razorpay_data(case_id)
            if not rzp_data or not rzp_data.get("dispute"):
                step.details = {"error": "case_not_found"}
                return {"error": f"Case {case_id} not found in synthetic data"}
            step.details = {
                "has_payment": rzp_data.get("payment") is not None,
                "has_order": rzp_data.get("order") is not None,
                "has_customer": rzp_data.get("customer") is not None,
            }

        # 2. Normalize Razorpay data to canonical evidence
        with audit.step("evidence_normalized", "normalizer") as step:
            evidence: list[Evidence] = []

            payment = rzp_data.get("payment")
            if payment:
                evidence.append(normalize_razorpay_payment(payment, case_id, self._quarantine))

            order = rzp_data.get("order")
            if order:
                evidence.append(normalize_razorpay_order(order, case_id, self._quarantine))

            # Refunds from synthetic data
            refund_data = self._connector.get_refunds(case_id)
            payment_id = payment.get("id", "") if payment else ""
            refund_ev = normalize_razorpay_refunds(refund_data, case_id, payment_id)
            if refund_ev:
                evidence.append(refund_ev)

            # 3. Fetch and normalize merchant data
            shipping = self._connector.get_shipping(case_id)
            evidence.append(normalize_shipping(shipping, case_id, self._quarantine))

            delivery = self._connector.get_delivery(case_id)
            evidence.append(normalize_delivery(delivery, case_id, self._quarantine))

            auth = self._connector.get_auth(case_id)
            evidence.append(normalize_auth(auth, case_id, self._quarantine))

            comms = self._connector.get_communications(case_id)
            evidence.append(normalize_communications(comms, case_id, self._quarantine))

            step.evidence_ids = [ev.evidence_id for ev in evidence]
            step.details = {"evidence_count": len(evidence)}

        # 3.5 Fetch carrier data (independent second source)
        with audit.step("carrier_data_fetched", "mock_carrier") as step:
            tracking_id = ""
            if shipping:
                tracking_id = shipping.get("tracking_id", "")
            carrier_ev = self._carrier.get_delivery_status(case_id, tracking_id)
            if carrier_ev:
                evidence.append(carrier_ev)
                step.evidence_ids = [carrier_ev.evidence_id]
                step.details = {"carrier_status": carrier_ev.content.get("status", "unknown")}
            else:
                step.details = {"carrier_status": "no_data"}

        # 3.6 Fetch evidence from active integrations
        if active_db is not None:
            with audit.step("integration_evidence_fetched", "integration_hub") as step:
                try:
                    from app.services.integration_service import IntegrationService
                    integration_svc = IntegrationService()
                    integration_evidence = integration_svc.fetch_all_active_evidence(
                        case_id, active_db,
                    )
                    evidence.extend(integration_evidence)
                    step.details = {
                        "integration_evidence_count": len(integration_evidence),
                    }
                    step.evidence_ids = [ev.evidence_id for ev in integration_evidence]
                except Exception as e:
                    step.details = {
                        "integration_evidence_count": 0,
                        "error": str(e),
                    }

        # 4. Build timeline
        with audit.step("timeline_built", "timeline_builder") as step:
            timeline = build_timeline(evidence)
            step.details = {"event_count": len(timeline)}

        # 4.5 Causal validation (physically impossible timelines)
        with audit.step("causal_validation_complete", "causal_validator") as step:
            causal_violations = validate_causal_order(evidence)
            step.details = {
                "violation_count": len(causal_violations),
            }

        # 5. Multi-source triangulation
        with audit.step("triangulation_complete", "triangulation") as step:
            triangulation = triangulate_delivery(evidence)
            evidence = apply_triangulation(evidence, triangulation)
            step.details = {
                "signal_count": triangulation.signal_count,
                "triangulated": triangulation.triangulated,
                "supporting": triangulation.supporting_count,
                "conflicting": triangulation.conflicting_count,
            }

        # 6. Check evidence completeness
        dispute = rzp_data.get("dispute", {})
        reason_code = dispute.get("reason_code", "product_not_received")

        with audit.step("completeness_checked", "completeness_checker") as step:
            checklist, missing = check_completeness(
                evidence,
                dispute_type=reason_code,
                evidence_relevance=None,
            )
            step.details = {
                "dispute_type": reason_code,
                "checklist_items": len(checklist),
                "missing_count": len(missing),
                "missing_categories": missing,
            }

        # 6. Detect contradictions (rules 1-8 unified)
        with audit.step("contradictions_detected", "contradiction_engine") as step:
            dispute_created_at = None
            if dispute.get("created_at"):
                dispute_created_at = _parse_timestamp(dispute["created_at"])

            contradictions = detect_contradictions(
                evidence,
                dispute_created_at=dispute_created_at,
                dispute_reason=reason_code,
            )
            step.details = {
                "contradiction_count": len(contradictions),
            }
            step.evidence_ids = [c.evidence_a_id for c in contradictions]

        # 7. Assess case strength
        with audit.step("assessment_produced", "decision_engine") as step:
            assessment = assess_case(
                case_id=case_id,
                checklist=checklist,
                contradictions=contradictions,
                missing_required=missing,
            )
            step.details = {
                "score": assessment.score,
                "case_strength": assessment.case_strength.value,
                "recommendation": assessment.recommendation.value,
                "auto_submit_eligible": assessment.auto_submit_eligible,
            }

        # 8. Generate response draft (if recommending contest)
        response_draft = None
        citation_verification = None
        if assessment.recommendation.value in ("contest", "human_review"):
            with audit.step("response_generated", "response_generator") as step:
                response_draft = self._response_gen.generate(
                    evidence=evidence,
                    timeline=timeline,
                    assessment=assessment,
                    dispute=dispute,
                )
                step.details = {"draft_length": len(response_draft) if response_draft else 0}

        # 9. Citation verification gate
        if response_draft:
            with audit.step("citation_verified", "citation_verifier") as step:
                citation_verification = verify_response(
                    response_draft, evidence, assessment,
                )
                if not citation_verification.passed:
                    assessment.requires_human_review = True
                    assessment.auto_submit_eligible = False
                step.details = {
                    "passed": citation_verification.passed,
                    "checks_run": citation_verification.checks_run,
                    "violation_count": len(citation_verification.violations),
                }

        return {
            "case_id": case_id,
            "evidence": evidence,
            "timeline": timeline,
            "contradictions": contradictions,
            "causal_violations": causal_violations,
            "checklist": checklist,
            "missing_evidence": missing,
            "assessment": assessment,
            "response_draft": response_draft,
            "triangulation": triangulation,
            "citation_verification": citation_verification,
            "audit_trail": audit.to_dict(),
        }


def _format_amount(paise: int) -> str:
    return f"Rs.{paise / 100:,.2f}"


def print_investigation(result: dict) -> None:
    """Pretty-print investigation results to terminal."""
    if "error" in result:
        print(f"\n  ERROR: {result['error']}")
        return

    case_id = result["case_id"]
    assessment: Assessment = result["assessment"]
    evidence = result["evidence"]
    timeline = result["timeline"]
    contradictions = result["contradictions"]
    missing = result["missing_evidence"]

    print()
    print("=" * 60)
    print(f"  RAVEN Investigation: {case_id}")
    print("=" * 60)

    print("\n  EVIDENCE GATHERED:")
    for ev in evidence:
        status_icon = {
            "available": "+",
            "missing": "-",
            "conflicting": "!",
            "unverified": "?",
            "not_applicable": "~",
        }.get(ev.status.value, "?")
        print(f"    [{status_icon}] {ev.category.value.title()}: {ev.summary}")

    if timeline:
        print("\n  TIMELINE:")
        for event in timeline:
            time_str = event.timestamp_utc.strftime("%b %d %H:%M")
            tz_flag = "" if event.timezone_confident else " [TZ?]"
            print(f"    {time_str}  {event.label}{tz_flag}  ({event.source_system})")

    if contradictions:
        print(f"\n  CONTRADICTIONS: {len(contradictions)}")
        for c in contradictions:
            print(f"    [!] {c.impact.upper()}: {c.description[:80]}")
    else:
        print("\n  CONTRADICTIONS: None")

    if missing:
        print(f"\n  MISSING REQUIRED: {', '.join(missing)}")

    print(f"\n  ASSESSMENT:")
    print(f"    Score: {assessment.score:.2f} ({assessment.score_methodology})")
    print(f"    Strength: {assessment.case_strength.value.upper()}")
    print(f"    Recommendation: {assessment.recommendation.value.upper()}")
    print(f"    Confidence: {assessment.confidence.value.upper()}")
    print(f"    Auto-submit eligible: {'YES' if assessment.auto_submit_eligible else 'NO'}")
    print(f"    Human review needed: {'YES' if assessment.requires_human_review else 'NO'}")

    print(f"\n  REASONS:")
    for reason in assessment.reasons:
        print(f"    - {reason}")

    if result.get("response_draft"):
        print(f"\n  RESPONSE DRAFT:")
        for line in result["response_draft"].split("\n"):
            print(f"    {line}")

    print()
    print("=" * 60)


# ── CLI Entry Point ───────────────────────────────────────────

if __name__ == "__main__":
    case_id = sys.argv[1] if len(sys.argv) > 1 else "CASE-00001"
    runner = DeterministicRunner()
    result = runner.investigate(case_id)
    print_investigation(result)
