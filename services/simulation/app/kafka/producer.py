"""
Simulation Kafka Producer
=========================
Publishes simulation telemetry events to Kafka topics so that
CargoPilot (services/api) can consume and react to them.

This is OUTBOUND ONLY. The simulation service does not consume from Kafka here.
Consuming CargoPilot decisions is handled by SimulationKafkaConsumer.

Topics published (consumed by services/api):
    simulation.vessel-events     → VESSEL_DEPARTED, VESSEL_ARRIVED, VESSEL_DELAYED, …
    simulation.port-events       → PORT_CONGESTION_CHANGED, BERTH_OCCUPIED, …
    simulation.container-events  → CONTAINER_GATE_IN, CONTAINER_GATE_OUT, …
    simulation.booking-events    → BOOKING_CREATED, BOOKING_CANCELLED, …
    simulation.disruption-events → STORM_STARTED, DISRUPTION_ACTIVATED, …

Publishing happens AFTER each simulation step (best-effort, fire-and-forget).
There is no outbox here; events are published directly from the step event log.

Env vars:
    KAFKA_BOOTSTRAP_SERVERS   Kafka broker address (default: localhost:19092)
    KAFKA_ENABLED             Set to "true"/"1" to enable (default: false / mock mode)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "false").lower() in ("true", "1")

# ─────────────────────────────────────────────────────────────────────────────
# Topic routing: maps keyword fragments in event_type → Kafka topic
# ─────────────────────────────────────────────────────────────────────────────
_TOPIC_RULES: list[tuple[tuple[str, ...], str]] = [
    (("VESSEL",),                               "simulation.vessel-events"),
    (("PORT", "BERTH"),                         "simulation.port-events"),
    (("CONTAINER", "EQUIPMENT"),                "simulation.container-events"),
    (("BOOKING",),                              "simulation.booking-events"),
    (("DISRUPTION", "STORM", "STRIKE"),         "simulation.disruption-events"),
    (("COST", "PENALTY", "LEASE", "REPOSITION"), "simulation.cost-events"),
    (("FORECAST", "POSITION", "STATUS"),        "simulation.forecast-events"),
]

# Internal-only event types that should NEVER be published externally
_INTERNAL_EVENTS = frozenset({
    "SIMULATION_STARTED", "SIMULATION_PAUSED", "SIMULATION_RESUMED",
    "SIMULATION_RESET", "STEP_COMPLETED", "VALIDATION_FAILED",
})


def _route_topic(event_type: str) -> Optional[str]:
    """Return the Kafka topic for an event_type, or None for internal-only events."""
    if event_type in _INTERNAL_EVENTS:
        return None
    for keywords, topic in _TOPIC_RULES:
        if any(kw in event_type for kw in keywords):
            return topic
    return None


class SimulationKafkaProducer:
    """
    Fire-and-forget Kafka producer for simulation telemetry events.

    Called at the end of each simulation step with the list of SimEvents
    produced during that step. Routes each event to the correct topic and
    publishes it so CargoPilot can consume and react.

    Operates in offline/mock mode when KAFKA_ENABLED=false.
    """

    def __init__(
        self,
        bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
        enabled: bool = KAFKA_ENABLED,
    ) -> None:
        self._enabled = enabled
        self._bootstrap_servers = bootstrap_servers
        self._producer = None

        if self._enabled:
            try:
                from confluent_kafka import Producer
                self._producer = Producer({"bootstrap.servers": self._bootstrap_servers})
                logger.info(
                    "SimulationKafkaProducer initialized at %s", self._bootstrap_servers
                )
            except Exception as ex:
                logger.warning(
                    "Failed to initialize Kafka producer: %s — running in mock mode.", ex
                )
                self._enabled = False

    # ─────────────────────────────────────────────────────────────────────────
    # Core publish
    # ─────────────────────────────────────────────────────────────────────────

    def _publish_raw(self, topic: str, key: str, payload: Dict[str, Any]) -> bool:
        """Publish one JSON message. Returns True on success / mock, False on error."""
        if not self._enabled or self._producer is None:
            logger.debug(
                "Kafka mock publish → topic=%s key=%s event=%s",
                topic, key, payload.get("event_type"),
            )
            return True

        try:
            self._producer.produce(
                topic=topic,
                key=key.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8"),
            )
            self._producer.poll(0)   # trigger delivery callbacks without blocking
            return True
        except Exception:
            logger.exception(
                "Kafka publish failed (topic=%s key=%s event=%s)",
                topic, key, payload.get("event_type"),
            )
            return False

    def flush(self, timeout: float = 5.0) -> None:
        """Block until all queued messages are delivered."""
        if self._producer:
            self._producer.flush(timeout=timeout)

    # ─────────────────────────────────────────────────────────────────────────
    # Step-level publish: called after each advance() call
    # ─────────────────────────────────────────────────────────────────────────

    def publish_step_events(self, step_events: List[Any]) -> int:
        """
        Publish all publishable events from a simulation step to Kafka.

        Args:
            step_events: List of SimEvent objects from EventBus.flush_step_log()
                         (or the list returned by controller.advance()).

        Returns:
            Number of events successfully published.
        """
        published = 0
        for event in step_events:
            event_type: str = event.event_type if hasattr(event, "event_type") else str(event)
            topic = _route_topic(event_type)
            if topic is None:
                continue   # internal event — skip

            # Build the payload using to_dict() if available, otherwise a minimal dict
            if hasattr(event, "to_dict"):
                payload = event.to_dict()
            else:
                payload = {"event_type": event_type}

            key = str(event.entity_id) if hasattr(event, "entity_id") else event_type
            if self._publish_raw(topic, key, payload):
                published += 1

        if published > 0:
            logger.debug("Published %d simulation events to Kafka", published)
        return published
