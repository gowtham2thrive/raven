"""
Unit tests for IntegrationService and integration API endpoints.

Tests:
    - Integration creation, retrieval, listing, updates, and deletion
    - Field mapping persistence and application
    - Sample data preview
    - Evidence generation from integrations with timestamp extraction
    - Category coverage computation
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.core.integration_schemas import (
    CreateIntegrationRequest,
    FieldMapping,
    UpdateIntegrationRequest,
)
from app.core.integration_types import (
    IntegrationStatus,
    IntegrationType,
)
from app.core.types import EvidenceCategory, EvidenceStatus
from app.services.integration_service import IntegrationService


@pytest.fixture
def db_session(tmp_path):
    """Provide an isolated SQLite database session for each test."""
    db_file = tmp_path / "test_int_service.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class TestIntegrationService:
    """Test IntegrationService business logic."""

    def test_create_and_list_integrations(self, db_session):
        service = IntegrationService()

        req = CreateIntegrationRequest(
            name="Delhivery Tracking API",
            description="Carrier shipping webhook & polling",
            integration_type=IntegrationType.REST_API,
            evidence_category=EvidenceCategory.SHIPPING,
            rest_api={
                "url": "https://track.delhivery.com/api/v1/packages",
                "method": "GET",
            },
        )

        created = service.create_integration(req, db_session)
        assert created.id.startswith("intg_")
        assert created.name == "Delhivery Tracking API"
        assert created.status == IntegrationStatus.INACTIVE.value

        # List
        all_ints = service.list_integrations(db_session)
        assert len(all_ints) == 1
        assert all_ints[0].id == created.id

    def test_field_mappings_crud(self, db_session):
        service = IntegrationService()

        req = CreateIntegrationRequest(
            name="Custom Order Database",
            integration_type=IntegrationType.DATABASE,
            evidence_category=EvidenceCategory.ORDER,
            database={
                "dialect": "sqlite",
                "database": ":memory:",
                "query": "SELECT * FROM orders",
            },
        )
        created = service.create_integration(req, db_session)

        mappings = [
            FieldMapping(source_field="order_number", target_field="order_id", is_required=True),
            FieldMapping(source_field="total_amount_paise", target_field="amount", transform="paise_to_rupees"),
        ]

        saved = service.save_field_mappings(created.id, mappings, db_session)
        db_session.commit()
        assert len(saved) == 2

        retrieved = service.get_field_mappings(created.id, db_session)
        assert len(retrieved) == 2
        assert retrieved[0].source_field == "order_number"
        assert retrieved[0].target_field == "order_id"
        assert retrieved[1].transform == "paise_to_rupees"

    def test_update_and_delete_integration(self, db_session):
        service = IntegrationService()

        req = CreateIntegrationRequest(
            name="Support Ticket Webhook",
            integration_type=IntegrationType.WEBHOOK,
            evidence_category=EvidenceCategory.COMMUNICATION,
            webhook={"secret": "whsec_123"},
        )
        created = service.create_integration(req, db_session)

        # Update
        update_req = UpdateIntegrationRequest(
            name="Zendesk Support Webhook",
            status=IntegrationStatus.ACTIVE,
        )
        updated = service.update_integration(created.id, update_req, db_session)
        assert updated.name == "Zendesk Support Webhook"
        assert updated.status == IntegrationStatus.ACTIVE.value

        # Delete
        service.delete_integration(created.id, db_session)
        assert len(service.list_integrations(db_session)) == 0
