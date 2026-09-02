"""
Webhook Adapter — Receive evidence via inbound webhooks.

Generates a unique endpoint for each integration. External systems
POST data to this endpoint, which is validated via HMAC signature
and stored for field mapping.

Unlike other adapters that pull data, this adapter receives pushes.
The stored payloads are then available via fetch_raw_data().
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.connectors.adapter_registry import register_adapter
from app.connectors.base_adapter import BaseAdapter
from app.core.integration_schemas import (
    IntegrationTestResult,
    WebhookConfig,
)
from app.core.integration_types import (
    IntegrationError,
    IntegrationType,
)

logger = logging.getLogger(__name__)

MAX_SAMPLE_RECORDS = 5

# In-memory buffer for received webhook payloads
# In production, this would be backed by a database or queue
_webhook_buffers: dict[str, list[dict[str, Any]]] = {}


def get_webhook_buffer(integration_id: str) -> list[dict[str, Any]]:
    """Get the payload buffer for a webhook integration."""
    return _webhook_buffers.get(integration_id, [])


def append_webhook_payload(integration_id: str, payload: dict[str, Any]) -> None:
    """Store a received webhook payload in the buffer."""
    if integration_id not in _webhook_buffers:
        _webhook_buffers[integration_id] = []
    _webhook_buffers[integration_id].append({
        **payload,
        "_received_at": datetime.now(timezone.utc).isoformat(),
    })
    # Keep buffer bounded
    MAX_BUFFER_SIZE = 1000
    if len(_webhook_buffers[integration_id]) > MAX_BUFFER_SIZE:
        _webhook_buffers[integration_id] = _webhook_buffers[integration_id][-MAX_BUFFER_SIZE:]


def clear_webhook_buffer(integration_id: str) -> None:
    """Clear the payload buffer for a webhook integration."""
    _webhook_buffers.pop(integration_id, None)


def verify_webhook_signature(
    body: bytes,
    signature: str,
    secret: str,
) -> bool:
    """Verify HMAC-SHA256 webhook signature."""
    if not secret:
        return True  # No secret configured = skip verification

    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


@register_adapter(IntegrationType.WEBHOOK)
class WebhookAdapter(BaseAdapter):
    """Handles inbound webhook data for evidence ingestion.

    This adapter doesn't actively fetch data — it reads from
    a buffer of received webhook payloads.
    """

    def __init__(self, config: dict[str, Any], integration_id: str = ""):
        self._integration_id = integration_id
        self._config = WebhookConfig.model_validate(config)
        self._discovered_fields: list[str] = []

    def test_connection(self) -> IntegrationTestResult:
        """Check the webhook buffer for received payloads."""
        def _test():
            buffer = get_webhook_buffer(self._integration_id)

            if not buffer:
                return IntegrationTestResult(
                    success=True,
                    message=(
                        "Webhook endpoint ready. No payloads received yet. "
                        f"POST data to: /webhooks/integrations/{self._integration_id}"
                    ),
                    sample_data=[],
                    discovered_fields=self._config.expected_fields,
                    record_count=0,
                )

            sample = buffer[-MAX_SAMPLE_RECORDS:]
            fields = self._discover_fields_from_records(sample)
            self._discovered_fields = fields

            return IntegrationTestResult(
                success=True,
                message=f"Webhook active. {len(buffer)} payload(s) in buffer.",
                sample_data=sample,
                discovered_fields=fields,
                record_count=len(buffer),
            )

        return self._timed_test(_test)

    def fetch_raw_data(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Return all buffered webhook payloads."""
        return get_webhook_buffer(self._integration_id)

    def get_sample_fields(self) -> list[str]:
        """Return fields from received payloads or expected fields."""
        if self._discovered_fields:
            return self._discovered_fields

        if self._config.expected_fields:
            return self._config.expected_fields

        buffer = get_webhook_buffer(self._integration_id)
        if buffer:
            return self._discover_fields_from_records(buffer[:MAX_SAMPLE_RECORDS])

        return []

    @staticmethod
    def generate_endpoint_path() -> str:
        """Generate a unique webhook endpoint path."""
        return f"/webhooks/integrations/{uuid.uuid4().hex[:12]}"

    @staticmethod
    def generate_secret() -> str:
        """Generate a random HMAC secret for webhook verification."""
        return uuid.uuid4().hex

    @staticmethod
    def _discover_fields_from_records(records: list[dict]) -> list[str]:
        """Collect all unique field names across records."""
        fields: set[str] = set()
        for record in records:
            fields.update(k for k in record.keys() if not k.startswith("_"))
        return sorted(fields)
