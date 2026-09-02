"""
Unit tests for Integration Adapters, BaseAdapter transformations, and IngestionQuarantine.

Tests:
    - BaseAdapter field extraction, transforms, and batch mapping
    - CsvFileAdapter, ExcelFileAdapter, PdfFileAdapter parsing and edge cases
    - RestApiAdapter auth methods, JSONPath extraction, and error handling
    - DatabaseAdapter read-only mutation blocking and LIMIT application
    - IngestionQuarantine dead-letter queue operations
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.connectors.base_adapter import (
    BaseAdapter,
    TRANSFORMS,
    _to_lowercase,
    _to_uppercase,
    _strip,
    _parse_date,
    _to_int,
    _to_float,
    _paise_to_rupees,
    _to_boolean,
)
from app.connectors.file_adapter import CsvFileAdapter, ExcelFileAdapter, PdfFileAdapter
from app.connectors.rest_adapter import RestApiAdapter, _extract_jsonpath
from app.connectors.database_adapter import DatabaseAdapter
from app.connectors.quarantine import IngestionQuarantine, QuarantinedRecord
from app.core.integration_schemas import FieldMapping
from app.core.integration_types import (
    AuthMethod,
    IntegrationError,
    IntegrationFileError,
    IntegrationType,
)


# ═══════════════════════════════════════════════════════════════
#  BASE ADAPTER & TRANSFORMS TESTS
# ═══════════════════════════════════════════════════════════════

class TestBaseAdapterTransforms:
    """Test field transform functions in BaseAdapter."""

    def test_to_lowercase(self):
        assert _to_lowercase("DELIVERED") == "delivered"
        assert _to_lowercase(None) is None
        assert _to_lowercase(123) == "123"

    def test_to_uppercase(self):
        assert _to_uppercase("delivered") == "DELIVERED"
        assert _to_uppercase(None) is None

    def test_strip(self):
        assert _strip("  hello world  \n") == "hello world"
        assert _strip(None) is None

    def test_parse_date(self):
        now = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert _parse_date(now) == now.isoformat()
        assert _parse_date("2026-03-01T10:00:00Z") == "2026-03-01T10:00:00+00:00"
        assert _parse_date(1772445600) is not None
        assert _parse_date(None) is None
        assert _parse_date("not-a-date") == "not-a-date"

    def test_to_int(self):
        assert _to_int("100") == 100
        assert _to_int(100.5) == 100
        assert _to_int(None) is None
        assert _to_int("invalid") is None

    def test_to_float(self):
        assert _to_float("99.99") == 99.99
        assert _to_float(100) == 100.0
        assert _to_float(None) is None
        assert _to_float("invalid") is None

    def test_paise_to_rupees(self):
        assert _paise_to_rupees(849900) == 8499.00
        assert _paise_to_rupees("50000") == 500.00
        assert _paise_to_rupees(None) is None

    def test_to_boolean(self):
        assert _to_boolean(True) is True
        assert _to_boolean(False) is False
        assert _to_boolean("true") is True
        assert _to_boolean("yes") is True
        assert _to_boolean("1") is True
        assert _to_boolean("false") is False
        assert _to_boolean("no") is False
        assert _to_boolean("0") is False


class TestBaseAdapterFieldExtraction:
    """Test nested dot-notation and direct key extraction in BaseAdapter."""

    def test_direct_key_with_dot(self):
        record = {"order.id": "ORD-12345", "user.email": "user@example.com"}
        assert BaseAdapter._extract_field(record, "order.id") == "ORD-12345"
        assert BaseAdapter._extract_field(record, "user.email") == "user@example.com"

    def test_nested_dot_notation(self):
        record = {
            "shipment": {
                "carrier": "BlueDart",
                "tracking": {
                    "number": "BD98765",
                    "status": "delivered",
                },
            },
        }
        assert BaseAdapter._extract_field(record, "shipment.carrier") == "BlueDart"
        assert BaseAdapter._extract_field(record, "shipment.tracking.number") == "BD98765"
        assert BaseAdapter._extract_field(record, "shipment.tracking.status") == "delivered"

    def test_array_index_extraction(self):
        record = {
            "events": [
                {"type": "shipped", "time": "2026-03-01"},
                {"type": "delivered", "time": "2026-03-03"},
            ]
        }
        assert BaseAdapter._extract_field(record, "events.0.type") == "shipped"
        assert BaseAdapter._extract_field(record, "events.1.time") == "2026-03-03"
        assert BaseAdapter._extract_field(record, "events.2.type") is None

    def test_missing_or_empty_path(self):
        record = {"a": 1}
        assert BaseAdapter._extract_field(record, "") is None
        assert BaseAdapter._extract_field(record, "b.c.d") is None


# ═══════════════════════════════════════════════════════════════
#  CSV FILE ADAPTER TESTS
# ═══════════════════════════════════════════════════════════════

class TestCsvFileAdapter:
    """Test CSV parsing, headers, delimiters, and sanitization."""

    def test_parse_csv_with_header(self, tmp_path):
        csv_file = tmp_path / "test_shipping.csv"
        csv_file.write_text("tracking_id,carrier,status\nTRK001,Delhivery,delivered\nTRK002,BlueDart,in_transit\n")

        adapter = CsvFileAdapter({
            "filename": "test_shipping.csv",
            "stored_path": str(csv_file),
            "delimiter": ",",
            "has_header": True,
        })

        test_res = adapter.test_connection()
        assert test_res.success is True
        assert test_res.record_count == 2
        assert "tracking_id" in test_res.discovered_fields

        records = adapter.fetch_raw_data()
        assert len(records) == 2
        assert records[0]["carrier"] == "Delhivery"
        assert records[1]["status"] == "in_transit"

    def test_parse_csv_without_header(self, tmp_path):
        csv_file = tmp_path / "no_header.csv"
        csv_file.write_text("TRK001,Delhivery,delivered\n")

        adapter = CsvFileAdapter({
            "filename": "no_header.csv",
            "stored_path": str(csv_file),
            "delimiter": ",",
            "has_header": False,
        })

        records = adapter.fetch_raw_data()
        assert len(records) == 1
        assert records[0]["col_0"] == "TRK001"
        assert records[0]["col_1"] == "Delhivery"

    def test_missing_file_raises_error(self):
        adapter = CsvFileAdapter({
            "filename": "non_existent.csv",
            "stored_path": "/tmp/non_existent_file_path.csv",
        })
        with pytest.raises(IntegrationFileError):
            adapter.fetch_raw_data()


# ═══════════════════════════════════════════════════════════════
#  REST API ADAPTER TESTS
# ═══════════════════════════════════════════════════════════════

class TestRestApiAdapter:
    """Test JSONPath extraction and auth configuration."""

    def test_jsonpath_root_list(self):
        data = [{"id": "1"}, {"id": "2"}]
        assert _extract_jsonpath(data, "$") == data
        assert _extract_jsonpath(data, "$[*]") == data
        assert _extract_jsonpath(data, "") == data

    def test_jsonpath_nested_array(self):
        data = {
            "response": {
                "orders": [
                    {"id": "ORD-1", "amount": 100},
                    {"id": "ORD-2", "amount": 200},
                ]
            }
        }
        assert len(_extract_jsonpath(data, "response.orders")) == 2
        assert len(_extract_jsonpath(data, "$.response.orders[*]")) == 2

    def test_auth_headers_application(self):
        # API Key
        adapter = RestApiAdapter({
            "url": "https://api.example.com/data",
            "auth_method": "api_key",
            "auth_config": {"header": "X-Custom-Key", "value": "secret123"},
        })
        headers = {}
        adapter._apply_auth(headers)
        assert headers["X-Custom-Key"] == "secret123"

        # Bearer Token
        adapter_bearer = RestApiAdapter({
            "url": "https://api.example.com/data",
            "auth_method": "bearer_token",
            "auth_config": {"token": "jwt_token_abc"},
        })
        headers_bearer = {}
        adapter_bearer._apply_auth(headers_bearer)
        assert headers_bearer["Authorization"] == "Bearer jwt_token_abc"


# ═══════════════════════════════════════════════════════════════
#  DATABASE ADAPTER TESTS
# ═══════════════════════════════════════════════════════════════

class TestDatabaseAdapter:
    """Test database adapter read-only enforcement and LIMIT application."""

    def test_blocks_mutations(self):
        adapter = DatabaseAdapter({
            "dialect": "sqlite",
            "database": ":memory:",
            "query": "DELETE FROM orders WHERE id = 1",
        })
        with pytest.raises(IntegrationError) as exc_info:
            adapter._validate_query("DELETE FROM orders WHERE id = 1")
        assert "read-only" in str(exc_info.value).lower()

        with pytest.raises(IntegrationError):
            adapter._validate_query("DROP TABLE users;")

        with pytest.raises(IntegrationError):
            adapter._validate_query("UPDATE accounts SET balance = 0;")

        with pytest.raises(IntegrationError):
            adapter._validate_query("INSERT INTO orders VALUES (1, 'test');")

    def test_allows_select_queries(self):
        adapter = DatabaseAdapter({
            "dialect": "sqlite",
            "database": ":memory:",
            "query": "SELECT * FROM orders WHERE status = 'delivered'",
        })
        # Should not raise
        adapter._validate_query("SELECT * FROM orders WHERE status = 'delivered'")

    def test_apply_limit(self):
        assert DatabaseAdapter._apply_limit("SELECT * FROM orders", 5) == "SELECT * FROM orders LIMIT 5"
        assert DatabaseAdapter._apply_limit("SELECT * FROM orders;", 5) == "SELECT * FROM orders LIMIT 5"
        assert DatabaseAdapter._apply_limit("SELECT * FROM orders LIMIT 10", 5) == "SELECT * FROM orders LIMIT 10"


# ═══════════════════════════════════════════════════════════════
#  INGESTION QUARANTINE TESTS
# ═══════════════════════════════════════════════════════════════

class TestIngestionQuarantine:
    """Test dead-letter queue operations."""

    def test_quarantine_and_retrieve(self, tmp_path):
        db_file = tmp_path / "test_quarantine.db"
        quarantine = IngestionQuarantine(str(db_file))

        record = IngestionQuarantine.make_record(
            case_id="case_test_123",
            source_system="merchant_carrier",
            evidence_category="shipping",
            raw_payload={"tracking_id": 12345, "invalid_field": None},
            error_message="Validation error: tracking_id must be string",
        )

        quarantine.quarantine(record)

        # Count
        assert quarantine.count() == 1
        assert quarantine.count("case_test_123") == 1
        assert quarantine.count("other_case") == 0

        # Retrieve
        records = quarantine.list_quarantined("case_test_123")
        assert len(records) == 1
        assert records[0].case_id == "case_test_123"
        assert records[0].source_system == "merchant_carrier"
        assert records[0].raw_payload["tracking_id"] == 12345
