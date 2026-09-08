"""
Import Return & Equipment Availability Model
=============================================
Models customer-use duration and empty container returns to local equipment pools.

Doc 2 §10 — Import Return & Equipment Availability Model:
    §10.2 — Return Time:
            T_return = T_delivery + T_customer_use
    §10.3 — Equipment Availability:
            CUSTOMER → EMPTY → EMPTY_AVAILABLE
            Inventory at return location increments.
    §10.4 — Parameters:
            IMPORT_RETURN_MEAN_DAYS, IMPORT_RETURN_VARIANCE,
            IMPORT_RETURN_MIN_DAYS, IMPORT_RETURN_MAX_DAYS,
            IMPORT_RETURN_DELAY_PROBABILITY, IMPORT_RETURN_DELAY_DAYS
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import ContainerState, EquipmentBalance, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §10.2, §28)
# ---------------------------------------------------------------------------

def calculate_customer_use_days(
    mean_days: float = 5.0,
    min_days: float = 1.0,
    max_days: float = 14.0,
    delay_prob: float = 0.05,
    delay_days: float = 3.0,
    rng: Optional[random.Random] = None,
    deterministic: bool = False,
) -> float:
    """
    Calculate customer use duration in days.
    Doc 2 §10.2:
        T_return = T_delivery + T_customer_use
    """
    if deterministic:
        return mean_days

    if rng is None:
        rng = random.Random()

    # Sample from bounded triangular/uniform around mean
    spread = (max_days - min_days) / 4.0
    val = rng.gauss(mean_days, spread)
    days = max(min_days, min(max_days, val))

    # Stochastic return delay (e.g. detention/demurrage delay)
    if rng.random() < delay_prob:
        days += delay_days

    return float(days)


def calculate_return_timestamp(
    delivery_time: datetime,
    customer_use_days: float,
) -> datetime:
    """
    Calculate timestamp when container is returned empty.
    Doc 2 §10.2:
        T_return = T_delivery + T_customer_use
    """
    return delivery_time + timedelta(days=max(0.1, customer_use_days))


# ---------------------------------------------------------------------------
# Import Return Model Class
# ---------------------------------------------------------------------------

class ImportReturnModel:
    """
    Domain model for scheduling and processing import container returns.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(
        self,
        registry: ParameterRegistry,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._reg = registry
        self._rng = rng or random.Random(42)

    def schedule_customer_return(
        self,
        container: ContainerState,
        delivery_time: datetime,
        state: WorldState,
        deterministic: bool = False,
    ) -> Tuple[datetime, float]:
        """
        Compute scheduled return timestamp for container delivered to customer.
        Sets container.status = 'CUSTOMER'.
        """
        container.status = "CUSTOMER"

        try:
            mean_days = float(
                self._reg.get("IMPORT_RETURN_MEAN_DAYS", scope_key=container.equipment_type)
            )
        except KeyError:
            mean_days = 5.0

        try:
            min_days = float(self._reg.get("IMPORT_RETURN_MIN_DAYS"))
        except KeyError:
            min_days = 1.0

        try:
            max_days = float(self._reg.get("IMPORT_RETURN_MAX_DAYS"))
        except KeyError:
            max_days = 14.0

        try:
            delay_prob = float(self._reg.get("IMPORT_RETURN_DELAY_PROBABILITY"))
        except KeyError:
            delay_prob = 0.05

        try:
            delay_days = float(self._reg.get("IMPORT_RETURN_DELAY_DAYS"))
        except KeyError:
            delay_days = 3.0

        use_days = calculate_customer_use_days(
            mean_days=mean_days,
            min_days=min_days,
            max_days=max_days,
            delay_prob=delay_prob,
            delay_days=delay_days,
            rng=self._rng,
            deterministic=deterministic,
        )

        return_time = calculate_return_timestamp(delivery_time, use_days)
        container.available_from = return_time
        return return_time, use_days

    def process_empty_return(
        self,
        container: ContainerState,
        return_location_id: str,
        sim_time: datetime,
        state: WorldState,
    ) -> SimEvent:
        """
        Process the physical return of container into depot/port pool.
        Doc 2 §10.3:
            CUSTOMER → EMPTY → EMPTY_AVAILABLE
            Local pool available stock + 1
        """
        container.status = "EMPTY_AVAILABLE"
        container.current_location_id = return_location_id
        container.booking_id = None
        container.allocation_id = None
        container.available_from = sim_time

        bal = state.get_equipment(return_location_id, container.equipment_type)
        bal.available += 1

        logger.info(
            "Container %s RETURNED EMPTY at %s (pool available=%d)",
            container.container_id,
            return_location_id,
            bal.available,
        )

        return SimEvent(
            event_type=EventType.CONTAINER_RETURNED_EMPTY,
            entity_type="container",
            entity_id=container.container_id,
            simulation_time=sim_time,
            source="import_return_model",
            world_id=state.world_id,
            payload={
                "container_id": container.container_id,
                "location_id": return_location_id,
                "equipment_type": container.equipment_type,
                "new_available_pool": bal.available,
            },
        )
