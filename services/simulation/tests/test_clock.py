"""
Unit tests for SimulationClock (Doc 2 §2.1, §2.2).
"""
from datetime import datetime, timezone, timedelta
import pytest

from app.clock.simulation_clock import SimulationClock


def test_clock_initialization():
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start)
    assert clock.now == start
    assert clock.start_time == start
    assert clock.elapsed_hours == 0.0
    assert clock.elapsed_days == 0.0
    assert clock.to_simpy_time() == 0.0


def test_clock_naive_datetime_raises():
    naive = datetime(2026, 1, 1, 0, 0, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        SimulationClock(naive)


def test_clock_advance_valid():
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start)

    # Advance 6 hours
    t1 = clock.advance(6.0)
    assert t1 == datetime(2026, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
    assert clock.elapsed_hours == 6.0
    assert clock.elapsed_days == 0.25
    assert clock.to_simpy_time() == 6.0

    # Advance another 18 hours (total 24)
    t2 = clock.advance(18.0)
    assert t2 == datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    assert clock.elapsed_hours == 24.0
    assert clock.elapsed_days == 1.0


def test_clock_advance_invalid_bounds():
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start)

    # Non-positive
    with pytest.raises(ValueError, match="positive"):
        clock.advance(0.0)
    with pytest.raises(ValueError, match="positive"):
        clock.advance(-1.0)

    # Exceeds 24 hours (Doc 2 §2.2 limit)
    with pytest.raises(ValueError, match="≤ 24.0h"):
        clock.advance(24.5)


def test_clock_target_time():
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start)

    target = clock.target_time(12.0)
    assert target == datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    # Target time does not mutate the clock
    assert clock.now == start
    assert clock.elapsed_hours == 0.0


def test_clock_simpy_conversions():
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start)
    clock.advance(12.5)

    assert clock.to_simpy_time() == 12.5
    converted = clock.from_simpy_time(36.0)
    assert converted == datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)


def test_clock_reset():
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock = SimulationClock(start)
    clock.advance(24.0)
    assert clock.elapsed_hours == 24.0

    # Reset without args goes back to initial start
    clock.reset()
    assert clock.now == start
    assert clock.elapsed_hours == 0.0

    # Reset with new start time
    new_start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    clock.reset(new_start)
    assert clock.now == new_start
    assert clock.start_time == new_start
    assert clock.elapsed_hours == 0.0
