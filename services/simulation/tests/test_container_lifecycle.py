"""
Unit tests for Container & Equipment Model (Doc 2 §6).
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config.parameters import ParameterRegistry
from app.models.container_model import (
    ContainerModel,
    check_damage,
    check_damage_severity,
    calculate_repair_duration_hours,
    validate_status_transition,
)
from app.world.world_state import ContainerState, EquipmentBalance, WorldState


def test_valid_lifecycle_transitions():
    """Doc 2 §6.2: Validate full container lifecycle progression."""
    registry = ParameterRegistry()
    model = ContainerModel(registry)
    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    container = ContainerState(
        container_id="C001",
        equipment_type="40HC",
        status="EMPTY_AVAILABLE",
        condition="GOOD",
        current_location_id="CNSHA",
    )
    state.containers["C001"] = container
    eq = state.get_equipment("CNSHA", "40HC")
    eq.available = 10

    # 1. Allocate to booking
    model.allocate_container(container, "BK001", state, sim_time)
    assert container.status == "ALLOCATED"
    assert container.booking_id == "BK001"
    assert eq.available == 9
    assert eq.allocated == 1

    # 2. Gate Out
    model.transition_status(container, "GATE_OUT", sim_time + timedelta(hours=1), state)
    assert container.status == "GATE_OUT"

    # 3. Stuffing
    model.transition_status(container, "STUFFING", sim_time + timedelta(hours=3), state)
    assert container.status == "STUFFING"

    # 4. Loaded
    model.transition_status(container, "LOADED", sim_time + timedelta(hours=6), state)
    assert container.status == "LOADED"

    # 5. Load on vessel (enters transit)
    model.load_on_vessel(container, "V001", "VY001", state, sim_time + timedelta(hours=8))
    assert container.status == "IN_TRANSIT"
    assert container.current_voyage_id == "VY001"
    assert container.current_location_id is None
    assert eq.allocated == 0
    assert eq.in_transit == 1

    # 6. Discharge at destination port
    model.discharge_from_vessel(container, "USLAX", state, sim_time + timedelta(hours=100))
    assert container.status == "DISCHARGED"
    assert container.current_location_id == "USLAX"
    assert container.current_voyage_id is None

    # 7. Customer delivery
    model.transition_status(container, "CUSTOMER", sim_time + timedelta(hours=105), state)
    assert container.status == "CUSTOMER"

    # 8. Empty after customer devanning
    model.transition_status(container, "EMPTY", sim_time + timedelta(hours=150), state)
    assert container.status == "EMPTY"

    # 9. Return empty to depot
    dest_eq = state.get_equipment("USLAX", "40HC")
    dest_eq.available = 5
    model.return_empty(container, "USLAX", state, sim_time + timedelta(hours=155))
    assert container.status == "EMPTY_AVAILABLE"
    assert container.booking_id is None
    assert dest_eq.available == 6


def test_invalid_lifecycle_transition_raises():
    """Attempting an invalid transition (e.g. EMPTY_AVAILABLE -> LOADED) must raise ValueError."""
    registry = ParameterRegistry()
    model = ContainerModel(registry)
    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    container = ContainerState(
        container_id="C002",
        equipment_type="20DC",
        status="EMPTY_AVAILABLE",
        condition="GOOD",
    )

    with pytest.raises(ValueError, match="Invalid container status transition"):
        model.transition_status(container, "LOADED", sim_time, state)


def test_damage_and_maintenance_bernoulli():
    """Doc 2 §6.5: Damage ~ Bernoulli(p_damage)."""
    assert check_damage(0.0) is False
    assert check_damage(1.0) is True

    assert check_damage_severity(0.0) is False
    assert check_damage_severity(1.0) is True


class DeterministicRNG:
    def __init__(self, values):
        self._values = list(values)
        self._idx = 0

    def random(self):
        val = self._values[self._idx % len(self._values)]
        self._idx += 1
        return val


def test_damage_and_repair_lifecycle():
    """Doc 2 §6.5: Damaged container enters MAINTENANCE then returns to GOOD."""
    registry = ParameterRegistry()
    registry.set("CONTAINER_DAMAGE_PROBABILITY", 0.05, scope_key="20DC")
    registry.set("CONTAINER_DAMAGE_SEVERITY", 0.0, scope_key="20DC")
    registry.set("CONTAINER_REPAIR_TIME", 2.0, scope_key="20DC")  # 2 days = 48h

    # RNG returns 0.01 (which is < 0.05, triggering damage)
    model = ContainerModel(registry, rng=DeterministicRNG([0.01, 0.5]))
    sim_time = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    container = ContainerState(
        container_id="C003",
        equipment_type="20DC",
        status="EMPTY_AVAILABLE",
        condition="GOOD",
        current_location_id="SGSIN",
    )
    state.containers["C003"] = container

    # Evaluate damage
    event = model.evaluate_operational_damage(container, sim_time, state)
    assert event is not None
    assert container.condition == "DAMAGED"
    assert container.status == "MAINTENANCE"
    assert container.available_from == sim_time + timedelta(hours=48)

    # Complete repair after 48h
    repair_time = sim_time + timedelta(hours=48)
    repair_event = model.complete_repair(container, repair_time, state)
    assert container.condition == "GOOD"
    assert container.status == "EMPTY_AVAILABLE"


def test_severe_damage_marks_unavailable():
    """Doc 2 §6.5: Severe damage sets condition to UNAVAILABLE."""
    registry = ParameterRegistry()
    registry.set("CONTAINER_DAMAGE_PROBABILITY", 0.05, scope_key="40DC")
    registry.set("CONTAINER_DAMAGE_SEVERITY", 0.5, scope_key="40DC")

    # 1st call for damage: 0.01 (< 0.05 -> damaged), 2nd call for severity: 0.1 (< 0.5 -> severe)
    model = ContainerModel(registry, rng=DeterministicRNG([0.01, 0.1]))
    sim_time = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    container = ContainerState(
        container_id="C004",
        equipment_type="40DC",
        status="LOADED",
        condition="GOOD",
        current_location_id="CNSHA",
    )
    state.containers["C004"] = container

    event = model.evaluate_operational_damage(container, sim_time, state)
    assert event is not None
    assert container.condition == "UNAVAILABLE"
    assert container.status == "UNAVAILABLE"
