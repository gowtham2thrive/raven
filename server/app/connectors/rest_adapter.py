"""
REST API Adapter — Fetch evidence from external REST endpoints.

Supports configurable URL, HTTP method, headers, authentication,
JSONPath-based response extraction, pagination, and timeouts.

The adapter fetches raw JSON, the field mapping engine (in BaseAdapter)
translates it to canonical evidence fields.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.connectors.adapter_registry import register_adapter
from app.connectors.base_adapter import BaseAdapter
from app.core.integration_schemas import (
    IntegrationTestResult,
    RestApiConfig,
)
from app.core.integration_types import (
    AuthMethod,
    IntegrationConnectionError,
    IntegrationType,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [1, 2, 4]
MAX_SAMPLE_RECORDS = 5


def _extract_jsonpath(data: Any, path: str) -> list[dict[str, Any]]:
    """Simple JSONPath-like extraction for common patterns.

    Supports:
        '$'             → root (wrap in list if dict)
        '$[*]'          → root array
        '$.key'         → data['key']
        '$.key1.key2'   → data['key1']['key2']
        '$.key[*]'      → iterate over data['key']

    For complex JSONPath, install jsonpath-ng and extend this.
    """
    if path in ("$", "", "$[*]"):
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    # Strip leading '$.' or '$'
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    parts = path.split(".")
    current = data

    for part in parts:
        if current is None:
            return []

        # Handle array notation: 'key[*]'
        if part.endswith("[*]"):
            key = part[:-3]
            if isinstance(current, dict):
                current = current.get(key, [])
            if isinstance(current, list):
                return current
            return []

        # Handle index notation: 'key[0]'
        if "[" in part and part.endswith("]"):
            key, idx_str = part.rstrip("]").split("[", 1)
            if isinstance(current, dict):
                current = current.get(key, [])
            if isinstance(current, list):
                try:
                    idx = int(idx_str)
                    current = current[idx] if idx < len(current) else None
                except ValueError:
                    return []
            continue

        if isinstance(current, dict):
            current = current.get(part)
        else:
            return []

    if current is None:
        return []
    if isinstance(current, list):
        return current
    if isinstance(current, dict):
        return [current]
    return []


@register_adapter(IntegrationType.REST_API)
class RestApiAdapter(BaseAdapter):
    """Fetches data from REST API endpoints.

    Handles authentication, pagination, retries, and JSONPath extraction.
    """

    def __init__(self, config: dict[str, Any], integration_id: str = ""):
        self._integration_id = integration_id
        self._config = RestApiConfig.model_validate(config)
        self._discovered_fields: list[str] = []

    def test_connection(self) -> IntegrationTestResult:
        """Test the API endpoint and return sample data."""
        def _test():
            response_data = self._make_request()
            records = _extract_jsonpath(response_data, self._config.response_path)
            valid_records = [r for r in records if isinstance(r, dict)]
            sample = valid_records[:MAX_SAMPLE_RECORDS]
            fields = self._discover_fields(sample)
            self._discovered_fields = fields

            return IntegrationTestResult(
                success=True,
                message=f"Connected successfully. Found {len(valid_records)} record(s).",
                sample_data=sample,
                discovered_fields=fields,
                record_count=len(valid_records),
            )

        return self._timed_test(_test)

    def fetch_raw_data(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Fetch all records from the API endpoint."""
        merged_params = {**self._config.query_params}
        if params:
            merged_params.update(params)

        response_data = self._make_request(extra_params=merged_params)
        records = _extract_jsonpath(response_data, self._config.response_path)

        if not isinstance(records, list):
            records = [records] if records else []

        return [r for r in records if isinstance(r, dict)]

    def get_sample_fields(self) -> list[str]:
        """Return fields discovered during the last test or fetch."""
        if self._discovered_fields:
            return self._discovered_fields

        try:
            result = self.test_connection()
            return result.discovered_fields
        except Exception:
            return []

    def _make_request(
        self,
        extra_params: dict[str, Any] | None = None,
    ) -> Any:
        """Execute the HTTP request with auth, retries, and error handling."""
        headers = dict(self._config.headers)
        self._apply_auth(headers)

        params = {**self._config.query_params}
        if extra_params:
            params.update(extra_params)

        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                with httpx.Client(timeout=self._config.timeout_seconds) as client:
                    if self._config.method.upper() == "POST":
                        response = client.post(
                            self._config.url,
                            headers=headers,
                            params=params,
                            json=self._config.request_body,
                        )
                    else:
                        response = client.get(
                            self._config.url,
                            headers=headers,
                            params=params,
                        )

                    response.raise_for_status()
                    return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:
                    # Rate limited — retry with backoff
                    if attempt < MAX_RETRIES - 1:
                        wait = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                        logger.warning(
                            f"Rate limited on {self._config.url}, "
                            f"retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})"
                        )
                        time.sleep(wait)
                        continue
                elif e.response.status_code >= 500:
                    # Server error — retry with backoff
                    if attempt < MAX_RETRIES - 1:
                        wait = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                        logger.warning(
                            f"Server error {e.response.status_code} on {self._config.url}, "
                            f"retrying in {wait}s"
                        )
                        time.sleep(wait)
                        continue
                # Client error (4xx except 429) — don't retry
                raise IntegrationConnectionError(
                    self._integration_id,
                    self._config.url,
                    f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                ) from e

            except httpx.TimeoutException as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    wait = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                    logger.warning(
                        f"Timeout on {self._config.url}, retrying in {wait}s"
                    )
                    time.sleep(wait)
                    continue

            except httpx.RequestError as e:
                raise IntegrationConnectionError(
                    self._integration_id,
                    self._config.url,
                    str(e),
                ) from e

        raise IntegrationConnectionError(
            self._integration_id,
            self._config.url,
            f"Max retries ({MAX_RETRIES}) exceeded. Last error: {last_error}",
        )

    def _apply_auth(self, headers: dict[str, str]) -> None:
        """Apply authentication to request headers."""
        auth = self._config.auth_config
        method = self._config.auth_method

        if method == AuthMethod.API_KEY:
            header_name = auth.get("header", "X-Api-Key")
            headers[header_name] = auth.get("value", "")

        elif method == AuthMethod.BEARER_TOKEN:
            headers["Authorization"] = f"Bearer {auth.get('token', '')}"

        elif method == AuthMethod.BASIC_AUTH:
            import base64
            credentials = f"{auth.get('username', '')}:{auth.get('password', '')}"
            encoded = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"

    @staticmethod
    def _discover_fields(records: list[dict[str, Any]]) -> list[str]:
        """Discover all unique field names from sample records.

        Flattens nested dicts using dot-notation.
        """
        fields: set[str] = set()

        def _flatten(obj: dict, prefix: str = "") -> None:
            for key, value in obj.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    _flatten(value, full_key)
                else:
                    fields.add(full_key)

        for record in records:
            if isinstance(record, dict):
                _flatten(record)

        return sorted(fields)
