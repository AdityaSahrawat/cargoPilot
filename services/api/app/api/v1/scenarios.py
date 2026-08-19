from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_db, Base, engine
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
    """GET /api/v1/scenarios - List available backend scenario definitions."""
    return AVAILABLE_SCENARIOS


@router.post("/scenarios/{scenario_id}/reset")
def reset_scenario(scenario_id: str, db: Session = Depends(get_db)):
    """POST /api/v1/scenarios/:id/reset - Reset database and seed exact scenario state."""
    # Wipe and recreate all tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

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
        "message": f"Database reset and seeded with scenario '{scenario_id}'",
    }
