"""
CargoPilot Kafka Producer
=========================
Publishes CargoPilot optimization decisions to Kafka topics consumed
by the Simulation Engine.

Topics published:
    cargopilot.allocation-events  → ALLOCATION_COMMITTED
    cargopilot.decision-events    → REPOSITIONING_DISPATCHED, LEASE_ORDERED

The simulation engine's SimulationKafkaConsumer subscribes to exactly
these topics and injects decisions into the running simulation world state.

Env vars:
    KAFKA_BOOTSTRAP_SERVERS   Kafka broker address (default: localhost:19092)
    KAFKA_ENABLED             Set to "true"/"1" to enable real publishing (default: false)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "false").lower() in ("true", "1")

# ─────────────────────────────────────────────────────────────────────────────
# Topic constants (mirror what simulation/app/events/event_types.py expects)
# ─────────────────────────────────────────────────────────────────────────────
TOPIC_ALLOCATION = "cargopilot.allocation-events"
TOPIC_DECISIONS = "cargopilot.decision-events"


class CargoPilotKafkaProducer:
    """
    Synchronous Kafka producer for CargoPilot decision events.

    Operates in offline/mock mode when KAFKA_ENABLED=false so that the
    API service continues to function without a running Kafka broker
    (e.g. during unit tests or local development without Docker).
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
                    "CargoPilot Kafka Producer initialized at %s", self._bootstrap_servers
                )
            except Exception as ex:
                logger.warning(
                    "Failed to initialize Kafka producer: %s — running in mock mode.", ex
                )
                self._enabled = False

    # ─────────────────────────────────────────────────────────────────────────
    # Low-level publish
    # ─────────────────────────────────────────────────────────────────────────

    def _publish(self, topic: str, key: str, payload: Dict[str, Any]) -> bool:
        """Publish one JSON payload to a Kafka topic."""
        if not self._enabled or self._producer is None:
            logger.debug(
                "Kafka mock publish → topic=%s key=%s event_type=%s",
                topic, key, payload.get("event_type"),
            )
            return True

        try:
            self._producer.produce(
                topic=topic,
                key=key.encode("utf-8"),
                value=json.dumps(payload).encode("utf-8"),
            )
            self._producer.poll(0)  # trigger delivery callbacks without blocking
            return True
        except Exception:
            logger.exception("Kafka publish failed (topic=%s key=%s)", topic, key)
            return False

    def flush(self, timeout: float = 5.0) -> None:
        """Block until all queued messages are delivered (call at end of request if needed)."""
        if self._producer:
            self._producer.flush(timeout=timeout)

    # ─────────────────────────────────────────────────────────────────────────
    # High-level decision publishers
    # ─────────────────────────────────────────────────────────────────────────

    def publish_allocation(
        self,
        run_id: str,
        booking_id: str,
        container_id: str,
        voyage_id: str,
    ) -> bool:
        """
        Publish an ALLOCATION_COMMITTED event to `cargopilot.allocation-events`.

        The simulation consumer uses this to call:
            allocation_model.observe_cargo_pilot_allocation(...)
        """
        payload: Dict[str, Any] = {
            "event_type": "ALLOCATION_COMMITTED",
            "run_id": run_id,
            "booking_id": booking_id,
            "container_id": container_id,
            "voyage_id": voyage_id,
        }
        ok = self._publish(TOPIC_ALLOCATION, booking_id, payload)
        if ok:
            logger.info(
                "Published ALLOCATION_COMMITTED booking=%s container=%s voyage=%s",
                booking_id, container_id, voyage_id,
            )
        return ok

    def publish_repositioning(
        self,
        run_id: str,
        reposition_id: str,
        source_location_id: str,
        destination_location_id: str,
        equipment_type: str,
        quantity: int,
        transit_days: float = 7.0,
        cost_per_container: float = 300.0,
    ) -> bool:
        """
        Publish a REPOSITIONING_DISPATCHED event to `cargopilot.decision-events`.

        The simulation consumer uses this to call:
            repositioning_model.dispatch_repositioning(...)
        """
        payload: Dict[str, Any] = {
            "event_type": "REPOSITIONING_DISPATCHED",
            "run_id": run_id,
            "reposition_id": reposition_id,
            "source_location_id": source_location_id,
            "destination_location_id": destination_location_id,
            "equipment_type": equipment_type,
            "quantity": quantity,
            "transit_days": transit_days,
            "cost_per_container": cost_per_container,
        }
        ok = self._publish(TOPIC_DECISIONS, reposition_id, payload)
        if ok:
            logger.info(
                "Published REPOSITIONING_DISPATCHED id=%s %s → %s qty=%d",
                reposition_id, source_location_id, destination_location_id, quantity,
            )
        return ok

    def publish_lease(
        self,
        run_id: str,
        lease_id: str,
        location_id: str,
        equipment_type: str,
        quantity: int,
        daily_rate: float = 10.0,
        duration_days: float = 30.0,
    ) -> bool:
        """
        Publish a LEASE_ORDERED event to `cargopilot.decision-events`.

        The simulation consumer uses this to call:
            leasing_model.order_lease(...)
        """
        payload: Dict[str, Any] = {
            "event_type": "LEASE_ORDERED",
            "run_id": run_id,
            "lease_id": lease_id,
            "location_id": location_id,
            "equipment_type": equipment_type,
            "quantity": quantity,
            "daily_rate": daily_rate,
            "duration_days": duration_days,
        }
        ok = self._publish(TOPIC_DECISIONS, lease_id, payload)
        if ok:
            logger.info(
                "Published LEASE_ORDERED id=%s location=%s qty=%d × %s",
                lease_id, location_id, quantity, equipment_type,
            )
        return ok


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton (lazy, safe to import without a running broker)
# ─────────────────────────────────────────────────────────────────────────────
_producer_instance: CargoPilotKafkaProducer | None = None


def get_producer() -> CargoPilotKafkaProducer:
    """Return the shared producer instance, creating it on first call."""
    global _producer_instance
    if _producer_instance is None:
        _producer_instance = CargoPilotKafkaProducer()
    return _producer_instance
