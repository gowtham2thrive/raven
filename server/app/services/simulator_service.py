"""
Dispute Case Simulator Service.

Generates realistic chargeback dispute cases across diverse archetypes:
- Physical Goods (Strong proof, Weak proof, Lost in transit)
- Fraud / Unauthorized (Strong 3DS, Suspicious IP/Device)
- Digital Services & Subscriptions (Active usage logs, Terms accepted)
- Product Quality / Not as Described (Expired policy, Chat logs)
- Billing / Duplicate Charge (Already refunded)
- Contradictory Evidence (Merchant vs Carrier conflict)
- Edge Cases (Timezone parsing discrepancies)
- Custom User-Defined Scenarios

All generated cases write to the canonical Synthetic data storage and
register in the database so that both the deterministic pipeline and ADK agent
can inspect them seamlessly.
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    AgentRunModel,
    AuditLogModel,
    CaseModel,
    ContradictionModel,
    EvidenceModel,
    TimelineEventModel,
)
from app.services.case_service import CaseService
from data.synthetic.generator import CARRIERS, CITIES, FIRST_NAMES, LAST_NAMES
from data.synthetic.razorpay_mock import (
    mock_customer,
    mock_dispute,
    mock_order,
    mock_payment,
    mock_refund,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  PRESET SCENARIO DEFINITIONS
# ═══════════════════════════════════════════════════════════════

SIMULATION_PRESETS = [
    {
        "id": "physical_strong_delivery",
        "name": "E-Commerce: Verified Delivery",
        "category": "Physical Goods",
        "icon": "truck",
        "reason_code": "product_not_received",
        "reason_description": "Customer claims the ordered product was never delivered to their address.",
        "default_product": "Wireless Headphones (Sony WH-1000XM5)",
        "default_amount": 2499900,  # ₹24,999.00
        "difficulty": "High Strength",
        "expected_recommendation": "contest",
        "expected_confidence": "high",
        "summary": "Complete proof chain: valid carrier tracking, recipient signature, photo proof, OTP auth, matching delivery coordinates.",
    },
    {
        "id": "physical_weak_delivery",
        "name": "E-Commerce: Unsigned Delivery",
        "category": "Physical Goods",
        "icon": "package",
        "reason_code": "product_not_received",
        "reason_description": "Customer claims package was not received. Courier marked as left at door without signature.",
        "default_product": "Running Shoes (Nike Air Max)",
        "default_amount": 899900,  # ₹8,999.00
        "difficulty": "Medium Strength",
        "expected_recommendation": "human_review",
        "expected_confidence": "medium",
        "summary": "Partial proof: courier marked left at door, no recipient signature, no photo proof. Requires human assessment.",
    },
    {
        "id": "physical_lost_in_transit",
        "name": "E-Commerce: Lost in Transit",
        "category": "Physical Goods",
        "icon": "alert-triangle",
        "reason_code": "product_not_received",
        "reason_description": "Customer complains package is delayed indefinitely and never arrived.",
        "default_product": "Mechanical Keyboard (Keychron K8)",
        "default_amount": 899900,  # ₹8,999.00
        "difficulty": "Low Strength",
        "expected_recommendation": "accept_loss",
        "expected_confidence": "high",
        "summary": "Carrier tracking stuck in-transit for weeks. No delivery confirmation exists. Recommend accept loss to avoid arbitration penalties.",
    },
    {
        "id": "unauthorized_strong_3ds",
        "name": "Fraud: Verified 3DS & Trusted Device",
        "category": "Fraud & Security",
        "icon": "shield-check",
        "reason_code": "unauthorized_transaction",
        "reason_description": "Customer claims their credit card was charged without their knowledge or authorization.",
        "default_product": "Annual Enterprise SaaS License",
        "default_amount": 1499900,  # ₹14,999.00
        "difficulty": "High Strength",
        "expected_recommendation": "contest",
        "expected_confidence": "high",
        "summary": "Strong authorization defense: 3D Secure v2 OTP authenticated, known device fingerprint with 12 prior orders, matching IP geo-location.",
    },
    {
        "id": "unauthorized_suspicious",
        "name": "Fraud: Suspicious Auth & Foreign IP",
        "category": "Fraud & Security",
        "icon": "shield-alert",
        "reason_code": "unauthorized_transaction",
        "reason_description": "Cardholder claims a fraudulent transaction was processed on their account.",
        "default_product": "Digital Gaming Gift Card",
        "default_amount": 1200000,  # ₹12,000.00
        "difficulty": "Low Strength",
        "expected_recommendation": "accept_loss",
        "expected_confidence": "high",
        "summary": "Weak merchant defense: OTP failed/fallback, foreign proxy IP detected, brand new device fingerprint. Cardholder claim likely genuine.",
    },
    {
        "id": "digital_service_active",
        "name": "SaaS: Active Usage & Access Logs",
        "category": "Digital Services",
        "icon": "activity",
        "reason_code": "service_not_rendered",
        "reason_description": "Customer claims they never received or used the digital software subscription.",
        "default_product": "Cloud Database Pro Subscription",
        "default_amount": 649900,  # ₹6,499.00
        "difficulty": "High Strength",
        "expected_recommendation": "contest",
        "expected_confidence": "high",
        "summary": "Platform access logs demonstrate 184 API requests and active user sessions after billing. Terms of service accepted with timestamp.",
    },
    {
        "id": "quality_return_expired",
        "name": "Quality: Return Window Expired",
        "category": "Product Quality",
        "icon": "check-circle",
        "reason_code": "product_not_as_described",
        "reason_description": "Customer claims item received is defective or materially different from listing description.",
        "default_product": "OtterBox Smartphone Case & Lens Kit",
        "default_amount": 349900,  # ₹3,499.00
        "difficulty": "High Strength",
        "expected_recommendation": "contest",
        "expected_confidence": "high",
        "summary": "Delivered 45 days prior (14-day return policy expired). Support chats show customer admitted user damage.",
    },
    {
        "id": "duplicate_billing_refunded",
        "name": "Billing: Duplicate Already Refunded",
        "category": "Billing & Charges",
        "icon": "refresh-cw",
        "reason_code": "duplicate_transaction",
        "reason_description": "Customer disputes double charge for a single order purchase.",
        "default_product": "Rain Design Laptop Stand",
        "default_amount": 349900,  # ₹3,499.00
        "difficulty": "High Strength",
        "expected_recommendation": "contest",
        "expected_confidence": "high",
        "summary": "Duplicate charge was already detected and automatically refunded via Razorpay refund ID within 24 hours. Proof of refund attached.",
    },
    {
        "id": "contradictory_carrier_rts",
        "name": "Conflict: Carrier Return vs Merchant",
        "category": "Contradictions",
        "icon": "git-pull-request",
        "reason_code": "product_not_received",
        "reason_description": "Dispute over delivery status: merchant logged delivery but courier reports returned.",
        "default_product": "Samsung Galaxy Buds Pro",
        "default_amount": 849900,  # ₹8,499.00
        "difficulty": "Contradiction Flagged",
        "expected_recommendation": "human_review",
        "expected_confidence": "low",
        "summary": "Direct evidence conflict: merchant internal DB records successful delivery, but carrier API shows 'returned_to_sender'. Flags mandatory human review.",
    },
    {
        "id": "edge_timezone_mismatch",
        "name": "Edge Case: Multi-Timezone Anomaly",
        "category": "Edge Cases",
        "icon": "clock",
        "reason_code": "product_not_received",
        "reason_description": "Disputed delivery timeline due to international timezone parsing discrepancies.",
        "default_product": "BenQ Designer Desk Lamp",
        "default_amount": 699900,  # ₹6,999.00
        "difficulty": "Medium Strength",
        "expected_recommendation": "human_review",
        "expected_confidence": "medium",
        "summary": "Carrier timestamp logged in America/Los_Angeles (PST) while merchant order logged in Asia/Kolkata (IST). Reconstructed with timezone awareness.",
    },
]


# ═══════════════════════════════════════════════════════════════
#  REQUEST / CONFIG SCHEMAS
# ═══════════════════════════════════════════════════════════════

class CustomCaseConfig(BaseModel):
    """Configuration for custom case simulation."""
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    product_name: str = "Custom Merchandise"
    amount_inr: float = 4999.00  # in rupees
    reason_code: str = "product_not_received"
    reason_description: str = "Customer claims item was not received."
    evidence_profile: str = "strong"  # strong | weak | missing | contradictory
    carrier: str = "Delhivery"
    delivery_status: str = "delivered"  # delivered | in_transit | returned_to_sender | none
    proof_type: str = "signature"  # signature | left_at_door | none
    auth_verified: bool = True
    device_known: bool = True
    has_refund: bool = False
    has_support_chat: bool = False


class SimulateCaseRequest(BaseModel):
    """API payload to simulate a case."""
    preset_id: str | None = None
    custom_config: CustomCaseConfig | None = None
    auto_investigate: bool = True


# ═══════════════════════════════════════════════════════════════
#  SIMULATOR SERVICE CLASS
# ═══════════════════════════════════════════════════════════════

class SimulatorService:
    """Core engine for dispute case generation and test environment management."""

    def __init__(self, cases_dir: Path | None = None):
        if cases_dir is None:
            cases_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "cases"
        self.cases_dir = cases_dir
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    def get_presets(self) -> list[dict]:
        """Return the catalog of simulation presets."""
        return SIMULATION_PRESETS

    def clear_all_cases(self, db: Session) -> int:
        """Purge all cases and related records from the database, and delete simulation files."""
        deleted_count = db.query(CaseModel).count()

        db.query(ContradictionModel).delete()
        db.query(TimelineEventModel).delete()
        db.query(AgentRunModel).delete()
        db.query(AuditLogModel).delete()
        db.query(EvidenceModel).delete()
        db.query(CaseModel).delete()

        db.commit()

        # Delete all simulation files (SIM-*.json) from self.cases_dir
        # Preserves golden cases CASE-00001.json - CASE-00057.json and manifest.json
        sim_files = list(self.cases_dir.glob("SIM-*.json"))
        removed_sim_files = 0
        for f in sim_files:
            try:
                f.unlink(missing_ok=True)
                removed_sim_files += 1
            except Exception as e:
                logger.warning(f"Failed to delete simulation file {f}: {e}")

        # Clear synthetic connector cache
        from app.connectors.synthetic import SyntheticConnector
        SyntheticConnector(self.cases_dir).clear_cache()

        logger.info(f"Purged {deleted_count} DB cases and {removed_sim_files} simulation files from {self.cases_dir}")
        return deleted_count

    def generate_case(
        self,
        request: SimulateCaseRequest,
        db: Session,
        case_service: CaseService,
    ) -> dict[str, Any]:
        """Generate a new synthetic case, store on disk and DB, and optionally investigate."""
        # 1. Generate unique IDs and timestamps
        now = datetime.now(timezone.utc)
        short_id = uuid.uuid4().hex[:6].upper()
        case_id = f"SIM-{short_id}"
        dispute_id = f"disp_{short_id.lower()}"
        payment_id = f"pay_{short_id.lower()}"
        order_id = f"order_{short_id.lower()}"
        customer_id = f"cust_{short_id.lower()}"

        # 2. Build case payload based on preset or custom config
        if request.preset_id:
            case_data = self._build_preset_case(
                preset_id=request.preset_id,
                case_id=case_id,
                dispute_id=dispute_id,
                payment_id=payment_id,
                order_id=order_id,
                customer_id=customer_id,
                now=now,
            )
        elif request.custom_config:
            case_data = self._build_custom_case(
                config=request.custom_config,
                case_id=case_id,
                dispute_id=dispute_id,
                payment_id=payment_id,
                order_id=order_id,
                customer_id=customer_id,
                now=now,
            )
        else:
            # Default to strong delivery preset
            case_data = self._build_preset_case(
                preset_id="physical_strong_delivery",
                case_id=case_id,
                dispute_id=dispute_id,
                payment_id=payment_id,
                order_id=order_id,
                customer_id=customer_id,
                now=now,
            )

        # 3. Write case JSON to disk so all connectors/tools can read it
        case_file = self.cases_dir / f"{case_id}.json"
        with open(case_file, "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=2, default=str)

        # 4. Insert into database
        dispute = case_data["razorpay_dispute"]
        payment = case_data["razorpay_payment"]

        case_record = CaseModel(
            id=case_id,
            status="created",
            dispute_reason=dispute.get("reason_description", "") or dispute.get("reason_code", "chargeback"),
            rzp_dispute_id=dispute["id"],
            rzp_payment_id=payment["id"],
            rzp_order_id=payment.get("order_id"),
            rzp_customer_id=payment.get("customer_id"),
            amount=dispute["amount"],
            currency=dispute.get("currency", "INR"),
            reason_code=dispute.get("reason_code", "product_not_received"),
            reason_description=dispute.get("reason_description", ""),
            dispute_phase=dispute.get("phase", "chargeback"),
            respond_by=datetime.fromtimestamp(dispute["respond_by"], tz=timezone.utc),
            rzp_dispute_status=dispute.get("status", "open"),
            rzp_created_at=datetime.fromtimestamp(dispute["created_at"], tz=timezone.utc),
        )
        db.add(case_record)

        # Audit log for creation
        audit = AuditLogModel(
            case_id=case_id,
            action="case_created",
            actor="system:simulator",
            details={
                "preset_id": request.preset_id,
                "profile": case_data.get("profile", "CUSTOM"),
                "simulated": True,
            },
        )
        db.add(audit)
        db.commit()
        db.refresh(case_record)

        # 5. Auto-investigate if requested
        investigation_result = None
        if request.auto_investigate:
            try:
                investigation_result = case_service.investigate(case_id, db)
                db.refresh(case_record)
            except Exception as e:
                logger.error(f"Auto-investigation failed for {case_id}: {e}", exc_info=True)

        return {
            "case_id": case_id,
            "status": case_record.status,
            "amount": case_record.amount,
            "currency": case_record.currency,
            "reason_code": case_record.reason_code,
            "reason_description": case_record.reason_description,
            "recommendation": case_record.recommendation,
            "case_strength": case_record.case_strength,
            "score": case_record.assessment_score,
            "auto_investigated": request.auto_investigate,
            "assessment": investigation_result.get("assessment") if investigation_result else None,
        }

    # ── Internal Generators ──────────────────────────────────────

    def _random_person(self) -> tuple[str, str, str]:
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}@example.com"
        phone = f"+91{random.randint(7000000000, 9999999999)}"
        return name, email, phone

    def _build_preset_case(
        self,
        preset_id: str,
        case_id: str,
        dispute_id: str,
        payment_id: str,
        order_id: str,
        customer_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        """Build case JSON for a named preset archetype."""
        name, email, phone = self._random_person()
        city = random.choice(CITIES)
        carrier = random.choice(CARRIERS)

        # Timeline anchor: 6 days ago
        order_time = now - timedelta(days=6)
        pay_time = order_time + timedelta(minutes=1)
        ship_time = order_time + timedelta(days=1)
        deliv_time = order_time + timedelta(days=3)
        disp_time = order_time + timedelta(days=5)
        respond_by = order_time + timedelta(days=9)

        if preset_id in ("physical_strong_delivery", "physical_strong"):
            amount = 2499900
            return {
                "case_id": case_id,
                "profile": "A_STRONG",
                "razorpay_dispute": mock_dispute(
                    dispute_id=dispute_id, payment_id=payment_id, amount=amount,
                    reason_code="product_not_received",
                    created_at=int(disp_time.timestamp()), respond_by=int(respond_by.timestamp()),
                ),
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": mock_order(
                    order_id=order_id, amount=amount, receipt=f"ORD-{case_id[-4:]}",
                    created_at=int(order_time.timestamp()),
                ),
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": {
                        "carrier": carrier,
                        "tracking_id": f"BLU{random.randint(100000, 999999)}",
                        "shipped_at": ship_time.isoformat(),
                        "origin_city": "Mumbai",
                        "destination_city": city,
                        "status": "delivered",
                    },
                    "delivery": {
                        "delivered_at": deliv_time.isoformat(),
                        "signed_by": name.split()[0][0] + ". " + name.split()[1],
                        "delivery_address": f"Flat 402, {city}",
                        "proof_type": "signature",
                        "photo_proof": True,
                    },
                    "authentication": {
                        "method": "OTP", "verified": True, "device_known": True, "ip_country": "IN",
                    },
                    "communications": [],
                    "refunds": [],
                },
                "expected": {
                    "recommendation": "contest", "case_strength": "high", "confidence": "high",
                    "auto_submit_eligible": True,
                },
            }

        elif preset_id in ("physical_weak_delivery", "physical_weak_unsigned", "physical_weak"):
            amount = 899900
            return {
                "case_id": case_id,
                "profile": "B_WEAK",
                "razorpay_dispute": mock_dispute(
                    dispute_id=dispute_id, payment_id=payment_id, amount=amount,
                    reason_code="product_not_received",
                    created_at=int(disp_time.timestamp()), respond_by=int(respond_by.timestamp()),
                ),
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": mock_order(
                    order_id=order_id, amount=amount, receipt=f"ORD-{case_id[-4:]}",
                    created_at=int(order_time.timestamp()),
                ),
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": {
                        "carrier": carrier,
                        "tracking_id": f"DEL{random.randint(100000, 999999)}",
                        "shipped_at": ship_time.isoformat(),
                        "status": "delivered",
                    },
                    "delivery": {
                        "delivered_at": deliv_time.isoformat(),
                        "signed_by": None,
                        "proof_type": "left_at_door",
                        "photo_proof": False,
                    },
                    "authentication": {
                        "method": "OTP", "verified": True, "device_known": False, "ip_country": "IN",
                    },
                    "communications": [],
                    "refunds": [],
                },
                "expected": {
                    "recommendation": "human_review", "case_strength": "medium", "confidence": "medium",
                    "auto_submit_eligible": False,
                },
            }

        elif preset_id in ("physical_lost_in_transit", "physical_in_transit_lost", "physical_lost"):
            amount = 899900
            return {
                "case_id": case_id,
                "profile": "C_MISSING",
                "razorpay_dispute": mock_dispute(
                    dispute_id=dispute_id, payment_id=payment_id, amount=amount,
                    reason_code="product_not_received",
                    created_at=int(disp_time.timestamp()), respond_by=int(respond_by.timestamp()),
                ),
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": mock_order(
                    order_id=order_id, amount=amount, receipt=f"ORD-{case_id[-4:]}",
                    created_at=int(order_time.timestamp()),
                ),
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": {
                        "carrier": carrier,
                        "tracking_id": f"FDX{random.randint(100000, 999999)}",
                        "shipped_at": ship_time.isoformat(),
                        "status": "in_transit",
                    },
                    "delivery": None,
                    "authentication": {
                        "method": "OTP", "verified": True, "device_known": True, "ip_country": "IN",
                    },
                    "communications": [],
                    "refunds": [],
                },
                "expected": {
                    "recommendation": "accept_loss", "case_strength": "low", "confidence": "high",
                    "auto_submit_eligible": False,
                },
            }

        elif preset_id in ("unauthorized_strong_3ds", "unauthorized_strong"):
            amount = 1499900
            return {
                "case_id": case_id,
                "profile": "UNAUTHORIZED_STRONG_AUTH",
                "razorpay_dispute": {
                    "id": dispute_id, "entity": "dispute", "payment_id": payment_id,
                    "amount": amount, "currency": "INR", "amount_deducted": 0,
                    "reason_code": "unauthorized_transaction",
                    "reason_description": "I did not authorize this payment. Card was charged fraudulently.",
                    "respond_by": int(respond_by.timestamp()), "status": "open", "phase": "chargeback",
                    "created_at": int(disp_time.timestamp()),
                },
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": {
                    "id": order_id, "entity": "order", "amount": amount, "amount_paid": amount,
                    "currency": "INR", "receipt": f"SUB-{case_id[-4:]}", "status": "paid",
                    "notes": {"item": "Annual Enterprise SaaS License"},
                    "created_at": int(order_time.timestamp()),
                },
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": None,
                    "delivery": None,
                    "authentication": {
                        "method": "3DS_v2", "verified": True, "device_known": True,
                        "ip_country": "IN", "ip_address": "103.21.45.78",
                        "device_fingerprint": "d8f9a2e1-known-device", "previous_transactions": 12,
                    },
                    "communications": [],
                    "refunds": [],
                },
                "expected": {
                    "recommendation": "contest", "case_strength": "high", "confidence": "high",
                },
            }

        elif preset_id == "unauthorized_suspicious":
            amount = 1200000
            return {
                "case_id": case_id,
                "profile": "UNAUTHORIZED_WEAK_AUTH",
                "razorpay_dispute": {
                    "id": dispute_id, "entity": "dispute", "payment_id": payment_id,
                    "amount": amount, "currency": "INR", "amount_deducted": 0,
                    "reason_code": "unauthorized_transaction",
                    "reason_description": "Fraudulent transaction reported by issuer.",
                    "respond_by": int(respond_by.timestamp()), "status": "open", "phase": "chargeback",
                    "created_at": int(disp_time.timestamp()),
                },
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": {
                    "id": order_id, "entity": "order", "amount": amount, "amount_paid": amount,
                    "currency": "INR", "receipt": f"GFT-{case_id[-4:]}", "status": "paid",
                    "notes": {"item": "Digital Gaming Gift Card"},
                    "created_at": int(order_time.timestamp()),
                },
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": None,
                    "delivery": None,
                    "authentication": {
                        "method": "None", "verified": False, "device_known": False,
                        "ip_country": "RU", "ip_address": "185.220.101.5",
                        "device_fingerprint": "new-untrusted-proxy", "previous_transactions": 0,
                    },
                    "communications": [],
                    "refunds": [],
                },
                "expected": {
                    "recommendation": "accept_loss", "case_strength": "low", "confidence": "high",
                },
            }

        elif preset_id in ("digital_service_active", "digital_service"):
            amount = 649900
            return {
                "case_id": case_id,
                "profile": "SERVICE_ACTIVE_USAGE",
                "razorpay_dispute": {
                    "id": dispute_id, "entity": "dispute", "payment_id": payment_id,
                    "amount": amount, "currency": "INR", "amount_deducted": 0,
                    "reason_code": "service_not_rendered",
                    "reason_description": "Claiming software subscription was never provided.",
                    "respond_by": int(respond_by.timestamp()), "status": "open", "phase": "chargeback",
                    "created_at": int(disp_time.timestamp()),
                },
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": {
                    "id": order_id, "entity": "order", "amount": amount, "amount_paid": amount,
                    "currency": "INR", "receipt": f"SRV-{case_id[-4:]}", "status": "paid",
                    "notes": {"item": "Cloud Database Pro Subscription"},
                    "created_at": int(order_time.timestamp()),
                },
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": None,
                    "delivery": None,
                    "authentication": {
                        "method": "OTP", "verified": True, "device_known": True, "ip_country": "IN",
                    },
                    "communications": [
                        {
                            "type": "support_ticket",
                            "timestamp": (deliv_time + timedelta(hours=3)).isoformat(),
                            "channel": "email",
                            "summary": "Customer requested API quota upgrade and thanked support team.",
                            "direction": "inbound",
                        }
                    ],
                    "refunds": [],
                },
                "expected": {
                    "recommendation": "contest", "case_strength": "high", "confidence": "high",
                },
            }

        elif preset_id in ("quality_return_expired", "quality_return_window_expired", "quality_expired"):
            amount = 349900
            return {
                "case_id": case_id,
                "profile": "QUALITY_RETURN_EXPIRED",
                "razorpay_dispute": {
                    "id": dispute_id, "entity": "dispute", "payment_id": payment_id,
                    "amount": amount, "currency": "INR", "amount_deducted": 0,
                    "reason_code": "product_not_as_described",
                    "reason_description": "Product is different from what was advertised.",
                    "respond_by": int(respond_by.timestamp()), "status": "open", "phase": "chargeback",
                    "created_at": int(disp_time.timestamp()),
                },
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": mock_order(
                    order_id=order_id, amount=amount, receipt=f"ORD-{case_id[-4:]}",
                    created_at=int(order_time.timestamp()),
                ),
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": {
                        "carrier": carrier,
                        "tracking_id": f"BLU{random.randint(100000, 999999)}",
                        "shipped_at": ship_time.isoformat(),
                        "status": "delivered",
                    },
                    "delivery": {
                        "delivered_at": deliv_time.isoformat(),
                        "signed_by": name,
                        "proof_type": "signature",
                        "photo_proof": True,
                    },
                    "authentication": {
                        "method": "OTP", "verified": True, "device_known": True, "ip_country": "IN",
                    },
                    "communications": [
                        {
                            "type": "support_ticket",
                            "timestamp": (deliv_time + timedelta(days=1)).isoformat(),
                            "channel": "chat",
                            "summary": "Customer stated they dropped and broke the case, requested free replacement outside warranty.",
                            "direction": "inbound",
                        }
                    ],
                    "refunds": [],
                },
                "expected": {
                    "recommendation": "contest", "case_strength": "high", "confidence": "high",
                },
            }

        elif preset_id in ("duplicate_billing_refunded", "duplicate_charge_refunded", "duplicate_refunded"):
            amount = 349900
            return {
                "case_id": case_id,
                "profile": "DUPLICATE_ALREADY_REFUNDED",
                "razorpay_dispute": {
                    "id": dispute_id, "entity": "dispute", "payment_id": payment_id,
                    "amount": amount, "currency": "INR", "amount_deducted": 0,
                    "reason_code": "duplicate_transaction",
                    "reason_description": "Card was billed twice for a single order.",
                    "respond_by": int(respond_by.timestamp()), "status": "open", "phase": "chargeback",
                    "created_at": int(disp_time.timestamp()),
                },
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": mock_order(
                    order_id=order_id, amount=amount, receipt=f"ORD-{case_id[-4:]}",
                    created_at=int(order_time.timestamp()),
                ),
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": {
                        "carrier": carrier,
                        "tracking_id": f"DEL{random.randint(100000, 999999)}",
                        "shipped_at": ship_time.isoformat(),
                        "status": "delivered",
                    },
                    "delivery": {
                        "delivered_at": deliv_time.isoformat(),
                        "signed_by": name,
                        "proof_type": "signature",
                        "photo_proof": True,
                    },
                    "authentication": {
                        "method": "OTP", "verified": True, "device_known": True, "ip_country": "IN",
                    },
                    "communications": [],
                    "refunds": [
                        mock_refund(
                            refund_id=f"rfnd_{case_id[-6:].lower()}01",
                            payment_id=payment_id,
                            amount=amount,
                            status="processed",
                            created_at=int((pay_time + timedelta(hours=2)).timestamp()),
                        )
                    ],
                },
                "expected": {
                    "recommendation": "contest", "case_strength": "high", "confidence": "high",
                },
            }

        elif preset_id in ("contradictory_carrier_rts", "contradictory_rts", "contradiction"):
            amount = 849900
            return {
                "case_id": case_id,
                "profile": "D_CONTRADICTORY",
                "razorpay_dispute": mock_dispute(
                    dispute_id=dispute_id, payment_id=payment_id, amount=amount,
                    reason_code="product_not_received",
                    created_at=int(disp_time.timestamp()), respond_by=int(respond_by.timestamp()),
                ),
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": mock_order(
                    order_id=order_id, amount=amount, receipt=f"ORD-{case_id[-4:]}",
                    created_at=int(order_time.timestamp()),
                ),
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": {
                        "carrier": carrier,
                        "tracking_id": f"DTC{random.randint(100000, 999999)}",
                        "shipped_at": ship_time.isoformat(),
                        "status": "returned_to_sender",  # Conflict!
                    },
                    "delivery": {
                        "delivered_at": deliv_time.isoformat(),
                        "signed_by": name,
                        "proof_type": "signature",
                        "photo_proof": False,
                        "source": "merchant_system",
                    },
                    "authentication": {
                        "method": "OTP", "verified": True, "device_known": True, "ip_country": "IN",
                    },
                    "communications": [
                        {
                            "type": "support_ticket",
                            "timestamp": (deliv_time + timedelta(hours=2)).isoformat(),
                            "channel": "email",
                            "summary": "Customer confirmed courier refused delivery and sent parcel back.",
                            "direction": "inbound",
                        }
                    ],
                    "refunds": [],
                },
                "expected": {
                    "recommendation": "human_review", "case_strength": "medium", "confidence": "low",
                    "contradictions": 1,
                },
            }

        else:  # edge_timezone_mismatch
            amount = 699900
            # Delivery appears before order due to timezone calculation anomaly
            deliver_pst = order_time - timedelta(hours=2)
            return {
                "case_id": case_id,
                "profile": "E_EDGE",
                "razorpay_dispute": mock_dispute(
                    dispute_id=dispute_id, payment_id=payment_id, amount=amount,
                    reason_code="product_not_received",
                    created_at=int(disp_time.timestamp()), respond_by=int(respond_by.timestamp()),
                ),
                "razorpay_payment": mock_payment(
                    payment_id=payment_id, order_id=order_id, amount=amount,
                    customer_id=customer_id, email=email, contact=phone, name=name,
                    created_at=int(pay_time.timestamp()),
                ),
                "razorpay_order": mock_order(
                    order_id=order_id, amount=amount, receipt=f"ORD-{case_id[-4:]}",
                    created_at=int(order_time.timestamp()),
                ),
                "razorpay_customer": mock_customer(
                    customer_id=customer_id, name=name, email=email, contact=phone,
                ),
                "merchant_data": {
                    "shipping": {
                        "carrier": carrier,
                        "tracking_id": f"ECM{random.randint(100000, 999999)}",
                        "shipped_at": ship_time.isoformat(),
                        "status": "delivered",
                    },
                    "delivery": {
                        "delivered_at": deliver_pst.isoformat(),
                        "timezone": "America/Los_Angeles",
                        "signed_by": name.split()[0],
                        "proof_type": "signature",
                        "photo_proof": True,
                    },
                    "authentication": {
                        "method": "OTP", "verified": True, "device_known": True, "ip_country": "IN",
                    },
                    "communications": [],
                    "refunds": [],
                },
                "expected": {
                    "recommendation": "human_review", "case_strength": "medium", "confidence": "medium",
                },
            }

    def _build_custom_case(
        self,
        config: CustomCaseConfig,
        case_id: str,
        dispute_id: str,
        payment_id: str,
        order_id: str,
        customer_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        """Build case JSON for custom configuration."""
        name = config.customer_name or f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        email = config.customer_email or f"{name.lower().replace(' ', '.')}@example.com"
        phone = config.customer_phone or f"+91{random.randint(7000000000, 9999999999)}"
        amount_paise = int(config.amount_inr * 100)

        order_time = now - timedelta(days=6)
        pay_time = order_time + timedelta(minutes=1)
        ship_time = order_time + timedelta(days=1)
        deliv_time = order_time + timedelta(days=3)
        disp_time = order_time + timedelta(days=5)
        respond_by = order_time + timedelta(days=9)

        # Shipping object
        shipping_obj = None
        if config.delivery_status != "none":
            shipping_obj = {
                "carrier": config.carrier,
                "tracking_id": f"TRK{random.randint(100000, 999999)}",
                "shipped_at": ship_time.isoformat(),
                "status": config.delivery_status,
                "origin_city": "Mumbai",
                "destination_city": "Bangalore",
            }

        # Delivery object
        delivery_obj = None
        if config.delivery_status == "delivered":
            delivery_obj = {
                "delivered_at": deliv_time.isoformat(),
                "signed_by": name if config.proof_type == "signature" else None,
                "proof_type": config.proof_type,
                "photo_proof": config.proof_type == "signature",
                "delivery_address": "Sector 4, Bangalore",
            }

        # Comms
        comms = []
        if config.has_support_chat:
            comms.append({
                "type": "support_ticket",
                "timestamp": (deliv_time + timedelta(hours=2)).isoformat(),
                "channel": "chat",
                "summary": "Customer engaged in support discussion regarding the order.",
                "direction": "inbound",
            })

        # Refunds
        refunds = []
        if config.has_refund:
            refunds.append(
                mock_refund(
                    refund_id=f"rfnd_{uuid.uuid4().hex[:8]}",
                    payment_id=payment_id,
                    amount=amount_paise,
                    status="processed",
                    created_at=int((pay_time + timedelta(hours=4)).timestamp()),
                )
            )

        return {
            "case_id": case_id,
            "profile": f"CUSTOM_{config.evidence_profile.upper()}",
            "razorpay_dispute": mock_dispute(
                dispute_id=dispute_id,
                payment_id=payment_id,
                amount=amount_paise,
                reason_code=config.reason_code,
                reason_description=config.reason_description,
                created_at=int(disp_time.timestamp()),
                respond_by=int(respond_by.timestamp()),
            ),
            "razorpay_payment": mock_payment(
                payment_id=payment_id,
                order_id=order_id,
                amount=amount_paise,
                customer_id=customer_id,
                email=email,
                contact=phone,
                name=name,
                created_at=int(pay_time.timestamp()),
            ),
            "razorpay_order": mock_order(
                order_id=order_id,
                amount=amount_paise,
                receipt=f"ORD-{case_id[-4:]}",
                item=config.product_name,
                created_at=int(order_time.timestamp()),
            ),
            "razorpay_customer": mock_customer(
                customer_id=customer_id,
                name=name,
                email=email,
                contact=phone,
            ),
            "merchant_data": {
                "shipping": shipping_obj,
                "delivery": delivery_obj,
                "authentication": {
                    "method": "3DS_v2" if config.auth_verified else "None",
                    "verified": config.auth_verified,
                    "device_known": config.device_known,
                    "ip_country": "IN",
                },
                "communications": comms,
                "refunds": refunds,
            },
            "expected": {
                "recommendation": "contest" if config.evidence_profile == "strong" else "human_review",
            },
        }
