"""
Database Adapter — Fetch evidence from SQL databases.

Supports PostgreSQL, MySQL, and SQLite via SQLAlchemy.
Uses parameterized query templates for safe, read-only access.

Per AGENTS.md §15: investigation tools are read-only. This adapter
enforces read-only access — no INSERT, UPDATE, DELETE, or DDL.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.connectors.adapter_registry import register_adapter
from app.connectors.base_adapter import BaseAdapter
from app.core.integration_schemas import (
    DatabaseConfig,
    IntegrationTestResult,
)
from app.core.integration_types import (
    IntegrationConnectionError,
    IntegrationError,
    IntegrationType,
)

logger = logging.getLogger(__name__)

MAX_SAMPLE_RECORDS = 5
MAX_QUERY_ROWS = 1000

# Patterns that indicate a mutating query — blocked for safety
MUTATION_PATTERNS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)


@register_adapter(IntegrationType.DATABASE)
class DatabaseAdapter(BaseAdapter):
    """Fetches evidence data from SQL databases.

    Read-only enforcement: rejects any query containing mutation keywords.
    """

    def __init__(self, config: dict[str, Any], integration_id: str = ""):
        self._integration_id = integration_id
        self._config = DatabaseConfig.model_validate(config)
        self._discovered_fields: list[str] = []

    def test_connection(self) -> IntegrationTestResult:
        """Test database connectivity and run the configured query."""
        def _test():
            self._validate_query(self._config.query)
            engine = self._create_engine()

            try:
                from sqlalchemy import text
                with engine.connect() as conn:
                    # Test connectivity
                    conn.execute(text("SELECT 1"))

                    # Run the configured query with a limit
                    if self._config.query.strip():
                        limited_query = self._apply_limit(self._config.query, MAX_SAMPLE_RECORDS)
                        stmt = text(limited_query)
                        try:
                            result = conn.execute(stmt)
                        except Exception:
                            # If named bind parameters are required, provide blank defaults for connectivity test
                            params = {
                                m.group(1): ""
                                for m in re.finditer(r":([a-zA-Z_][a-zA-Z0-9_]*)", limited_query)
                            }
                            result = conn.execute(stmt, params)

                        columns = list(result.keys())
                        rows = [dict(zip(columns, row)) for row in result.fetchall()]

                        # Serialize non-JSON types for safe response
                        for row in rows:
                            for key, value in row.items():
                                if isinstance(value, datetime):
                                    row[key] = value.isoformat()
                                elif isinstance(value, bytes):
                                    row[key] = value.hex()
                                elif hasattr(value, "__str__") and not isinstance(value, (int, float, bool, str, type(None))):
                                    row[key] = str(value)

                        self._discovered_fields = columns

                        return IntegrationTestResult(
                            success=True,
                            message=f"Connected successfully. Query returned {len(rows)} sample row(s).",
                            sample_data=rows[:MAX_SAMPLE_RECORDS],
                            discovered_fields=columns,
                            record_count=len(rows),
                        )
                    else:
                        return IntegrationTestResult(
                            success=True,
                            message="Connected successfully. No query configured yet.",
                            sample_data=[],
                            discovered_fields=[],
                            record_count=0,
                        )
            finally:
                engine.dispose()

        return self._timed_test(_test)

    def fetch_raw_data(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute the configured query and return results."""
        self._validate_query(self._config.query)
        engine = self._create_engine()

        try:
            from sqlalchemy import text
            with engine.connect() as conn:
                limited_query = self._apply_limit(self._config.query, MAX_QUERY_ROWS)
                result = conn.execute(text(limited_query), params or {})
                columns = list(result.keys())
                rows = [dict(zip(columns, row)) for row in result.fetchall()]

                # Convert non-serializable types
                for row in rows:
                    for key, value in row.items():
                        if isinstance(value, datetime):
                            row[key] = value.isoformat()
                        elif isinstance(value, bytes):
                            row[key] = value.hex()
                        elif hasattr(value, "__str__") and not isinstance(value, (int, float, bool, str, type(None))):
                            row[key] = str(value)

                return rows
        finally:
            engine.dispose()

    def get_sample_fields(self) -> list[str]:
        """Return column names from the query result."""
        if self._discovered_fields:
            return self._discovered_fields

        try:
            result = self.test_connection()
            return result.discovered_fields
        except Exception:
            return []

    def _create_engine(self):
        """Create a SQLAlchemy engine from the config."""
        from sqlalchemy import create_engine

        conn_string = self._config.connection_string
        connect_args = {}

        if self._config.dialect.value == "sqlite":
            connect_args["check_same_thread"] = False
            connect_args["timeout"] = 30

        try:
            return create_engine(
                conn_string,
                echo=False,
                connect_args=connect_args,
                pool_pre_ping=True,
            )
        except Exception as e:
            raise IntegrationConnectionError(
                self._integration_id,
                conn_string.split("@")[-1] if "@" in conn_string else conn_string,
                f"Failed to create database connection: {e}",
            ) from e

    def _validate_query(self, query: str) -> None:
        """Reject queries that attempt data mutation.

        Investigation tools are read-only (AGENTS.md §15).
        """
        if not query.strip():
            return

        if MUTATION_PATTERNS.search(query):
            raise IntegrationError(
                self._integration_id,
                f"Query contains mutation keywords. "
                f"Integration database access is read-only. "
                f"Only SELECT queries are permitted.",
            )

    @staticmethod
    def _apply_limit(query: str, limit: int) -> str:
        """Add a LIMIT clause if the query doesn't already have one."""
        query_trimmed = query.strip().rstrip(";")
        if not re.search(r"\bLIMIT\b", query_trimmed, re.IGNORECASE):
            return f"{query_trimmed} LIMIT {limit}"
        return query_trimmed
