"""
RAVEN Integration Types — Enums and Exceptions.

Classification values and error hierarchy for the
pluggable integration system. Each integration connects
a merchant's external data source to the investigation pipeline.
"""

from __future__ import annotations

from enum import Enum

from .types import RavenError


# ═══════════════════════════════════════════════════════════════
#  ENUMS
# ═══════════════════════════════════════════════════════════════


class IntegrationType(str, Enum):
    """Supported integration source types."""

    REST_API = "rest_api"
    DATABASE = "database"
    CSV_FILE = "csv_file"
    EXCEL_FILE = "excel_file"
    PDF_FILE = "pdf_file"
    WEBHOOK = "webhook"


class IntegrationStatus(str, Enum):
    """Lifecycle status of an integration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    TESTING = "testing"


class AuthMethod(str, Enum):
    """Authentication methods for external data sources."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    OAUTH2 = "oauth2"


class DatabaseDialect(str, Enum):
    """Supported database dialects for the database adapter."""

    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"


class SyncDirection(str, Enum):
    """Data flow direction for an integration."""

    INBOUND = "inbound"     # External source → RAVEN evidence
    OUTBOUND = "outbound"   # RAVEN → external system (future)


# ═══════════════════════════════════════════════════════════════
#  EXCEPTIONS
# ═══════════════════════════════════════════════════════════════


class IntegrationError(RavenError):
    """Base exception for integration failures."""

    def __init__(self, integration_id: str, message: str):
        self.integration_id = integration_id
        super().__init__(f"Integration {integration_id}: {message}")


class IntegrationConnectionError(IntegrationError):
    """Failed to connect to the external data source."""

    def __init__(self, integration_id: str, source: str, details: str):
        self.source = source
        self.details = details
        super().__init__(
            integration_id,
            f"Connection to {source} failed: {details}",
        )


class IntegrationAuthError(IntegrationError):
    """Authentication with the external source failed."""

    def __init__(self, integration_id: str, auth_method: str):
        self.auth_method = auth_method
        super().__init__(
            integration_id,
            f"Authentication failed (method: {auth_method})",
        )


class IntegrationSchemaError(IntegrationError):
    """Data from the external source doesn't match the expected schema."""

    def __init__(self, integration_id: str, field: str, details: str):
        self.field = field
        self.details = details
        super().__init__(
            integration_id,
            f"Schema mismatch on field '{field}': {details}",
        )


class IntegrationNotFoundError(IntegrationError):
    """Integration does not exist."""

    def __init__(self, integration_id: str):
        super().__init__(integration_id, "not found")


class IntegrationFileError(IntegrationError):
    """File processing failed (parse, size, format)."""

    def __init__(self, integration_id: str, filename: str, details: str):
        self.filename = filename
        self.details = details
        super().__init__(
            integration_id,
            f"File '{filename}' error: {details}",
        )
