"""
Batch Evaluation Runner.

Runs all 50 annotated cases through the investigation pipeline
and compares results against ground truth annotations.

Usage:
    python -m tests.evaluation.runner

Output:
    - Per-case results (pass/fail/mismatch)
    - Aggregate metrics (precision, recall, F1)
    - False-positive cost analysis
    - Saves report to evaluation_report.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Add server root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.connectors.synthetic import SyntheticConnector
from app.pipeline.runner import DeterministicRunner
from tests.evaluation.annotations import ANNOTATIONS, get_annotation
from tests.evaluation.metrics import CaseResult, compute_metrics, format_report


def evaluate_case(runner: DeterministicRunner, annotation: dict) -> CaseResult:
    """Run investigation and compare against ground truth."""
    case_id = annotation["case_id"]

    start = time.perf_counter()
    try:
        result = runner.investigate(case_id)
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return CaseResult(
            case_id=case_id,
            passed=False,
            actual_recommendation="error",
            expected_recommendation=annotation["expected_recommendation"],
            actual_contradictions=0,
            expected_contradictions=annotation["expected_contradictions"],
            actual_missing=[],
            expected_missing=annotation["expected_missing"],
            actual_auto_submit=False,
            expected_auto_submit=annotation["auto_submit_ok"],
            score=0.0,
            investigation_time_ms=elapsed,
            evidence_count=0,
            error=str(e),
        )

    elapsed = (time.perf_counter() - start) * 1000

    if "error" in result:
        return CaseResult(
            case_id=case_id,
            passed=False,
            actual_recommendation="error",
            expected_recommendation=annotation["expected_recommendation"],
            actual_contradictions=0,
            expected_contradictions=annotation["expected_contradictions"],
            actual_missing=[],
            expected_missing=annotation["expected_missing"],
            actual_auto_submit=False,
            expected_auto_submit=annotation["auto_submit_ok"],
            score=0.0,
            investigation_time_ms=elapsed,
            evidence_count=0,
            error=result["error"],
        )

    assessment = result["assessment"]
    actual_rec = assessment.recommendation.value
    expected_rec = annotation["expected_recommendation"]

    actual_missing = [
        item.category for item in assessment.evidence_checklist
        if item.status == "missing"
    ]
    actual_contradictions = len(result["contradictions"])
    actual_auto_submit = assessment.auto_submit_eligible

    # Pass if recommendation matches expected
    passed = actual_rec == expected_rec

    return CaseResult(
        case_id=case_id,
        passed=passed,
        actual_recommendation=actual_rec,
        expected_recommendation=expected_rec,
        actual_contradictions=actual_contradictions,
        expected_contradictions=annotation["expected_contradictions"],
        actual_missing=actual_missing,
        expected_missing=annotation["expected_missing"],
        actual_auto_submit=actual_auto_submit,
        expected_auto_submit=annotation["auto_submit_ok"],
        score=assessment.score,
        investigation_time_ms=elapsed,
        evidence_count=len(result["evidence"]),
    )


def run_evaluation(
    data_dir: Path | None = None,
    verbose: bool = True,
) -> tuple[list[CaseResult], dict]:
    """Run full evaluation across all annotated cases.

    Returns:
        (results, metrics_dict)
    """
    if data_dir is None:
        data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "cases"

    if not data_dir.exists():
        print(f"\n  ⚠  Synthetic data not found at {data_dir}")
        print("  Run: python -m data.seed\n")
        sys.exit(1)

    connector = SyntheticConnector(cases_dir=data_dir)
    runner = DeterministicRunner(connector=connector)

    results: list[CaseResult] = []
    total = len(ANNOTATIONS)

    if verbose:
        print(f"\n  Running {total} evaluation cases...\n")

    for i, annotation in enumerate(ANNOTATIONS, 1):
        case_id = annotation["case_id"]
        result = evaluate_case(runner, annotation)
        results.append(result)

        if verbose:
            status = "PASS" if result.passed else ("ERROR" if result.error else "FAIL")
            detail = ""
            if not result.passed and not result.error:
                detail = f" (got={result.actual_recommendation}, expected={result.expected_recommendation})"
            print(f"  [{i:3d}/{total}] {case_id}  {status}{detail}  [{result.investigation_time_ms:.0f}ms]")

    # Compute aggregate metrics
    metrics = compute_metrics(results)

    if verbose:
        print(format_report(metrics))

    return results, _metrics_to_dict(metrics)


def _metrics_to_dict(m) -> dict:
    """Convert EvalMetrics to a JSON-serializable dict."""
    return {
        "total_cases": m.total_cases,
        "passed_cases": m.passed_cases,
        "error_rate": round(m.error_rate, 4),
        "decision": {
            "precision": round(m.decision_precision, 4),
            "recall": round(m.decision_recall, 4),
            "f1": round(m.decision_f1, 4),
            "accuracy": round(m.decision_accuracy, 4),
        },
        "evidence": {
            "missing_detection_rate": round(m.missing_detection_rate, 4),
        },
        "contradictions": {
            "precision": round(m.contradiction_precision, 4),
            "recall": round(m.contradiction_recall, 4),
        },
        "false_positives": {
            "count": m.false_positives,
            "missed_contests": m.false_negatives,
            "estimated_cost_inr": m.estimated_false_positive_cost,
        },
        "integrity": {
            "unsupported_claim_rate": m.unsupported_claim_rate,
        },
        "operational": {
            "avg_investigation_time_ms": round(m.avg_investigation_time_ms, 1),
            "avg_evidence_count": round(m.avg_evidence_count, 1),
        },
        "profile_results": m.profile_results,
    }


def main():
    """CLI entry point."""
    results, metrics_dict = run_evaluation(verbose=True)

    # Save report
    report_path = Path(__file__).resolve().parent.parent.parent / "evaluation_report.json"
    with open(report_path, "w") as f:
        json.dump(metrics_dict, f, indent=2)

    print(f"  Report saved to: {report_path}\n")

    # Exit with appropriate code
    if metrics_dict["passed_cases"] == metrics_dict["total_cases"]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
