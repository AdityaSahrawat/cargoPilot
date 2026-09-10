"""
World Initialization & Baseline Architecture Tests
===================================================
Validates:
1. Deterministic baseline generation with stable SHA-256 seed.
2. Exact vessel status counts:
   - 8 IN_TRANSIT, 5 IN_PORT, 3 SCHEDULED, 1 WAITING_FOR_BERTH, 1 AVAILABLE (18 total).
3. Exactly 24 voyages (18 active + 6 future scheduled).
4. Container lifecycle distribution (~12k containers, loaded units on transit vessels).
5. KRPUS berth full capacity (4/4) and initial event queue resolution for V006.
6. Initial event queue operational chains (V002 at T+12h, V014 at T+6h, V004 at T+6h, etc.).
7. Immutable baseline cloning (Run A and Run B share baseline_id, distinct run_ids).
8. Scenario configuration isolation (global parameter registry remains pristine).
"""
import copy
import datetime
import uuid
import pytest
from app.clock.simulation_clock import SimulationClock
from app.config.parameters import ParameterRegistry, get_registry
from app.controller.simulation_controller import SimulationController
from app.engine.simulation_kernel import SimulationKernel
from app.events.event_bus import EventBus
from app.events.event_types import EventType
from app.world.world_seeder import WorldSeeder, stable_world_seed


def test_stable_world_seed_deterministic():
    seed1 = stable_world_seed("world-2", "v1")
    seed2 = stable_world_seed("world-2", "v1")
    seed_v2 = stable_world_seed("world-2", "v2")
    assert seed1 == seed2
    assert seed1 != seed_v2
    # Verify fits in PostgreSQL BIGINT (signed 64-bit int)
    assert 0 <= seed1 < 2**63


def test_baseline_entity_counts_and_statuses():
    reg = get_registry()
    seeder = WorldSeeder(reg)
    sim_time = datetime.datetime(2026, 9, 1, 0, 0, tzinfo=datetime.timezone.utc)
    ws = seeder.build_baseline("world-2", "v1", sim_time)

    # 1. Ports
    assert len(ws.ports) == 55
    krpus = ws.ports["KRPUS"]
    assert krpus.berths_total == 4
    assert krpus.berths_occupied == 4
    assert krpus.vessel_queue == ["V006"]

    # 2. Vessels
    assert len(ws.vessels) == 18
    statuses = {}
    for v in ws.vessels.values():
        statuses[v.status] = statuses.get(v.status, 0) + 1

    expected_statuses = {
        "IN_TRANSIT": 8,
        "IN_PORT": 5,
        "SCHEDULED": 3,
        "WAITING_FOR_BERTH": 1,
        "AVAILABLE": 1,
    }
    assert statuses == expected_statuses

    # Specific vessels
    assert ws.vessels["V001"].status == "IN_TRANSIT"
    assert ws.vessels["V002"].status == "IN_PORT"
    assert ws.vessels["V004"].status == "SCHEDULED"
    assert ws.vessels["V006"].status == "WAITING_FOR_BERTH"
    assert ws.vessels["V013"].status == "AVAILABLE"

    # 3. Voyages: 24 total (18 active/assigned + 6 future scheduled)
    assert len(ws.voyages) == 24
    active_or_sched = [vy for vy in ws.voyages.values() if vy.voyage_id.startswith("VOY-V")]
    future_sched = [vy for vy in ws.voyages.values() if vy.voyage_id.startswith("VOY-FUT-")]
    assert len(active_or_sched) == 18
    assert len(future_sched) == 6

    # V002 remaining turnaround
    v002_voyage = ws.voyages[ws.vessels["V002"].current_voyage_id]
    assert v002_voyage.remaining_turnaround_hours == 12.0

    # 4. Containers
    assert len(ws.containers) == 12000
    loaded = [c for c in ws.containers.values() if c.status == "LOADED"]
    assert len(loaded) == 3600
    for v in ws.vessels.values():
        if v.status == "IN_TRANSIT":
            assert v.current_load_teu > 0

    # 5. Bookings & Allocations
    assert len(ws.bookings) == 1500
    assert len(ws.allocations) == 200

    # 6. Equipment balances
    assert len(ws.equipment) == 165


@pytest.mark.asyncio
async def test_initial_event_queue_operational_chains():
    start_time = datetime.datetime(2026, 9, 1, 0, 0, tzinfo=datetime.timezone.utc)
    clock = SimulationClock(start_time)
    registry = get_registry()
    bus = EventBus()
    kernel = SimulationKernel(clock, registry, bus)
    controller = SimulationController(clock, registry, bus, kernel, session_factory=None)

    ws = await controller.start("NORMAL", seed=42, world_id="world-2")
    baseline_id = ws.world_baseline_id
    assert baseline_id is not None

    # Inspect scheduled events in SimPy queue
    event_types = [item.sim_event.event_type for item in kernel._event_queue]
    assert EventType.VESSEL_ARRIVED in event_types
    assert EventType.VESSEL_UNBERTHED in event_types
    assert EventType.VESSEL_DEPARTED in event_types
    assert EventType.BERTH_RELEASED in event_types
    assert EventType.DEMAND_GENERATED in event_types

    # Find V002 unberth event at T+12h
    v002_events = [item for item in kernel._event_queue if item.sim_event.entity_id == "V002"]
    assert len(v002_events) == 1
    assert v002_events[0].sim_event.event_type == EventType.VESSEL_UNBERTHED
    assert v002_events[0].simpy_time == 12.0  # at T+12h

    # Find V014 unberth event at T+6h
    v014_events = [item for item in kernel._event_queue if item.sim_event.entity_id == "V014"]
    assert len(v014_events) == 1
    assert v014_events[0].simpy_time == 6.0

    # Find V004 departure event at T+6h
    v004_events = [item for item in kernel._event_queue if item.sim_event.entity_id == "V004"]
    assert len(v004_events) == 1
    assert v004_events[0].sim_event.event_type == EventType.VESSEL_DEPARTED
    assert v004_events[0].simpy_time == 6.0

    # Find KRPUS berth release at T+14h
    krpus_events = [item for item in kernel._event_queue if item.sim_event.entity_id == "KRPUS"]
    assert len(krpus_events) == 1
    assert krpus_events[0].sim_event.event_type == EventType.BERTH_RELEASED
    assert krpus_events[0].simpy_time == 14.0


@pytest.mark.asyncio
async def test_scenario_configuration_isolation():
    """Verify that running a scenario with parameter overrides does not mutate the global parameter registry."""
    start_time = datetime.datetime(2026, 9, 1, 0, 0, tzinfo=datetime.timezone.utc)
    clock = SimulationClock(start_time)
    base_registry = get_registry()
    bus = EventBus()
    kernel = SimulationKernel(clock, base_registry, bus)
    controller = SimulationController(clock, base_registry, bus, kernel, session_factory=None)

    # Initial global value
    initial_speed_factor = base_registry.get("VESSEL_STORM_SPEED_FACTOR") if "VESSEL_STORM_SPEED_FACTOR" in [p.name for p in base_registry.all_params()] else None

    # Start STORM run
    ws_storm = await controller.start("STORM", seed=42, world_id="world-2")
    storm_b_id = ws_storm.world_baseline_id

    # Reset and start NORMAL run
    await controller.reset()
    ws_normal = await controller.start("NORMAL", seed=42, world_id="world-2")
    normal_b_id = ws_normal.world_baseline_id

    # Same baseline, isolated runs
    assert storm_b_id == normal_b_id
    assert ws_storm.run_id != ws_normal.run_id

    # Base registry remains untouched
    if initial_speed_factor is not None:
        assert base_registry.get("VESSEL_STORM_SPEED_FACTOR") == initial_speed_factor


def test_clone_baseline_sets_ids_properly():
    reg = get_registry()
    seeder = WorldSeeder(reg)
    sim_time = datetime.datetime(2026, 9, 1, 0, 0, tzinfo=datetime.timezone.utc)
    base_state = seeder.build_baseline("world-2", "v1", sim_time)

    clock = SimulationClock(sim_time)
    kernel = SimulationKernel(clock, reg, EventBus())
    controller = SimulationController(clock, reg, EventBus(), kernel, session_factory=None)

    b_id = uuid.uuid4()
    run_a_id = uuid.uuid4()
    run_b_id = uuid.uuid4()

    cloned_a = controller._clone_baseline(base_state, baseline_id=b_id, run_id=run_a_id)
    cloned_b = controller._clone_baseline(base_state, baseline_id=b_id, run_id=run_b_id)

    assert cloned_a.run_id == run_a_id
    assert cloned_a.world_baseline_id == str(b_id)

    assert cloned_b.run_id == run_b_id
    assert cloned_b.world_baseline_id == str(b_id)

    assert cloned_a.run_id != cloned_b.run_id
    assert cloned_a.world_baseline_id == cloned_b.world_baseline_id
