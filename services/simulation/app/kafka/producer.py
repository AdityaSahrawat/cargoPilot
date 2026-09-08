"""
Kafka Producer & Outbox Publisher
=================================
Publishes simulation events to Kafka topics using the Transactional Outbox pattern.

Architectural Rule 5:
    Transactional outbox guarantees PostgreSQL and Kafka never permanently disagree.
    Outbox rows are committed in PostgreSQL first, then published here to Kafka.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.outbox import get_pending_outbox_rows, mark_published

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_ENABLED = os.environ.get("KAFKA_ENABLED", "false").lower() in ("true", "1")


class SimulationKafkaProducer:
    """
    Kafka publisher that delivers events from simulation_outbox to Kafka brokers.
    Can operate in no-op/mock mode when KAFKA_ENABLED=false (e.g. testing/offline).
    """

    def __init__(
        self,
        bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS,
        enabled: bool = KAFKA_ENABLED,
    ) -> None:
        self._enabled = enabled
        self._bootstrap_servers = bootstrap_servers
        self._producer = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

        if self._enabled:
            try:
                from confluent_kafka import Producer
                self._producer = Producer({"bootstrap.servers": self._bootstrap_servers})
                logger.info("Kafka Producer initialized at %s", self._bootstrap_servers)
            except Exception as ex:
                logger.warning("Failed to initialize Kafka producer: %s. Disabling Kafka.", ex)
                self._enabled = False

    def publish_message(
        self,
        topic: str,
        key: str,
        value: Dict[str, Any],
    ) -> bool:
        """Publish single event payload to a Kafka topic."""
        if not self._enabled or not self._producer:
            logger.debug("Kafka mock publish to %s (key=%s): %s", topic, key, value.get("event_type"))
            return True

        try:
            payload_str = json.dumps(value)
            self._producer.produce(
                topic=topic,
                key=key.encode("utf-8"),
                value=payload_str.encode("utf-8"),
            )
            self._producer.poll(0)
            return True
        except Exception:
            logger.exception("Failed to publish to Kafka topic %s", topic)
            return False

    async def flush_outbox(
        self,
        session: AsyncSession,
        limit: int = 100,
    ) -> int:
        """
        Read unpublished rows from simulation_outbox, publish to Kafka, and mark published.
        Doc 2 §25.5
        """
        rows = await get_pending_outbox_rows(session, limit=limit)
        if not rows:
            return 0

        published_count = 0
        for row in rows:
            success = self.publish_message(
                topic=row.kafka_topic,
                key=str(row.event_id),
                value=row.payload_json,
            )
            if success:
                await mark_published(session, row.id)
                published_count += 1
            else:
                logger.warning("Outbox publish failed for row %s; retrying next cycle", row.id)
                break

        if published_count > 0:
            await session.commit()
            logger.info("Flushed %d outbox messages to Kafka", published_count)

        return published_count

    async def start_background_task(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        poll_interval_seconds: float = 2.0,
    ) -> None:
        """Start periodic background task to flush outbox."""
        if self._running:
            return

        self._running = True

        async def _loop() -> None:
            while self._running:
                try:
                    async with session_factory() as session:
                        await self.flush_outbox(session)
                except asyncio.CancelledError:
                    break
                except Exception as ex:
                    logger.debug("Outbox publisher poll error: %s", ex)
                await asyncio.sleep(poll_interval_seconds)

        self._task = asyncio.create_task(_loop())
        logger.info("Outbox publisher background task started")

    async def stop(self) -> None:
        """Stop background publisher task and flush producer buffer."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._producer:
            self._producer.flush(timeout=5)
            logger.info("Kafka Producer flushed and stopped")
