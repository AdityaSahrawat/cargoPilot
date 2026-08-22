from datetime import datetime, date, timedelta
from typing import Optional, List
from app.db import models, enums


class TimingFeasibilityEngine:
    """Timing feasibility engine implementing time constraints and edge case rules from ag-res.md."""

    @staticmethod
    def is_container_time_feasible(
        available_from: Optional[datetime],
        required_by: datetime,
        gate_cutoff: Optional[datetime] = None,
        operational_buffer_hours: float = 2.0,
    ) -> bool:
        """Rule 1–6: Check if container availability allows pickup & delivery before cutoff."""
        if available_from is None:
            return True  # Immediately available

        latest_usable_time = gate_cutoff if gate_cutoff else required_by
        # Ensure available_from + operational_buffer <= latest_usable_time
        return (available_from + timedelta(hours=operational_buffer_hours)) <= latest_usable_time

    @staticmethod
    def is_repositioning_time_feasible(
        departure_time: datetime,
        lead_time_days: int,
        gate_cutoff: datetime,
        handling_buffer_hours: float = 4.0,
    ) -> bool:
        """Rule 7–10: Check if repositioning finishes before gate cutoff with handling time buffer."""
        arrival_time = departure_time + timedelta(days=lead_time_days)
        return (arrival_time + timedelta(hours=handling_buffer_hours)) <= gate_cutoff

    @staticmethod
    def is_voyage_timing_feasible(
        gate_cutoff: datetime,
        vessel_departure: datetime,
        voyage_expected_arrival: datetime,
        customer_required_arrival: Optional[date] = None,
    ) -> bool:
        """Rule 11–17: Check vessel departure relative to cutoff and voyage arrival relative to customer required date."""
        # Vessel must depart at or after gate cutoff
        if vessel_departure < gate_cutoff:
            return False

        # Voyage arrival must satisfy customer required arrival date
        if customer_required_arrival:
            # End of customer required arrival date (23:59:59)
            req_end = datetime.combine(customer_required_arrival, datetime.max.time())
            if voyage_expected_arrival > req_end:
                return False

        return True

    @staticmethod
    def is_commitment_time_overlapping(
        commitment_start: datetime,
        commitment_end: datetime,
        requested_start: datetime,
        requested_end: datetime,
    ) -> bool:
        """Rule 20–24: Check if an existing container commitment overlaps the requested booking window."""
        # Overlap exists if max(start1, start2) < min(end1, end2)
        return max(commitment_start, requested_start) < min(commitment_end, requested_end)

    @staticmethod
    def is_event_within_horizon(
        event_week: str,
        start_week: str = "W1",
        horizon_weeks: int = 10,
    ) -> bool:
        """Rule 31–34: Check if supply/demand event belongs to the active planning horizon (W1 to W10)."""
        try:
            event_num = int(event_week.replace("W", ""))
            start_num = int(start_week.replace("W", ""))
            return start_num <= event_num < (start_num + horizon_weeks)
        except ValueError:
            return True

    @staticmethod
    def is_closure_overlapping(
        target_time: datetime,
        closure_windows: List[models.LocationClosureWindow],
    ) -> bool:
        """Rule 44–45: Check if target operational time falls inside a location closure window."""
        for cw in closure_windows:
            if cw.start_time <= target_time <= cw.end_time:
                return True
        return False
