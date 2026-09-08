"""
Port & Terminal Model
=====================
Implements port operations, berth allocation, FIFO queueing, and
nonlinear congestion calculations.

Doc 2 §5 — Port & Terminal Model:
    §5.2 — Berth Capacity & allocation
    §5.3 — Yard Capacity consistency
    §5.4 — Resource Utilization: U = Usage / Capacity
    §5.5 — Nonlinear Congestion:
            For U ≤ U_c: F_cong = 1
            For U > U_c: F_cong = 1 + α × ((U - U_c) / (1 - U_c))^β
            T_handling = T_base × F_cong
    §5.6 — Port Operation Flow:
            Vessel Arrival → Berth Check → Berthing / Queue → Handling → Departure
    §5.7 — Configurable Parameters:
            PORT_BERTH_COUNT, PORT_CRANE_COUNT, PORT_YARD_CAPACITY,
            PORT_LOADING_RATE, PORT_DISCHARGE_RATE, PORT_BASE_HANDLING_TIME,
            PORT_CONGESTION_THRESHOLD, PORT_CONGESTION_FACTOR, PORT_CONGESTION_EXPONENT
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import PortState, VesselState, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §5.4, §5.5, §28)
# ---------------------------------------------------------------------------

def calculate_utilization(usage: float, capacity: float) -> float:
    """
    Calculate resource utilization U = ResourceUsage / ResourceCapacity.
    Doc 2 §5.4:
        U = Usage / Capacity
    Clamped to [0.0, 1.0] for capacity bounds, or > 1.0 if over capacity.
    """
    if capacity <= 0:
        return 1.0 if usage > 0 else 0.0
    return max(0.0, usage / capacity)


def calculate_congestion_factor(
    utilization: float,
    threshold_uc: float = 0.80,
    alpha: float = 2.0,
    beta: float = 2.0,
) -> float:
    """
    Moderate nonlinear congestion factor F_congestion.
    Doc 2 §5.5:
        For U ≤ U_c:
            F_congestion = 1.0
        For U > U_c:
            F_congestion = 1.0 + α × ((U - U_c) / (1 - U_c))^β

    Args:
        utilization: Current utilization ratio U ∈ [0, ∞).
        threshold_uc: Congestion threshold U_c (default 0.80).
        alpha: Congestion severity scalar α (default 2.0).
        beta: Nonlinearity exponent β (default 2.0).

    Returns:
        Multiplier F_congestion ≥ 1.0.
    """
    if utilization <= threshold_uc:
        return 1.0

    if threshold_uc >= 1.0:
        return 1.0

    # Clamp effective U to avoid domain errors if U > 1.0 (over capacity)
    effective_u = max(threshold_uc, utilization)
    normalized = (effective_u - threshold_uc) / (1.0 - threshold_uc)

    try:
        congestion = 1.0 + alpha * (normalized ** beta)
    except (OverflowError, ValueError):
        congestion = 1.0 + alpha * 100.0

    return float(congestion)


def calculate_handling_time(
    base_handling_time_hours: float,
    congestion_factor: float,
) -> float:
    """
    Handling time adjusted by port congestion.
    Doc 2 §5.5:
        T_handling = T_base × F_congestion
    """
    return max(0.1, base_handling_time_hours * congestion_factor)


def calculate_effective_berths(
    berths_total: int,
    is_closed: bool = False,
    is_strike_active: bool = False,
    strike_capacity_factor: float = 1.0,
) -> int:
    """
    Calculate active usable berths accounting for port strikes and closures.
    Doc 2 §5.2, §14.5
    """
    if is_closed:
        return 0
    if is_strike_active:
        return max(0, int(math.floor(berths_total * max(0.0, min(1.0, strike_capacity_factor)))))
    return berths_total


# ---------------------------------------------------------------------------
# Port Model Class
# ---------------------------------------------------------------------------

class PortModel:
    """
    Domain model for Port & Terminal operations.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    # ------------------------------------------------------------------
    # Berth capacity & allocation
    # ------------------------------------------------------------------

    def get_effective_berth_count(self, port: PortState) -> int:
        """Return usable berth count under current conditions."""
        return calculate_effective_berths(
            berths_total=port.berths_total,
            is_closed=port.is_closed,
            is_strike_active=port.is_strike_active,
            strike_capacity_factor=port.strike_capacity_factor,
        )

    def get_berths_available(self, port: PortState) -> int:
        """Return number of currently unoccupied, usable berths."""
        effective = self.get_effective_berth_count(port)
        return max(0, effective - port.berths_occupied)

    def request_berth(
        self,
        port: PortState,
        vessel_id: str,
        state: WorldState,
    ) -> bool:
        """
        Vessel requests berthing at port.
        Doc 2 §4.9:
            Port evaluates berth:
            If available → allocate berth, return True.
            If not available → enqueue vessel into FIFO queue, return False.
        """
        available = self.get_berths_available(port)
        if available > 0:
            port.berths_occupied += 1
            self.update_congestion(port, state)
            logger.info(
                "Port %s: Berth granted to vessel %s (%d/%d berths occupied)",
                port.port_id,
                vessel_id,
                port.berths_occupied,
                port.berths_total,
            )
            return True

        if vessel_id not in port.vessel_queue:
            port.vessel_queue.append(vessel_id)
            logger.info(
                "Port %s: Berth unavailable for vessel %s. Enqueued (queue depth=%d)",
                port.port_id,
                vessel_id,
                len(port.vessel_queue),
            )
        return False

    def release_berth(
        self,
        port: PortState,
        state: WorldState,
    ) -> Optional[str]:
        """
        Release a berth after vessel operations complete.
        Doc 2 §4.9:
            Decrements occupied berths.
            If vessel_queue has waiting vessels, pops first in FIFO order
            and grants them the freed berth.

        Returns:
            vessel_id of next berthed vessel, or None if queue is empty.
        """
        port.berths_occupied = max(0, port.berths_occupied - 1)
        self.update_congestion(port, state)

        # Check FIFO queue for next waiting vessel
        if port.vessel_queue and self.get_berths_available(port) > 0:
            next_vessel_id = port.vessel_queue.pop(0)
            port.berths_occupied += 1
            self.update_congestion(port, state)
            logger.info(
                "Port %s: Freed berth allocated to queued vessel %s (remaining queue=%d)",
                port.port_id,
                next_vessel_id,
                len(port.vessel_queue),
            )
            return next_vessel_id

        return None

    # ------------------------------------------------------------------
    # Congestion & Handling Time
    # ------------------------------------------------------------------

    def update_congestion(self, port: PortState, state: Optional[WorldState] = None) -> float:
        """
        Recompute nonlinear congestion index F_congestion for the port.
        Doc 2 §5.5:
            Utilization U is based on berth utilization and yard utilization.
        """
        effective_berths = self.get_effective_berth_count(port)
        berth_util = calculate_utilization(port.berths_occupied, effective_berths)

        yard_util = port.yard_utilization
        # Composite utilization: max of berth and yard utilization
        composite_util = max(berth_util, yard_util)

        # Look up parameters from registry with port-specific scope
        try:
            uc = float(self._reg.get("PORT_CONGESTION_THRESHOLD", scope_key=port.port_id))
        except KeyError:
            uc = 0.80
        try:
            alpha = float(self._reg.get("PORT_CONGESTION_FACTOR", scope_key=port.port_id))
        except KeyError:
            alpha = 2.0
        try:
            beta = float(self._reg.get("PORT_CONGESTION_EXPONENT", scope_key=port.port_id))
        except KeyError:
            beta = 2.0

        f_cong = calculate_congestion_factor(composite_util, threshold_uc=uc, alpha=alpha, beta=beta)
        port.congestion_index = f_cong
        return f_cong

    def calculate_turnaround_time_hours(
        self,
        port: PortState,
        vessel: VesselState,
        moves_teu: Optional[float] = None,
    ) -> float:
        """
        Calculate total port stay duration in hours for a vessel.
        Doc 2 §4.11, §5.5:
            T_handling = T_base × F_congestion
            Total port stay = T_handling + turnaround_buffer
        """
        f_cong = self.update_congestion(port)

        # Base turnaround time for vessel class
        try:
            base_turnaround = float(self._reg.get("VESSEL_TURNAROUND_TIME_HOURS"))
        except KeyError:
            base_turnaround = 12.0

        if moves_teu and moves_teu > 0:
            try:
                base_handling_per_teu = float(
                    self._reg.get("PORT_BASE_HANDLING_TIME", scope_key=port.port_id)
                )
            except KeyError:
                base_handling_per_teu = 0.04
            handling_time = moves_teu * base_handling_per_teu * f_cong
            return max(base_turnaround, handling_time)

        # If no explicit moves provided, apply congestion factor to turnaround time
        return calculate_handling_time(base_turnaround, f_cong)

    # ------------------------------------------------------------------
    # Disruption handlers (Doc 2 §14.5, §14.6)
    # ------------------------------------------------------------------

    def apply_strike_start(
        self,
        port: PortState,
        capacity_factor: float = 0.5,
    ) -> None:
        """Activate port strike: reduces berth/handling capacity."""
        port.is_strike_active = True
        port.strike_capacity_factor = capacity_factor
        logger.warning(
            "Port %s STRIKE STARTED. Capacity factor=%.2f",
            port.port_id,
            capacity_factor,
        )

    def apply_strike_end(self, port: PortState) -> None:
        """End port strike: restores capacity."""
        port.is_strike_active = False
        port.strike_capacity_factor = 1.0
        logger.info("Port %s STRIKE ENDED. Capacity restored.", port.port_id)

    def apply_port_closure(self, port: PortState) -> None:
        """Close port completely: 0 usable berths, operations halted."""
        port.is_closed = True
        logger.warning("Port %s CLOSED completely.", port.port_id)

    def apply_port_reopen(self, port: PortState) -> None:
        """Reopen closed port."""
        port.is_closed = False
        logger.info("Port %s REOPENED.", port.port_id)
