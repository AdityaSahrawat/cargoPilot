"""
Unit tests for Allocation & 7-Day Lock Model (Doc 2 §9) and Import Return Model (Doc 2 §10).
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config.parameters import ParameterRegistry
from app.models.allocation_model import (
    AllocationModel,
    calculate_lock_cutoff_time,
    is_allocation_locked,
)
from app.models.import_return_model import (
    ImportReturnModel,
    calculate_customer_use_days,
    calculate_return_timestamp,
)
from app.world.world_state import BookingState, ContainerState, EquipmentBalance, WorldState


def test_lock_cutoff_time_calculation():
    """Doc 2 §9.4: T_cutoff = T_departure - 7 days."""
    dep_time = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    cutoff = calculate_lock_cutoff_time(dep_time, lock_days=7.0)
    assert cutoff == datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def test_lock_boundary_conditions():
    """
    Doc 2 §9.4:
        T < T_cutoff  → UNLOCKED
        T ≥ T_cutoff  → LOCKED (equality belongs to locked state)
    """
    cutoff = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)

    # 1 second before cutoff -> Unlocked
    t_before = cutoff - timedelta(seconds=1)
    assert is_allocation_locked(t_before, cutoff) is False

    # Exactly at cutoff -> LOCKED
    assert is_allocation_locked(cutoff, cutoff) is True

    # After cutoff -> LOCKED
    t_after = cutoff + timedelta(hours=1)
    assert is_allocation_locked(t_after, cutoff) is True


def test_evaluate_booking_locks_transition():
    """Bookings crossing cutoff transition to LOCKED and emit BOOKING_LOCKED event."""
    registry = ParameterRegistry()
    model = AllocationModel(registry)

    sim_time = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    # Booking 1: Cutoff has passed (at cutoff)
    b1 = BookingState(
        booking_id="BK-001",
        origin_port_id="CNSHA",
        destination_port_id="USLAX",
        equipment_type="40HC",
        quantity=5,
        cargo_ready_time=sim_time,
        booking_time=sim_time - timedelta(days=10),
        status="ALLOCATED",
        lock_status="UNLOCKED",
        voyage_id="VY-01",
        cutoff_time=sim_time,  # cutoff = now
    )
    state.bookings["BK-001"] = b1

    # Booking 2: Cutoff is in the future
    b2 = BookingState(
        booking_id="BK-002",
        origin_port_id="CNSHA",
        destination_port_id="USLAX",
        equipment_type="40HC",
        quantity=5,
        cargo_ready_time=sim_time,
        booking_time=sim_time - timedelta(days=10),
        status="ALLOCATED",
        lock_status="UNLOCKED",
        voyage_id="VY-02",
        cutoff_time=sim_time + timedelta(days=2),  # in future
    )
    state.bookings["BK-002"] = b2

    events = model.evaluate_booking_locks(state, sim_time)
    assert len(events) == 1
    assert events[0].event_type == "BOOKING_LOCKED"
    assert b1.lock_status == "LOCKED"
    assert b2.lock_status == "UNLOCKED"


def test_locked_allocation_immutable():
    """Attempting to modify allocation for a LOCKED booking must raise ValueError."""
    registry = ParameterRegistry()
    model = AllocationModel(registry)

    sim_time = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    b_locked = BookingState(
        booking_id="BK-LOCKED",
        origin_port_id="CNSHA",
        destination_port_id="USLAX",
        equipment_type="40HC",
        quantity=1,
        cargo_ready_time=sim_time,
        booking_time=sim_time - timedelta(days=10),
        status="ALLOCATED",
        lock_status="LOCKED",
    )
    state.bookings["BK-LOCKED"] = b_locked

    with pytest.raises(ValueError, match="Violation of 7-day lock"):
        model.observe_cargo_pilot_allocation(
            booking_id="BK-LOCKED",
            container_id="C999",
            voyage_id="VY-NEW",
            sim_time=sim_time,
            state=state,
        )


def test_import_return_lifecycle():
    """Doc 2 §10: T_return = T_delivery + T_customer_use, pool available + 1."""
    registry = ParameterRegistry()
    registry.set("IMPORT_RETURN_MEAN_DAYS", 5.0, scope_key="40HC")

    model = ImportReturnModel(registry)
    delivery_time = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=delivery_time, world_id="world-2")

    container = ContainerState(
        container_id="C-IMPORT",
        equipment_type="40HC",
        status="DISCHARGED",
        current_location_id="USLAX",
    )
    state.containers["C-IMPORT"] = container

    # Schedule customer use (deterministic)
    ret_time, use_days = model.schedule_customer_return(
        container, delivery_time, state, deterministic=True
    )
    assert use_days == 5.0
    assert ret_time == delivery_time + timedelta(days=5)
    assert container.status == "CUSTOMER"

    # Process empty return at ret_time
    eq = state.get_equipment("USLAX", "40HC")
    eq.available = 10
    event = model.process_empty_return(container, "USLAX", ret_time, state)
    assert container.status == "EMPTY_AVAILABLE"
    assert eq.available == 11
    assert event.event_type == "CONTAINER_RETURNED_EMPTY"
