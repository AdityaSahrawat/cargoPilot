from datetime import datetime, date, timedelta
from app.optimization.timing_engine import TimingFeasibilityEngine
from app.db import models


def test_timing_rule_1_to_6_container_availability():
    """Rules 1-6: Normal booking timing, pickup windows, availability before/after gate cutoff."""
    engine = TimingFeasibilityEngine()

    gate_cutoff = datetime(2026, 9, 3, 14, 0)
    pickup_opens = datetime(2026, 9, 1, 8, 0)

    # Rule 1: Normal timing (available Aug 31) -> Feasible
    avail_normal = datetime(2026, 8, 31, 10, 0)
    assert engine.is_container_time_feasible(avail_normal, pickup_opens, gate_cutoff)

    # Rule 3: Available exactly at pickup opens (Sep 1 08:00) -> Feasible
    avail_exact_pickup = datetime(2026, 9, 1, 8, 0)
    assert engine.is_container_time_feasible(avail_exact_pickup, pickup_opens, gate_cutoff)

    # Rule 4: Available after pickup opens but before cutoff (Sep 2 10:00) -> Feasible
    avail_mid_window = datetime(2026, 9, 2, 10, 0)
    assert engine.is_container_time_feasible(avail_mid_window, pickup_opens, gate_cutoff)

    # Rule 5: Available exactly at gate cutoff (Sep 3 14:00) -> Infeasible due to 2h operational buffer requirement
    avail_at_cutoff = datetime(2026, 9, 3, 14, 0)
    assert not engine.is_container_time_feasible(avail_at_cutoff, pickup_opens, gate_cutoff)

    # Rule 6: Available after gate cutoff (Sep 3 16:00) -> Infeasible
    avail_after_cutoff = datetime(2026, 9, 3, 16, 0)
    assert not engine.is_container_time_feasible(avail_after_cutoff, pickup_opens, gate_cutoff)


def test_timing_rule_7_to_10_repositioning_lead_times():
    """Rules 7-10: Repositioning lead times vs pickup window & gate cutoff."""
    engine = TimingFeasibilityEngine()

    gate_cutoff = datetime(2026, 9, 3, 14, 0)

    # Rule 7: Repositioning 2 days starting Aug 29 -> Arrival Aug 31 -> Feasible
    dep_early = datetime(2026, 8, 29, 8, 0)
    assert engine.is_repositioning_time_feasible(dep_early, lead_time_days=2, gate_cutoff=gate_cutoff)

    # Rule 9: Repositioning 7 days starting Aug 29 -> Arrival Sep 5 -> Infeasible (misses cutoff Sep 3)
    dep_late = datetime(2026, 8, 29, 8, 0)
    assert not engine.is_repositioning_time_feasible(dep_late, lead_time_days=7, gate_cutoff=gate_cutoff)


def test_timing_rule_11_to_17_vessel_voyage_timing():
    """Rules 11-17: Vessel departure & scheduled vs expected arrival vs required arrival."""
    engine = TimingFeasibilityEngine()

    gate_cutoff = datetime(2026, 9, 3, 14, 0)
    vessel_dep = datetime(2026, 9, 3, 18, 0)
    scheduled_arr = datetime(2026, 9, 8, 8, 0)
    req_arr = date(2026, 9, 9)

    # Rule 15: Scheduled arrival Sep 8 <= Required arrival Sep 9 -> Feasible
    assert engine.is_voyage_timing_feasible(gate_cutoff, vessel_dep, scheduled_arr, req_arr)

    # Rule 16: Expected arrival delayed to Sep 10 > Required arrival Sep 9 -> Infeasible
    expected_delayed = datetime(2026, 9, 10, 8, 0)
    assert not engine.is_voyage_timing_feasible(gate_cutoff, vessel_dep, expected_delayed, req_arr)

    # Rule 11: Vessel departs before gate cutoff -> Infeasible
    early_dep = datetime(2026, 9, 3, 12, 0)
    assert not engine.is_voyage_timing_feasible(gate_cutoff, early_dep, scheduled_arr, req_arr)


def test_timing_rule_20_to_24_commitment_overlap():
    """Rules 20-24: Overlapping vs non-overlapping commitments."""
    engine = TimingFeasibilityEngine()

    comm_start = datetime(2026, 9, 1, 0, 0)
    comm_end = datetime(2026, 9, 10, 0, 0)

    # Rule 21: Overlaps Sep 5 -> True
    req_start = datetime(2026, 9, 5, 8, 0)
    req_end = datetime(2026, 9, 7, 8, 0)
    assert engine.is_commitment_time_overlapping(comm_start, comm_end, req_start, req_end)

    # Rule 22: Commitment ends before requested start (Sep 10 06:00 vs Sep 10 08:00) -> False (no overlap)
    comm_end_early = datetime(2026, 9, 10, 6, 0)
    req_start_after = datetime(2026, 9, 10, 8, 0)
    assert not engine.is_commitment_time_overlapping(comm_start, comm_end_early, req_start_after, req_end)


def test_timing_rule_31_to_34_horizon_boundary():
    """Rules 31-34: Horizon boundaries W1-W10 vs future supply."""
    engine = TimingFeasibilityEngine()

    assert engine.is_event_within_horizon("W1", "W1", 10)
    assert engine.is_event_within_horizon("W8", "W1", 10)
    assert not engine.is_event_within_horizon("W11", "W1", 10)


def test_timing_rule_44_to_45_location_closures():
    """Rules 44-45: Location closure windows."""
    engine = TimingFeasibilityEngine()

    cw = models.LocationClosureWindow(
        start_time=datetime(2026, 9, 3, 12, 0),
        end_time=datetime(2026, 9, 3, 14, 0),
    )

    # Target at 13:00 falls inside closure -> True
    assert engine.is_closure_overlapping(datetime(2026, 9, 3, 13, 0), [cw])
    # Target at 15:00 falls outside closure -> False
    assert not engine.is_closure_overlapping(datetime(2026, 9, 3, 15, 0), [cw])
