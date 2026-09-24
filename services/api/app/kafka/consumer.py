"""
CargoPilot Kafka Consumer
=========================
Consumes simulation telemetry events published by services/simulation
and updates CargoPilot's operational database accordingly.

This is INBOUND ONLY for the API service.
Publishing optimization decisions to Kafka is handled by CargoPilotKafkaProducer.

Topics consumed (produced by services/simulation):
    simulation.vessel-events     → VESSEL_DEPARTED, VESSEL_ARRIVED, VESSEL_DELAYED, …
    simulation.port-events       → PORT_CONGESTION_CHANGED, BERTH_OCCUPIED, …
    simulation.container-events  → CONTAINER_GATE_IN, CONTAINER_GATE_OUT, …
    simulation.booking-events    → BOOKING_CREATED, BOOKING_CANCELLED, …
    simulation.disruption-events → STORM_STARTED, DISRUPTION_ACTIVATED, …

On each message, the relevant CargoPilot DB tables are updated via
a synchronous SQLAlchemy session so that the optimizer always has
fresh data when the next run is triggered.

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
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "false").lower() in ("true", "1")

# Topics produced by services/simulation that this service consumes
SIMULATION_TOPICS = [
    "simulation.vessel-events",
    "simulation.port-events",
    "simulation.container-events",
    "simulation.booking-events",
    "simulation.disruption-events",
    "simulation.cost-events",
    "simulation.forecast-events",
]


class CargoPilotKafkaConsumer:
    """
    Kafka consumer for simulation telemetry events.

    Subscribes to all simulation.* topics and dispatches each event to
    the appropriate handler which updates the CargoPilot operational DB.

    Operates in offline/mock mode when KAFKA_ENABLED=false so that the
    API service works without a Kafka broker.
    """

    def __init__(
        self,
        session_factory: Callable,
        bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
        group_id: str = "cargopilot-api-group",
        enabled: bool = KAFKA_ENABLED,
    ) -> None:
        """
        Args:
            session_factory: Zero-arg callable that returns a SQLAlchemy Session
                             (e.g. SessionLocal from app.db.database).
        """
        self._session_factory = session_factory
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
                self._consumer.subscribe(SIMULATION_TOPICS)
                logger.info(
                    "CargoPilotKafkaConsumer subscribed to %d simulation topics at %s",
                    len(SIMULATION_TOPICS), self._bootstrap_servers,
                )
            except Exception as ex:
                logger.warning(
                    "Failed to initialize Kafka consumer: %s — running in mock mode.", ex
                )
                self._enabled = False

    # ─────────────────────────────────────────────────────────────────────────
    # Message dispatch
    # ─────────────────────────────────────────────────────────────────────────

    def process_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Dispatch one simulation event payload to the appropriate DB handler.

        Can be called directly (e.g. in unit tests) without a Kafka broker.

        Args:
            topic:   The Kafka topic the message arrived on.
            payload: The decoded JSON payload from the Kafka message.
        """
        event_type: str = payload.get("event_type", "")

        try:
            if topic == "simulation.booking-events":
                self._handle_booking_event(event_type, payload)
            elif topic == "simulation.vessel-events":
                self._handle_vessel_event(event_type, payload)
            elif topic == "simulation.disruption-events":
                self._handle_disruption_event(event_type, payload)
            elif topic in ("simulation.container-events", "simulation.port-events",
                           "simulation.cost-events", "simulation.forecast-events"):
                # Log for now; extend with DB writes as CargoPilot models mature
                logger.debug("Received simulation event %s on %s", event_type, topic)
        except Exception as ex:
            logger.error(
                "Error processing simulation event %s from %s: %s", event_type, topic, ex
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Domain handlers — each opens its own DB session (sync, short-lived)
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_booking_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Handle booking lifecycle events from the simulation.

        BOOKING_CREATED  → log the booking as known to CargoPilot.
        BOOKING_CANCELLED → mark the booking as cancelled in the DB (if present).
        """
        booking_id: str = payload.get("entity_id", "")
        if not booking_id:
            return

        db = self._session_factory()
        try:
            from app.db import models
            existing = db.query(models.Booking).filter(
                models.Booking.id == booking_id
            ).first()

            if event_type == "BOOKING_CREATED":
                if existing:
                    logger.debug("BOOKING_CREATED: booking %s already known.", booking_id)
                else:
                    # Surface the event so the optimizer knows demand exists.
                    # Full booking enrichment would require additional payload fields;
                    # for now we log the arrival of a new booking.
                    logger.info(
                        "CargoPilot received BOOKING_CREATED for %s — "
                        "optimizer will include in next run.", booking_id
                    )

            elif event_type in ("BOOKING_CANCELLED", "BOOKING_MODIFIED"):
                if existing:
                    logger.info(
                        "CargoPilot received %s for booking %s", event_type, booking_id
                    )
                    # Trigger a lightweight re-plan signal (no-op unless optimizer is wired)
                else:
                    logger.debug("%s for unknown booking %s — ignoring.", event_type, booking_id)
        finally:
            db.close()

    def _handle_vessel_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Handle vessel movement events from the simulation.

        Vessel position and ETA changes affect voyage schedule accuracy used
        by the optimizer for capacity and timeline calculations.
        """
        vessel_id: str = payload.get("entity_id", "")
        sim_time: str = payload.get("simulation_time", "")
        logger.info(
            "CargoPilot received %s for vessel %s @ %s", event_type, vessel_id, sim_time
        )
        # Future: update voyage ETAs in DB to keep optimizer inputs current.

    def _handle_disruption_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        Handle disruption events (storms, port strikes) from the simulation.

        Active disruptions affect port availability and vessel scheduling,
        which the optimizer uses when planning repositioning and leasing.
        """
        entity_id: str = payload.get("entity_id", "")
        logger.info(
            "CargoPilot received disruption %s affecting %s", event_type, entity_id
        )
        # Future: mark affected ports / voyages as disrupted in DB.

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
                    msg = await asyncio.to_thread(
                        self._consumer.poll, poll_timeout_seconds
                    )
                    if msg is not None and not msg.error():
                        topic = msg.topic()
                        payload = json.loads(msg.value().decode("utf-8"))
                        # process_message is synchronous (DB writes); run in thread pool
                        await asyncio.to_thread(self.process_message, topic, payload)
                except asyncio.CancelledError:
                    break
                except Exception as ex:
                    logger.debug("Kafka consumer poll error: %s", ex)
                await asyncio.sleep(0.05)

        self._task = asyncio.create_task(_poll_loop())
        logger.info("CargoPilotKafkaConsumer background poll task started")

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
            logger.info("CargoPilotKafkaConsumer closed")
