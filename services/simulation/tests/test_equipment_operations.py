"""
Unit tests for Equipment (Doc 2 §11), Leasing (Doc 2 §12), and Repositioning (Doc 2 §13).
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config.parameters import ParameterRegistry
from app.models.equipment_model import (
    EquipmentModel,
    calculate_shortage,
    calculate_surplus,
    calculate_deficit,
)
from app.models.leasing_model import (
    LeasingModel,
    calculate_lease_cost,
)
from app.models.repositioning_model import (
    RepositioningModel,
    calculate_repositioning_cost,
)
from app.world.world_state import EquipmentBalance, WorldState


def test_equipment_formulas():
    """Doc 2 §11.4 - §11.6 formulas."""
    # Shortage = max(0, Required - Available)
    assert calculate_shortage(required=10, available=4) == 6
    assert calculate_shortage(required=4, available=10) == 0

    # Surplus = max(0, Available - Target)
    assert calculate_surplus(available=15, target=10) == 5
    assert calculate_surplus(available=8, target=10) == 0

    # Deficit = max(0, Target - Available)
    assert calculate_deficit(available=4, target=10) == 6
    assert calculate_deficit(available=12, target=10) == 0


def test_equipment_scarcity_signals():
    """Doc 2 §11.7: Scarcity emits EQUIPMENT_SHORTAGE_DETECTED."""
    registry = ParameterRegistry()
    model = EquipmentModel(registry)

    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    bal = EquipmentBalance(
        location_id="CNSHA",
        equipment_type="40HC",
        available=2,
        allocated=10,  # required = 10 -> shortage = 8
        target=5,
    )
    events = model.evaluate_location_equipment(bal, sim_time, state)
    assert len(events) == 1
    assert events[0].event_type == "EQUIPMENT_SHORTAGE_DETECTED"
    assert events[0].payload["shortage"] == 8
    assert state.kpis.equipment_shortages == 8


def test_leasing_lifecycle_and_costs():
    """Doc 2 §12.3, §12.4: Lease execution and cost tracking."""
    registry = ParameterRegistry()
    registry.set("LEASE_START_DELAY", 2.0)  # 2 days delay
    model = LeasingModel(registry)

    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    eq = state.get_equipment("USLAX", "40HC")
    eq.available = 5

    # 1. Order 20 containers on 30-day lease at $12/day
    lease, avail_at, order_event = model.order_lease(
        lease_id="LS-001",
        location_id="USLAX",
        equipment_type="40HC",
        quantity=20,
        daily_rate=12.0,
        duration_days=30.0,
        sim_time=sim_time,
        state=state,
    )
    # Cost = 20 * 12 * 30 = $7200
    assert calculate_lease_cost(20, 12.0, 30.0) == 7200.0
    assert state.kpis.total_lease_cost == 7200.0
    assert avail_at == sim_time + timedelta(days=2)
    assert lease.status == "PENDING"
    assert eq.available == 5  # Not yet added!

    # 2. Activate after 2 days
    act_time = sim_time + timedelta(days=2)
    act_event = model.activate_leased_equipment(lease, act_time, state)
    assert lease.status == "ACTIVE"
    assert eq.available == 25  # Added!
    assert act_event.event_type == "LEASE_EQUIPMENT_AVAILABLE"


def test_repositioning_lifecycle_and_costs():
    """Doc 2 §13.3, §13.4: Repositioning execution and cost tracking."""
    registry = ParameterRegistry()
    model = RepositioningModel(registry)

    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    src_eq = state.get_equipment("CNSHA", "20DC")
    src_eq.available = 50
    dest_eq = state.get_equipment("USLAX", "20DC")
    dest_eq.available = 10

    # 1. Dispatch 15 containers from CNSHA to USLAX
    # Cost = 15 * $350 = $5250
    order, eta, disp_event = model.dispatch_repositioning(
        reposition_id="RP-001",
        source_location_id="CNSHA",
        destination_location_id="USLAX",
        equipment_type="20DC",
        quantity=15,
        transit_days=14.0,
        cost_per_container=350.0,
        sim_time=sim_time,
        state=state,
    )
    assert src_eq.available == 35
    assert src_eq.in_transit == 15
    assert dest_eq.available == 10
    assert state.kpis.total_repositioning_cost == 5250.0
    assert eta == sim_time + timedelta(days=14)
    assert order.status == "IN_TRANSIT"

    # 2. Complete arrival at USLAX after 14 days
    arrival_time = sim_time + timedelta(days=14)
    comp_event = model.complete_repositioning(order, arrival_time, state)
    assert order.status == "COMPLETED"
    assert src_eq.in_transit == 0
    assert dest_eq.available == 25  # 10 + 15
    assert comp_event.event_type == "REPOSITIONING_COMPLETED"
