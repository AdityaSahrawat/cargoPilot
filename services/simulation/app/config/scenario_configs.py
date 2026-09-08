"""
Scenario Configurations
=======================
Defines the 7 experiment scenarios. Each scenario specifies which disruption
types to activate and which model parameters to override.

Scenarios are experiment configurations.
Disruption types (disruption_types.py) are the mechanisms they activate.

Doc 2 §23 — Scenario Models
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

from app.config.disruption_types import DisruptionType


class ScenarioId(str):
    """Valid scenario identifiers."""
    NORMAL = "NORMAL"
    PORT_CONGESTION = "PORT_CONGESTION"
    VESSEL_DELAY = "VESSEL_DELAY"
    STORM = "STORM"
    EQUIPMENT_SHORTAGE = "EQUIPMENT_SHORTAGE"
    DEMAND_SPIKE = "DEMAND_SPIKE"
    MULTIPLE_DISRUPTIONS = "MULTIPLE_DISRUPTIONS"


@dataclass
class DisruptionActivation:
    """Specifies a disruption to activate as part of a scenario."""
    disruption_type: DisruptionType
    start_offset_hours: float = 0.0
    """Hours after simulation start before disruption activates."""
    duration_hours: float = 24.0
    severity: float = 0.5
    """Severity in [0,1]. Passed to the disruption model."""
    affected_entity_ids: List[str] = field(default_factory=list)
    """Empty list = affects all eligible entities."""


@dataclass
class ScenarioConfig:
    """
    A scenario modifies normal model behavior.
    It does not replace the simulation engine.

    Doc 2 §23.3:
        NORMAL MODEL
              +
        STORM PARAMETERS
              ↓
        STORM SCENARIO
    """
    scenario_id: str
    description: str
    disruptions: List[DisruptionActivation] = field(default_factory=list)
    parameter_overrides: Dict[str, Any] = field(default_factory=dict)
    """Parameter name → override value. Applied at simulation start."""


# ---------------------------------------------------------------------------
# 7 Scenario Definitions
# ---------------------------------------------------------------------------

SCENARIOS: Dict[str, ScenarioConfig] = {

    ScenarioId.NORMAL: ScenarioConfig(
        scenario_id=ScenarioId.NORMAL,
        description="Baseline operations. No disruptions. All parameters at defaults.",
        disruptions=[],
        parameter_overrides={},
    ),

    ScenarioId.PORT_CONGESTION: ScenarioConfig(
        scenario_id=ScenarioId.PORT_CONGESTION,
        description=(
            "One or more ports experience elevated congestion. Congestion threshold "
            "is lowered and yard fill injected, causing vessel queue buildup."
        ),
        disruptions=[
            DisruptionActivation(
                disruption_type=DisruptionType.PORT_CONGESTION_EVENT,
                start_offset_hours=24.0,
                duration_hours=72.0,
                severity=0.6,
            )
        ],
        parameter_overrides={
            "PORT_CONGESTION_THRESHOLD": 0.65,   # lowered from default 0.80
            "PORT_CONGESTION_FACTOR": 2.5,
        },
    ),

    ScenarioId.VESSEL_DELAY: ScenarioConfig(
        scenario_id=ScenarioId.VESSEL_DELAY,
        description=(
            "Fleet-wide schedule slippage. Elevated delay probability and "
            "mechanical failure rate."
        ),
        disruptions=[
            DisruptionActivation(
                disruption_type=DisruptionType.MECHANICAL_FAILURE,
                start_offset_hours=0.0,
                duration_hours=48.0,
                severity=0.4,
            )
        ],
        parameter_overrides={
            "VESSEL_DELAY_PROBABILITY": 0.45,      # elevated from default 0.15
            "VESSEL_MEAN_TIME_BETWEEN_FAILURES": 120.0,   # hours, reduced
        },
    ),

    ScenarioId.STORM: ScenarioConfig(
        scenario_id=ScenarioId.STORM,
        description=(
            "Severe weather storm reducing vessel speed and potentially "
            "generating port closure windows. Doc 2 §14.4."
        ),
        disruptions=[
            DisruptionActivation(
                disruption_type=DisruptionType.STORM,
                start_offset_hours=12.0,
                duration_hours=36.0,
                severity=0.7,
            )
        ],
        parameter_overrides={
            "STORM_SEVERITY": 0.7,
            "STORM_SPEED_FACTOR": 0.45,   # F_weather = 1 - alpha_s * s
            "STORM_DELAY_FACTOR": 1.8,
        },
    ),

    ScenarioId.EQUIPMENT_SHORTAGE: ScenarioConfig(
        scenario_id=ScenarioId.EQUIPMENT_SHORTAGE,
        description=(
            "Forced inventory depletion at target ports. Tests CargoPilot "
            "repositioning and leasing response."
        ),
        disruptions=[
            DisruptionActivation(
                disruption_type=DisruptionType.EQUIPMENT_SHOCK,
                start_offset_hours=0.0,
                duration_hours=120.0,
                severity=0.8,
            )
        ],
        parameter_overrides={
            "EQUIPMENT_SHORTAGE_THRESHOLD": 0.3,  # trigger threshold lowered
            "EQUIPMENT_AVAILABILITY_FACTOR": 0.4,
        },
    ),

    ScenarioId.DEMAND_SPIKE: ScenarioConfig(
        scenario_id=ScenarioId.DEMAND_SPIKE,
        description=(
            "Sudden cargo demand increase of +35% above baseline. "
            "Tests CargoPilot allocation and equipment response."
        ),
        disruptions=[
            DisruptionActivation(
                disruption_type=DisruptionType.DEMAND_SURGE,
                start_offset_hours=24.0,
                duration_hours=96.0,
                severity=0.35,   # 35% spike factor
            )
        ],
        parameter_overrides={
            "DEMAND_SPIKE_FACTOR": 1.35,
            "DEMAND_SPIKE_PROBABILITY": 1.0,   # forced in this scenario
        },
    ),

    ScenarioId.MULTIPLE_DISRUPTIONS: ScenarioConfig(
        scenario_id=ScenarioId.MULTIPLE_DISRUPTIONS,
        description=(
            "Compound disruption: simultaneous storm + port congestion + "
            "equipment shortage. Tests CargoPilot robustness."
        ),
        disruptions=[
            DisruptionActivation(
                disruption_type=DisruptionType.STORM,
                start_offset_hours=0.0,
                duration_hours=48.0,
                severity=0.65,
            ),
            DisruptionActivation(
                disruption_type=DisruptionType.PORT_CONGESTION_EVENT,
                start_offset_hours=12.0,
                duration_hours=60.0,
                severity=0.7,
            ),
            DisruptionActivation(
                disruption_type=DisruptionType.EQUIPMENT_SHOCK,
                start_offset_hours=24.0,
                duration_hours=72.0,
                severity=0.6,
            ),
        ],
        parameter_overrides={
            "STORM_SEVERITY": 0.65,
            "PORT_CONGESTION_THRESHOLD": 0.60,
            "EQUIPMENT_AVAILABILITY_FACTOR": 0.5,
        },
    ),
}


def get_scenario(scenario_id: str) -> ScenarioConfig:
    """Retrieve a scenario configuration by ID (case-insensitive)."""
    normalized = scenario_id.upper()
    if normalized not in SCENARIOS:
        raise ValueError(
            f"Unknown scenario '{scenario_id}'. "
            f"Valid scenarios: {list(SCENARIOS.keys())}"
        )
    return SCENARIOS[normalized]
