"""
Forecasting Model
=================
Generates operational demand and equipment forecasts for CargoPilot planning
without leaking future actual state.

Doc 2 §16 — Forecasting Model:
    §16.2 — Forecast vs Actual separation: Forecast(t, t+k) vs Actual(t+k)
    §16.3 — Generation:
            D̂_{t+k} = BaseForecast_t + Trend + Seasonality + ForecastError
            ForecastError ~ Normal(0, σ_noise)
    §16.4 — Information Leakage prevention: CargoPilot receives published estimates,
            never future actuals.
"""
from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §16.3, §28)
# ---------------------------------------------------------------------------

def calculate_forecast_value(
    base_forecast: float,
    trend_factor: float = 1.0,
    seasonal_factor: float = 1.0,
    noise_sigma: float = 0.0,
    rng: Optional[random.Random] = None,
    deterministic: bool = False,
) -> float:
    """
    Calculate demand forecast for period t+k.
    Doc 2 §16.3:
        D̂_{t+k} = BaseForecast_t × Trend × Seasonality + ForecastError
    """
    base = base_forecast * max(0.0, trend_factor) * max(0.0, seasonal_factor)
    if deterministic or noise_sigma <= 0.0:
        return max(0.0, base)

    if rng is None:
        rng = random.Random()

    noise = rng.gauss(0.0, noise_sigma)
    return max(0.0, base + noise)


# ---------------------------------------------------------------------------
# Forecasting Model Class
# ---------------------------------------------------------------------------

class ForecastingModel:
    """
    Domain model for generating forward-looking demand and equipment forecasts.

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

    def generate_demand_forecast(
        self,
        origin_port_id: str,
        destination_port_id: str,
        equipment_type: str,
        horizon_days: int,
        sim_time: datetime,
        state: WorldState,
        deterministic: bool = False,
    ) -> Tuple[Dict[str, float], SimEvent]:
        """
        Generate daily demand forecasts for the next horizon_days based on historical observations.
        Does NOT look into future actuals (prevents leakage per Doc 2 §16.4).
        """
        # Compute recent observed average from state.demand.historical_demand
        hist = state.demand.historical_demand
        relevant_vals = [
            v for (orig, dest, eq, _), v in hist.items()
            if orig == origin_port_id and dest == destination_port_id and eq == equipment_type
        ]
        base_observed = sum(relevant_vals) / len(relevant_vals) if relevant_vals else 5.0

        try:
            noise_sigma = float(self._reg.get("FORECAST_NOISE"))
        except KeyError:
            noise_sigma = 0.5

        forecast_by_day: Dict[str, float] = {}

        for k in range(1, horizon_days + 1):
            future_date = (sim_time + timedelta(days=k)).strftime("%Y-%m-%d")
            forecast_val = calculate_forecast_value(
                base_forecast=base_observed,
                noise_sigma=noise_sigma,
                rng=self._rng,
                deterministic=deterministic,
            )
            forecast_by_day[future_date] = round(forecast_val, 2)

        event = SimEvent(
            event_type=EventType.FORECAST_UPDATED,
            entity_type="forecast",
            entity_id=f"{origin_port_id}_{destination_port_id}_{equipment_type}",
            simulation_time=sim_time,
            source="forecasting_model",
            world_id=state.world_id,
            payload={
                "origin_port_id": origin_port_id,
                "destination_port_id": destination_port_id,
                "equipment_type": equipment_type,
                "horizon_days": horizon_days,
                "forecast": forecast_by_day,
            },
        )
        logger.info(
            "Forecast generated for %s→%s (%s) for %d days horizon",
            origin_port_id,
            destination_port_id,
            equipment_type,
            horizon_days,
        )
        return forecast_by_day, event
