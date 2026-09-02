"""
Synthetic Data Connector.

Reads merchant data from generated test case JSON files.
In production, these would be replaced by real API calls
to the merchant's shipping provider, CRM, auth service, etc.

The investigation engine doesn't know the difference —
it always gets the same dict structure regardless of source.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SyntheticConnector:
    """Reads merchant data from synthetic case JSON files.

    Acts as a unified connector for all merchant data sources
    during development and evaluation.
    """

    def __init__(self, cases_dir: Path | None = None):
        if cases_dir is None:
            cases_dir = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "cases"
        self._cases_dir = cases_dir
        self._cache: dict[str, dict] = {}

    def clear_cache(self) -> None:
        """Clear the in-memory case cache."""
        self._cache.clear()

    def _load_case(self, case_id: str) -> dict | None:
        """Load a synthetic case from disk (with caching)."""
        if case_id in self._cache:
            return self._cache[case_id]

        case_file = self._cases_dir / f"{case_id}.json"
        if not case_file.exists():
            logger.warning(f"Synthetic case file not found: {case_file}")
            return None

        try:
            with open(case_file) as f:
                data = json.load(f)
            self._cache[case_id] = data
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load synthetic case {case_id}: {e}")
            return None

    def get_merchant_data(self, case_id: str) -> dict | None:
        """Get the full merchant_data block for a case."""
        case = self._load_case(case_id)
        if case is None:
            return None
        return case.get("merchant_data")

    def get_shipping(self, case_id: str, order_id: str = "") -> dict | None:
        """Get shipping data from synthetic case.

        Returns: {
            carrier, tracking_id, shipped_at, origin_city,
            destination_city, status, events
        } or None
        """
        merchant = self.get_merchant_data(case_id)
        if merchant is None:
            return None
        return merchant.get("shipping")

    def get_delivery(self, case_id: str, order_id: str = "") -> dict | None:
        """Get delivery proof from synthetic case.

        Returns: {
            delivered_at, signed_by, delivery_address,
            proof_type, photo_proof, source
        } or None
        """
        merchant = self.get_merchant_data(case_id)
        if merchant is None:
            return None
        return merchant.get("delivery")

    def get_communications(self, case_id: str, customer_id: str = "") -> list[dict]:
        """Get customer communications from synthetic case.

        Returns: list of {type, timestamp, channel, summary, direction}
        """
        merchant = self.get_merchant_data(case_id)
        if merchant is None:
            return []
        return merchant.get("communications", [])

    def get_auth(self, case_id: str, payment_id: str = "") -> dict | None:
        """Get authentication events from synthetic case.

        Returns: {
            method, verified, device_known, ip_country
        } or None
        """
        merchant = self.get_merchant_data(case_id)
        if merchant is None:
            return None
        return merchant.get("authentication")

    def get_refunds(self, case_id: str, payment_id: str = "") -> list[dict]:
        """Get refund history from synthetic case.

        Returns: list of refund dicts
        """
        merchant = self.get_merchant_data(case_id)
        if merchant is None:
            return []
        return merchant.get("refunds", [])

    def get_expected_outcome(self, case_id: str) -> dict | None:
        """Get expected outcome (ground truth) for evaluation."""
        case = self._load_case(case_id)
        if case is None:
            return None
        return case.get("expected")

    def get_razorpay_data(self, case_id: str) -> dict[str, Any]:
        """Get all Razorpay mock objects for a case."""
        case = self._load_case(case_id)
        if case is None:
            return {}
        return {
            "dispute": case.get("razorpay_dispute"),
            "payment": case.get("razorpay_payment"),
            "order": case.get("razorpay_order"),
            "customer": case.get("razorpay_customer"),
        }
