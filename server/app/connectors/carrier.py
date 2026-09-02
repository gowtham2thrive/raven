"""
Mock Carrier Connector.

Simulates an independent carrier API (e.g., FedEx, BlueDart, Delhivery)
for testing multi-source triangulation.

In production, this would be replaced by a real carrier API connector.
The investigation engine doesn't know the difference — it always gets
the same canonical Evidence structure regardless of source.

Profiles:
    CASE-00001 to CASE-00015: Carrier CONFIRMS delivery (agrees with merchant)
    CASE-00016 to CASE-00025: Carrier has NO delivery record
    CASE-00026 to CASE-00035: Carrier has NO data (missing)
    CASE-00036 to CASE-00045: Carrier says RETURNED (conflicts with merchant)
    CASE-00046 to CASE-00050: Carrier has partial/ambiguous data
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.pipeline.ingest import _hash_payload, _make_id, _utc_now
from app.core.types import EvidenceCategory, EvidenceStatus
from app.core.schemas import Evidence

logger = logging.getLogger(__name__)


class MockCarrierConnector:
    """Simulates an independent carrier tracking API.

    Returns delivery evidence from the carrier's perspective,
    independently of the merchant's delivery records.
    """

    def get_delivery_status(self, case_id: str, tracking_id: str = "") -> Evidence | None:
        """Query the carrier for delivery status.

        Returns canonical Evidence from the carrier's perspective,
        or None if the carrier has no data for this shipment.
        """
        # If there's no shipping or delivery in the case at all (e.g. digital goods / pure auth transactions), carrier has no data
        try:
            from app.connectors.synthetic import SyntheticConnector
            conn = SyntheticConnector()
            ship = conn.get_shipping(case_id)
            deliv = conn.get_delivery(case_id)
            if ship is None and deliv is None:
                return None
            case_data = conn._load_case(case_id)
            if case_data and "profile" in case_data:
                profile = str(case_data["profile"]).upper()
                if profile in ("A_STRONG", "CUSTOM_STRONG") or profile.startswith("A_"):
                    return self._confirmed_delivery(case_id, tracking_id)
                elif profile in ("B_WEAK", "CUSTOM_WEAK") or profile.startswith("B_"):
                    return self._no_delivery_scan(case_id, tracking_id)
                elif profile in ("C_MISSING", "CUSTOM_MISSING") or profile.startswith("C_"):
                    return None
                elif profile in ("D_CONTRADICTORY", "CUSTOM_CONTRADICTORY") or profile.startswith("D_"):
                    return self._returned_to_sender(case_id, tracking_id)
                elif profile in ("E_EDGE", "CUSTOM_EDGE") or profile.startswith("E_"):
                    return self._ambiguous_delivery(case_id, tracking_id)
        except Exception:
            pass

        case_num = self._parse_case_number(case_id)
        if case_num is None:
            return None

        # Profile A: Strong cases — carrier confirms delivery
        if 1 <= case_num <= 15:
            return self._confirmed_delivery(case_id, tracking_id)

        # Profile B: Weak cases — carrier has no delivery scan
        if 16 <= case_num <= 25:
            return self._no_delivery_scan(case_id, tracking_id)

        # Profile C: Missing — carrier has no data at all
        if 26 <= case_num <= 35:
            return None

        # Profile D: Contradictory — carrier says returned
        if 36 <= case_num <= 45:
            return self._returned_to_sender(case_id, tracking_id)

        # Profile E: Edge — carrier has ambiguous data
        if 46 <= case_num <= 50:
            return self._ambiguous_delivery(case_id, tracking_id)

        return None

    def _get_case_delivery_time(self, case_id: str) -> datetime | None:
        """Fetch delivery timestamp from synthetic case if present."""
        try:
            from app.connectors.synthetic import SyntheticConnector
            conn = SyntheticConnector()
            deliv = conn.get_delivery(case_id)
            if deliv and deliv.get("delivered_at"):
                dt_str = str(deliv["delivered_at"])
                if dt_str.endswith("Z"):
                    dt_str = dt_str[:-1] + "+00:00"
                return datetime.fromisoformat(dt_str)
        except Exception:
            pass
        return None

    def _confirmed_delivery(self, case_id: str, tracking_id: str) -> Evidence:
        """Carrier confirms delivery with GPS coordinates."""
        deliv_dt = self._get_case_delivery_time(case_id) or _utc_now()
        iso_str = deliv_dt.isoformat()
        payload = {
            "carrier": "MockCarrier",
            "tracking_id": tracking_id or "MC-TRACK-001",
            "status": "delivered",
            "delivered_at": iso_str,
            "delivery_type": "doorstep",
            "gps_lat": 18.5204,
            "gps_lng": 73.8567,
        }
        return Evidence(
            evidence_id=_make_id(),
            case_id=case_id,
            category=EvidenceCategory.DELIVERY,
            status=EvidenceStatus.AVAILABLE,
            source_system="carrier_api",
            source_record_id=tracking_id or "MC-TRACK-001",
            event_time=deliv_dt,
            event_timezone="UTC",
            event_time_utc=deliv_dt,
            timezone_confident=True,
            observed_at=_utc_now(),
            content={
                "status": "delivered",
                "delivered_at": iso_str,
                "delivery_type": "doorstep",
                "signed_by": None,
                "proof_type": "gps",
            },
            summary="Carrier confirms delivery (GPS verified, doorstep)",
            relevance="high",
            reliability="high",
            raw_source=payload,
            raw_source_hash=_hash_payload(payload),
        )

    def _no_delivery_scan(self, case_id: str, tracking_id: str) -> Evidence:
        """Carrier shows in-transit, no delivery scan."""
        payload = {
            "carrier": "MockCarrier",
            "tracking_id": tracking_id or "MC-TRACK-002",
            "status": "in_transit",
            "last_scan": "2026-08-21T18:00:00+05:30",
        }
        return Evidence(
            evidence_id=_make_id(),
            case_id=case_id,
            category=EvidenceCategory.DELIVERY,
            status=EvidenceStatus.UNVERIFIED,
            source_system="carrier_api",
            source_record_id=tracking_id or "MC-TRACK-002",
            observed_at=_utc_now(),
            content={
                "status": "in_transit",
                "last_scan": "2026-08-21T18:00:00+05:30",
                "proof_type": "none",
            },
            summary="Carrier shows in-transit, no delivery confirmation",
            relevance="high",
            reliability="medium",
            raw_source=payload,
            raw_source_hash=_hash_payload(payload),
        )

    def _returned_to_sender(self, case_id: str, tracking_id: str) -> Evidence:
        """Carrier says package was returned to sender."""
        payload = {
            "carrier": "MockCarrier",
            "tracking_id": tracking_id or "MC-TRACK-003",
            "status": "returned_to_sender",
            "return_reason": "customer_refused",
            "returned_at": "2026-08-23T10:00:00+05:30",
        }
        return Evidence(
            evidence_id=_make_id(),
            case_id=case_id,
            category=EvidenceCategory.DELIVERY,
            status=EvidenceStatus.AVAILABLE,
            source_system="carrier_api",
            source_record_id=tracking_id or "MC-TRACK-003",
            event_time=datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc),
            event_timezone="Asia/Kolkata",
            event_time_utc=datetime(2026, 8, 23, 4, 30, tzinfo=timezone.utc),
            timezone_confident=True,
            observed_at=_utc_now(),
            content={
                "status": "returned_to_sender",
                "return_reason": "customer_refused",
                "returned_at": "2026-08-23T10:00:00+05:30",
                "proof_type": "scan",
            },
            summary="Carrier reports package returned to sender (customer refused)",
            relevance="high",
            reliability="high",
            raw_source=payload,
            raw_source_hash=_hash_payload(payload),
        )

    def _ambiguous_delivery(self, case_id: str, tracking_id: str) -> Evidence:
        """Carrier has ambiguous data — status unclear."""
        payload = {
            "carrier": "MockCarrier",
            "tracking_id": tracking_id or "MC-TRACK-004",
            "status": "exception",
            "exception_reason": "address_incomplete",
        }
        return Evidence(
            evidence_id=_make_id(),
            case_id=case_id,
            category=EvidenceCategory.DELIVERY,
            status=EvidenceStatus.UNVERIFIED,
            source_system="carrier_api",
            source_record_id=tracking_id or "MC-TRACK-004",
            observed_at=_utc_now(),
            content={
                "status": "exception",
                "exception_reason": "address_incomplete",
                "proof_type": "none",
            },
            summary="Carrier reports delivery exception (address incomplete)",
            relevance="high",
            reliability="low",
            raw_source=payload,
            raw_source_hash=_hash_payload(payload),
        )

    @staticmethod
    def _parse_case_number(case_id: str) -> int | None:
        """Extract numeric part from CASE-XXXXX format."""
        try:
            return int(case_id.split("-")[1])
        except (IndexError, ValueError):
            return None
