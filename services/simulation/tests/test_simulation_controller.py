"""
Unit tests for Simulation Controller (Component 9).
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.clock.simulation_clock import SimulationClock
from app.config.parameters import ParameterRegistry
from app.controller.simulation_controller import SimulationController, SimulationStatus
from app.engine.simulation_kernel import SimulationKernel
from app.events.event_bus import EventBus


@pytest.mark.asyncio
async def test_simulation_controller_lifecycle():
    """Test start, advance, pause, resume, reset lifecycle."""
    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start_time)
    registry = ParameterRegistry()
    bus = EventBus()
    kernel = SimulationKernel(clock, registry, bus)

    controller = SimulationController(clock, registry, bus, kernel)
    assert controller.get_status()["status"] == SimulationStatus.IDLE

    # 1. Start simulation
    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = await controller.start(scenario_id="normal", seed=42, start_time=start_time)
    assert controller.get_status()["status"] == SimulationStatus.RUNNING
    assert len(state.ports) == 55
    assert len(state.vessels) == 18

    # 2. Advance 24 hours
    updated_state, events = await controller.advance(24.0)
    assert clock.now == datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)
    assert controller.get_status()["simpy_time_hours"] == 24.0

    # 3. Inject disruption
    dis_id = await controller.inject_disruption(
        disruption_type="STORM",
        severity=0.5,
        duration_hours=12.0,
        affected_entity_ids=["V001"],
    )
    assert dis_id.startswith("DIS-")

    # 4. Advance 12 hours -> processes disruption
    updated_state2, events2 = await controller.advance(12.0)
    assert clock.now == datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    assert any(d.disruption_id == dis_id for d in updated_state2.disruptions)

    # 5. Pause & resume
    await controller.pause()
    assert controller.get_status()["status"] == SimulationStatus.PAUSED
    await controller.resume()
    assert controller.get_status()["status"] == SimulationStatus.RUNNING

    # 6. Reset
    await controller.reset()
    assert controller.get_status()["status"] == SimulationStatus.IDLE
    assert controller.state is None
