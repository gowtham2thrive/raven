"""
Integration API Routes — CRUD, test, sync, upload, and field mapping.

Endpoints:
    GET    /integrations                    — List all integrations
    POST   /integrations                    — Create a new integration
    POST   /integrations/upload             — File upload (CSV, Excel, PDF)
    GET    /integrations/types/available     — List integration types
    GET    /integrations/categories/available — List evidence categories
    GET    /integrations/:id                — Get integration detail
    PUT    /integrations/:id                — Update integration config
    DELETE /integrations/:id                — Remove integration
    POST   /integrations/:id/test           — Test connectivity + sample
    GET    /integrations/:id/sample         — Preview with field mappings
    PUT    /integrations/:id/mappings       — Save field mappings
    GET    /integrations/:id/mappings       — Get field mappings
    POST   /integrations/:id/sync           — Manually trigger data fetch
    POST   /integrations/:id/activate       — Activate integration
    POST   /integrations/:id/deactivate     — Deactivate integration

IMPORTANT: Static routes (/upload, /types/available, /categories/available)
must be defined BEFORE parameterized routes (/{integration_id}) to avoid
FastAPI matching "upload" or "types" as an integration_id.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.integration_schemas import (
    CreateIntegrationRequest,
    FieldMapping,
    UpdateIntegrationRequest,
)
from app.core.integration_types import (
    IntegrationError,
    IntegrationNotFoundError,
    IntegrationStatus,
    IntegrationType,
)
from app.core.types import EvidenceCategory
from app.services.integration_service import IntegrationService

logger = logging.getLogger(__name__)

integrations_router = APIRouter()

_service = IntegrationService()


# ═══════════════════════════════════════════════════════════════
#  LIST / CREATE (no path parameters — safe first)
# ═══════════════════════════════════════════════════════════════


@integrations_router.get("")
def list_integrations(
    status: str | None = Query(None, description="Filter by status"),
    evidence_category: str | None = Query(None, description="Filter by evidence category"),
    integration_type: str | None = Query(None, description="Filter by type"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List all integrations with optional filters."""
    status_enum = None
    if status:
        try:
            status_enum = IntegrationStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: '{status}'. Expected one of: {[s.value for s in IntegrationStatus]}",
            )

    integrations = _service.list_integrations(
        db,
        status=status_enum,
        evidence_category=evidence_category,
        integration_type=integration_type,
    )
    return {
        "integrations": [_service.to_summary(i) for i in integrations],
        "total": len(integrations),
    }


@integrations_router.post("", status_code=201)
def create_integration(
    request: CreateIntegrationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a new integration."""
    try:
        integration = _service.create_integration(request, db)
        return _service.to_detail(integration, db)
    except IntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ═══════════════════════════════════════════════════════════════
#  STATIC ROUTES — must come BEFORE /{integration_id}
# ═══════════════════════════════════════════════════════════════


@integrations_router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    integration_type: str = Query(..., description="csv_file, excel_file, or pdf_file"),
) -> dict[str, Any]:
    """Upload a CSV, Excel, or PDF file for integration.

    Returns file metadata to include in the CreateIntegrationRequest.
    """
    try:
        itype = IntegrationType(integration_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid integration type: {integration_type}. "
            f"Expected one of: csv_file, excel_file, pdf_file",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        metadata = _service.handle_file_upload(content, file.filename or "upload", itype)
        return {
            "status": "uploaded",
            **metadata,
        }
    except IntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


EVIDENCE_CATEGORIES = [
    {"id": cat.value, "name": cat.value.replace("_", " ").title()}
    for cat in EvidenceCategory
]


@integrations_router.get("/types/available")
def list_integration_types() -> dict[str, Any]:
    """List available integration types with descriptions."""
    from app.connectors.adapter_registry import list_registered_adapters

    types = [
        {
            "id": IntegrationType.REST_API.value,
            "name": "REST API",
            "description": "Connect to any REST API endpoint to fetch evidence data.",
            "icon": "api",
            "config_fields": ["url", "method", "headers", "auth", "response_path"],
        },
        {
            "id": IntegrationType.DATABASE.value,
            "name": "Database",
            "description": "Query PostgreSQL, MySQL, or SQLite databases for evidence.",
            "icon": "database",
            "config_fields": ["dialect", "host", "port", "database", "query"],
        },
        {
            "id": IntegrationType.CSV_FILE.value,
            "name": "CSV File",
            "description": "Upload CSV or TSV files containing evidence data.",
            "icon": "file_csv",
            "config_fields": ["delimiter", "encoding", "has_header"],
        },
        {
            "id": IntegrationType.EXCEL_FILE.value,
            "name": "Excel File",
            "description": "Upload Excel spreadsheets (.xlsx) with evidence data.",
            "icon": "file_excel",
            "config_fields": ["sheet_name", "header_row"],
        },
        {
            "id": IntegrationType.PDF_FILE.value,
            "name": "PDF Document",
            "description": "Upload PDFs to extract text and tabular evidence.",
            "icon": "file_pdf",
            "config_fields": ["extract_tables"],
        },
        {
            "id": IntegrationType.WEBHOOK.value,
            "name": "Webhook",
            "description": "Receive evidence data via inbound webhooks from external systems.",
            "icon": "webhook",
            "config_fields": ["secret", "signature_header"],
        },
    ]

    registered = list_registered_adapters()

    return {
        "types": types,
        "registered_adapters": registered,
    }


@integrations_router.get("/categories/available")
def list_evidence_categories() -> dict[str, Any]:
    """List evidence categories that integrations can feed into."""
    return {"categories": EVIDENCE_CATEGORIES}


# ═══════════════════════════════════════════════════════════════
#  PARAMETERIZED ROUTES — /{integration_id} and sub-paths
# ═══════════════════════════════════════════════════════════════


@integrations_router.get("/{integration_id}")
def get_integration(
    integration_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get full integration detail including field mappings."""
    try:
        integration = _service.get_integration(integration_id, db)
        return _service.to_detail(integration, db)
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@integrations_router.put("/{integration_id}")
def update_integration(
    integration_id: str,
    request: UpdateIntegrationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update an integration's configuration."""
    try:
        integration = _service.update_integration(integration_id, request, db)
        return _service.to_detail(integration, db)
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except IntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@integrations_router.delete("/{integration_id}")
def delete_integration(
    integration_id: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Delete an integration."""
    try:
        _service.delete_integration(integration_id, db)
        return {"status": "deleted", "id": integration_id}
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ── Test / Sample / Sync ─────────────────────────────────────


@integrations_router.post("/{integration_id}/test")
def test_integration(
    integration_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Test integration connectivity and return sample data."""
    try:
        result = _service.test_integration(integration_id, db)
        return result.model_dump()
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@integrations_router.get("/{integration_id}/sample")
def get_sample_data(
    integration_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Preview sample data with current field mappings applied."""
    try:
        result = _service.get_sample_data(integration_id, db)
        return result.model_dump()
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@integrations_router.post("/{integration_id}/sync")
def sync_integration(
    integration_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Manually trigger a data fetch from the integration.

    Does not create Evidence — just validates data can be fetched.
    """
    try:
        integration = _service.get_integration(integration_id, db)
        adapter = _service._get_adapter_for_integration(integration)
        raw_data = adapter.fetch_raw_data()
        return {
            "status": "ok",
            "records_fetched": len(raw_data),
            "integration_id": integration_id,
        }
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except IntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ── Field Mappings ────────────────────────────────────────────


@integrations_router.put("/{integration_id}/mappings")
def save_field_mappings(
    integration_id: str,
    mappings: list[FieldMapping],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Save or replace field mappings for an integration."""
    try:
        saved = _service.save_field_mappings(integration_id, mappings, db)
        db.commit()
        return {
            "status": "ok",
            "mappings_saved": len(saved),
            "integration_id": integration_id,
        }
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@integrations_router.get("/{integration_id}/mappings")
def get_field_mappings(
    integration_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get current field mappings for an integration."""
    try:
        mappings = _service.get_field_mappings(integration_id, db)
        return {
            "integration_id": integration_id,
            "mappings": [m.model_dump() for m in mappings],
        }
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


# ── Activate / Deactivate ────────────────────────────────────


@integrations_router.post("/{integration_id}/activate")
def activate_integration(
    integration_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Activate an integration so it feeds evidence into investigations."""
    try:
        request = UpdateIntegrationRequest(status=IntegrationStatus.ACTIVE)
        _service.update_integration(integration_id, request, db)
        return {"status": "activated", "id": integration_id}
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@integrations_router.post("/{integration_id}/deactivate")
def deactivate_integration(
    integration_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Deactivate an integration — stops feeding evidence."""
    try:
        request = UpdateIntegrationRequest(status=IntegrationStatus.INACTIVE)
        _service.update_integration(integration_id, request, db)
        return {"status": "deactivated", "id": integration_id}
    except IntegrationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
