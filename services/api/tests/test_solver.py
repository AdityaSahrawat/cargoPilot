import uuid
import pytest
from app.db import enums
from app.optimization.models import (
    OptimizationInput,
    ForecastItem,
    LegCapacityItem,
)
from app.optimization.solver import Solver


def test_api_solver_milp_flow_conservation_and_tradeoff():
    solver = Solver()

    port_a = uuid.uuid4()
    port_b = uuid.uuid4()
    leg_id = uuid.uuid4()
    ctype = enums.ContainerType.DRY_40FT

    # Port A has surplus (100 containers), Port B has deficit (0 containers, 30 demand)
    # Leg capacity from A to B is 20 units.
    # The optimal MILP decision:
    # - Reposition 20 containers from A to B (hitting leg capacity constraint, cost = 20 * 50 = 1000)
    # - To fulfill remaining 10 demand at B, lease 10 containers (cost = 10 * 450 = 4500)
    #   because shortage penalty (3500) > leasing cost (450) + handling (150).
    # - Served demand at B = 30, Backlog = 0.
    # - Ending inventory at A = 100 - 20 = 80.
    # - Ending inventory at B = 0 (20 repo + 10 lease - 30 served).

    inp = OptimizationInput(
        company_id=uuid.uuid4(),
        start_week="2026-W35",
        horizon_weeks=1,
        container_types=[ctype],
        location_ids=[port_a, port_b],
        initial_inventories={
            f"{port_a}_{ctype.value}": 100,
            f"{port_b}_{ctype.value}": 0,
        },
        forecasts=[
            ForecastItem(
                location_id=port_b,
                container_type=ctype,
                week="2026-W35",
                quantity=30,
            )
        ],
        leg_capacities=[
            LegCapacityItem(
                leg_id=leg_id,
                voyage_id=uuid.uuid4(),
                from_port_id=port_a,
                to_port_id=port_b,
                available_capacity=20,
            )
        ],
    )

    result = solver.solve(inp)

    # 1. Repositioning: must exactly equal available leg capacity (20)
    assert len(result.repositioning) == 1
    repo = result.repositioning[0]
    assert repo.voyage_leg_id == leg_id
    assert repo.quantity == 20
    assert repo.cost == 20 * solver.COST_REPOSITIONING_PER_CONTAINER

    # 2. Leasing: must cover remaining 10 units at Port B
    assert len(result.leasing) == 1
    lease = result.leasing[0]
    assert lease.location_id == port_b
    assert lease.quantity == 10
    assert lease.cost == 10 * solver.COST_LEASE_PER_CONTAINER

    # 3. Demand: 30 served, 0 backlog (not the old heuristic 80% = 24!)
    assert len(result.demand) == 1
    dm = result.demand[0]
    assert dm.forecast_demand == 30
    assert dm.forecast_served == 30
    assert dm.forecast_backlog == 0

    # 4. Inventories:
    inv_map = {r.location_id: r.quantity for r in result.inventory if r.container_type == ctype}
    assert inv_map[port_a] == 80  # 100 - 20 outflow
    assert inv_map[port_b] == 0   # 0 + 20 in + 10 lease - 30 served

    # 5. Objective value matches exact breakdown:
    # Repo (20 * 50 = 1000) + Lease (10 * 450 = 4500) + Handling (30 * 150 = 4500) + Holding (80 * 35 = 2800)
    expected_obj = 1000.0 + 4500.0 + 4500.0 + 2800.0
    assert abs(result.objective_value - expected_obj) < 1e-3
