"""
Unit tests for Event Priority Ordering (Doc 2 §2.5) and Event Scheduling.
"""
import uuid
from datetime import datetime, timezone
import pytest

from app.clock.simulation_clock import SimulationClock
from app.config.parameters import ParameterRegistry
from app.engine.simulation_kernel import SimulationKernel
from app.events.event_bus import EventBus
from app.events.event_types import (
    SimEvent,
    EventPriority,
    EventType,
)
from app.world.world_state import WorldState


def create_kernel_and_state():
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start)
    registry = ParameterRegistry()
    bus = EventBus()
    kernel = SimulationKernel(clock, registry, bus)
    state = WorldState(run_id=uuid.uuid4(), world_id="TEST", simulation_time=start)
    return kernel, state, clock, bus


def test_ten_level_event_priority_ordering():
    """
    Doc 2 §2.5: When events occur at the exact same simulation time,
    they must be processed strictly according to the 10-level priority.
    """
    kernel, state, clock, bus = create_kernel_and_state()
    execution_order = []

    # Map each priority level (1 to 10) to a representative EventType
    priority_events = [
        (EventPriority.PERSISTENCE_PUBLICATION, EventType.STEP_COMPLETED),
        (EventPriority.COST_ACCOUNTING, EventType.DELAY_COST_INCURRED),
        (EventPriority.CARGOPILOT_DECISION, EventType.ALLOCATION_COMMITTED),
        (EventPriority.INFORMATION_FORECAST, EventType.FORECAST_UPDATED),
        (EventPriority.BOOKING_GENERATION, EventType.BOOKING_CREATED),
        (EventPriority.DEMAND_GENERATION, EventType.DEMAND_GENERATED),
        (EventPriority.CONTAINER_OPERATIONAL, EventType.CONTAINER_GATE_IN),
        (EventPriority.PORT_RESOURCE, EventType.PORT_CONGESTION_CHANGED),
        (EventPriority.VESSEL_MOVEMENT, EventType.VESSEL_ARRIVED),
        (EventPriority.DISRUPTION_ACTIVATION, EventType.DISRUPTION_ACTIVATED),
    ]

    sim_t = 10.0  # All scheduled at exact same timestamp

    for prio, event_type in priority_events:
        evt = SimEvent(
            event_type=event_type,
            entity_type="test",
            entity_id=prio.name,
            simulation_time=clock.from_simpy_time(sim_t),
            source="test_source",
            world_id="TEST",
        )

        def make_handler(p=prio):
            return lambda e, s: execution_order.append(p)

        kernel.schedule(evt, at_simpy_time=sim_t, handler=make_handler(prio))

    # Advance kernel across sim_t
    kernel.advance(state, delta_hours=12.0)

    # Verify order matches numeric priority 1..10
    expected_order = sorted([p for p, _ in priority_events], key=lambda p: p.value)
    assert execution_order == expected_order
    assert execution_order[0] == EventPriority.DISRUPTION_ACTIVATION
    assert execution_order[-1] == EventPriority.PERSISTENCE_PUBLICATION


def test_fifo_tie_breaking_for_equal_priority_and_time():
    """
    Same timestamp + same priority must be processed in insertion order (FIFO).
    """
    kernel, state, clock, bus = create_kernel_and_state()
    executed_ids = []

    sim_t = 5.0
    for entity_id in ["VESSEL_A", "VESSEL_B", "VESSEL_C"]:
        evt = SimEvent(
            event_type=EventType.VESSEL_ARRIVED,
            entity_type="vessel",
            entity_id=entity_id,
            simulation_time=clock.from_simpy_time(sim_t),
            source="vessel_model",
            world_id="TEST",
        )

        def make_handler(eid=entity_id):
            return lambda e, s: executed_ids.append(eid)

        kernel.schedule(evt, at_simpy_time=sim_t, handler=make_handler(entity_id))

    kernel.advance(state, delta_hours=10.0)
    assert executed_ids == ["VESSEL_A", "VESSEL_B", "VESSEL_C"]


def test_chronological_ordering_trumps_priority():
    """
    An earlier event with low priority MUST execute before a later event
    with higher priority.
    """
    kernel, state, clock, bus = create_kernel_and_state()
    execution_order = []

    # Priority 10 at T=2h
    evt_early_low_prio = SimEvent(
        event_type=EventType.STEP_COMPLETED,
        entity_type="simulation",
        entity_id="EARLY",
        simulation_time=clock.from_simpy_time(2.0),
        source="simulation_engine",
        world_id="TEST",
    )
    kernel.schedule(
        evt_early_low_prio,
        at_simpy_time=2.0,
        handler=lambda e, s: execution_order.append("EARLY_LOW_PRIO"),
    )

    # Priority 1 at T=4h
    evt_late_high_prio = SimEvent(
        event_type=EventType.DISRUPTION_ACTIVATED,
        entity_type="disruption",
        entity_id="LATE",
        simulation_time=clock.from_simpy_time(4.0),
        source="disruption_engine",
        world_id="TEST",
    )
    kernel.schedule(
        evt_late_high_prio,
        at_simpy_time=4.0,
        handler=lambda e, s: execution_order.append("LATE_HIGH_PRIO"),
    )

    kernel.advance(state, delta_hours=6.0)
    assert execution_order == ["EARLY_LOW_PRIO", "LATE_HIGH_PRIO"]


def test_events_beyond_target_remain_in_queue():
    """
    Events scheduled past T_target must not execute until reached in a subsequent step.
    """
    kernel, state, clock, bus = create_kernel_and_state()
    execution_order = []

    evt_step1 = SimEvent(
        event_type=EventType.VESSEL_ARRIVED,
        entity_type="vessel",
        entity_id="1",
        simulation_time=clock.from_simpy_time(10.0),
        source="vessel_model",
        world_id="TEST",
    )
    evt_step2 = SimEvent(
        event_type=EventType.VESSEL_ARRIVED,
        entity_type="vessel",
        entity_id="2",
        simulation_time=clock.from_simpy_time(30.0),
        source="vessel_model",
        world_id="TEST",
    )

    kernel.schedule(evt_step1, at_simpy_time=10.0, handler=lambda e, s: execution_order.append("STEP_1"))
    kernel.schedule(evt_step2, at_simpy_time=30.0, handler=lambda e, s: execution_order.append("STEP_2"))

    # Step 1: 0h to 24h
    kernel.advance(state, delta_hours=24.0)
    assert execution_order == ["STEP_1"]

    # Step 2: 24h to 48h
    kernel.advance(state, delta_hours=24.0)
    assert execution_order == ["STEP_1", "STEP_2"]


def test_event_bus_pub_sub_and_wildcard():
    """
    EventBus must dispatch to specific topic subscribers and wildcard subscribers.
    """
    bus = EventBus()
    specific_received = []
    wildcard_received = []

    def specific_handler(evt: SimEvent):
        specific_received.append(evt.event_type)

    def wildcard_handler(evt: SimEvent):
        wildcard_received.append(evt.event_type)

    bus.subscribe(EventType.VESSEL_ARRIVED, specific_handler)
    bus.subscribe_all(wildcard_handler)

    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    e1 = SimEvent(
        event_type=EventType.VESSEL_ARRIVED,
        entity_type="vessel",
        entity_id="V01",
        simulation_time=now,
        source="vessel_model",
        world_id="TEST",
    )
    e2 = SimEvent(
        event_type=EventType.PORT_CONGESTION_CHANGED,
        entity_type="port",
        entity_id="SGSIN",
        simulation_time=now,
        source="port_model",
        world_id="TEST",
    )

    bus.emit(e1)
    bus.emit(e2)

    assert specific_received == [EventType.VESSEL_ARRIVED]
    assert wildcard_received == [EventType.VESSEL_ARRIVED, EventType.PORT_CONGESTION_CHANGED]
    assert bus.pending_event_count == 2

    flushed = bus.flush_step_log()
    assert len(flushed) == 2
    assert bus.pending_event_count == 0
