"""
Simulation Clock
================
Maintains the one authoritative virtual clock T_sim.

Doc 2 §2.1:
    The simulator maintains one authoritative virtual clock: T_sim.
    Simulation time is independent of real-world execution time.

Doc 2 §2.2:
    T_target = T_current + Δt,  where 0 < Δt ≤ 24h

Rules:
    - Never call datetime.utcnow() or datetime.now() here.
    - All simulation time comes from this clock.
    - The clock is set by the SimulationController at run start.
    - reset() always goes back to the configured start time.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


class SimulationClock:
    """
    Authoritative virtual clock T_sim.

    Usage::

        clock = SimulationClock(start_time=datetime(2026, 9, 1, tzinfo=timezone.utc))
        clock.advance(24.0)          # advance 1 day
        print(clock.now)             # 2026-09-02 00:00:00+00:00

    Constraints:
        - 0 < delta_hours ≤ 24 (Doc 2 §2.2)
        - Clock is monotonically increasing — cannot go backwards except via reset().
    """

    MAX_DELTA_HOURS: float = 24.0
    """Hard upper bound on a single advancement step. Doc 2 §2.2."""

    def __init__(self, start_time: datetime) -> None:
        """
        Args:
            start_time: The virtual clock start. Must be timezone-aware (UTC).
        """
        if start_time.tzinfo is None:
            raise ValueError("SimulationClock start_time must be timezone-aware (UTC).")
        self._start_time: datetime = start_time
        self._current_time: datetime = start_time

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def now(self) -> datetime:
        """Current simulation time T_sim."""
        return self._current_time

    @property
    def start_time(self) -> datetime:
        """Configured simulation start time."""
        return self._start_time

    @property
    def elapsed_hours(self) -> float:
        """Total simulation hours elapsed since start."""
        delta = self._current_time - self._start_time
        return delta.total_seconds() / 3600.0

    @property
    def elapsed_days(self) -> float:
        """Total simulation days elapsed since start."""
        return self.elapsed_hours / 24.0

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def advance(self, delta_hours: float) -> datetime:
        """
        Advance T_sim by delta_hours.

        Doc 2 §2.2: T_target = T_current + Δt, where 0 < Δt ≤ 24h.

        Args:
            delta_hours: Positive time delta. Must satisfy 0 < delta_hours ≤ 24.

        Returns:
            New T_sim after advancement.

        Raises:
            ValueError: If delta_hours violates the constraint.
        """
        if delta_hours <= 0:
            raise ValueError(
                f"delta_hours must be positive. Got: {delta_hours}"
            )
        if delta_hours > self.MAX_DELTA_HOURS:
            raise ValueError(
                f"delta_hours must be ≤ {self.MAX_DELTA_HOURS}h (Doc 2 §2.2). "
                f"Got: {delta_hours}h. Use repeated advancements for longer periods."
            )
        self._current_time = self._current_time + timedelta(hours=delta_hours)
        return self._current_time

    def reset(self, start_time: datetime | None = None) -> None:
        """
        Reset the clock to start_time (or the original configured start time).

        Args:
            start_time: Optional new start time. If None, uses original start_time.
        """
        if start_time is not None:
            if start_time.tzinfo is None:
                raise ValueError("start_time must be timezone-aware (UTC).")
            self._start_time = start_time
        self._current_time = self._start_time

    def target_time(self, delta_hours: float) -> datetime:
        """
        Compute T_target = T_current + Δt without advancing the clock.

        Useful for the kernel to determine the event processing window
        before actually advancing.
        """
        return self._current_time + timedelta(hours=delta_hours)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"SimulationClock("
            f"now={self._current_time.isoformat()}, "
            f"elapsed={self.elapsed_hours:.1f}h)"
        )

    def to_simpy_time(self) -> float:
        """
        Convert current T_sim to a SimPy float time (hours since start).
        SimPy operates in abstract numeric time; we use hours.
        """
        return self.elapsed_hours

    def from_simpy_time(self, simpy_time: float) -> datetime:
        """Convert a SimPy float time (hours since start) back to a datetime."""
        return self._start_time + timedelta(hours=simpy_time)
