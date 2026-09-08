"""
Backlog Model
=============
Tracks operational backlog across resources (ports, terminals, yards)
and computes congestion pressure.

Doc 2 §21 — Backlog Model:
    §21.2 — Backlog Balance:
            Backlog_{t+1} = Backlog_t + Arrivals - Completed
            with Backlog_t ≥ 0
    §21.3 — Processing Capacity:
            If Arrivals > ProcessingCapacity → backlog grows
    §21.4 — Causal cascade: Backlog → Congestion → Longer Handling → Vessel Delay
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import BacklogState, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §21.2, §28)
# ---------------------------------------------------------------------------

def calculate_next_backlog(
    current_backlog: int,
    arrivals: int,
    completed: int,
) -> int:
    """
    Doc 2 §21.2:
        Backlog_{t+1} = max(0, Backlog_t + Arrivals - Completed)
    """
    return max(0, current_backlog + arrivals - completed)


# ---------------------------------------------------------------------------
# Backlog Model Class
# ---------------------------------------------------------------------------

class BacklogModel:
    """
    Domain model for operational backlog tracking.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def update_resource_backlog(
        self,
        resource_id: str,
        resource_type: str,
        arrivals: int,
        completed: int,
        state: WorldState,
    ) -> BacklogState:
        """Update backlog for a resource (e.g. PORT or VESSEL)."""
        if resource_id not in state.backlog:
            state.backlog[resource_id] = BacklogState(
                resource_id=resource_id,
                resource_type=resource_type,
                backlog_count=0,
            )

        b_state = state.backlog[resource_id]
        new_count = calculate_next_backlog(b_state.backlog_count, arrivals, completed)
        b_state.backlog_count = new_count

        logger.debug(
            "Backlog for %s (%s): %d (arrivals=%d, completed=%d)",
            resource_id,
            resource_type,
            new_count,
            arrivals,
            completed,
        )
        return b_state
