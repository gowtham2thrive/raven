"""
Database Seeding Script.

Seeds the RAVEN database with synthetic cases for development and evaluation.

Usage:
    cd server
    python -m data.seed
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add server directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import Base, SessionLocal, engine
from app.db.models import AuditLogModel, CaseModel
from data.synthetic.generator import SyntheticCaseGenerator


def seed(case_count: int = 50) -> int:
    """Seed the database with synthetic cases.

    Returns:
        Number of cases seeded
    """
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("[OK] Database tables created")

    # Generate synthetic cases
    output_dir = Path(__file__).parent / "synthetic" / "cases"
    generator = SyntheticCaseGenerator(output_dir=output_dir)
    cases = generator.generate_all(count=case_count)
    print(f"[OK] Generated {len(cases)} synthetic cases")

    # Insert into database
    db = SessionLocal()
    inserted = 0
    try:
        for case_data in cases:
            dispute = case_data["razorpay_dispute"]
            payment = case_data["razorpay_payment"]

            # Check if case already exists (safe re-seeding)
            existing = db.query(CaseModel).filter_by(id=case_data["case_id"]).first()
            if existing:
                continue

            case = CaseModel(
                id=case_data["case_id"],
                status="created",
                dispute_reason=dispute.get("reason_description", "") or dispute.get("reason_code", "product_not_received"),
                rzp_dispute_id=dispute["id"],
                rzp_payment_id=dispute["payment_id"],
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
            db.add(case)

            # Add initial audit log
            audit = AuditLogModel(
                case_id=case_data["case_id"],
                action="case_created",
                actor="system:seed",
                details={
                    "source": "synthetic_data_generator",
                    "profile": case_data["profile"],
                },
            )
            db.add(audit)
            inserted += 1

        db.commit()
        print(f"[OK] Seeded {inserted} cases into database")

        # Print summary
        from sqlalchemy import func

        total = db.query(func.count(CaseModel.id)).scalar()
        print(f"\n  Total cases in database: {total}")

        statuses = (
            db.query(CaseModel.status, func.count(CaseModel.id))
            .group_by(CaseModel.status)
            .all()
        )
        for status, count in statuses:
            print(f"  Status '{status}': {count}")

    finally:
        db.close()

    return inserted


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    seed(count)
