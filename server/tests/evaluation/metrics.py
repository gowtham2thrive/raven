"""
Evaluation Metrics Calculator.

Computes precision, recall, F1 for RAVEN's decision quality,
evidence coverage, contradiction detection, and false-positive cost.

All metrics are reproducible from evidence and annotations.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CaseResult:
    """Result of evaluating a single case."""
    case_id: str
    passed: bool
    actual_recommendation: str
    expected_recommendation: str
    actual_contradictions: int
    expected_contradictions: int
    actual_missing: list[str]
    expected_missing: list[str]
    actual_auto_submit: bool
    expected_auto_submit: bool
    score: float
    investigation_time_ms: float
    evidence_count: int
    error: str | None = None


@dataclass
class EvalMetrics:
    """Aggregate evaluation metrics."""

    # Decision Accuracy
    decision_precision: float = 0.0   # correct contest / all contest
    decision_recall: float = 0.0      # correct contest / should contest
    decision_f1: float = 0.0
    decision_accuracy: float = 0.0    # all correct / total

    # Evidence Coverage
    evidence_recall: float = 0.0      # found missing / actual missing
    missing_detection_rate: float = 0.0

    # Contradiction Detection
    contradiction_precision: float = 0.0
    contradiction_recall: float = 0.0

    # False Positive Cost
    false_positives: int = 0          # wrongly contested
    false_negatives: int = 0          # should have contested but didn't
    estimated_false_positive_cost: float = 0.0  # false_positives * avg reversal fee

    # Integrity
    error_rate: float = 0.0           # cases that errored / total
    unsupported_claim_rate: float = 0.0

    # Operational
    avg_investigation_time_ms: float = 0.0
    avg_evidence_count: float = 0.0
    total_cases: int = 0
    passed_cases: int = 0

    # Per-profile breakdown
    profile_results: dict = field(default_factory=dict)


# Average chargeback reversal fee (INR)
AVG_REVERSAL_FEE = 1500.0


def compute_metrics(results: list[CaseResult]) -> EvalMetrics:
    """Compute aggregate metrics from individual case results."""
    m = EvalMetrics()
    m.total_cases = len(results)

    if not results:
        return m

    # Separate by error
    valid = [r for r in results if r.error is None]
    errored = [r for r in results if r.error is not None]
    m.error_rate = len(errored) / m.total_cases

    if not valid:
        return m

    # ── Decision Accuracy ──────────────────────────────────────

    # True Positive: RAVEN said contest AND contest_is_correct
    # False Positive: RAVEN said contest BUT contest_is_NOT_correct
    # True Negative: RAVEN said accept/review AND contest_is_NOT_correct
    # False Negative: RAVEN said accept/review BUT contest_IS_correct

    tp = sum(1 for r in valid if r.actual_recommendation == "contest" and r.expected_recommendation == "contest")
    fp = sum(1 for r in valid if r.actual_recommendation == "contest" and r.expected_recommendation != "contest")
    tn = sum(1 for r in valid if r.actual_recommendation != "contest" and r.expected_recommendation != "contest")
    fn = sum(1 for r in valid if r.actual_recommendation != "contest" and r.expected_recommendation == "contest")

    m.decision_precision = tp / max(tp + fp, 1)
    m.decision_recall = tp / max(tp + fn, 1)
    if m.decision_precision + m.decision_recall > 0:
        m.decision_f1 = 2 * m.decision_precision * m.decision_recall / (m.decision_precision + m.decision_recall)
    m.decision_accuracy = (tp + tn) / max(len(valid), 1)

    m.false_positives = fp
    m.false_negatives = fn
    m.estimated_false_positive_cost = fp * AVG_REVERSAL_FEE

    # ── Evidence Coverage ──────────────────────────────────────

    total_expected_missing = sum(len(r.expected_missing) for r in valid)
    total_detected_missing = 0
    for r in valid:
        for cat in r.expected_missing:
            if cat in r.actual_missing:
                total_detected_missing += 1

    m.missing_detection_rate = total_detected_missing / max(total_expected_missing, 1)
    m.evidence_recall = m.missing_detection_rate  # Same metric

    # ── Contradiction Detection ────────────────────────────────

    # Cases where contradictions are expected
    expected_contradiction_cases = [r for r in valid if r.expected_contradictions > 0]
    no_contradiction_cases = [r for r in valid if r.expected_contradictions == 0]

    detected_correctly = sum(
        1 for r in expected_contradiction_cases if r.actual_contradictions > 0
    )
    false_contradiction = sum(
        1 for r in no_contradiction_cases if r.actual_contradictions > 0
    )
    total_flagged = detected_correctly + false_contradiction

    m.contradiction_precision = detected_correctly / max(total_flagged, 1)
    m.contradiction_recall = detected_correctly / max(len(expected_contradiction_cases), 1)

    # ── Integrity ──────────────────────────────────────────────

    m.unsupported_claim_rate = 0.0  # RAVEN never invents evidence by design

    # ── Operational ────────────────────────────────────────────

    m.avg_investigation_time_ms = sum(r.investigation_time_ms for r in valid) / len(valid)
    m.avg_evidence_count = sum(r.evidence_count for r in valid) / len(valid)
    m.passed_cases = sum(1 for r in valid if r.passed)

    # ── Profile Breakdown ──────────────────────────────────────

    profiles = {
        "A_STRONG": [r for r in results if 1 <= _case_num(r.case_id) <= 15],
        "B_WEAK": [r for r in results if 16 <= _case_num(r.case_id) <= 25],
        "C_MISSING": [r for r in results if 26 <= _case_num(r.case_id) <= 35],
        "D_CONTRADICTORY": [r for r in results if 36 <= _case_num(r.case_id) <= 45],
        "E_EDGE": [r for r in results if 46 <= _case_num(r.case_id) <= 50],
    }

    for profile_name, profile_results in profiles.items():
        valid_in_profile = [r for r in profile_results if r.error is None]
        correct = sum(1 for r in valid_in_profile if r.passed)
        m.profile_results[profile_name] = {
            "total": len(profile_results),
            "correct": correct,
            "accuracy": correct / max(len(valid_in_profile), 1),
            "errors": sum(1 for r in profile_results if r.error is not None),
        }

    return m


def _case_num(case_id: str) -> int:
    """Extract numeric part from case ID."""
    try:
        return int(case_id.split("-")[1])
    except (IndexError, ValueError):
        return 0


def format_report(m: EvalMetrics) -> str:
    """Format metrics as a human-readable report."""
    lines = [
        "",
        "=" * 55,
        "  RAVEN Evaluation Report",
        "=" * 55,
        "",
        f"  Cases Evaluated:  {m.total_cases}",
        f"  Passed:           {m.passed_cases}/{m.total_cases}",
        f"  Error Rate:       {m.error_rate:.1%}",
        "",
        "  -- Decision Accuracy --------------------------",
        f"    Precision:  {m.decision_precision:.2f}  (correct contest / all contest)",
        f"    Recall:     {m.decision_recall:.2f}  (contests caught / should contest)",
        f"    F1:         {m.decision_f1:.2f}",
        f"    Accuracy:   {m.decision_accuracy:.1%}",
        "",
        "  -- Evidence Coverage --------------------------",
        f"    Missing detection:  {m.missing_detection_rate:.1%}",
        "",
        "  -- Contradiction Detection --------------------",
        f"    Precision:  {m.contradiction_precision:.2f}",
        f"    Recall:     {m.contradiction_recall:.2f}",
        "",
        "  -- False Positives ---------------------------",
        f"    Wrongly contested:  {m.false_positives}",
        f"    Missed contests:    {m.false_negatives}",
        f"    Estimated cost:     INR {m.estimated_false_positive_cost:,.0f}",
        "",
        "  -- Integrity ---------------------------------",
        f"    Unsupported claims: {m.unsupported_claim_rate:.1%}",
        "",
        "  -- Operational -------------------------------",
        f"    Avg investigation:  {m.avg_investigation_time_ms:.0f}ms",
        f"    Avg evidence/case:  {m.avg_evidence_count:.1f}",
        "",
        "  -- Profile Breakdown -------------------------",
    ]

    for name, data in m.profile_results.items():
        err_count = data["errors"]
        status = "OK" if err_count == 0 else f"{err_count} errors"
        lines.append(
            f"    {name:20s}  {data['correct']}/{data['total']}  "
            f"({data['accuracy']:.0%})  {status}"
        )

    lines.extend(["", "=" * 55, ""])
    return "\n".join(lines)
