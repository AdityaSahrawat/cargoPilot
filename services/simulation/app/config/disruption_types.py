"""
Disruption Types
================
Defines the 6 individual operational disruption types.

Disruption types are the mechanisms. Scenarios (scenario_configs.py)
are the experiment configurations that activate one or more disruption types.

Doc 2 §14 — Disruption Models
"""
from enum import Enum


class DisruptionType(str, Enum):
    """Individual operational shock types."""

    STORM = "STORM"
    """Weather storm reducing vessel speed and potentially closing ports."""

    PORT_STRIKE = "PORT_STRIKE"
    """Terminal labour strike reducing port handling capacity."""

    MECHANICAL_FAILURE = "MECHANICAL_FAILURE"
    """Vessel mechanical failure causing vessel unavailability."""

    DEMAND_SURGE = "DEMAND_SURGE"
    """Sudden spike in cargo demand above baseline."""

    EQUIPMENT_SHOCK = "EQUIPMENT_SHOCK"
    """Sudden depletion of available equipment at one or more locations."""

    PORT_CONGESTION_EVENT = "PORT_CONGESTION_EVENT"
    """Externally-triggered port congestion beyond normal utilization."""


class DisruptionStatus(str, Enum):
    """Active window status of a disruption."""

    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    """
    Disruption window ended. Consequences (delays, shortages) may persist
    in world state as per Doc 2 §14.3.
    """
