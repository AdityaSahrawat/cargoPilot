from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_test_db, Base, test_engine
from app.db import models, enums, schemas
from app.optimization.service import OptimizationService
from tests.test_world.scenario_builder import ScenarioBuilder

router = APIRouter()


class ScenarioInfo(BaseModel):
    id: str
    name: str
    description: str


AVAILABLE_SCENARIOS = [
    ScenarioInfo(
        id="baseline",
        name="Baseline — Normal Operations",
        description="Standard balanced fleet operations across Asia-ME trade route.",
    ),
    ScenarioInfo(
        id="capacity_shortage",
        name="Vessel Capacity Shortage",
        description="Export surge out of Shanghai consumes 96% of commercial vessel capacity.",
    ),
    ScenarioInfo(
        id="demand_spike",
        name="Demand Surge in Dubai",
        description="Sudden 80 TEU demand surge in Dubai evaluating local lease vs repositioning.",
    ),
]


@router.get("/scenarios", response_model=List[ScenarioInfo])
def get_scenarios():
    """GET /api/v1/scenarios - List available scenario definitions."""
    return AVAILABLE_SCENARIOS


@router.post("/scenarios/{scenario_id}/reset")
def reset_test_scenario(scenario_id: str, db: Session = Depends(get_test_db)):
    """POST /api/v1/scenarios/:id/reset - Reset and seed the ISOLATED TEST DATABASE."""
    # Wipe and recreate only the TEST database tables
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    builder = ScenarioBuilder(db)

    if scenario_id == "baseline":
        builder.setup_base_world()
    elif scenario_id == "capacity_shortage":
        builder.build_scenario_capacity_shortage()
    elif scenario_id == "demand_spike":
        builder.build_scenario_demand_spike()
    else:
        builder.setup_base_world()

    return {
        "status": "success",
        "scenarioId": scenario_id,
        "environment": "ISOLATED_TEST_DATABASE",
        "message": f"Test database (cargo_pilot_test.db) reset and seeded with scenario '{scenario_id}'",
    }


@router.post("/scenarios/{scenario_id}/run")
def run_test_scenario_optimization(scenario_id: str, db: Session = Depends(get_test_db)):
    """POST /api/v1/scenarios/:id/run - Run optimization on the ISOLATED TEST DATABASE."""
    c = db.query(models.Company).filter(models.Company.is_self == True).first()
    if not c:
        c = db.query(models.Company).first()
    if not c:
        raise HTTPException(status_code=404, detail="Test world company not initialized")

    opt_service = OptimizationService(db)
    opt_run = opt_service.run_optimization(
        company_id=c.id,
        start_week="2026-W36",
        horizon_weeks=8,
    )

    plan = opt_service.get_plan(opt_run.id)
    return {
        "runId": opt_run.id,
        "status": opt_run.status,
        "plan": plan,
    }


@router.get("/scenarios/test-world/overview")
def get_test_world_overview(db: Session = Depends(get_test_db)):
    """GET /api/v1/scenarios/test-world/overview - Overview metrics from ISOLATED TEST DATABASE."""
    locations = db.query(models.Location).all()
    vessels = db.query(models.Vessel).all()
    containers_count = db.query(models.Container).count()
    bookings_count = db.query(models.Booking).count()
    voyages_count = db.query(models.Voyage).count()

    loc_list = [
        {
            "id": str(loc.id),
            "name": loc.name,
            "unlocode": loc.unlocode,
            "locationType": loc.location_type.value if hasattr(loc.location_type, "value") else str(loc.location_type),
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "operationalStatus": loc.operational_status.value if hasattr(loc.operational_status, "value") else str(loc.operational_status),
        }
        for loc in locations
    ]

    ves_list = [
        {
            "id": str(v.id),
            "name": v.name,
            "containerCapacity": v.container_capacity,
            "status": v.status.value if hasattr(v.status, "value") else str(v.status),
        }
        for v in vessels
    ]

    return {
        "environment": "ISOLATED_TEST_DATABASE",
        "locations": loc_list,
        "vessels": ves_list,
        "metrics": {
            "ports": len(locations),
            "vessels": len(vessels),
            "containers": containers_count,
            "bookings": bookings_count,
            "voyages": voyages_count,
        },
    }
