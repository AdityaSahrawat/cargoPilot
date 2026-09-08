"""
Unit tests for Kafka Integration (Component 10).
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.clock.simulation_clock import SimulationClock
from app.config.parameters import ParameterRegistry
from app.controller.simulation_controller import SimulationController
from app.engine.simulation_kernel import SimulationKernel
from app.events.event_bus import EventBus
from app.kafka.consumer import SimulationKafkaConsumer
from app.kafka.producer import SimulationKafkaProducer
from app.world.world_state import BookingState


@pytest.mark.asyncio
async def test_kafka_producer_mock_publish():
    """Producer publishes successfully in offline/mock mode."""
    producer = SimulationKafkaProducer(enabled=False)
    success = producer.publish_message(
        topic="simulation.vessel-events",
        key="test-key",
        value={"event_type": "VESSEL_DEPARTED", "vessel_id": "V001"},
    )
    assert success is True


@pytest.mark.asyncio
async def test_kafka_consumer_decision_processing():
    """Consumer processes allocation, lease, and repositioning decisions into controller."""
    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start_time)
    registry = ParameterRegistry()
    bus = EventBus()
    kernel = SimulationKernel(clock, registry, bus)

    controller = SimulationController(clock, registry, bus, kernel)
    await controller.start(scenario_id="normal", seed=42, start_time=start_time)

    consumer = SimulationKafkaConsumer(controller, enabled=False)

    # 1. Test incoming allocation
    state = controller.state
    assert state is not None

    b = BookingState(
        booking_id="BK-KAFKA-1",
        origin_port_id="CNSHA",
        destination_port_id="USLAX",
        equipment_type="40HC",
        quantity=1,
        cargo_ready_time=start_time,
        booking_time=start_time,
        status="SUBMITTED",
        lock_status="UNLOCKED",
    )
    state.bookings["BK-KAFKA-1"] = b

    await consumer.process_incoming_message(
        topic="cargopilot.allocation-events",
        payload={
            "event_type": "ALLOCATION_COMMITTED",
            "booking_id": "BK-KAFKA-1",
            "container_id": "C001",
            "voyage_id": "VY001",
        },
    )
    assert b.status == "ALLOCATED"
    assert "AL-BK-KAFKA-1" in state.allocations

    # 2. Test incoming lease order
    eq = state.get_equipment("SGSIN", "20DC")
    prev_avail = eq.available

    await consumer.process_incoming_message(
        topic="cargopilot.decision-events",
        payload={
            "event_type": "LEASE_ORDERED",
            "lease_id": "LS-KAFKA-1",
            "location_id": "SGSIN",
            "equipment_type": "20DC",
            "quantity": 10,
            "daily_rate": 15.0,
            "duration_days": 20.0,
        },
    )
    assert "LS-KAFKA-1" in state.leases
    assert state.kpis.total_lease_cost == 3000.0  # 10 * 15 * 20
