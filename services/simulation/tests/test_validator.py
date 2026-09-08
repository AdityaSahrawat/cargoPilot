"""
Unit tests for World State Validator (Doc 2 §27).
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.events.event_types import SimEvent, EventType
from app.world.validator import (
    ValidationError,
    validate_event_schema,
    validate_local_event,
    validate_advancement_state,
)
from app.world.world_state import (
    ContainerState,
    EquipmentBalance,
    PortState,
    VesselState,
    WorldState,
)


def test_event_schema_validation():
    """Doc 2 §27.6: Event must have all required fields."""
    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)

    # Valid event
    valid_event = SimEvent(
        event_type=EventType.VESSEL_ARRIVED,
        entity_type="vessel",
        entity_id="V001",
        simulation_time=sim_time,
        source="test",
        world_id="world-2",
    )
    validate_event_schema(valid_event)  # Should not raise

    # Missing event_type
    with pytest.raises(ValidationError, match="missing event_type"):
        invalid_event = SimEvent(
            event_type="",
            entity_type="vessel",
            entity_id="V001",
            simulation_time=sim_time,
            source="test",
            world_id="world-2",
        )
        validate_event_schema(invalid_event)


def test_local_event_container_consistency():
    """Doc 2 §27.2: Container cannot be IN_TRANSIT with a port location_id."""
    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    # Inconsistent container: IN_TRANSIT but location_id set to CNSHA
    c = ContainerState(
        container_id="C999",
        equipment_type="40HC",
        status="IN_TRANSIT",
        current_location_id="CNSHA",
    )
    state.containers["C999"] = c

    event = SimEvent(
        event_type=EventType.CONTAINER_LOADED,
        entity_type="container",
        entity_id="C999",
        simulation_time=sim_time,
        source="test",
        world_id="world-2",
    )

    with pytest.raises(ValidationError, match="is IN_TRANSIT but has location_id"):
        validate_local_event(event, state)


def test_advancement_port_capacity_constraint():
    """Doc 2 §27.3: Berths occupied cannot exceed berths total."""
    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    # Over-occupied port (5 occupied out of 4 berths)
    port = PortState(
        port_id="CNSHA",
        unlocode="CNSHA",
        berths_total=4,
        berths_occupied=5,
    )
    state.ports["CNSHA"] = port

    with pytest.raises(ValidationError, match="berths occupied .* exceeds total"):
        validate_advancement_state(state)


def test_advancement_equipment_conservation():
    """Doc 2 §27.5: Negative equipment counts are invalid."""
    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    bal = EquipmentBalance(
        location_id="USLAX",
        equipment_type="20DC",
        available=-2,  # Invalid negative count!
        allocated=0,
    )
    state.equipment[("USLAX", "20DC")] = bal

    with pytest.raises(ValidationError, match="Negative equipment count"):
        validate_advancement_state(state)
