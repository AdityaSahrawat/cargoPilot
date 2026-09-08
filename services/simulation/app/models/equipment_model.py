"""
Equipment Supply & Scarcity Model
==================================
Calculates equipment availability, shortage, surplus, and deficit across locations.

Doc 2 §11 — Equipment Supply & Scarcity Model:
    §11.4 — Shortage = max(0, Required - Available)
    §11.5 — Surplus  = max(0, Available - Target)
    §11.6 — Deficit  = max(0, Target - Available)
    §11.7 — Scarcity Effects:
            Signals shortage/surplus to CargoPilot via events.
            Simulator does NOT automatically lease or reposition!
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import EquipmentBalance, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §11.4 - §11.6, §28)
# ---------------------------------------------------------------------------

def calculate_shortage(required: int, available: int) -> int:
    """Doc 2 §11.4: Shortage = max(0, Required - Available)"""
    return max(0, required - available)


def calculate_surplus(available: int, target: int) -> int:
    """Doc 2 §11.5: Surplus = max(0, Available - Target)"""
    return max(0, available - target)


def calculate_deficit(available: int, target: int) -> int:
    """Doc 2 §11.6: Deficit = max(0, Target - Available)"""
    return max(0, target - available)


# ---------------------------------------------------------------------------
# Equipment Model Class
# ---------------------------------------------------------------------------

class EquipmentModel:
    """
    Domain model for evaluating equipment balance and scarcity signals.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def evaluate_location_equipment(
        self,
        balance: EquipmentBalance,
        sim_time: datetime,
        state: WorldState,
        shortage_threshold: int = 1,
    ) -> List[SimEvent]:
        """
        Evaluate equipment scarcity or surplus for a single location pool.
        Emits EQUIPMENT_SHORTAGE_DETECTED or EQUIPMENT_SURPLUS_DETECTED.
        """
        events: List[SimEvent] = []

        shortage = balance.shortage
        surplus = balance.surplus

        if shortage >= shortage_threshold:
            state.kpis.equipment_shortages += shortage
            event = SimEvent(
                event_type=EventType.EQUIPMENT_SHORTAGE_DETECTED,
                entity_type="equipment",
                entity_id=f"{balance.location_id}_{balance.equipment_type}",
                simulation_time=sim_time,
                source="equipment_model",
                world_id=state.world_id,
                payload={
                    "location_id": balance.location_id,
                    "equipment_type": balance.equipment_type,
                    "available": balance.available,
                    "allocated": balance.allocated,
                    "shortage": shortage,
                },
            )
            events.append(event)
            logger.warning(
                "EQUIPMENT SHORTAGE: %s %s (shortage=%d, available=%d, req=%d)",
                balance.location_id,
                balance.equipment_type,
                shortage,
                balance.available,
                balance.allocated,
            )

        elif surplus > 0:
            event = SimEvent(
                event_type=EventType.EQUIPMENT_SURPLUS_DETECTED,
                entity_type="equipment",
                entity_id=f"{balance.location_id}_{balance.equipment_type}",
                simulation_time=sim_time,
                source="equipment_model",
                world_id=state.world_id,
                payload={
                    "location_id": balance.location_id,
                    "equipment_type": balance.equipment_type,
                    "available": balance.available,
                    "target": balance.target,
                    "surplus": surplus,
                },
            )
            events.append(event)

        return events
