"""
Unit tests for Backlog Model (Doc 2 §21) and Cost Models (Doc 2 §22).
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.config.parameters import ParameterRegistry
from app.models.backlog_model import BacklogModel, calculate_next_backlog
from app.models.cost_model import (
    CostModel,
    calculate_delay_cost,
    calculate_storage_cost,
    calculate_shortage_cost,
)
from app.world.world_state import KPIAccumulator, WorldState


def test_backlog_balance_equation():
    """Doc 2 §21.2: Backlog_{t+1} = max(0, Backlog_t + Arrivals - Completed)."""
    # 10 arrivals, 6 completed -> backlog = 4
    assert calculate_next_backlog(current_backlog=0, arrivals=10, completed=6) == 4

    # Current backlog 4, 2 arrivals, 5 completed -> backlog = 1
    assert calculate_next_backlog(current_backlog=4, arrivals=2, completed=5) == 1

    # Over-completed cannot drop backlog below 0
    assert calculate_next_backlog(current_backlog=1, arrivals=0, completed=5) == 0


def test_cost_formulas():
    """Doc 2 §22.3, §22.6, §22.7 mathematical formulas."""
    # Delay cost: 10h @ $1500/h = $15,000
    assert calculate_delay_cost(delay_hours=10.0, cost_per_hour=1500.0) == 15000.0

    # Storage cost: 50 containers for 3 days @ $25/day = $3,750
    assert calculate_storage_cost(container_count=50, days=3.0, cost_per_day=25.0) == 3750.0

    # Shortage penalty: 4 containers @ $500/container = $2,000
    assert calculate_shortage_cost(shortage_count=4, cost_per_container=500.0) == 2000.0


def test_cost_accumulation_in_kpis():
    """Doc 2 §22.2: TotalCost = ∑ Cost_i."""
    registry = ParameterRegistry()
    registry.set("VESSEL_DELAY_COST_PER_HOUR", 1000.0)
    registry.set("STORAGE_COST_PER_DAY", 20.0)
    registry.set("SHORTAGE_COST_PER_CONTAINER", 400.0)

    model = CostModel(registry)
    sim_time = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    # 1. Record delay
    model.record_delay_cost("V001", delay_hours=5.0, sim_time=sim_time, state=state)
    assert state.kpis.total_delay_cost == 5000.0

    # 2. Record storage
    model.record_storage_cost("SGSIN", container_count=10, days=5.0, sim_time=sim_time, state=state)
    assert state.kpis.total_storage_cost == 1000.0

    # 3. Record shortage penalty
    model.record_shortage_penalty("CNSHA", "40HC", shortage_count=2, sim_time=sim_time, state=state)
    assert state.kpis.total_shortage_penalty == 800.0

    # Total cost = 5000 + 1000 + 800 = $6,800
    assert state.kpis.total_cost == 6800.0
