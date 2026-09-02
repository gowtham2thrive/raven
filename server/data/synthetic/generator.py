"""
Synthetic Data Generator for RAVEN Evaluation.

Generates 50+ cases across 5 evidence profiles:

    Profile A — STRONG (15 cases)
        All evidence present, consistent, delivery confirmed with signature.
        Expected: contest, HIGH confidence

    Profile B — WEAK (10 cases)
        Payment + order present, delivery present but weak proof.
        Expected: human_review, MEDIUM confidence

    Profile C — MISSING (10 cases)
        Key delivery/shipping evidence missing entirely.
        Expected: human_review or accept_loss, LOW confidence

    Profile D — CONTRADICTORY (10 cases)
        Merchant says delivered, carrier says returned-to-sender.
        Expected: human_review, varies

    Profile E — EDGE (5 cases)
        Timezone mismatches, duplicate events, partial data.
        Expected: varies

Each case includes:
    - Razorpay mock objects (dispute, payment, order, customer)
    - Merchant data (shipping, delivery, auth, communications)
    - Expected outcome (ground truth for evaluation)
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .razorpay_mock import mock_customer, mock_dispute, mock_order, mock_payment


# ── Indian Names for Realistic Data ──────────────────────────

FIRST_NAMES = [
    "Arjun", "Priya", "Rajesh", "Sneha", "Vikram", "Deepika", "Amit",
    "Kavita", "Rohan", "Ananya", "Siddharth", "Meera", "Karan", "Pooja",
    "Aditya", "Neha", "Rahul", "Divya", "Suresh", "Lakshmi",
    "Manish", "Ritu", "Nikhil", "Swati", "Varun", "Nandini",
]

LAST_NAMES = [
    "Mehta", "Sharma", "Kumar", "Patel", "Singh", "Nair", "Gupta",
    "Rao", "Reddy", "Joshi", "Verma", "Iyer", "Chauhan", "Desai",
    "Bhat", "Pillai", "Saxena", "Malhotra", "Tiwari", "Agarwal",
]

PRODUCTS = [
    ("Wireless Headphones (Sony WH-1000XM5)", 2499900),
    ("Smartphone Case (OtterBox)", 149900),
    ("Running Shoes (Nike Air Max)", 899900),
    ("Laptop Stand (Rain Design)", 349900),
    ("Bluetooth Speaker (JBL Flip 6)", 749900),
    ("Yoga Mat (Manduka PRO)", 599900),
    ("Mechanical Keyboard (Keychron K8)", 899900),
    ("Water Bottle (Hydro Flask)", 299900),
    ("Backpack (Samsonite)", 449900),
    ("Smartwatch Band (Apple)", 349900),
    ("USB-C Hub (Anker)", 249900),
    ("Desk Lamp (BenQ)", 699900),
    ("Earbuds (Samsung Galaxy Buds)", 849900),
    ("External SSD (Samsung T7)", 549900),
    ("Gaming Mouse (Logitech G502)", 399900),
]

CARRIERS = ["BlueDart", "Delhivery", "FedEx India", "DTDC", "Ecom Express"]
CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai",
    "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow",
]


class SyntheticCaseGenerator:
    """Generates synthetic chargeback cases for evaluation."""

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0

    def generate_all(self, count: int = 50) -> list[dict]:
        """Generate a full test set across all profiles."""
        cases: list[dict] = []
        cases.extend(self._generate_profile("A_STRONG", 15, self._make_strong_case))
        cases.extend(self._generate_profile("B_WEAK", 10, self._make_weak_case))
        cases.extend(self._generate_profile("C_MISSING", 10, self._make_missing_case))
        cases.extend(self._generate_profile("D_CONTRADICTORY", 10, self._make_contradictory_case))
        cases.extend(self._generate_profile("E_EDGE", 5, self._make_edge_case))

        if self.output_dir:
            # Write individual case files
            for case in cases:
                path = self.output_dir / f"{case['case_id']}.json"
                with open(path, "w") as f:
                    json.dump(case, f, indent=2, default=str)

            # Write manifest
            manifest = {
                "total_cases": len(cases),
                "profiles": {
                    "A_STRONG": 15,
                    "B_WEAK": 10,
                    "C_MISSING": 10,
                    "D_CONTRADICTORY": 10,
                    "E_EDGE": 5,
                },
                "case_ids": [c["case_id"] for c in cases],
            }
            with open(self.output_dir / "manifest.json", "w") as f:
                json.dump(manifest, f, indent=2)

        return cases

    def _generate_profile(
        self,
        profile: str,
        count: int,
        factory: Any,
    ) -> list[dict]:
        """Generate N cases for a given profile."""
        cases = []
        for _ in range(count):
            self._counter += 1
            case = factory(self._counter, profile)
            cases.append(case)
        return cases

    def _random_person(self) -> tuple[str, str, str]:
        """Generate a random Indian name, email, phone."""
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}@example.com"
        phone = f"+91{random.randint(7000000000, 9999999999)}"
        return name, email, phone

    def _random_product(self) -> tuple[str, int]:
        return random.choice(PRODUCTS)

    def _base_ids(self, n: int) -> dict:
        """Generate Razorpay-style IDs for a case."""
        short = uuid.uuid4().hex[:8]
        return {
            "case_id": f"CASE-{n:05d}",
            "dispute_id": f"disp_{short}Ov{n:04d}",
            "payment_id": f"pay_{short}Hf{n:04d}",
            "order_id": f"order_{short}Jb{n:04d}",
            "customer_id": f"cust_{short}Aa{n:04d}",
        }

    def _base_times(self, days_ago: int = 6) -> dict:
        """Generate a base timeline anchored to 'days_ago'."""
        now = datetime.now(timezone.utc)
        order_time = now - timedelta(days=days_ago)
        return {
            "order_time": order_time,
            "payment_time": order_time + timedelta(minutes=1),
            "ship_time": order_time + timedelta(days=1),
            "deliver_time": order_time + timedelta(days=3),
            "dispute_time": order_time + timedelta(days=5),
            "respond_by": order_time + timedelta(days=8),
        }

    # ── Profile A: Strong Evidence ────────────────────────────

    def _make_strong_case(self, n: int, profile: str) -> dict:
        ids = self._base_ids(n)
        times = self._base_times(days_ago=random.randint(5, 10))
        name, email, phone = self._random_person()
        product, amount = self._random_product()
        carrier = random.choice(CARRIERS)
        city = random.choice(CITIES)

        return {
            "case_id": ids["case_id"],
            "profile": profile,

            # Razorpay mock objects
            "razorpay_dispute": mock_dispute(
                dispute_id=ids["dispute_id"],
                payment_id=ids["payment_id"],
                amount=amount,
                created_at=int(times["dispute_time"].timestamp()),
                respond_by=int(times["respond_by"].timestamp()),
            ),
            "razorpay_payment": mock_payment(
                payment_id=ids["payment_id"],
                order_id=ids["order_id"],
                amount=amount,
                customer_id=ids["customer_id"],
                email=email,
                contact=phone,
                created_at=int(times["payment_time"].timestamp()),
            ),
            "razorpay_order": mock_order(
                order_id=ids["order_id"],
                amount=amount,
                receipt=f"ORD-{n:04d}",
                created_at=int(times["order_time"].timestamp()),
            ),
            "razorpay_customer": mock_customer(
                customer_id=ids["customer_id"],
                name=name,
                email=email,
                contact=phone,
            ),

            # Merchant data — all present and consistent
            "merchant_data": {
                "shipping": {
                    "carrier": carrier,
                    "tracking_id": f"BLU{random.randint(100000, 999999)}",
                    "shipped_at": times["ship_time"].isoformat(),
                    "origin_city": "Mumbai",
                    "destination_city": city,
                    "status": "delivered",
                },
                "delivery": {
                    "delivered_at": times["deliver_time"].isoformat(),
                    "signed_by": name.split()[0][0] + ". " + name.split()[1],
                    "delivery_address": f"Flat 402, {city}",
                    "proof_type": "signature",
                    "photo_proof": True,
                },
                "authentication": {
                    "method": "OTP",
                    "verified": True,
                    "device_known": True,
                    "ip_country": "IN",
                },
                "communications": [],
                "refunds": [],
            },

            # Expected outcome (ground truth for evaluation)
            "expected": {
                "recommendation": "contest",
                "case_strength": "high",
                "confidence": "high",
                "contradictions": 0,
                "missing_evidence": [],
                "auto_submit_eligible": True,
            },
        }

    # ── Profile B: Weak Evidence ──────────────────────────────

    def _make_weak_case(self, n: int, profile: str) -> dict:
        ids = self._base_ids(n)
        times = self._base_times(days_ago=random.randint(5, 10))
        name, email, phone = self._random_person()
        product, amount = self._random_product()

        return {
            "case_id": ids["case_id"],
            "profile": profile,
            "razorpay_dispute": mock_dispute(
                dispute_id=ids["dispute_id"],
                payment_id=ids["payment_id"],
                amount=amount,
                created_at=int(times["dispute_time"].timestamp()),
                respond_by=int(times["respond_by"].timestamp()),
            ),
            "razorpay_payment": mock_payment(
                payment_id=ids["payment_id"],
                order_id=ids["order_id"],
                amount=amount,
                customer_id=ids["customer_id"],
                email=email,
                contact=phone,
                created_at=int(times["payment_time"].timestamp()),
            ),
            "razorpay_order": mock_order(
                order_id=ids["order_id"],
                amount=amount,
                receipt=f"ORD-{n:04d}",
                created_at=int(times["order_time"].timestamp()),
            ),
            "razorpay_customer": mock_customer(
                customer_id=ids["customer_id"],
                name=name,
                email=email,
                contact=phone,
            ),
            "merchant_data": {
                "shipping": {
                    "carrier": random.choice(CARRIERS),
                    "tracking_id": f"DEL{random.randint(100000, 999999)}",
                    "shipped_at": times["ship_time"].isoformat(),
                    "status": "delivered",
                },
                "delivery": {
                    "delivered_at": times["deliver_time"].isoformat(),
                    "signed_by": None,       # No signature
                    "proof_type": "left_at_door",
                    "photo_proof": False,     # No photo
                },
                "authentication": {
                    "method": "OTP",
                    "verified": True,
                    "device_known": False,    # New device
                    "ip_country": "IN",
                },
                "communications": [],
                "refunds": [],
            },
            "expected": {
                "recommendation": "human_review",
                "case_strength": "medium",
                "confidence": "medium",
                "contradictions": 0,
                "missing_evidence": ["delivery_signature"],
                "auto_submit_eligible": False,
            },
        }

    # ── Profile C: Missing Evidence ───────────────────────────

    def _make_missing_case(self, n: int, profile: str) -> dict:
        ids = self._base_ids(n)
        times = self._base_times(days_ago=random.randint(5, 10))
        name, email, phone = self._random_person()
        product, amount = self._random_product()

        return {
            "case_id": ids["case_id"],
            "profile": profile,
            "razorpay_dispute": mock_dispute(
                dispute_id=ids["dispute_id"],
                payment_id=ids["payment_id"],
                amount=amount,
                created_at=int(times["dispute_time"].timestamp()),
                respond_by=int(times["respond_by"].timestamp()),
            ),
            "razorpay_payment": mock_payment(
                payment_id=ids["payment_id"],
                order_id=ids["order_id"],
                amount=amount,
                customer_id=ids["customer_id"],
                email=email,
                contact=phone,
                created_at=int(times["payment_time"].timestamp()),
            ),
            "razorpay_order": mock_order(
                order_id=ids["order_id"],
                amount=amount,
                receipt=f"ORD-{n:04d}",
                created_at=int(times["order_time"].timestamp()),
            ),
            "razorpay_customer": mock_customer(
                customer_id=ids["customer_id"],
                name=name,
                email=email,
                contact=phone,
            ),
            "merchant_data": {
                "shipping": {
                    "carrier": random.choice(CARRIERS),
                    "tracking_id": f"FDX{random.randint(100000, 999999)}",
                    "shipped_at": times["ship_time"].isoformat(),
                    "status": "in_transit",    # Never delivered
                },
                "delivery": None,              # NO delivery data
                "authentication": {
                    "method": "OTP",
                    "verified": True,
                    "device_known": True,
                    "ip_country": "IN",
                },
                "communications": [],
                "refunds": [],
            },
            "expected": {
                "recommendation": "accept_loss",
                "case_strength": "low",
                "confidence": "high",         # High confidence it's weak
                "contradictions": 0,
                "missing_evidence": ["delivery", "delivery_proof"],
                "auto_submit_eligible": False,
            },
        }

    # ── Profile D: Contradictory Evidence ─────────────────────

    def _make_contradictory_case(self, n: int, profile: str) -> dict:
        ids = self._base_ids(n)
        times = self._base_times(days_ago=random.randint(5, 10))
        name, email, phone = self._random_person()
        product, amount = self._random_product()

        return {
            "case_id": ids["case_id"],
            "profile": profile,
            "razorpay_dispute": mock_dispute(
                dispute_id=ids["dispute_id"],
                payment_id=ids["payment_id"],
                amount=amount,
                created_at=int(times["dispute_time"].timestamp()),
                respond_by=int(times["respond_by"].timestamp()),
            ),
            "razorpay_payment": mock_payment(
                payment_id=ids["payment_id"],
                order_id=ids["order_id"],
                amount=amount,
                customer_id=ids["customer_id"],
                email=email,
                contact=phone,
                created_at=int(times["payment_time"].timestamp()),
            ),
            "razorpay_order": mock_order(
                order_id=ids["order_id"],
                amount=amount,
                receipt=f"ORD-{n:04d}",
                created_at=int(times["order_time"].timestamp()),
            ),
            "razorpay_customer": mock_customer(
                customer_id=ids["customer_id"],
                name=name,
                email=email,
                contact=phone,
            ),
            "merchant_data": {
                "shipping": {
                    "carrier": random.choice(CARRIERS),
                    "tracking_id": f"DTC{random.randint(100000, 999999)}",
                    "shipped_at": times["ship_time"].isoformat(),
                    "status": "returned_to_sender",    # CONTRADICTION
                },
                "delivery": {
                    "delivered_at": times["deliver_time"].isoformat(),
                    "signed_by": name.split()[0][0] + ". " + name.split()[1],
                    "proof_type": "signature",
                    "photo_proof": False,
                    "source": "merchant_system",        # Merchant says delivered
                },
                "authentication": {
                    "method": "OTP",
                    "verified": True,
                    "device_known": True,
                    "ip_country": "IN",
                },
                "communications": [
                    {
                        "type": "support_ticket",
                        "timestamp": (times["deliver_time"] + timedelta(hours=2)).isoformat(),
                        "channel": "email",
                        "summary": "Customer confirmed receipt in support chat",
                        "direction": "inbound",
                    },
                ],
                "refunds": [],
            },
            "expected": {
                "recommendation": "human_review",
                "case_strength": "medium",
                "confidence": "low",
                "contradictions": 1,          # Merchant vs carrier
                "missing_evidence": [],
                "auto_submit_eligible": False,
            },
        }

    # ── Profile E: Edge Cases ─────────────────────────────────

    def _make_edge_case(self, n: int, profile: str) -> dict:
        ids = self._base_ids(n)
        times = self._base_times(days_ago=random.randint(5, 10))
        name, email, phone = self._random_person()
        product, amount = self._random_product()

        # Simulate timezone mismatch: delivery timestamp in PST
        # looks like it happened BEFORE the order in UTC if parsed wrong
        deliver_pst = times["deliver_time"] - timedelta(hours=13, minutes=30)

        return {
            "case_id": ids["case_id"],
            "profile": profile,
            "razorpay_dispute": mock_dispute(
                dispute_id=ids["dispute_id"],
                payment_id=ids["payment_id"],
                amount=amount,
                created_at=int(times["dispute_time"].timestamp()),
                respond_by=int(times["respond_by"].timestamp()),
            ),
            "razorpay_payment": mock_payment(
                payment_id=ids["payment_id"],
                order_id=ids["order_id"],
                amount=amount,
                customer_id=ids["customer_id"],
                email=email,
                contact=phone,
                created_at=int(times["payment_time"].timestamp()),
            ),
            "razorpay_order": mock_order(
                order_id=ids["order_id"],
                amount=amount,
                receipt=f"ORD-{n:04d}",
                created_at=int(times["order_time"].timestamp()),
            ),
            "razorpay_customer": mock_customer(
                customer_id=ids["customer_id"],
                name=name,
                email=email,
                contact=phone,
            ),
            "merchant_data": {
                "shipping": {
                    "carrier": random.choice(CARRIERS),
                    "tracking_id": f"ECM{random.randint(100000, 999999)}",
                    "shipped_at": times["ship_time"].isoformat(),
                    "status": "delivered",
                },
                "delivery": {
                    "delivered_at": deliver_pst.isoformat(),  # Wrong timezone!
                    "timezone": "America/Los_Angeles",        # PST, not IST
                    "signed_by": name.split()[0],
                    "proof_type": "signature",
                    "photo_proof": True,
                },
                "authentication": {
                    "method": "OTP",
                    "verified": True,
                    "device_known": True,
                    "ip_country": "IN",
                },
                "communications": [],
                "refunds": [],
            },
            "expected": {
                "recommendation": "human_review",
                "case_strength": "medium",
                "confidence": "medium",
                "contradictions": 0,
                "missing_evidence": [],
                "auto_submit_eligible": False,
                "notes": "Timezone mismatch — delivery timestamp in PST could look anomalous",
            },
        }


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/synthetic/cases")
    gen = SyntheticCaseGenerator(output_dir=output)
    cases = gen.generate_all()
    print(f"Generated {len(cases)} cases in {output}")
    for profile in ["A_STRONG", "B_WEAK", "C_MISSING", "D_CONTRADICTORY", "E_EDGE"]:
        count = sum(1 for c in cases if c["profile"] == profile)
        print(f"  {profile}: {count} cases")
