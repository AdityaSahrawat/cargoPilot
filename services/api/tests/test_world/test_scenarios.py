import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from main import app
from app.db.database import Base, get_test_db, get_db
from app.db import models, enums, schemas
from app.optimization.input_builder import OptimizationInputBuilder
from tests.test_world.validator import WorldValidator


@pytest.fixture(scope="function")
def api_client():
    """Test client using an isolated in-memory SQLite database for full REST API tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_test_db] = override_get_db
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    db_session = TestingSessionLocal()
    yield client, db_session

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_baseline_scenario_api_flow(api_client):
    """Test 1: Full REST API workflow for Baseline Scenario."""
    client, db = api_client

    # 1. Reset Scenario via HTTP API
    reset_res = client.post("/api/v1/scenarios/baseline/reset")
    assert reset_res.status_code == 200, reset_res.text
    assert reset_res.json()["status"] == "success"

    # 2. Query Reference Entities via HTTP APIs
    loc_res = client.get("/api/v1/locations")
    assert loc_res.status_code == 200
    locations = loc_res.json()
    assert len(locations) >= 5

    ves_res = client.get("/api/v1/vessels")
    assert ves_res.status_code == 200
    vessels = ves_res.json()
    assert len(vessels) >= 2

    cnt_res = client.get("/api/v1/containers")
    assert cnt_res.status_code == 200
    containers = cnt_res.json()
    assert containers["total"] == 25

    # 3. Trigger Optimization Run via HTTP API
    opt_res = client.post("/api/v1/scenarios/baseline/run")
    assert opt_res.status_code == 200
    opt_data = opt_res.json()
    assert "runId" in opt_data

    # 4. Validate Optimization Plan
    plan_dict = opt_data["plan"]
    plan_obj = schemas.OptimizationPlanResponse(**plan_dict)
    validator = WorldValidator(db)
    validator.validate_plan_capacity(plan_obj)
    validator.validate_non_negative_quantities(plan_obj)


def test_container_usability_filtering(api_client):
    """Test 4: Verify usability filtering logic excludes non-controlled, committed, in-transit, repair, customs hold, emergency reserve, & ON_HOLD containers."""
    client, db = api_client
    client.post("/api/v1/scenarios/baseline/reset")

    builder = OptimizationInputBuilder(db)

    # Get Chennai location
    chennai = db.query(models.Location).filter(models.Location.unlocode == "INMAA").first()
    assert chennai is not None

    # Get usable 40FT_DRY containers at Chennai
    usable_40gp = builder.get_usable_containers(
        location_id=chennai.id,
        container_type=enums.ContainerType.DRY_40FT,
    )
    usable_numbers = [c.container_number for c in usable_40gp]

    # CONT_001 and CONT_002 must be usable
    assert "MSCU9900001" in usable_numbers
    assert "MSCU9900002" in usable_numbers

    # CONT_003 (controlled_by_carrier=False), CONT_004 (committed COM_001), CONT_005 (IN_TRANSIT), CONT_006 (UNDER_REPAIR), CONT_011 (is_emergency_reserve=True) must NOT be usable
    assert "MSCU9900003" not in usable_numbers
    assert "MSCU9900004" not in usable_numbers
    assert "MSCU9900005" not in usable_numbers
    assert "MSCU9900006" not in usable_numbers
    assert "MSCU9900011" not in usable_numbers

    # Check Dubai location & ON_HOLD container CONT_015
    dubai = db.query(models.Location).filter(models.Location.unlocode == "AEDXB").first()
    assert dubai is not None
    usable_dubai_40gp = builder.get_usable_containers(
        location_id=dubai.id,
        container_type=enums.ContainerType.DRY_40FT,
    )
    usable_dubai_numbers = [c.container_number for c in usable_dubai_40gp]
    assert "MSCU9900015" not in usable_dubai_numbers  # CONT_015 ON_HOLD excluded!

    # Check 20FT_DRY at Chennai
    usable_20gp = builder.get_usable_containers(
        location_id=chennai.id,
        container_type=enums.ContainerType.DRY_20FT,
    )
    usable_20gp_numbers = [c.container_number for c in usable_20gp]

    # CONT_007 is usable, CONT_008 (customs_hold=True) is NOT usable
    assert "MSCU9900007" in usable_20gp_numbers
    assert "MSCU9900008" not in usable_20gp_numbers


def test_capacity_shortage_scenario_api_flow(api_client):
    """Test 2: Full REST API workflow for Capacity Shortage Scenario."""
    client, db = api_client

    # Reset Scenario via HTTP API
    reset_res = client.post("/api/v1/scenarios/capacity_shortage/reset")
    assert reset_res.status_code == 200

    # Run Optimization via HTTP API
    opt_res = client.post("/api/v1/scenarios/capacity_shortage/run")
    assert opt_res.status_code == 200
    opt_data = opt_res.json()

    # Validate Plan
    plan_obj = schemas.OptimizationPlanResponse(**opt_data["plan"])
    validator = WorldValidator(db)
    validator.validate_plan_capacity(plan_obj)
    validator.validate_non_negative_quantities(plan_obj)


def test_container_event_lifecycle_api_flow(api_client):
    """Test 3: Full REST API workflow for Container Events & State Reconstruction."""
    client, db = api_client

    # Reset baseline
    client.post("/api/v1/scenarios/baseline/reset")

    # Get a container ID
    cnt_list = client.get("/api/v1/containers").json()["data"]
    container_id = cnt_list[0]["id"]
    location_id = cnt_list[0]["currentLocationId"]

    # Submit GATE_IN Container Event via HTTP API
    event_payload = {
        "containerId": container_id,
        "eventType": "GATE_IN",
        "timestamp": "2026-08-19T20:00:00Z",
        "locationId": location_id,
        "metadata": {"terminal": "T1"},
    }
    evt_res = client.post("/api/v1/container-events", json=event_payload)
    assert evt_res.status_code == 201, evt_res.text
    evt_data = evt_res.json()
    assert evt_data["eventType"] == "GATE_IN"

    # Query event history via HTTP API
    history_res = client.get(f"/api/v1/containers/{container_id}/events")
    assert history_res.status_code == 200
    events = history_res.json()
    assert len(events) >= 1
