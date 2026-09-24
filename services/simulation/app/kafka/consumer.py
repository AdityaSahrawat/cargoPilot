"""
Simulation Kafka Consumer
=========================
Listens to CargoPilot optimization decisions published by services/api
and injects them into the running simulation engine world state.

This is INBOUND ONLY. The simulation service does not produce to Kafka.
Publishing optimization decisions to Kafka is the responsibility of services/api.

Topics consumed:
    cargopilot.allocation-events  → ALLOCATION_COMMITTED
    cargopilot.decision-events    → REPOSITIONING_DISPATCHED, LEASE_ORDERED

Env vars:
    KAFKA_BOOTSTRAP_SERVERS   Kafka broker address (default: localhost:19092)
    KAFKA_ENABLED             Set to "true"/"1" to enable (default: false / mock mode)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.controller.simulation_controller import SimulationController
from app.events.event_types import EventType

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "false").lower() in ("true", "1")

# Topics produced by services/api that this service consumes
TOPIC_ALLOCATION = "cargopilot.allocation-events"
TOPIC_DECISIONS = "cargopilot.decision-events"


class SimulationKafkaConsumer:
    """
    Kafka consumer for CargoPilot decision events.

    Listens to:
        cargopilot.allocation-events   — allocation committed by the optimizer
        cargopilot.decision-events     — repositioning dispatched / lease ordered

    On each message it calls the appropriate domain model method on the
    SimulationController, updating the in-memory WorldState.

    Operates in offline/mock mode when KAFKA_ENABLED=false so unit tests
    and local development without Docker are unaffected.
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
                    "enable.auto.commit": True,
                })
                self._consumer.subscribe([TOPIC_ALLOCATION, TOPIC_DECISIONS])
                logger.info(
                    "SimulationKafkaConsumer subscribed to [%s, %s] at %s",
                    TOPIC_ALLOCATION, TOPIC_DECISIONS, self._bootstrap_servers,
                )
            except Exception as ex:
                logger.warning(
                    "Failed to initialize Kafka consumer: %s — running in mock mode.", ex
                )
                self._enabled = False

    # ─────────────────────────────────────────────────────────────────────────
    # Message processing
    # ─────────────────────────────────────────────────────────────────────────

    async def process_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Dispatch an incoming CargoPilot decision payload into the simulation.

        Can be called directly (e.g. in tests) without a running Kafka broker.

        Args:
            topic:   The Kafka topic the message arrived on.
            payload: The decoded JSON payload from the Kafka message.
        """
        event_type = payload.get("event_type", "")
        sim_time = datetime.now(timezone.utc)

        state = self._controller.state
        if state is None:
            logger.warning(
                "Dropping incoming decision %s — simulation is not running.", event_type
            )
            return

        # ── ALLOCATION_COMMITTED ──────────────────────────────────────────────
        if topic == TOPIC_ALLOCATION or "ALLOCATION" in event_type:
            booking_id = payload.get("booking_id")
            container_id = payload.get("container_id")
            voyage_id = payload.get("voyage_id")

            if not (booking_id and container_id and voyage_id):
                logger.warning("ALLOCATION_COMMITTED missing required fields: %s", payload)
                return

            try:
                self._controller._allocation_model.observe_cargo_pilot_allocation(
                    booking_id=booking_id,
                    container_id=container_id,
                    voyage_id=voyage_id,
                    sim_time=sim_time,
                    state=state,
                )
                logger.info(
                    "Injected allocation: booking=%s → container=%s voyage=%s",
                    booking_id, container_id, voyage_id,
                )
            except Exception as ex:
                logger.error("Failed to apply ALLOCATION_COMMITTED: %s", ex)

        # ── LEASE_ORDERED ─────────────────────────────────────────────────────
        elif event_type == EventType.LEASE_ORDERED or "LEASE" in event_type:
            lease_id = payload.get("lease_id", f"LS-{int(sim_time.timestamp())}")
            location_id = payload.get("location_id")
            eq_type = payload.get("equipment_type")
            qty = int(payload.get("quantity", 1))
            daily_rate = float(payload.get("daily_rate", 10.0))
            duration = float(payload.get("duration_days", 30.0))

            if not (location_id and eq_type):
                logger.warning("LEASE_ORDERED missing required fields: %s", payload)
                return

            try:
                self._controller._leasing_model.order_lease(
                    lease_id=lease_id,
                    location_id=location_id,
                    equipment_type=eq_type,
                    quantity=qty,
                    daily_rate=daily_rate,
                    duration_days=duration,
                    sim_time=sim_time,
                    state=state,
                )
                logger.info(
                    "Injected lease order: id=%s location=%s qty=%d × %s",
                    lease_id, location_id, qty, eq_type,
                )
            except Exception as ex:
                logger.error("Failed to apply LEASE_ORDERED: %s", ex)

        # ── REPOSITIONING_DISPATCHED ──────────────────────────────────────────
        elif event_type == EventType.REPOSITIONING_DISPATCHED or "REPOSITIONING" in event_type:
            repo_id = payload.get("reposition_id", f"RP-{int(sim_time.timestamp())}")
            src = payload.get("source_location_id")
            dest = payload.get("destination_location_id")
            eq_type = payload.get("equipment_type")
            qty = int(payload.get("quantity", 1))
            transit_days = float(payload.get("transit_days", 7.0))
            cost_per_container = float(payload.get("cost_per_container", 300.0))

            if not (src and dest and eq_type):
                logger.warning("REPOSITIONING_DISPATCHED missing required fields: %s", payload)
                return

            try:
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
                logger.info(
                    "Injected repositioning: id=%s %s → %s qty=%d",
                    repo_id, src, dest, qty,
                )
            except Exception as ex:
                logger.error("Failed to apply REPOSITIONING_DISPATCHED: %s", ex)

        else:
            logger.debug("Unhandled event_type=%s on topic=%s — ignoring.", event_type, topic)

    # ─────────────────────────────────────────────────────────────────────────
    # Background poll loop
    # ─────────────────────────────────────────────────────────────────────────

    async def start(self, poll_timeout_seconds: float = 1.0) -> None:
        """
        Start the background Kafka polling task.

        No-op if KAFKA_ENABLED=false or already running.
        """
        if not self._enabled or self._consumer is None or self._running:
            return

        self._running = True

        async def _poll_loop() -> None:
            while self._running:
                try:
                    # poll() is blocking — run in a thread pool to avoid blocking the event loop
                    msg = await asyncio.to_thread(self._consumer.poll, poll_timeout_seconds)
                    if msg is not None and not msg.error():
                        topic = msg.topic()
                        payload = json.loads(msg.value().decode("utf-8"))
                        await self.process_message(topic, payload)
                except asyncio.CancelledError:
                    break
                except Exception as ex:
                    logger.debug("Kafka poll error: %s", ex)
                await asyncio.sleep(0.05)  # yield back to event loop between polls

        self._task = asyncio.create_task(_poll_loop())
        logger.info("SimulationKafkaConsumer background poll task started")

    async def stop(self) -> None:
        """Stop the background polling task and close the Kafka consumer."""
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
            logger.info("SimulationKafkaConsumer closed")
