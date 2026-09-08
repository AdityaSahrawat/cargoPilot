"""
Transactional Outbox
====================
Implements the outbox pattern for reliable Kafka publication.

Pattern (Rule 5 of architectural rules):

    Simulation Event
          ↓
    DB Transaction:
      ┌──────────────────────────────────┐
      │ 1. State change (e.g. vessel     │
      │    position update)              │
      │ 2. INSERT into simulation_outbox │
      └──────────────────────────────────┘
          ↓
    PostgreSQL COMMIT
          ↓
    Background publisher reads outbox
          ↓
    Kafka publish
          ↓
    Mark outbox row as published

If Kafka publish fails after DB commit, the row remains pending and
retries on the next publish cycle. PostgreSQL and Kafka never permanently
disagree because the outbox is committed atomically with the state change.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.sim_models import SimulationOutbox

logger = logging.getLogger(__name__)


async def write_outbox(
    session: AsyncSession,
    run_id: UUID,
    event_id: UUID,
    kafka_topic: str,
    payload: Dict[str, Any],
) -> SimulationOutbox:
    """
    Write one outbox row inside the current database transaction.

    This MUST be called within the same transaction as the state change.
    Do not commit before calling this function.

    Args:
        session: Active SQLAlchemy async session (transaction in progress).
        run_id: Current simulation run ID.
        event_id: The simulation_events.event_id this outbox row relates to.
        kafka_topic: Kafka topic to publish to.
        payload: JSON-serializable event payload.

    Returns:
        The newly created (unflushed) outbox row.
    """
    row = SimulationOutbox(
        run_id=run_id,
        event_id=event_id,
        kafka_topic=kafka_topic,
        payload_json=payload,
    )
    session.add(row)
    # Not flushed yet — caller commits the transaction.
    return row


async def get_pending_outbox_rows(
    session: AsyncSession,
    limit: int = 100,
) -> list[SimulationOutbox]:
    """
    Retrieve unpublished outbox rows ordered by creation time.

    Called by the background publisher task after each DB commit.
    """
    result = await session.execute(
        select(SimulationOutbox)
        .where(SimulationOutbox.published_at.is_(None))
        .order_by(SimulationOutbox.created_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_published(
    session: AsyncSession,
    outbox_id: UUID,
) -> None:
    """
    Mark an outbox row as successfully published to Kafka.
    Called by the publisher after a successful Kafka send.
    """
    await session.execute(
        update(SimulationOutbox)
        .where(SimulationOutbox.id == outbox_id)
        .values(published_at=datetime.now(tz=timezone.utc))
    )


async def increment_retry(
    session: AsyncSession,
    outbox_id: UUID,
) -> None:
    """
    Increment retry counter for a failed outbox row.
    Publisher calls this after a Kafka publish failure.
    """
    result = await session.execute(
        select(SimulationOutbox).where(SimulationOutbox.id == outbox_id)
    )
    row = result.scalar_one_or_none()
    if row:
        row.retry_count += 1
