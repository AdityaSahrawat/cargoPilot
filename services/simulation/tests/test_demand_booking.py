"""
Unit tests for Demand Model (Doc 2 §7) and Booking Generation Model (Doc 2 §8).
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config.parameters import ParameterRegistry
from app.models.demand_model import (
    DemandModel,
    calculate_demand_rate,
    sample_poisson_demand,
)
from app.models.booking_model import (
    BookingModel,
    check_cancellation,
    calculate_cargo_ready_time,
)
from app.world.world_state import BookingState, WorldState


class DeterministicRNG:
    def __init__(self, values):
        self._values = list(values)
        self._idx = 0

    def random(self):
        val = self._values[self._idx % len(self._values)]
        self._idx += 1
        return val


def test_calculate_demand_rate():
    """Doc 2 §7.4: λ = D_base * F_trend * F_seasonal * F_scenario."""
    base = 10.0
    f_trend = 1.10
    f_seasonal = 1.05
    f_scenario = 1.35

    rate = calculate_demand_rate(base, f_trend, f_seasonal, f_scenario)
    expected = 10.0 * 1.10 * 1.05 * 1.35
    assert pytest.approx(rate, rel=1e-3) == expected


def test_sample_poisson_demand_deterministic():
    """Deterministic mode rounds λ to nearest integer."""
    assert sample_poisson_demand(5.4, deterministic=True) == 5
    assert sample_poisson_demand(5.6, deterministic=True) == 6
    assert sample_poisson_demand(0.0, deterministic=True) == 0


def test_demand_generation_cycle():
    """Test generating demand across active OD pairs and saving to historical demand."""
    registry = ParameterRegistry()
    registry.set("DEMAND_BASE_RATE", 10.0)
    model = DemandModel(registry)

    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    pairs = [("CNSHA", "USLAX", "40HC"), ("SGSIN", "NLRTM", "20DC")]

    # Deterministic mode
    events = model.step_demand_generation(
        state=state,
        sim_time=sim_time,
        active_od_pairs=pairs,
        days_since_start=0.0,
        deterministic=True,
    )
    assert len(events) == 2
    assert state.demand.current_demand[("CNSHA", "USLAX", "40HC")] == 10.0
    assert state.demand.historical_demand[("CNSHA", "USLAX", "40HC", 0)] == 10.0


def test_booking_creation_and_cargo_ready_time():
    """Doc 2 §8.4: Booking creation with lead time and cutoff."""
    registry = ParameterRegistry()
    registry.set("BOOKING_LEAD_TIME", 14.0)
    model = BookingModel(registry)

    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    departure_time = sim_time + timedelta(days=20)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    booking, event = model.create_booking_from_demand(
        origin_port_id="CNSHA",
        destination_port_id="USLAX",
        equipment_type="40HC",
        quantity=5,
        sim_time=sim_time,
        state=state,
        voyage_id="VY100",
        departure_time=departure_time,
    )
    assert booking.status == "SUBMITTED"
    assert booking.lock_status == "UNLOCKED"
    assert booking.quantity == 5
    assert booking.cargo_ready_time == sim_time + timedelta(days=14)
    # T_cutoff = T_departure - 7 days (Doc 2 §9.4)
    assert booking.cutoff_time == departure_time - timedelta(days=7)
    assert state.kpis.bookings_created == 1


def test_booking_cancellation():
    """Doc 2 §8.5: Cancellation respects lock status."""
    registry = ParameterRegistry()
    registry.set("BOOKING_CANCELLATION_PROBABILITY", 0.05)

    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    # RNG returns 0.01 (< 0.05 -> cancel)
    model = BookingModel(registry, rng=DeterministicRNG([0.01]))

    # 1. Unlocked booking cancels
    unlocked_b = BookingState(
        booking_id="BK-01",
        origin_port_id="CNSHA",
        destination_port_id="USLAX",
        equipment_type="40HC",
        quantity=2,
        cargo_ready_time=sim_time,
        booking_time=sim_time,
        status="SUBMITTED",
        lock_status="UNLOCKED",
    )
    event = model.evaluate_cancellation(unlocked_b, sim_time, state)
    assert event is not None
    assert unlocked_b.status == "CANCELLED"
    assert state.kpis.bookings_cancelled == 1

    # 2. Locked booking is IMMUNE to cancellation
    locked_b = BookingState(
        booking_id="BK-02",
        origin_port_id="CNSHA",
        destination_port_id="USLAX",
        equipment_type="40HC",
        quantity=2,
        cargo_ready_time=sim_time,
        booking_time=sim_time,
        status="SUBMITTED",
        lock_status="LOCKED",  # LOCKED
    )
    event_locked = model.evaluate_cancellation(locked_b, sim_time, state)
    assert event_locked is None
    assert locked_b.status == "SUBMITTED"
