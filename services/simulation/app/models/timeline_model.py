"""
Operational Timeline Model
==========================
Maintains the operational milestone chain and dynamically recalculates milestones
when departure schedules shift.

Doc 2 §18 — Operational Timeline Model:
    §18.2 — Milestones:
            Empty Release → Gate-in Cutoff → SI Cutoff → VGM Cutoff → Load-list Closure → Departure
    §18.4 — Milestone Calculation:
            T_milestone = T_departure - X_lead_time
    §18.5 — Dynamic Recalculation:
            If vessel departure changes, unlocked future milestones are dynamically updated.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import VoyageState, WorldState

logger = logging.getLogger(__name__)


# Standard default lead times before vessel departure (hours)
DEFAULT_LEAD_TIMES_HOURS: Dict[str, float] = {
    "EMPTY_RELEASE": 168.0,       # 7 days (7 * 24h)
    "SI_CUTOFF": 48.0,            # 48 hours
    "VGM_CUTOFF": 24.0,           # 24 hours
    "GATE_IN_CUTOFF": 12.0,       # 12 hours
    "LOAD_LIST_CLOSURE": 6.0,     # 6 hours
}


@dataclass
class Milestone:
    name: str
    target_time: datetime
    lead_time_hours: float
    is_completed: bool = False
    is_locked: bool = False


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §18.4)
# ---------------------------------------------------------------------------

def calculate_milestone_time(
    departure_time: datetime,
    lead_time_hours: float,
) -> datetime:
    """Doc 2 §18.4: T_milestone = T_departure - X_lead_time"""
    return departure_time - timedelta(hours=lead_time_hours)


# ---------------------------------------------------------------------------
# Timeline Model Class
# ---------------------------------------------------------------------------

class TimelineModel:
    """
    Domain model for operational milestone chain management.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def build_voyage_milestones(
        self,
        voyage_id: str,
        departure_time: datetime,
    ) -> Dict[str, Milestone]:
        """Generate complete set of operational milestones for a voyage leg."""
        milestones: Dict[str, Milestone] = {}
        for name, lead_h in DEFAULT_LEAD_TIMES_HOURS.items():
            t_ms = calculate_milestone_time(departure_time, lead_h)
            milestones[name] = Milestone(
                name=name,
                target_time=t_ms,
                lead_time_hours=lead_h,
                is_completed=False,
                is_locked=False,
            )
        return milestones

    def recalculate_on_departure_change(
        self,
        milestones: Dict[str, Milestone],
        new_departure_time: datetime,
        sim_time: datetime,
    ) -> List[Tuple[str, datetime, datetime]]:
        """
        Doc 2 §18.5: Dynamic Recalculation Rule.
        If departure changes, recalculate future unlocked milestones.
        Returns:
            List of (milestone_name, old_time, new_time) for modified milestones.
        """
        updated: List[Tuple[str, datetime, datetime]] = []

        for name, ms in milestones.items():
            # Completed or locked milestones must not be rewritten
            if ms.is_completed or ms.is_locked:
                continue

            old_time = ms.target_time
            new_time = calculate_milestone_time(new_departure_time, ms.lead_time_hours)

            # Only update future milestones (target_time > sim_time)
            if new_time > sim_time:
                ms.target_time = new_time
                updated.append((name, old_time, new_time))
                logger.info(
                    "Milestone %s shifted: %s → %s (departure changed to %s)",
                    name,
                    old_time.isoformat(),
                    new_time.isoformat(),
                    new_departure_time.isoformat(),
                )

        return updated
