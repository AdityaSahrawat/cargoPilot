"""
Demand Generation Model
=======================
Implements cargo demand generation over simulation time using Poisson distribution,
trend, seasonality, and scenario modifiers.

Doc 2 §7 — Demand Model:
    §7.3 — Base Demand D_base per (origin, destination, equipment_type)
    §7.4 — Rate calculation:
            λ_{i,j,e,t} = D_base × F_trend × F_seasonal × F_scenario
            D_{i,j,e,t} ~ Poisson(λ_{i,j,e,t})
    §7.5 — Historical Demand Tracking:
            Updates historical demand dataset for forecasting
    §7.6 — Parameters:
            DEMAND_BASE_RATE, DEMAND_GROWTH_RATE, DEMAND_SEASONAL_FACTOR,
            DEMAND_VARIANCE, DEMAND_SPIKE_PROBABILITY, DEMAND_SPIKE_FACTOR,
            DEMAND_GENERATION_INTERVAL
"""
from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import DemandState, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §7.4, §28)
# ---------------------------------------------------------------------------

def calculate_demand_rate(
    base_rate: float,
    f_trend: float = 1.0,
    f_seasonal: float = 1.0,
    f_scenario: float = 1.0,
) -> float:
    """
    Calculate Poisson intensity rate λ for demand.
    Doc 2 §7.4:
        λ_{i,j,e,t} = D_base × F_trend × F_seasonal × F_scenario
    """
    rate = base_rate * max(0.0, f_trend) * max(0.0, f_seasonal) * max(0.0, f_scenario)
    return max(0.0, rate)


def sample_poisson_demand(
    lambda_rate: float,
    rng: Optional[random.Random] = None,
    deterministic: bool = False,
) -> int:
    """
    Sample demand from Poisson distribution with mean λ.
    Doc 2 §7.4:
        D ~ Poisson(λ)
    If deterministic is True, returns round(λ).
    """
    if lambda_rate <= 0.0:
        return 0

    if deterministic:
        return int(round(lambda_rate))

    # Knuth algorithm for Poisson draw (or Python standard)
    if rng is None:
        rng = random.Random()

    # For small to moderate lambda:
    if lambda_rate < 30.0:
        L = math.exp(-lambda_rate)
        k = 0
        p = 1.0
        while p > L:
            k += 1
            p *= rng.random()
        return k - 1
    else:
        # Gaussian approximation for large lambda
        val = rng.gauss(lambda_rate, math.sqrt(lambda_rate))
        return max(0, int(round(val)))


# ---------------------------------------------------------------------------
# Demand Model Class
# ---------------------------------------------------------------------------

class DemandModel:
    """
    Domain model for cargo demand generation.

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

    def generate_demand_for_od(
        self,
        origin_port_id: str,
        destination_port_id: str,
        equipment_type: str,
        sim_time: datetime,
        days_since_start: float,
        is_spike_active: bool = False,
        deterministic: bool = False,
    ) -> int:
        """
        Generate demand volume for an OD pair and equipment type.
        Doc 2 §7.4:
            λ = D_base × F_trend × F_seasonal × F_scenario
            D ~ Poisson(λ)
        """
        route_scope = f"{origin_port_id}_{destination_port_id}_{equipment_type}"

        # 1. Base rate
        try:
            base_rate = float(self._reg.get("DEMAND_BASE_RATE", scope_key=route_scope))
        except KeyError:
            try:
                base_rate = float(self._reg.get("DEMAND_BASE_RATE"))
            except KeyError:
                base_rate = 5.0

        # 2. Trend factor (weekly growth)
        try:
            growth_per_week = float(self._reg.get("DEMAND_GROWTH_RATE"))
        except KeyError:
            growth_per_week = 0.0
        weeks = days_since_start / 7.0
        f_trend = max(0.1, 1.0 + growth_per_week * weeks)

        # 3. Seasonal factor
        try:
            f_seasonal = float(self._reg.get("DEMAND_SEASONAL_FACTOR"))
        except KeyError:
            f_seasonal = 1.0

        # 4. Scenario factor (demand spike)
        f_scenario = 1.0
        if is_spike_active:
            try:
                f_scenario = float(self._reg.get("DEMAND_SPIKE_FACTOR"))
            except KeyError:
                f_scenario = 1.35

        # Calculate rate λ
        lambda_rate = calculate_demand_rate(base_rate, f_trend, f_seasonal, f_scenario)

        # Sample demand
        demand_volume = sample_poisson_demand(
            lambda_rate, rng=self._rng, deterministic=deterministic
        )
        return demand_volume

    def step_demand_generation(
        self,
        state: WorldState,
        sim_time: datetime,
        active_od_pairs: List[Tuple[str, str, str]],
        days_since_start: float = 0.0,
        is_spike_active: bool = False,
        deterministic: bool = False,
    ) -> List[SimEvent]:
        """
        Execute demand generation cycle for active OD pairs.
        Updates state.demand and emits DEMAND_GENERATED events.
        """
        events: List[SimEvent] = []

        day_int = int(days_since_start)

        for origin, destination, eq_type in active_od_pairs:
            volume = self.generate_demand_for_od(
                origin_port_id=origin,
                destination_port_id=destination,
                equipment_type=eq_type,
                sim_time=sim_time,
                days_since_start=days_since_start,
                is_spike_active=is_spike_active,
                deterministic=deterministic,
            )

            # Store in world state
            key = (origin, destination, eq_type)
            state.demand.current_demand[key] = float(volume)
            hist_key = (origin, destination, eq_type, day_int)
            state.demand.historical_demand[hist_key] = float(volume)

            if volume > 0:
                event = SimEvent(
                    event_type=EventType.DEMAND_GENERATED,
                    entity_type="demand",
                    entity_id=f"{origin}_{destination}_{eq_type}",
                    simulation_time=sim_time,
                    source="demand_model",
                    world_id=state.world_id,
                    payload={
                        "origin_port_id": origin,
                        "destination_port_id": destination,
                        "equipment_type": eq_type,
                        "volume_teu": volume,
                        "day_offset": day_int,
                    },
                )
                events.append(event)

        logger.info(
            "Demand generation complete: %d OD pairs, %d events emitted",
            len(active_od_pairs),
            len(events),
        )
        return events
