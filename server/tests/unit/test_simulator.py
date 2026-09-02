"""
Unit tests for Dispute Simulator Service and API endpoints.
"""

import pytest
from app.db.database import Base, SessionLocal, engine
from app.services.case_service import CaseService
from app.services.simulator_service import (
    CustomCaseConfig,
    SimulateCaseRequest,
    SimulatorService,
    SIMULATION_PRESETS,
)


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def simulator():
    return SimulatorService()


@pytest.fixture
def case_service():
    return CaseService()


def test_presets_catalog(simulator):
    """Presets catalog contains at least 10 valid dispute archetypes."""
    presets = simulator.get_presets()
    assert len(presets) >= 10
    preset_ids = {p["id"] for p in presets}
    assert "physical_strong_delivery" in preset_ids
    assert "unauthorized_strong_3ds" in preset_ids
    assert "digital_service_active" in preset_ids
    assert "contradictory_carrier_rts" in preset_ids


def test_simulate_strong_preset(db, simulator, case_service):
    """Simulating strong delivery preset creates and investigates case."""
    req = SimulateCaseRequest(preset_id="physical_strong_delivery", auto_investigate=True)
    res = simulator.generate_case(req, db, case_service)

    assert res["case_id"].startswith("SIM-")
    assert res["reason_code"] == "product_not_received"
    assert res["auto_investigated"] is True
    assert res["assessment"] is not None
    assert res["recommendation"] == "contest"


def test_simulate_contradiction_preset(db, simulator, case_service):
    """Simulating contradictory carrier preset flags contradiction and needs review."""
    req = SimulateCaseRequest(preset_id="contradictory_carrier_rts", auto_investigate=True)
    res = simulator.generate_case(req, db, case_service)

    assert res["case_id"].startswith("SIM-")
    assert res["recommendation"] == "human_review"
    assert res["assessment"] is not None
    assert res["assessment"].contradiction_count >= 1


def test_simulate_custom_case(db, simulator, case_service):
    """Custom configuration generates bespoke dispute case."""
    custom = CustomCaseConfig(
        customer_name="Pooja Sharma",
        product_name="Custom Software Subscription",
        amount_inr=15000.0,
        reason_code="unauthorized_transaction",
        evidence_profile="strong",
        auth_verified=True,
        delivery_status="none",
    )
    req = SimulateCaseRequest(custom_config=custom, auto_investigate=True)
    res = simulator.generate_case(req, db, case_service)

    assert res["case_id"].startswith("SIM-")
    assert res["amount"] == 1500000
    assert res["reason_code"] == "unauthorized_transaction"


def test_clear_all_cases_purges_db_and_simulation_files(db, simulator):
    """Clearing all cases purges everything from database and deletes ONLY SIM-*.json files."""
    # Generate a couple of simulation cases first
    req = SimulateCaseRequest(preset_id="physical_strong_delivery", auto_investigate=False)
    simulator.generate_case(req, db, None)
    req2 = SimulateCaseRequest(preset_id="digital_service_active", auto_investigate=False)
    simulator.generate_case(req2, db, None)

    sim_files_before = list(simulator.cases_dir.glob("SIM-*.json"))
    golden_files_before = list(simulator.cases_dir.glob("CASE-*.json"))
    assert len(sim_files_before) >= 2

    # Clear all cases
    deleted_count = simulator.clear_all_cases(db)
    from app.db.models import CaseModel
    assert db.query(CaseModel).count() == 0

    # Verify SIM-*.json files are deleted
    sim_files_after = list(simulator.cases_dir.glob("SIM-*.json"))
    assert len(sim_files_after) == 0

    # Verify CASE-*.json golden benchmark files remain completely intact
    golden_files_after = list(simulator.cases_dir.glob("CASE-*.json"))
    assert len(golden_files_after) == len(golden_files_before)


@pytest.mark.parametrize("preset", SIMULATION_PRESETS)
def test_all_simulation_presets_accuracy(db, simulator, case_service, preset):
    """Verify that every preset archetype produces its expected recommendation."""
    req = SimulateCaseRequest(preset_id=preset["id"], auto_investigate=True)
    res = simulator.generate_case(req, db, case_service)

    assert res["case_id"].startswith("SIM-")
    assert res["recommendation"] == preset["expected_recommendation"]
    assert res["assessment"] is not None
    assert 0.0 <= res["assessment"].score <= 1.0
