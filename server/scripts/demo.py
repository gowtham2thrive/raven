"""
RAVEN Demo Mode.

Seeds the database with test cases and runs investigation on each.
Designed for live demonstrations and quick setup.

Usage:
    python -m scripts.demo [--cases N]

Steps:
    1. Reset database (fresh tables)
    2. Generate N webhook payloads (default: 8)
    3. Send each to the API (auto-investigates)
    4. Print summary with case breakdown
    5. Print dashboard URL
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

API_BASE = "http://localhost:8000"

# Demo cases — curated for variety
DEMO_CASES = [
    {"dispute_id": "disp_demo_strong1", "amount": 2499900, "desc": "Sony WH-1000XM5"},
    {"dispute_id": "disp_demo_strong2", "amount": 899900, "desc": "Nike Air Max"},
    {"dispute_id": "disp_demo_strong3", "amount": 349900, "desc": "Laptop Stand"},
    {"dispute_id": "disp_demo_mid1", "amount": 749900, "desc": "JBL Flip 6"},
    {"dispute_id": "disp_demo_mid2", "amount": 149900, "desc": "Phone Case"},
    {"dispute_id": "disp_demo_small1", "amount": 54999, "desc": "USB-C Hub"},
    {"dispute_id": "disp_demo_high1", "amount": 4999900, "desc": "MacBook Pro"},
    {"dispute_id": "disp_demo_high2", "amount": 1299900, "desc": "iPhone Case"},
]


def check_server():
    """Verify the API server is running."""
    try:
        resp = urllib.request.urlopen(f"{API_BASE}/health")
        data = json.loads(resp.read())
        return data.get("status") == "ok"
    except Exception:
        return False


def send_webhook(dispute_id: str, amount: int) -> dict | None:
    """Send a dispute webhook to the API."""
    payload = json.dumps({
        "event": "payment.dispute.created",
        "payload": {
            "dispute": {
                "entity": {
                    "id": dispute_id,
                    "payment_id": f"pay_{dispute_id[5:]}",
                    "amount": amount,
                    "currency": "INR",
                    "reason_code": "chargeback",
                    "reason_description": "Product not received",
                    "phase": "chargeback",
                    "status": "open",
                    "respond_by_date": int(time.time()) + 86400 * 7,
                    "created_at": int(time.time()),
                }
            }
        },
    }).encode()

    try:
        req = urllib.request.Request(
            f"{API_BASE}/webhooks/razorpay",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_case(case_id: str) -> dict | None:
    """Fetch case details."""
    try:
        resp = urllib.request.urlopen(f"{API_BASE}/cases/{case_id}")
        return json.loads(resp.read())
    except Exception:
        return None


def get_metrics() -> dict:
    """Fetch dashboard metrics."""
    try:
        resp = urllib.request.urlopen(f"{API_BASE}/metrics/summary")
        return json.loads(resp.read())
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="RAVEN Demo Mode")
    parser.add_argument("--cases", type=int, default=8, help="Number of cases to seed")
    args = parser.parse_args()

    print("\n  RAVEN Demo Mode")
    print("  " + "=" * 50)

    # Check server
    if not check_server():
        print("\n  ERROR: API server not running!")
        print("  Start it with: python -m uvicorn app.main:app --port 8000")
        print()
        sys.exit(1)

    print("  Server: OK")

    # Seed cases
    num_cases = min(args.cases, len(DEMO_CASES))
    cases = DEMO_CASES[:num_cases]

    print(f"\n  Seeding {num_cases} cases...\n")

    created = []
    for i, case in enumerate(cases, 1):
        result = send_webhook(case["dispute_id"], case["amount"])
        case_id = result.get("case_id", "???")
        status = result.get("status", "error")
        amt = case["amount"] / 100
        print(f"  [{i:2d}/{num_cases}] {case_id}  INR {amt:>10,.2f}  {case['desc']}  [{status}]")
        if case_id != "???":
            created.append(case_id)

    # Fetch details
    print(f"\n  Fetching investigation results...\n")
    print(f"  {'CASE ID':<14} {'STATUS':<12} {'SCORE':>6} {'RECOMMENDATION':<16} {'EVIDENCE':>8}")
    print(f"  {'-'*14} {'-'*12} {'-'*6} {'-'*16} {'-'*8}")

    for case_id in created:
        detail = get_case(case_id)
        if detail and "case" in detail:
            c = detail["case"]
            ev_count = len(detail.get("evidence", []))
            score = c.get("assessment_score")
            score_str = f"{score:.2f}" if score is not None else "-"
            print(f"  {c['case_id']:<14} {c['status']:<12} {score_str:>6} {c.get('recommendation', '-'):<16} {ev_count:>8}")

    # Metrics
    metrics = get_metrics()
    print(f"\n  -- Dashboard Metrics -------------------------")
    print(f"    Total Cases:     {metrics.get('total_cases', 0)}")
    print(f"    Open:            {metrics.get('open_cases', 0)}")
    print(f"    Pending Review:  {metrics.get('pending_review', 0)}")
    print(f"    Win Rate:        {(metrics.get('win_rate', 0) * 100):.0f}%")
    print(f"    Avg Score:       {metrics.get('avg_score', 0):.2f}")

    print(f"\n  Open the dashboard:")
    print(f"    http://localhost:5173")
    print(f"\n  API docs:")
    print(f"    http://localhost:8000/docs")
    print()


if __name__ == "__main__":
    main()
