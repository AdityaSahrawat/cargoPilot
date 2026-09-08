"""
Kafka Consumer
==============
Consumes optimization and operational decisions published by CargoPilot
and injects them into the simulation engine.

Topics consumed:
    cargopilot.allocation-events → ALLOCATION_COMMITTED
    cargopilot.decision-events   → REPOSITIONING_DISPATCHED / LEASE_ORDERED
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from app.controller.simulation_controller import SimulationController
from app.events.event_types import EventType, SimEvent

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "false").lower() in ("true", "1")


class SimulationKafkaConsumer:
    """
    Kafka consumer listening to CargoPilot decisions.
    """

    def __init__(
        self,
        controller: SimulationController,
        bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
        group_id: str = "simulation-service-group",
        enabled: bool = KAFKA_ENABLED,
    ) -> None:
        self._controller = controller
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._enabled = enabled
        self._consumer = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

        if self._enabled:
            try:
                from confluent_kafka import Consumer
                self._consumer = Consumer({
                    "bootstrap.servers": self._bootstrap_servers,
                    "group.id": self._group_id,
                    "auto.offset.reset": "latest",
                })
                self._consumer.subscribe([
                    "cargopilot.allocation-events",
                    "cargopilot.decision-events",
                ])
                logger.info("Kafka Consumer subscribed to CargoPilot topics at %s", self._bootstrap_servers)
            except Exception as ex:
                logger.warning("Failed to initialize Kafka consumer: %s. Disabling Kafka consumer.", ex)
                self._enabled = False

    async def process_incoming_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Process incoming CargoPilot decision payload and inject into simulation.
        Can be called directly for in-memory testing or by Kafka polling loop.
        """
        event_type = payload.get("event_type", "")
        sim_time = datetime.now(timezone.utc)

        state = self._controller.state
        if not state:
            logger.warning("Cannot process decision %s: simulation is not running", event_type)
            return

        if "ALLOCATION" in event_type or topic == "cargopilot.allocation-events":
            booking_id = payload.get("booking_id")
            container_id = payload.get("container_id")
            voyage_id = payload.get("voyage_id")
            if booking_id and container_id and voyage_id:
                try:
                    self._controller._allocation_model.observe_cargo_pilot_allocation(
                        booking_id=booking_id,
                        container_id=container_id,
                        voyage_id=voyage_id,
                        sim_time=sim_time,
                        state=state,
                    )
                    logger.info("Processed CargoPilot allocation: %s → %s", booking_id, container_id)
                except Exception as ex:
                    logger.error("Failed to process allocation: %s", ex)

        elif event_type == EventType.LEASE_ORDERED or "LEASE" in event_type:
            lease_id = payload.get("lease_id", f"LS-{int(sim_time.timestamp())}")
            location_id = payload.get("location_id")
            eq_type = payload.get("equipment_type")
            qty = int(payload.get("quantity", 1))
            daily_rate = float(payload.get("daily_rate", 10.0))
            duration = float(payload.get("duration_days", 30.0))
            if location_id and eq_type:
                lease, avail_at, event = self._controller._leasing_model.order_lease(
                    lease_id=lease_id,
                    location_id=location_id,
                    equipment_type=eq_type,
                    quantity=qty,
                    daily_rate=daily_rate,
                    duration_days=duration,
                    sim_time=sim_time,
                    state=state,
                )
                logger.info("Processed CargoPilot lease order: %s (%d × %s)", lease_id, qty, eq_type)

        elif event_type == EventType.REPOSITIONING_DISPATCHED or "REPOSITIONING" in event_type:
            repo_id = payload.get("reposition_id", f"RP-{int(sim_time.timestamp())}")
            src = payload.get("source_location_id")
            dest = payload.get("destination_location_id")
            eq_type = payload.get("equipment_type")
            qty = int(payload.get("quantity", 1))
            transit_days = float(payload.get("transit_days", 7.0))
            cost_per_container = float(payload.get("cost_per_container", 300.0))
            if src and dest and eq_type:
                self._controller._repositioning_model.dispatch_repositioning(
                    reposition_id=repo_id,
                    source_location_id=src,
                    destination_location_id=dest,
                    equipment_type=eq_type,
                    quantity=qty,
                    transit_days=transit_days,
                    cost_per_container=cost_per_container,
                    sim_time=sim_time,
                    state=state,
                )
                logger.info("Processed CargoPilot repositioning dispatch: %s (%s → %s)", repo_id, src, dest)

    async def start_background_task(self, poll_timeout_seconds: float = 1.0) -> None:
        """Start periodic background task to consume messages."""
        if not self._enabled or not self._consumer or self._running:
            return

        self._running = True

        async def _loop() -> None:
            while self._running:
                try:
                    msg = await asyncio.to_thread(self._consumer.poll, poll_timeout_seconds)
                    if msg is not None and not msg.error():
                        payload = json.loads(msg.value().decode("utf-8"))
                        topic = msg.topic()
                        await self.process_incoming_message(topic, payload)
                except asyncio.CancelledError:
                    break
                except Exception as ex:
                    logger.debug("Kafka consumer poll error: %s", ex)
                await asyncio.sleep(0.1)

        self._task = asyncio.create_task(_loop())
        logger.info("Kafka consumer background task started")

    async def stop(self) -> None:
        """Stop background consumer task and close consumer."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._consumer:
            self._consumer.close()
            logger.info("Kafka Consumer closed")
