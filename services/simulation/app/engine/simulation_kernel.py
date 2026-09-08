"""
Simulation Kernel
==================
SimPy-based discrete event execution engine.

This is the core of the simulation. The kernel:
    1. Loads WorldState from PostgreSQL
    2. Processes all scheduled events in [T_current, T_target] (chronological)
    3. Applies 10-level priority for same-time events
    4. Runs local validation after each event
    5. Runs full advancement validation after the step completes
    6. Persists WorldState changes to PostgreSQL via outbox pattern
    7. Publishes events to Kafka through the outbox

Doc 2 §29.5 — Execution Principle:
    Load Current State
          ↓
    Identify Relevant Events
          ↓
    Execute Chronological Event
          ↓
    Update State
          ↓
    Generate Consequences → Schedule Dependent Events
          ↓
    Continue Until T_target
          ↓
    Validate
          ↓
    Persist + Publish

Key rule: Does NOT run every model every simulated hour.
Events are scheduled and fired only when due.

Doc 2 §2.5 — Same-time event priority (10 levels).
See event_types.py EventPriority enum.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import UUID

import simpy

from app.clock.simulation_clock import SimulationClock
from app.config.parameters import ParameterRegistry
from app.events.event_types import SimEvent, EventPriority
from app.events.event_bus import EventBus
from app.world.world_state import WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scheduled event wrapper for SimPy priority queue
# ---------------------------------------------------------------------------

@dataclass(order=True)
class ScheduledEvent:
    """
    Wrapper that gives SimPy events a deterministic processing order.

    SimPy processes events at the same time in FIFO order by default.
    We override this using a (simpy_time, priority, sequence) tuple.

    Doc 2 §2.5: same-time events follow the 10-level priority order.
    """
    simpy_time: float            # hours since simulation start
    priority: int                # EventPriority value (lower = first)
    sequence: int                # tie-breaker: insertion order
    sim_event: SimEvent = field(compare=False)
    handler: Optional[Callable[[SimEvent, WorldState], None]] = field(compare=False, default=None)

    @classmethod
    def from_sim_event(
        cls,
        event: SimEvent,
        simpy_time: float,
        sequence: int,
        handler: Optional[Callable] = None,
    ) -> "ScheduledEvent":
        return cls(
            simpy_time=simpy_time,
            priority=event.priority.value,
            sequence=sequence,
            sim_event=event,
            handler=handler,
        )


# ---------------------------------------------------------------------------
# Simulation Kernel
# ---------------------------------------------------------------------------

class SimulationKernel:
    """
    SimPy-based discrete event execution engine.

    Manages the SimPy environment, event scheduling queue, and the
    full advancement lifecycle per step.

    Usage::

        kernel = SimulationKernel(clock, registry, event_bus)
        kernel.initialize(world_state)

        # Advance 24 simulation hours
        changed_state, events = await kernel.advance(world_state, delta_hours=24.0)
    """

    def __init__(
        self,
        clock: SimulationClock,
        registry: ParameterRegistry,
        event_bus: EventBus,
    ) -> None:
        self._clock = clock
        self._registry = registry
        self._bus = event_bus

        # SimPy environment — runs in abstract numeric time (hours since start)
        self._env: simpy.Environment = simpy.Environment(
            initial_time=clock.to_simpy_time()
        )

        # Priority queue of scheduled events
        self._event_queue: List[ScheduledEvent] = []
        self._sequence_counter: int = 0

        # Registered model handlers: event_type → callable
        self._model_handlers: Dict[str, Callable[[SimEvent, WorldState], None]] = {}

        # Validation functions registered by world/validator.py
        self._local_validators: List[Callable[[SimEvent, WorldState], None]] = []
        self._advancement_validators: List[Callable[[WorldState], None]] = []

        logger.info("SimulationKernel initialized at T_sim=%s", clock.now.isoformat())

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def register_handler(
        self,
        event_type: str,
        handler: Callable[[SimEvent, WorldState], None],
    ) -> None:
        """
        Register a domain model handler for an event type.

        The handler signature is:
            handler(event: SimEvent, state: WorldState) -> None

        The handler mutates WorldState in-place and may call
        kernel.schedule() to enqueue consequence events.

        Args:
            event_type: EventType constant (e.g. EventType.VESSEL_ARRIVED).
            handler: Callable(SimEvent, WorldState) → None.
        """
        self._model_handlers[event_type] = handler
        logger.debug("Registered handler for event type: %s", event_type)

    def register_local_validator(
        self, validator: Callable[[SimEvent, WorldState], None]
    ) -> None:
        """Register a function called after each event to validate affected state."""
        self._local_validators.append(validator)

    def register_advancement_validator(
        self, validator: Callable[[WorldState], None]
    ) -> None:
        """Register a function called once at the end of each advancement step."""
        self._advancement_validators.append(validator)

    # ------------------------------------------------------------------
    # Event scheduling
    # ------------------------------------------------------------------

    def schedule(
        self,
        event: SimEvent,
        at_simpy_time: float,
        handler: Optional[Callable[[SimEvent, WorldState], None]] = None,
    ) -> None:
        """
        Schedule an event to be processed at a specific SimPy time.

        This is the ONLY way events enter the processing queue.
        No direct world state mutations are allowed outside model handlers.

        Args:
            event: The SimEvent to schedule.
            at_simpy_time: SimPy time (hours since start) when event fires.
            handler: Optional handler override. If None, uses registered handler.
        """
        scheduled = ScheduledEvent.from_sim_event(
            event=event,
            simpy_time=at_simpy_time,
            sequence=self._sequence_counter,
            handler=handler or self._model_handlers.get(event.event_type),
        )
        self._sequence_counter += 1

        # Insert in sorted position (by simpy_time, priority, sequence)
        import bisect
        bisect.insort(self._event_queue, scheduled)

        logger.debug(
            "SCHEDULED %s at T+%.1fh (priority=%d seq=%d)",
            event.event_type,
            at_simpy_time,
            scheduled.priority,
            scheduled.sequence,
        )

    def schedule_now(
        self,
        event: SimEvent,
        state: WorldState,
        handler: Optional[Callable] = None,
    ) -> None:
        """Schedule an event at the current SimPy time (immediate)."""
        self.schedule(event, at_simpy_time=self._env.now, handler=handler)

    # ------------------------------------------------------------------
    # Core advancement
    # ------------------------------------------------------------------

    def advance(
        self,
        state: WorldState,
        delta_hours: float,
    ) -> Tuple[WorldState, List[SimEvent]]:
        """
        Advance the simulation by delta_hours.

        Doc 2 §2.2: 0 < delta_hours ≤ 24h

        Execution cycle:
            1. Validate delta
            2. Compute T_target
            3. Process all events in [T_current, T_target] in priority order
            4. Run advancement validation
            5. Flush event log
            6. Advance clock

        Args:
            state: Current WorldState (in-process cache).
            delta_hours: Time advancement in hours (0 < Δt ≤ 24).

        Returns:
            Tuple of (updated WorldState, list of all events emitted this step).
        """
        if delta_hours <= 0 or delta_hours > 24.0:
            raise ValueError(
                f"delta_hours must satisfy 0 < Δt ≤ 24h (Doc 2 §2.2). Got: {delta_hours}"
            )

        t_current_simpy = self._env.now
        t_target_simpy = t_current_simpy + delta_hours

        logger.info(
            "ADVANCE: T_sim=%s → T+%.1fh (SimPy: %.1f → %.1f)",
            self._clock.now.isoformat(),
            delta_hours,
            t_current_simpy,
            t_target_simpy,
        )

        # Process all events scheduled within [t_current, t_target]
        events_processed = 0
        while self._event_queue:
            next_scheduled = self._event_queue[0]

            if next_scheduled.simpy_time > t_target_simpy:
                break  # All remaining events are beyond T_target — stop

            # Pop the earliest-priority event
            self._event_queue.pop(0)

            # Set SimPy env time to event time
            # (We're using SimPy in a non-generator mode — controlling time explicitly)
            self._env._now = next_scheduled.simpy_time  # type: ignore[attr-defined]

            self._process_single_event(next_scheduled, state)
            events_processed += 1

        # Advance SimPy clock to T_target
        self._env._now = t_target_simpy  # type: ignore[attr-defined]

        # Advance virtual clock
        self._clock.advance(delta_hours)
        state.simulation_time = self._clock.now

        logger.info(
            "ADVANCE complete: %d events processed. T_sim now %s",
            events_processed,
            self._clock.now.isoformat(),
        )

        # Run full advancement validation (Level 2)
        self._run_advancement_validation(state)

        # Flush event log from bus
        step_events = self._bus.flush_step_log()
        state.step_events = step_events

        return state, step_events

    # ------------------------------------------------------------------
    # Internal event processing
    # ------------------------------------------------------------------

    def _process_single_event(
        self,
        scheduled: ScheduledEvent,
        state: WorldState,
    ) -> None:
        """
        Process one event:
            1. Call model handler (updates WorldState, schedules consequence events)
            2. Emit through event bus (calls bus subscribers)
            3. Run local validation (Level 1)
        """
        event = scheduled.sim_event

        logger.debug(
            "PROCESS %s | entity=%s | id=%s | T+%.2fh",
            event.event_type,
            event.entity_type,
            event.entity_id,
            scheduled.simpy_time,
        )

        # 1. Model handler
        if scheduled.handler:
            try:
                scheduled.handler(event, state)
            except Exception:
                logger.exception(
                    "Model handler failed for event %s (entity=%s id=%s)",
                    event.event_type, event.entity_type, event.entity_id,
                )
                raise

        # 2. Event bus (secondary subscribers, event logging)
        self._bus.emit(event)

        # 3. Local validation (Level 1 — after each event)
        self._run_local_validation(event, state)

    def _run_local_validation(self, event: SimEvent, state: WorldState) -> None:
        """Run all registered local validators after a single event."""
        for validator in self._local_validators:
            try:
                validator(event, state)
            except Exception:
                logger.exception(
                    "Local validation failed after event %s", event.event_type
                )
                raise

    def _run_advancement_validation(self, state: WorldState) -> None:
        """
        Run all registered advancement validators at end of step.
        Level 2 validation (Doc 2 §27.7).
        """
        for validator in self._advancement_validators:
            try:
                validator(state)
            except Exception:
                logger.exception("Advancement validation failed")
                raise

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self, start_time: datetime) -> None:
        """
        Reset the kernel for a new simulation run.
        Clears the event queue, resets SimPy environment, resets clock.
        """
        self._env = simpy.Environment(initial_time=0.0)
        self._event_queue.clear()
        self._sequence_counter = 0
        self._clock.reset(start_time)
        logger.info("SimulationKernel reset. T_sim=%s", start_time.isoformat())

    @property
    def current_simpy_time(self) -> float:
        """Current SimPy time (hours since start)."""
        return self._env.now

    @property
    def pending_event_count(self) -> int:
        """Number of events in the queue waiting to be processed."""
        return len(self._event_queue)

    def peek_next_event_time(self) -> Optional[float]:
        """Return the SimPy time of the next scheduled event, or None if empty."""
        if not self._event_queue:
            return None
        return self._event_queue[0].simpy_time
