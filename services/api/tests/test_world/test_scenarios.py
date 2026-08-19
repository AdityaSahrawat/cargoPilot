import os
import sys
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.db.database import Base
from app.optimization.service import OptimizationService
from tests.test_world.scenario_builder import ScenarioBuilder
from tests.test_world.validator import WorldValidator


@pytest.fixture(scope="function")
def scenario_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_baseline_scenario(scenario_db):
    """Scenario 1: Normal operations in Miniature World."""
    builder = ScenarioBuilder(scenario_db)
    builder.setup_base_world()

    opt_service = OptimizationService(scenario_db)
    carrier_id = builder.companies["carrier"].id

    run = opt_service.run_optimization(
        company_id=carrier_id,
        start_week=date.today().isoformat(),
        horizon_weeks=8,
    )

    plan = opt_service.get_plan(run.id)
    validator = WorldValidator(scenario_db)
    validator.validate_plan_capacity(plan)
    validator.validate_non_negative_quantities(plan)
    validator.validate_container_assignments()


def test_capacity_shortage_scenario(scenario_db):
    """Scenario 2: Vessel Leg capacity constraint restricts empty repositioning."""
    builder = ScenarioBuilder(scenario_db)
    builder.build_scenario_capacity_shortage()

    opt_service = OptimizationService(scenario_db)
    carrier_id = builder.companies["carrier"].id

    run = opt_service.run_optimization(
        company_id=carrier_id,
        start_week=date.today().isoformat(),
        horizon_weeks=8,
    )

    plan = opt_service.get_plan(run.id)
    validator = WorldValidator(scenario_db)
    validator.validate_plan_capacity(plan)
    validator.validate_non_negative_quantities(plan)


def test_demand_spike_scenario(scenario_db):
    """Scenario 5: Demand surge in Dubai evaluated by optimizer."""
    builder = ScenarioBuilder(scenario_db)
    builder.build_scenario_demand_spike()

    opt_service = OptimizationService(scenario_db)
    carrier_id = builder.companies["carrier"].id

    run = opt_service.run_optimization(
        company_id=carrier_id,
        start_week=date.today().isoformat(),
        horizon_weeks=8,
    )

    plan = opt_service.get_plan(run.id)
    validator = WorldValidator(scenario_db)
    validator.validate_plan_capacity(plan)
    validator.validate_non_negative_quantities(plan)
    assert len(plan.demand) > 0
