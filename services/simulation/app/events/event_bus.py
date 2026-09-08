"""
Event Bus
==========
In-process event routing. All state changes go through here.

Rule 4 (Architectural Rules):
    No direct world state mutation outside the event system.
    inject_disruption() creates an event → event queue → model handler → world state.

Flow:
    SimEvent created by model
          ↓
    EventBus.emit(event)
          ↓
    Registered handlers called (synchronous, in-process)
          ↓
    Event appended to step event log
          ↓
    (After step) Persistence layer writes to DB + outbox
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Dict, List

from app.events.event_types import SimEvent

logger = logging.getLogger(__name__)

# Handler type: a callable that takes a SimEvent and returns None
EventHandler = Callable[[SimEvent], None]


class EventBus:
    """
    In-process synchronous event bus.

    Handlers are registered per event type. When an event is emitted,
    all handlers for that type are called in registration order.

    The bus does NOT call Kafka or write to DB.
    That happens in the kernel's persistence step (after the full step completes).
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: List[EventHandler] = []
        self._event_log: List[SimEvent] = []
        """Accumulates all events emitted during the current advancement step."""

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        Register a handler for a specific event type.

        Args:
            event_type: EventType constant (e.g. EventType.VESSEL_ARRIVED).
            handler: Callable(SimEvent) → None.
        """
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed handler %s to event type %s", handler.__name__, event_type)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Register a handler that receives ALL events (wildcard)."""
        self._wildcard_handlers.append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove a specific handler for an event type."""
        self._handlers[event_type] = [
            h for h in self._handlers[event_type] if h is not handler
        ]

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def emit(self, event: SimEvent) -> None:
        """
        Emit an event through the bus.

        Calls all registered handlers for the event type, then wildcard handlers.
        Appends the event to the current step's event log.

        This is synchronous — handlers run in the same thread before returning.

        Args:
            event: The SimEvent to emit.
        """
        logger.debug(
            "EVENT %s entity=%s id=%s sim_time=%s",
            event.event_type,
            event.entity_type,
            event.entity_id,
            event.simulation_time.isoformat(),
        )

        # Call type-specific handlers
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Handler %s failed for event %s (entity=%s id=%s)",
                    handler.__name__,
                    event.event_type,
                    event.entity_type,
                    event.entity_id,
                )
                raise

        # Call wildcard handlers
        for handler in self._wildcard_handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Wildcard handler %s failed for event %s",
                    handler.__name__,
                    event.event_type,
                )
                raise

        # Append to step log
        self._event_log.append(event)

    # ------------------------------------------------------------------
    # Step lifecycle
    # ------------------------------------------------------------------

    def flush_step_log(self) -> List[SimEvent]:
        """
        Return all events emitted in the current step and clear the log.

        Called by the kernel at the end of each advancement step,
        before writing events to the DB + outbox.
        """
        events = list(self._event_log)
        self._event_log.clear()
        return events

    def clear_all_handlers(self) -> None:
        """Clear all registered handlers. Used during simulation reset."""
        self._handlers.clear()
        self._wildcard_handlers.clear()
        self._event_log.clear()

    @property
    def pending_event_count(self) -> int:
        """Number of events in the current step's log not yet flushed."""
        return len(self._event_log)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the module-level singleton event bus."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def reset_event_bus() -> EventBus:
    """Reset the event bus. Called during simulation reset."""
    global _bus
    _bus = EventBus()
    return _bus
