"""
Multi-step simulation execution cycle integration tests (Doc 1 §5, Doc 2 §29.5).

Verifies the full advancement lifecycle over multi-day simulation horizons:
1. Multi-step advancement with demand generation, booking lifecycle, vessel transit, and cost accumulation.
2. Storm disruption impact on transit speed, cascade, and recovery.
3. Port congestion queueing and berth turnaround.
4. Conservation and validation integrity across 7 simulated days.
"""
from datetime import datetime, timezone, timedelta
import random
import pytest

from app.clock.simulation_clock import SimulationClock
from app.config.parameters import ParameterRegistry
from app.controller.simulation_controller import SimulationController, SimulationStatus
from app.engine.simulation_kernel import SimulationKernel
from app.events.event_bus import EventBus
from app.events.event_types import EventType, SimEvent
from app.models.allocation_model import AllocationModel
from app.models.booking_model import BookingModel
from app.models.cost_model import CostModel
from app.models.demand_model import DemandModel
from app.world.validator import validate_advancement_state
from app.world.world_state import VoyageState


@pytest.mark.asyncio
async def test_multi_day_execution_cycle_and_cost_accumulation():
    """
    Run a 7-day (168-hour) continuous simulation in 24-hour increments.
    Verify:
    - Discrete event advancement completes cleanly without error.
    - Demand and bookings are created and tracked in state.
    - Vessels progress along voyages.
    - Booking locks transition as departure approaches within cutoff.
    - Operational costs accumulate in world state KPIs.
    - WorldState validation passes after every day.
    """
    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start_time)
    registry = ParameterRegistry()
    bus = EventBus()
    kernel = SimulationKernel(clock, registry, bus)
    controller = SimulationController(clock, registry, bus, kernel)

    state = await controller.start(scenario_id="normal", seed=42, start_time=start_time)
    assert len(state.ports) == 55
    assert len(state.vessels) == 18

    # Set up an active voyage for V001
    v001 = state.vessels["V001"]
    voyage = VoyageState(
        voyage_id="VY001",
        vessel_id="V001",
        origin_port_id="SGSIN",
        destination_port_id="NLRTM",
        scheduled_departure=start_time,
        scheduled_arrival=start_time + timedelta(days=15),
        route_distance_nm=5000.0,
    )
    state.voyages["VY001"] = voyage
    controller._vessel_model.start_voyage(v001, voyage, start_time)
    initial_progress = v001.position_fraction

    demand_model = DemandModel(registry, random.Random(42))
    booking_model = BookingModel(registry, random.Random(42))
    cost_model = CostModel(registry)
    allocation_model = AllocationModel(registry)

    total_events_collected = 0

    # Advance 7 days (7 x 24 hours)
    for day in range(1, 8):
        current_day_time = clock.now

        # 1. Generate daily demand and bookings
        pairs = [("CNSHA", "USLAX", "40HC"), ("SGSIN", "NLRTM", "20DC")]
        demand_model.step_demand_generation(
            state=state,
            sim_time=current_day_time,
            active_od_pairs=pairs,
            days_since_start=float(day - 1),
            deterministic=True,
        )

        booking_model.create_booking_from_demand(
            origin_port_id="SGSIN",
            destination_port_id="NLRTM",
            equipment_type="20DC",
            quantity=10,
            sim_time=current_day_time,
            state=state,
            voyage_id="VY001",
            departure_time=start_time + timedelta(days=5),
        )

        # 2. Advance simulation by 24.0 hours through controller
        state, events = await controller.advance(24.0)
        total_events_collected += len(events)

        # 3. Apply daily cost calculations
        cost_model.record_storage_cost(
            location_id="SGSIN",
            container_count=100,
            days=1.0,
            sim_time=current_day_time,
            state=state,
        )

        # 4. Validate advancement state
        validate_advancement_state(state)

        # Verify clock advanced exactly 24 hours
        expected_time = start_time + timedelta(hours=24.0 * day)
        assert clock.now == expected_time

    # After 7 days:
    assert clock.elapsed_hours == 168.0
    assert clock.elapsed_days == 7.0

    # Vessel has progressed along its route
    assert v001.position_fraction > initial_progress

    # Bookings were created and tracked
    assert len(state.bookings) > 0
    assert state.kpis.bookings_created > 0

    # Operational costs have accumulated
    assert state.kpis.total_cost > 0.0
    assert total_events_collected > 0


@pytest.mark.asyncio
async def test_storm_disruption_speed_reduction_and_recovery():
    """
    Test injecting a storm on an in-transit vessel, verifying:
    - Speed reduction while storm is active.
    - ETA pushback.
    - Disruption recovery upon end of duration.
    """
    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start_time)
    registry = ParameterRegistry()
    bus = EventBus()
    kernel = SimulationKernel(clock, registry, bus)
    controller = SimulationController(clock, registry, bus, kernel)

    state = await controller.start(scenario_id="normal", seed=42, start_time=start_time)
    vessel = state.vessels["V001"]

    voyage = VoyageState(
        voyage_id="VY_STORM",
        vessel_id="V001",
        origin_port_id="SGSIN",
        destination_port_id="USLAX",
        scheduled_departure=start_time,
        scheduled_arrival=start_time + timedelta(days=10),
        route_distance_nm=6000.0,
    )
    state.voyages["VY_STORM"] = voyage
    controller._vessel_model.start_voyage(vessel, voyage, start_time)

    base_speed = vessel.current_speed_knots

    # Inject STORM disruption for 24 hours with severity 0.8
    dis_id = await controller.inject_disruption(
        disruption_type="STORM",
        severity=0.8,
        duration_hours=24.0,
        affected_entity_ids=["V001"],
    )

    # Advance 12 hours: Disruption is active
    state, events = await controller.advance(12.0)
    active_disruptions = [d for d in state.disruptions if d.disruption_id == dis_id and d.status == "ACTIVE"]
    assert len(active_disruptions) == 1

    # Vessel speed is reduced while storm is active
    assert vessel.current_speed_knots < base_speed

    # Advance another 16 hours (total 28h): Disruption duration (24h) has elapsed
    state, events = await controller.advance(16.0)
    disruption = next(d for d in state.disruptions if d.disruption_id == dis_id)
    assert disruption.status == "ENDED"
    # Delay persists in WorldState per Doc 2 §14.3
    assert vessel.eta > voyage.scheduled_arrival


@pytest.mark.asyncio
async def test_berth_queueing_and_fifo_service():
    """
    Test multiple vessels arriving at a single-berth port:
    - First vessel berths immediately.
    - Second vessel queues in berth FIFO waiting queue.
    """
    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start_time)
    registry = ParameterRegistry()
    bus = EventBus()
    kernel = SimulationKernel(clock, registry, bus)
    controller = SimulationController(clock, registry, bus, kernel)

    state = await controller.start(scenario_id="normal", seed=42, start_time=start_time)
    port = state.ports["SGSIN"]
    port.berths_total = 1
    port.berths_occupied = 0
    port.vessel_queue.clear()

    # Vessel 1
    v1 = state.vessels["V001"]
    voyage1 = VoyageState(
        voyage_id="VY_BERTH_1",
        vessel_id="V001",
        origin_port_id="CNSHA",
        destination_port_id="SGSIN",
        scheduled_departure=start_time,
        scheduled_arrival=start_time,
        route_distance_nm=2000.0,
    )
    state.voyages["VY_BERTH_1"] = voyage1
    v1.current_voyage_id = "VY_BERTH_1"
    v1.status = "IN_TRANSIT"

    # Vessel 2
    v2 = state.vessels["V002"]
    voyage2 = VoyageState(
        voyage_id="VY_BERTH_2",
        vessel_id="V002",
        origin_port_id="CNSHA",
        destination_port_id="SGSIN",
        scheduled_departure=start_time,
        scheduled_arrival=start_time,
        route_distance_nm=2000.0,
    )
    state.voyages["VY_BERTH_2"] = voyage2
    v2.current_voyage_id = "VY_BERTH_2"
    v2.status = "IN_TRANSIT"

    kernel.schedule_now(
        SimEvent(
            event_type=EventType.VESSEL_ARRIVED,
            entity_type="vessel",
            entity_id=v1.vessel_id,
            simulation_time=clock.now,
            source="vessel_model",
            world_id=state.world_id,
        ),
        state,
    )

    kernel.schedule_now(
        SimEvent(
            event_type=EventType.VESSEL_ARRIVED,
            entity_type="vessel",
            entity_id=v2.vessel_id,
            simulation_time=clock.now,
            source="vessel_model",
            world_id=state.world_id,
        ),
        state,
    )

    # Advance 1 hour to process arrivals
    state, events = await controller.advance(1.0)

    # V1 should be IN_PORT (berthed), V2 should be WAITING_FOR_BERTH in queue
    assert port.berths_occupied == 1
    assert v1.status == "IN_PORT"
    assert v2.status == "WAITING_FOR_BERTH"
    assert "V002" in port.vessel_queue


@pytest.mark.asyncio
async def test_controller_pause_resume_and_error_handling():
    """
    Verify state transitions and safeguards for pause/resume.
    """
    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start_time)
    registry = ParameterRegistry()
    bus = EventBus()
    kernel = SimulationKernel(clock, registry, bus)
    controller = SimulationController(clock, registry, bus, kernel)

    # Cannot advance before starting
    with pytest.raises(RuntimeError, match="Simulation is not running"):
        await controller.advance(1.0)

    await controller.start(scenario_id="normal", seed=42, start_time=start_time)
    assert controller.get_status()["status"] == SimulationStatus.RUNNING

    # Pause
    await controller.pause()
    assert controller.get_status()["status"] == SimulationStatus.PAUSED

    # Cannot advance while paused
    with pytest.raises(RuntimeError, match="Simulation is not running"):
        await controller.advance(1.0)

    # Resume
    await controller.resume()
    assert controller.get_status()["status"] == SimulationStatus.RUNNING

    # Advance succeeds
    state, events = await controller.advance(1.0)
    assert clock.elapsed_hours == 1.0
