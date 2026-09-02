"""
Base Adapter — Abstract interface for all integration adapters.

Every adapter (REST, database, file, webhook) implements this
contract. The investigation pipeline interacts only with this
interface — it never knows which specific adapter is behind it.

Each adapter:
- Has one clear purpose (fetch data from a specific source type)
- Validates its own inputs
- Returns source identifiers with every result
- Reports errors honestly — never returns fabricated fallback data
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.integration_schemas import (
    FieldMapping,
    IntegrationTestResult,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  FIELD TRANSFORMS
# ═══════════════════════════════════════════════════════════════

TRANSFORMS: dict[str, Callable] = {}


def register_transform(name: str):
    """Decorator to register a field transform function."""
    def decorator(func):
        TRANSFORMS[name] = func
        return func
    return decorator


@register_transform("to_lowercase")
def _to_lowercase(value: Any) -> Any:
    """Convert string value to lowercase."""
    return str(value).lower() if value is not None else value


@register_transform("to_uppercase")
def _to_uppercase(value: Any) -> Any:
    """Convert string value to uppercase."""
    return str(value).upper() if value is not None else value


@register_transform("strip")
def _strip(value: Any) -> Any:
    """Strip whitespace from string."""
    return str(value).strip() if value is not None else value


@register_transform("parse_date")
def _parse_date(value: Any) -> str | None:
    """Parse various date formats to ISO 8601 string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    value_str = str(value).strip()
    if value_str.endswith("Z"):
        value_str = value_str[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value_str).isoformat()
    except ValueError:
        return value_str


@register_transform("to_int")
def _to_int(value: Any) -> int | None:
    """Convert to integer."""
    if value is None:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


@register_transform("to_float")
def _to_float(value: Any) -> float | None:
    """Convert to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


@register_transform("paise_to_rupees")
def _paise_to_rupees(value: Any) -> float | None:
    """Convert Indian paise to rupees."""
    int_val = _to_int(value)
    return int_val / 100 if int_val is not None else None


@register_transform("boolean")
def _to_boolean(value: Any) -> bool:
    """Convert various truthy/falsy values to boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "1", "y")
    return bool(value)


# ═══════════════════════════════════════════════════════════════
#  BASE ADAPTER
# ═══════════════════════════════════════════════════════════════


class BaseAdapter(ABC):
    """Abstract base class for all integration adapters.

    Subclasses implement the connection and data-fetching logic.
    Field mapping and transform application are handled here.
    """

    @abstractmethod
    def test_connection(self) -> IntegrationTestResult:
        """Verify the source is reachable and return sample data.

        Must return an honest result — never fabricate success.
        """

    @abstractmethod
    def fetch_raw_data(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch raw records from the external source.

        Args:
            params: Source-specific query parameters
                    (e.g., order_id, date range, case_id).

        Returns:
            List of raw dicts exactly as received from the source.
        """

    @abstractmethod
    def get_sample_fields(self) -> list[str]:
        """Discover available field names from the source.

        Used by the UI to populate the field mapping editor.
        """

    def apply_field_mappings(
        self,
        raw_record: dict[str, Any],
        mappings: list[FieldMapping],
    ) -> dict[str, Any]:
        """Translate a raw record using field mappings.

        Extracts source fields (supports dot-notation paths),
        applies transforms, and maps to target field names.

        Returns a dict keyed by target field names.
        """
        result: dict[str, Any] = {}

        for mapping in mappings:
            value = self._extract_field(raw_record, mapping.source_field)

            if value is None and mapping.default_value is not None:
                value = mapping.default_value

            if value is None and mapping.is_required:
                logger.warning(
                    f"Required field '{mapping.source_field}' missing from source record"
                )
                continue

            if value is not None and mapping.transform:
                transform_fn = TRANSFORMS.get(mapping.transform)
                if transform_fn:
                    value = transform_fn(value)
                else:
                    logger.warning(f"Unknown transform '{mapping.transform}', skipping")

            if value is not None:
                result[mapping.target_field] = value

        return result

    def apply_mappings_batch(
        self,
        raw_records: list[dict[str, Any]],
        mappings: list[FieldMapping],
    ) -> list[dict[str, Any]]:
        """Apply field mappings to a batch of raw records."""
        return [
            self.apply_field_mappings(record, mappings)
            for record in raw_records
        ]

    @staticmethod
    def _extract_field(record: dict[str, Any], field_path: str) -> Any:
        """Extract a value from a nested dict using dot-notation path.

        Supports paths like 'shipment.tracking.number' to access
        record['shipment']['tracking']['number'], as well as direct keys with dots.
        """
        if not field_path:
            return None

        # Check direct top-level key first (e.g. CSV or SQL columns named "order.id")
        if isinstance(record, dict) and field_path in record:
            return record[field_path]

        parts = field_path.split(".")
        current = record

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, (list, tuple)) and part.isdigit():
                idx = int(part)
                current = current[idx] if idx < len(current) else None
            else:
                return None

            if current is None:
                return None

        return current

    @staticmethod
    def _timed_test(func) -> IntegrationTestResult:
        """Execute a test function with timing and error handling.

        Utility for subclasses to wrap their test_connection logic.
        """
        start = time.monotonic()
        try:
            result = func()
            result.latency_ms = (time.monotonic() - start) * 1000
            result.tested_at = datetime.now(timezone.utc)
            return result
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return IntegrationTestResult(
                success=False,
                message=f"Connection test failed: {e}",
                errors=[str(e)],
                latency_ms=elapsed,
                tested_at=datetime.now(timezone.utc),
            )
