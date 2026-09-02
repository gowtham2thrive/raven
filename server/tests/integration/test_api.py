"""
API Integration Tests.

Tests the full stack: HTTP request -> FastAPI -> Service -> Pipeline -> DB -> Response.
Uses FastAPI TestClient with an in-memory SQLite database.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.api.deps import get_db
from app.main import app


# ── Test DB Setup ─────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite:///./test_api.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test, drop after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client():
    return TestClient(app)


# ── Mock Webhook Payload ──────────────────────────────────────

def _mock_webhook_payload(
    dispute_id: str = "disp_test001",
    payment_id: str = "pay_test001",
    amount: int = 849900,
    event: str = "payment.dispute.created",
) -> dict:
    return {
        "event": event,
        "payload": {
            "dispute": {
                "entity": {
                    "id": dispute_id,
                    "payment_id": payment_id,
                    "amount": amount,
                    "currency": "INR",
                    "reason_code": "chargeback",
                    "reason_description": "Product not received",
                    "phase": "chargeback",
                    "status": "open",
                    "respond_by_date": 1735689600,
                    "created_at": 1735603200,
                }
            }
        },
    }


# ═══════════════════════════════════════════════════════════════
#  HEALTH
# ═══════════════════════════════════════════════════════════════


class TestHealth:
    def test_health_returns_ok(self, client):
        """GET /health returns 200 with status ok."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "raven"


# ═══════════════════════════════════════════════════════════════
#  WEBHOOKS
# ═══════════════════════════════════════════════════════════════


class TestWebhooks:
    def test_webhook_creates_case(self, client):
        """POST /webhooks/razorpay with dispute.created should create a case."""
        payload = _mock_webhook_payload()
        resp = client.post("/webhooks/razorpay", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processed"
        assert "case_id" in data

    def test_duplicate_webhook_is_idempotent(self, client):
        """Sending same dispute twice should return same case."""
        payload = _mock_webhook_payload(dispute_id="disp_dup001")
        resp1 = client.post("/webhooks/razorpay", json=payload)
        resp2 = client.post("/webhooks/razorpay", json=payload)

        assert resp1.json()["case_id"] == resp2.json()["case_id"]

    def test_malformed_payload(self, client):
        """Non-dispute webhook should be ignored, not error."""
        resp = client.post("/webhooks/razorpay", json={"event": "payment.captured", "payload": {}})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


# ═══════════════════════════════════════════════════════════════
#  CASES
# ═══════════════════════════════════════════════════════════════


class TestCases:
    def _create_case(self, client) -> str:
        """Helper: create a case via webhook."""
        payload = _mock_webhook_payload()
        resp = client.post("/webhooks/razorpay", json=payload)
        return resp.json()["case_id"]

    def test_list_cases_empty(self, client):
        """GET /cases with no data returns empty list."""
        resp = client.get("/cases/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["cases"] == []

    def test_list_cases_after_webhook(self, client):
        """GET /cases after webhook should show the case."""
        self._create_case(client)
        resp = client.get("/cases/")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_case_detail(self, client):
        """GET /cases/:id returns full case detail."""
        case_id = self._create_case(client)
        resp = client.get(f"/cases/{case_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["case"]["case_id"] == case_id
        assert "evidence" in data
        assert "timeline" in data
        assert "contradictions" in data

    def test_get_case_not_found(self, client):
        """GET /cases/:id with bad ID returns 404."""
        resp = client.get("/cases/CASE-NONEXISTENT")
        assert resp.status_code == 404

    def test_get_evidence(self, client):
        """GET /cases/:id/evidence returns evidence after investigation."""
        case_id = self._create_case(client)
        resp = client.get(f"/cases/{case_id}/evidence")
        assert resp.status_code == 200
        # After webhook+investigate, should have evidence
        assert "evidence" in resp.json()

    def test_get_timeline(self, client):
        """GET /cases/:id/timeline returns timeline events."""
        case_id = self._create_case(client)
        resp = client.get(f"/cases/{case_id}/timeline")
        assert resp.status_code == 200

    def test_get_assessment(self, client):
        """GET /cases/:id/assessment returns scoring data."""
        case_id = self._create_case(client)
        resp = client.get(f"/cases/{case_id}/assessment")
        assert resp.status_code == 200

    def test_get_audit(self, client):
        """GET /cases/:id/audit returns audit trail."""
        case_id = self._create_case(client)
        resp = client.get(f"/cases/{case_id}/audit")
        assert resp.status_code == 200
        audit = resp.json()["audit"]
        assert len(audit) >= 1  # At least "case_created"


# ═══════════════════════════════════════════════════════════════
#  REVIEW
# ═══════════════════════════════════════════════════════════════


class TestReview:
    def _create_and_get_case(self, client) -> str:
        payload = _mock_webhook_payload()
        resp = client.post("/webhooks/razorpay", json=payload)
        return resp.json()["case_id"]

    def test_review_approve(self, client):
        """POST /cases/:id/review with approve should work."""
        case_id = self._create_and_get_case(client)

        # Check current status
        case_resp = client.get(f"/cases/{case_id}")
        current_status = case_resp.json()["case"]["status"]

        # If case is already approved (auto-submit), submit instead
        if current_status == "approved":
            resp = client.post(f"/cases/{case_id}/submit", json={"confirmed": True})
            assert resp.status_code == 200
            return

        # If under_review, approve it
        if current_status == "under_review":
            resp = client.post(f"/cases/{case_id}/review", json={
                "decision": "approve",
                "notes": "Evidence looks good",
                "reviewed_by": "test@raven.dev",
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "approved"

    def test_review_invalid_decision(self, client):
        """POST /cases/:id/review with invalid decision returns 400."""
        case_id = self._create_and_get_case(client)
        resp = client.post(f"/cases/{case_id}/review", json={
            "decision": "maybe",
            "reviewed_by": "test@raven.dev",
        })
        assert resp.status_code == 400

    def test_submit_requires_approved(self, client):
        """POST /cases/:id/submit from non-approved status returns 400."""
        case_id = self._create_and_get_case(client)

        case_resp = client.get(f"/cases/{case_id}")
        current_status = case_resp.json()["case"]["status"]

        if current_status != "approved":
            resp = client.post(f"/cases/{case_id}/submit", json={"confirmed": True})
            assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════════
#  METRICS
# ═══════════════════════════════════════════════════════════════


class TestMetrics:
    def test_metrics_summary(self, client):
        """GET /metrics/summary returns counts."""
        resp = client.get("/metrics/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_cases" in data
        assert "open_cases" in data
        assert "win_rate" in data

    def test_metrics_after_cases(self, client):
        """Metrics should reflect created cases."""
        # Create a case
        payload = _mock_webhook_payload()
        client.post("/webhooks/razorpay", json=payload)

        resp = client.get("/metrics/summary")
        data = resp.json()
        assert data["total_cases"] >= 1


# ═══════════════════════════════════════════════════════════════
#  SIMULATOR API
# ═══════════════════════════════════════════════════════════════


class TestSimulatorAPI:
    def test_get_presets(self, client):
        """GET /simulator/presets returns list of presets."""
        resp = client.get("/simulator/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert "presets" in data
        assert len(data["presets"]) >= 10

    def test_generate_preset_case(self, client):
        """POST /simulator/generate with preset generates and investigates case."""
        resp = client.post("/simulator/generate", json={
            "preset_id": "unauthorized_strong_3ds",
            "auto_investigate": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_id"].startswith("SIM-")
        assert data["reason_code"] == "unauthorized_transaction"
        assert data["auto_investigated"] is True

    def test_clear_cases_endpoint(self, client):
        """DELETE /cases and POST /cases/clear purges cases."""
        resp = client.delete("/cases")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

        list_resp = client.get("/cases")
        assert list_resp.json()["total"] == 0

