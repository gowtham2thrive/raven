"""
RAVEN Integration Schemas — Pydantic models for integration configuration.

Contains:
- IntegrationConfig: Base configuration for any integration
- RestApiConfig: REST API connection settings
- DatabaseConfig: Database connection settings
- FileUploadConfig: CSV/Excel/PDF file settings
- WebhookConfig: Inbound webhook settings
- FieldMapping: Source field → canonical evidence field mapping
- IntegrationTestResult: Connectivity test output
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .integration_types import (
    AuthMethod,
    DatabaseDialect,
    IntegrationStatus,
    IntegrationType,
)
from .types import EvidenceCategory


# ═══════════════════════════════════════════════════════════════
#  FIELD MAPPING
# ═══════════════════════════════════════════════════════════════


class FieldMapping(BaseModel):
    """Maps a source field to a RAVEN canonical evidence field.

    Source fields are discovered from sample data. Target fields
    are the known fields within a canonical evidence content dict
    (e.g., 'carrier', 'tracking_id', 'delivered_at').
    """

    source_field: str
    """Field name or path in the source data (e.g., 'shipment.tracking_number')."""

    target_field: str
    """Canonical evidence content field (e.g., 'tracking_id')."""

    transform: str | None = None
    """Optional transform function name (e.g., 'parse_date', 'to_lowercase', 'paise_to_rupees')."""

    is_required: bool = False
    """Whether this mapping is required for valid evidence."""

    default_value: str | None = None
    """Fallback value if source field is absent."""


# ═══════════════════════════════════════════════════════════════
#  TYPE-SPECIFIC CONFIGS
# ═══════════════════════════════════════════════════════════════


class RestApiConfig(BaseModel):
    """Configuration for a REST API integration."""

    model_config = ConfigDict(extra="forbid")

    url: str
    """Full URL endpoint (e.g., 'https://api.merchant.com/v1/orders')."""

    method: str = "GET"
    """HTTP method (GET, POST)."""

    headers: dict[str, str] = Field(default_factory=dict)
    """Additional request headers."""

    auth_method: AuthMethod = AuthMethod.NONE
    """Authentication mechanism."""

    auth_config: dict[str, str] = Field(default_factory=dict)
    """Auth-specific config. For API_KEY: {'header': 'X-Api-Key', 'value': '...'}
    For BEARER_TOKEN: {'token': '...'}. For BASIC_AUTH: {'username': '...', 'password': '...'}."""

    response_path: str = "$"
    """JSONPath to extract records from the response (e.g., '$.data.orders[*]')."""

    query_params: dict[str, str] = Field(default_factory=dict)
    """Default query parameters."""

    request_body: dict[str, Any] | None = None
    """Request body for POST methods."""

    timeout_seconds: int = 30
    """Request timeout."""

    pagination: dict[str, Any] | None = None
    """Pagination config: {'type': 'offset'|'cursor'|'page', 'param': '...', 'limit': 50}."""


class DatabaseConfig(BaseModel):
    """Configuration for a database integration."""

    model_config = ConfigDict(extra="forbid")

    dialect: DatabaseDialect
    """Database type (postgresql, mysql, sqlite)."""

    host: str = "localhost"
    """Database host."""

    port: int | None = None
    """Database port (default per dialect if None)."""

    database: str = ""
    """Database name or file path for SQLite."""

    username: str = ""
    """Database username."""

    password: str = ""
    """Database password (stored encrypted in production)."""

    query: str = ""
    """SQL query template. Use :param_name for parameters.
    Example: 'SELECT * FROM orders WHERE order_id = :order_id'"""

    connection_params: dict[str, str] = Field(default_factory=dict)
    """Additional connection parameters (e.g., SSL settings)."""

    @property
    def connection_string(self) -> str:
        """Build SQLAlchemy connection string from components."""
        if self.dialect == DatabaseDialect.SQLITE:
            return f"sqlite:///{self.database}"
        port_str = f":{self.port}" if self.port else ""
        creds = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.dialect.value}://{creds}{self.host}{port_str}/{self.database}"


class FileUploadConfig(BaseModel):
    """Configuration for a CSV/Excel/PDF file integration."""

    model_config = ConfigDict(extra="forbid")

    filename: str = ""
    """Original uploaded filename."""

    stored_path: str = ""
    """Server-side storage path."""

    file_size_bytes: int = 0
    """File size for validation."""

    # CSV-specific
    delimiter: str = ","
    """CSV delimiter character."""

    encoding: str = "utf-8"
    """File encoding."""

    has_header: bool = True
    """Whether the first row is a header."""

    # Excel-specific
    sheet_name: str | None = None
    """Excel sheet to read (default: first sheet)."""

    header_row: int = 0
    """Zero-indexed row number for headers."""

    # PDF-specific
    extract_tables: bool = True
    """Attempt to extract tabular data from PDFs."""


class WebhookConfig(BaseModel):
    """Configuration for an inbound webhook integration."""

    model_config = ConfigDict(extra="forbid")

    endpoint_path: str = ""
    """Generated webhook path (e.g., '/webhooks/integrations/abc123')."""

    secret: str = ""
    """HMAC secret for signature verification."""

    signature_header: str = "X-Webhook-Signature"
    """Header name containing the signature."""

    expected_fields: list[str] = Field(default_factory=list)
    """Fields expected in the webhook payload (for documentation/validation)."""


# ═══════════════════════════════════════════════════════════════
#  INTEGRATION CONFIG (UNIFIED)
# ═══════════════════════════════════════════════════════════════


class IntegrationConfig(BaseModel):
    """Unified integration configuration.

    The type-specific config lives in the corresponding field
    (rest_api, database, file_upload, webhook). Only one should
    be set, matching the integration_type.
    """

    name: str
    """Human-readable integration name (e.g., 'Shopify Orders API')."""

    description: str = ""
    """Brief description of what this integration provides."""

    integration_type: IntegrationType
    """Which adapter to use."""

    evidence_category: EvidenceCategory
    """Which evidence category this integration feeds."""

    status: IntegrationStatus = IntegrationStatus.INACTIVE
    """Current lifecycle status."""

    # Type-specific configs — only one should be populated
    rest_api: RestApiConfig | None = None
    database: DatabaseConfig | None = None
    file_upload: FileUploadConfig | None = None
    webhook: WebhookConfig | None = None

    # Field mappings
    field_mappings: list[FieldMapping] = Field(default_factory=list)
    """Source field → canonical evidence field mappings."""


# ═══════════════════════════════════════════════════════════════
#  TEST RESULT
# ═══════════════════════════════════════════════════════════════


class IntegrationTestResult(BaseModel):
    """Result of testing an integration's connectivity and data fetch."""

    success: bool
    """Whether the connection and data fetch succeeded."""

    message: str = ""
    """Human-readable result message."""

    sample_data: list[dict[str, Any]] = Field(default_factory=list)
    """Up to 5 sample records from the source."""

    discovered_fields: list[str] = Field(default_factory=list)
    """Field names discovered in the sample data."""

    record_count: int = 0
    """Number of records available (or in sample)."""

    latency_ms: float = 0.0
    """Time taken for the test request."""

    errors: list[str] = Field(default_factory=list)
    """Any errors encountered during testing."""

    tested_at: datetime | None = None
    """When the test was executed."""


# ═══════════════════════════════════════════════════════════════
#  API REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════


class CreateIntegrationRequest(BaseModel):
    """API request body for creating a new integration."""

    name: str
    description: str = ""
    integration_type: IntegrationType
    evidence_category: EvidenceCategory

    rest_api: RestApiConfig | None = None
    database: DatabaseConfig | None = None
    file_upload: FileUploadConfig | None = None
    webhook: WebhookConfig | None = None

    field_mappings: list[FieldMapping] = Field(default_factory=list)


class UpdateIntegrationRequest(BaseModel):
    """API request body for updating an integration."""

    name: str | None = None
    description: str | None = None
    evidence_category: EvidenceCategory | None = None
    status: IntegrationStatus | None = None

    rest_api: RestApiConfig | None = None
    database: DatabaseConfig | None = None
    file_upload: FileUploadConfig | None = None
    webhook: WebhookConfig | None = None

    field_mappings: list[FieldMapping] | None = None


class IntegrationSummary(BaseModel):
    """API response model for integration list items."""

    id: str
    name: str
    description: str
    integration_type: IntegrationType
    evidence_category: EvidenceCategory
    status: IntegrationStatus
    last_sync_at: datetime | None = None
    last_error: str | None = None
    field_mapping_count: int = 0
    created_at: datetime
    updated_at: datetime
