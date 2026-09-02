"""
Integration Service — Business logic for managing integrations.

Orchestrates the full integration lifecycle:
    create → configure → test → map fields → activate → fetch evidence

This service is the single entry point for all integration operations.
It coordinates between the database, adapter registry, and the
evidence normalization pipeline.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.connectors.adapter_registry import get_adapter
from app.connectors.base_adapter import BaseAdapter
from app.core.integration_schemas import (
    CreateIntegrationRequest,
    FieldMapping,
    IntegrationConfig,
    IntegrationSummary,
    IntegrationTestResult,
    UpdateIntegrationRequest,
)
from app.core.integration_types import (
    IntegrationError,
    IntegrationNotFoundError,
    IntegrationStatus,
    IntegrationType,
)
from app.core.types import EvidenceCategory, EvidenceStatus
from app.core.schemas import Evidence
from app.db.models import IntegrationFieldMappingModel, IntegrationModel
from app.pipeline.ingest import _hash_payload, _make_id, _utc_now

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


class IntegrationService:
    """Manages the full lifecycle of data source integrations."""

    def __init__(self, upload_dir: Path | None = None):
        self._upload_dir = upload_dir or UPLOAD_DIR

    # ── Create ────────────────────────────────────────────────

    def create_integration(
        self,
        request: CreateIntegrationRequest,
        db: Session,
    ) -> IntegrationModel:
        """Create a new integration configuration.

        Validates the config matches the integration type and
        persists to the database in INACTIVE status.
        """
        config_dict = self._extract_type_config(request)

        integration = IntegrationModel(
            name=request.name,
            description=request.description,
            integration_type=request.integration_type.value,
            evidence_category=request.evidence_category.value,
            status=IntegrationStatus.INACTIVE.value,
            config=config_dict,
        )

        db.add(integration)
        db.flush()

        # Save field mappings if provided
        if request.field_mappings:
            self._save_field_mappings(db, integration.id, request.field_mappings)

        db.commit()
        db.refresh(integration)

        logger.info(
            f"Created integration {integration.id}: "
            f"{integration.name} ({integration.integration_type})"
        )
        return integration

    # ── Read ──────────────────────────────────────────────────

    def get_integration(self, integration_id: str, db: Session) -> IntegrationModel:
        """Fetch a single integration by ID."""
        integration = db.query(IntegrationModel).filter_by(id=integration_id).first()
        if not integration:
            raise IntegrationNotFoundError(integration_id)
        return integration

    def list_integrations(
        self,
        db: Session,
        status: IntegrationStatus | None = None,
        evidence_category: str | None = None,
        integration_type: str | None = None,
    ) -> list[IntegrationModel]:
        """List integrations with optional filters."""
        from sqlalchemy.orm import joinedload

        query = db.query(IntegrationModel).options(joinedload(IntegrationModel.field_mappings))

        if status:
            query = query.filter_by(status=status.value)
        if evidence_category:
            query = query.filter_by(evidence_category=evidence_category)
        if integration_type:
            query = query.filter_by(integration_type=integration_type)

        return query.order_by(IntegrationModel.created_at.desc()).all()

    # ── Update ────────────────────────────────────────────────

    def update_integration(
        self,
        integration_id: str,
        request: UpdateIntegrationRequest,
        db: Session,
    ) -> IntegrationModel:
        """Update an existing integration's configuration."""
        integration = self.get_integration(integration_id, db)

        if request.name is not None:
            integration.name = request.name
        if request.description is not None:
            integration.description = request.description
        if request.evidence_category is not None:
            integration.evidence_category = request.evidence_category.value
        if request.status is not None:
            integration.status = request.status.value

        # Update type-specific config
        new_config = self._extract_type_config_from_update(request, integration)
        if new_config:
            integration.config = new_config

        # Update field mappings
        if request.field_mappings is not None:
            self._save_field_mappings(db, integration_id, request.field_mappings)

        integration.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(integration)

        logger.info(f"Updated integration {integration_id}")
        return integration

    # ── Delete ────────────────────────────────────────────────

    def delete_integration(self, integration_id: str, db: Session) -> None:
        """Delete an integration and its field mappings."""
        integration = self.get_integration(integration_id, db)

        # Clean up uploaded files if applicable
        config = integration.config or {}
        stored_path = config.get("stored_path", "")
        if stored_path:
            file_path = Path(stored_path)
            if file_path.exists():
                file_path.unlink(missing_ok=True)
                logger.info(f"Deleted uploaded file: {stored_path}")

        db.delete(integration)
        db.commit()
        logger.info(f"Deleted integration {integration_id}")

    # ── Test ──────────────────────────────────────────────────

    def test_integration(
        self,
        integration_id: str,
        db: Session,
    ) -> IntegrationTestResult:
        """Test an integration's connectivity and return sample data."""
        integration = self.get_integration(integration_id, db)
        adapter = self._get_adapter_for_integration(integration)
        result = adapter.test_connection()

        # Update integration status based on test result
        if result.success:
            if integration.status == IntegrationStatus.ERROR.value:
                integration.status = IntegrationStatus.INACTIVE.value
            integration.last_error = None
        else:
            integration.last_error = result.message

        db.commit()
        return result

    # ── Sample Data ───────────────────────────────────────────

    def get_sample_data(
        self,
        integration_id: str,
        db: Session,
    ) -> IntegrationSampleDataResponse:
        """Fetch sample data with current field mappings applied."""
        integration = self.get_integration(integration_id, db)
        adapter = self._get_adapter_for_integration(integration)
        mappings = self.get_field_mappings(integration_id, db)

        test_result = adapter.test_connection()
        if not test_result.success:
            return IntegrationSampleDataResponse(
                integration_id=integration_id,
                raw_samples=test_result.sample_data,
                mapped_samples=[],
                fields_discovered=test_result.discovered_fields,
            )

        raw_samples = test_result.sample_data
        mapped_samples = (
            adapter.apply_mappings_batch(raw_samples, mappings)
            if mappings
            else raw_samples
        )

        return IntegrationSampleDataResponse(
            integration_id=integration_id,
            raw_samples=raw_samples,
            mapped_samples=mapped_samples,
            fields_discovered=test_result.discovered_fields,
        )

    # ── Field Mappings ────────────────────────────────────────

    def save_field_mappings(
        self,
        integration_id: str,
        mappings: list[FieldMapping],
        db: Session,
    ) -> list[IntegrationFieldMappingModel]:
        """Replace all field mappings for an integration."""
        self.get_integration(integration_id, db)  # Verify exists
        return self._save_field_mappings(db, integration_id, mappings)

    def get_field_mappings(
        self,
        integration_id: str,
        db: Session,
    ) -> list[FieldMapping]:
        """Load field mappings for an integration."""
        return self._load_field_mappings(db, integration_id)

    # ── Fetch Evidence (Pipeline Integration) ─────────────────

    def fetch_evidence_from_integration(
        self,
        integration_id: str,
        case_id: str,
        params: dict[str, Any] | None,
        db: Session,
    ) -> list[Evidence]:
        """Fetch data from an integration and convert to Evidence objects.

        This is the bridge between the integration hub and the
        investigation pipeline.
        """
        integration = self.get_integration(integration_id, db)
        adapter = self._get_adapter_for_integration(integration)
        mappings = self.get_field_mappings(integration_id, db)

        try:
            raw_records = adapter.fetch_raw_data(params)
        except Exception as e:
            logger.error(f"Integration {integration_id} fetch failed: {e}")
            integration.last_error = str(e)
            integration.status = IntegrationStatus.ERROR.value
            db.commit()
            return []

        if not raw_records:
            return []

        # Apply field mappings and create Evidence objects
        evidence_list: list[Evidence] = []
        evidence_category = EvidenceCategory(integration.evidence_category)

        for raw_record in raw_records:
            if mappings:
                mapped = adapter.apply_field_mappings(raw_record, mappings)
            else:
                mapped = raw_record

            # Extract event time if present in mapped or raw record
            ts_raw = (
                mapped.get("event_time")
                or mapped.get("timestamp")
                or mapped.get("delivered_at")
                or mapped.get("shipped_at")
                or mapped.get("created_at")
                or mapped.get("date")
                or raw_record.get("event_time")
                or raw_record.get("timestamp")
                or raw_record.get("created_at")
            )
            ev_time: datetime | None = None
            ev_time_utc: datetime | None = None
            if ts_raw is not None:
                if isinstance(ts_raw, datetime):
                    ev_time = ts_raw
                elif isinstance(ts_raw, (int, float)):
                    ev_time = datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                elif isinstance(ts_raw, str) and ts_raw.strip():
                    try:
                        s = ts_raw.strip()
                        if s.endswith("Z"):
                            s = s[:-1] + "+00:00"
                        ev_time = datetime.fromisoformat(s)
                    except Exception:
                        pass
                if ev_time is not None:
                    ev_time_utc = ev_time if ev_time.tzinfo else ev_time.replace(tzinfo=timezone.utc)
                    ev_time_utc = ev_time_utc.astimezone(timezone.utc)

            evidence = Evidence(
                evidence_id=_make_id(),
                case_id=case_id,
                category=evidence_category,
                status=EvidenceStatus.AVAILABLE,
                source_system=f"integration:{integration.name}",
                source_record_id=str(mapped.get("id", mapped.get("record_id", ""))),
                event_time=ev_time,
                event_time_utc=ev_time_utc,
                timezone_confident=True,
                observed_at=_utc_now(),
                content=mapped,
                summary=self._generate_summary(mapped, evidence_category),
                relevance="medium",
                reliability="medium",
                raw_source=raw_record,
                raw_source_hash=_hash_payload(raw_record),
            )
            evidence_list.append(evidence)

        # Update sync state
        integration.last_sync_at = datetime.now(timezone.utc)
        integration.last_error = None
        integration.sync_count = (integration.sync_count or 0) + 1
        db.commit()

        logger.info(
            f"Integration {integration_id} produced {len(evidence_list)} "
            f"evidence item(s) for case {case_id}"
        )
        return evidence_list

    def fetch_all_active_evidence(
        self,
        case_id: str,
        db: Session,
        params: dict[str, Any] | None = None,
    ) -> list[Evidence]:
        """Fetch evidence from ALL active integrations.

        Used by the pipeline runner to augment synthetic/direct evidence.
        """
        active_integrations = self.list_integrations(
            db, status=IntegrationStatus.ACTIVE,
        )

        all_evidence: list[Evidence] = []
        for integration in active_integrations:
            try:
                evidence = self.fetch_evidence_from_integration(
                    integration.id, case_id, params, db,
                )
                all_evidence.extend(evidence)
            except Exception as e:
                logger.error(
                    f"Failed to fetch from integration {integration.id}: {e}"
                )

        return all_evidence

    # ── File Upload ───────────────────────────────────────────

    def handle_file_upload(
        self,
        file_content: bytes,
        filename: str,
        integration_type: IntegrationType,
    ) -> dict[str, Any]:
        """Save an uploaded file and return storage metadata.

        Files are stored in the uploads directory with a unique name
        to prevent collisions.
        """
        self._upload_dir.mkdir(parents=True, exist_ok=True)

        # Validate file extension
        allowed_extensions = self._get_allowed_extensions(integration_type)
        ext = Path(filename).suffix.lower()
        if ext not in allowed_extensions:
            raise IntegrationError(
                "",
                f"File type '{ext}' not allowed. Expected: {allowed_extensions}",
            )

        # Generate unique filename
        unique_name = f"{uuid.uuid4().hex[:12]}_{filename}"
        stored_path = self._upload_dir / unique_name

        stored_path.write_bytes(file_content)
        logger.info(f"Uploaded file: {filename} → {stored_path}")

        return {
            "filename": filename,
            "stored_path": str(stored_path),
            "file_size_bytes": len(file_content),
        }

    # ── Serialization ─────────────────────────────────────────

    def to_summary(self, integration: IntegrationModel) -> dict[str, Any]:
        """Convert an IntegrationModel to an API response dict."""
        return {
            "id": integration.id,
            "name": integration.name,
            "description": integration.description or "",
            "integration_type": integration.integration_type,
            "evidence_category": integration.evidence_category,
            "status": integration.status,
            "last_sync_at": integration.last_sync_at.isoformat() if integration.last_sync_at else None,
            "last_error": integration.last_error,
            "field_mapping_count": len(integration.field_mappings) if integration.field_mappings else 0,
            "sync_count": integration.sync_count or 0,
            "created_at": integration.created_at.isoformat() if integration.created_at else None,
            "updated_at": integration.updated_at.isoformat() if integration.updated_at else None,
            "config": integration.config or {},
        }

    def to_detail(self, integration: IntegrationModel, db: Session) -> dict[str, Any]:
        """Convert to a full detail dict including field mappings."""
        summary = self.to_summary(integration)
        summary["field_mappings"] = [
            {
                "id": m.id,
                "source_field": m.source_field,
                "target_field": m.target_field,
                "transform": m.transform,
                "is_required": m.is_required,
                "default_value": m.default_value,
            }
            for m in (integration.field_mappings or [])
        ]
        return summary

    # ── Private Helpers ───────────────────────────────────────

    def _get_adapter_for_integration(self, integration: IntegrationModel) -> BaseAdapter:
        """Resolve the adapter for an integration model."""
        integration_type = IntegrationType(integration.integration_type)
        config = integration.config or {}
        return get_adapter(integration_type, config, integration.id)

    def _save_field_mappings(
        self,
        db: Session,
        integration_id: str,
        mappings: list[FieldMapping],
    ) -> list[IntegrationFieldMappingModel]:
        """Replace all field mappings for an integration (delete + insert)."""
        db.query(IntegrationFieldMappingModel).filter_by(
            integration_id=integration_id,
        ).delete()

        models = []
        for mapping in mappings:
            model = IntegrationFieldMappingModel(
                integration_id=integration_id,
                source_field=mapping.source_field,
                target_field=mapping.target_field,
                transform=mapping.transform,
                is_required=mapping.is_required,
                default_value=mapping.default_value,
            )
            db.add(model)
            models.append(model)

        db.flush()
        return models

    def _load_field_mappings(
        self,
        db: Session,
        integration_id: str,
    ) -> list[FieldMapping]:
        """Load field mappings from the database."""
        rows = db.query(IntegrationFieldMappingModel).filter_by(
            integration_id=integration_id,
        ).all()

        return [
            FieldMapping(
                source_field=row.source_field,
                target_field=row.target_field,
                transform=row.transform,
                is_required=row.is_required,
                default_value=row.default_value,
            )
            for row in rows
        ]

    @staticmethod
    def _extract_type_config(request: CreateIntegrationRequest) -> dict[str, Any]:
        """Extract the type-specific config dict from a create request."""
        if request.rest_api:
            return request.rest_api.model_dump()
        if request.database:
            return request.database.model_dump()
        if request.file_upload:
            return request.file_upload.model_dump()
        if request.webhook:
            return request.webhook.model_dump()
        return {}

    @staticmethod
    def _extract_type_config_from_update(
        request: UpdateIntegrationRequest,
        integration: IntegrationModel,
    ) -> dict[str, Any] | None:
        """Extract type-specific config from an update request."""
        if request.rest_api:
            return request.rest_api.model_dump()
        if request.database:
            return request.database.model_dump()
        if request.file_upload:
            return request.file_upload.model_dump()
        if request.webhook:
            return request.webhook.model_dump()
        return None

    @staticmethod
    def _generate_summary(mapped: dict[str, Any], category: EvidenceCategory) -> str:
        """Generate a human-readable summary from mapped evidence data."""
        parts = []

        if category == EvidenceCategory.SHIPPING:
            carrier = mapped.get("carrier", "")
            tracking = mapped.get("tracking_id", "")
            status = mapped.get("status", "")
            if carrier:
                parts.append(f"Shipped via {carrier}")
            if tracking:
                parts.append(f"tracking: {tracking}")
            if status:
                parts.append(f"status: {status}")

        elif category == EvidenceCategory.DELIVERY:
            delivered_at = mapped.get("delivered_at", "")
            signed_by = mapped.get("signed_by", "")
            if delivered_at:
                parts.append(f"Delivered at {delivered_at}")
            if signed_by:
                parts.append(f"signed by {signed_by}")

        elif category == EvidenceCategory.PAYMENT:
            amount = mapped.get("amount", "")
            method = mapped.get("method", "")
            if amount:
                parts.append(f"Payment of {amount}")
            if method:
                parts.append(f"via {method}")

        elif category == EvidenceCategory.ORDER:
            order_id = mapped.get("order_id", mapped.get("id", ""))
            if order_id:
                parts.append(f"Order {order_id}")

        elif category == EvidenceCategory.COMMUNICATION:
            msg_type = mapped.get("type", "")
            channel = mapped.get("channel", "")
            if msg_type:
                parts.append(msg_type)
            if channel:
                parts.append(f"via {channel}")

        if parts:
            return f"[Integration] {', '.join(parts)}"
        return f"[Integration] {category.value} evidence from external source"

    @staticmethod
    def _get_allowed_extensions(integration_type: IntegrationType) -> set[str]:
        """Return allowed file extensions for a given integration type."""
        extension_map = {
            IntegrationType.CSV_FILE: {".csv", ".tsv", ".txt"},
            IntegrationType.EXCEL_FILE: {".xlsx", ".xls"},
            IntegrationType.PDF_FILE: {".pdf"},
        }
        return extension_map.get(integration_type, set())
