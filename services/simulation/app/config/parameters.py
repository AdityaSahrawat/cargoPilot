"""
Central Parameter Registry
===========================
Every configurable model parameter for the CargoPilot Simulation Engine.

Doc 2 §24 — Parameters & Configuration
Doc 2 §1.5 — Configurable Model Parameters
Doc 2 §1.6 — Parameter Classification

Rules:
- No model hardcodes a tunable value. It must appear here.
- Scope resolution: most specific scope wins over broader scope.
  Example: PORT_LOADING_RATE[INMAA]=70 overrides PORT_LOADING_RATE=100
- Runtime-editable parameters may be changed by admin during simulation.
  The change persists to PostgreSQL; only future events are affected.
  Past events are never rewritten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import copy
import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ParameterType(str, Enum):
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    DISTRIBUTION = "DISTRIBUTION"
    STRING = "STRING"


class ParameterScope(str, Enum):
    """
    Scope resolution order (most specific wins):
    ROUTE+EQUIPMENT > PORT+EQUIPMENT > OD_PAIR > EQUIPMENT_TYPE
    > VESSEL_CLASS > ROUTE > PORT > SCENARIO > WORLD > GLOBAL
    """
    GLOBAL = "GLOBAL"
    WORLD = "WORLD"
    SCENARIO = "SCENARIO"
    PORT = "PORT"
    ROUTE = "ROUTE"
    OD_PAIR = "OD_PAIR"
    VESSEL_CLASS = "VESSEL_CLASS"
    EQUIPMENT_TYPE = "EQUIPMENT_TYPE"
    PORT_EQUIPMENT = "PORT+EQUIPMENT"
    ROUTE_EQUIPMENT = "ROUTE+EQUIPMENT"


# ---------------------------------------------------------------------------
# Parameter descriptor
# ---------------------------------------------------------------------------

@dataclass
class SimParameter:
    """
    Full descriptor for one simulation parameter.
    Every field matches Doc 2 §24.1 required fields.
    """
    name: str
    model: str
    description: str
    value: Any
    default: Any
    unit: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    param_type: ParameterType = ParameterType.NUMBER
    distribution: Optional[str] = None
    scope: ParameterScope = ParameterScope.GLOBAL
    admin_editable: bool = True
    runtime_editable: bool = False
    scenario_override: bool = True
    allowed_values: Optional[List[Any]] = None   # for ENUM type


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ParameterRegistry:
    """
    Central store for all simulation parameters.

    Usage:
        registry = ParameterRegistry()
        speed = registry.get("VESSEL_BASE_SPEED_KNOTS")
        registry.set("PORT_LOADING_RATE", 80.0, scope_key="INMAA")
    """

    def __init__(self) -> None:
        self._params: Dict[str, SimParameter] = {}
        self._scoped: Dict[Tuple[str, str], Any] = {}
        """key: (param_name, scope_key) → override value"""
        self._register_all()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, name: str, scope_key: Optional[str] = None) -> Any:
        """
        Retrieve a parameter value applying scope resolution.
        Most specific (scoped) value wins over global default.
        """
        if scope_key and (name, scope_key) in self._scoped:
            return self._scoped[(name, scope_key)]
        if name not in self._params:
            raise KeyError(f"Unknown parameter: '{name}'")
        return self._params[name].value

    def set(
        self,
        name: str,
        value: Any,
        scope_key: Optional[str] = None,
        runtime: bool = False,
    ) -> None:
        """
        Update a parameter value.

        Args:
            name: Parameter name.
            value: New value.
            scope_key: Port ID / route ID / vessel class etc.
            runtime: If True, validates that parameter is runtime_editable.
        """
        if name not in self._params:
            raise KeyError(f"Unknown parameter: '{name}'")
        p = self._params[name]
        if runtime and not p.runtime_editable:
            raise ValueError(f"Parameter '{name}' is not runtime-editable.")
        if p.min_value is not None and value < p.min_value:
            raise ValueError(f"'{name}' value {value} below min {p.min_value}")
        if p.max_value is not None and value > p.max_value:
            raise ValueError(f"'{name}' value {value} above max {p.max_value}")
        if scope_key:
            self._scoped[(name, scope_key)] = value
        else:
            p.value = value

    def apply_scenario_overrides(self, overrides: Dict[str, Any]) -> None:
        """Apply a scenario's parameter override map at simulation start."""
        for name, value in overrides.items():
            self.set(name, value)

    def clone(self) -> ParameterRegistry:
        """Create an isolated deep copy of this registry so runs do not mutate global defaults."""
        new_reg = ParameterRegistry.__new__(ParameterRegistry)
        new_reg._params = {k: copy.copy(v) for k, v in self._params.items()}
        new_reg._scoped = dict(self._scoped)
        return new_reg

    def resolve_for_run(
        self, overrides: Dict[str, Any]
    ) -> Tuple[ParameterRegistry, Dict[str, Any], str]:
        """
        Produce an isolated ParameterRegistry for a specific run by cloning self
        and applying scenario overrides.
        Returns:
            (run_registry, resolved_parameters_dict, config_hash)
        """
        run_reg = self.clone()
        run_reg.apply_scenario_overrides(overrides)

        resolved = {p.name: p.value for p in run_reg.all_params()}
        if run_reg._scoped:
            resolved["_scoped"] = {f"{k[0]}[{k[1]}]": v for k, v in run_reg._scoped.items()}

        raw = json.dumps(resolved, sort_keys=True, default=str)
        config_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

        return run_reg, resolved, config_hash

    def all_params(self) -> List[SimParameter]:
        return list(self._params.values())

    def describe(self, name: str) -> SimParameter:
        if name not in self._params:
            raise KeyError(f"Unknown parameter: '{name}'")
        return self._params[name]

    # ------------------------------------------------------------------
    # Internal registration
    # ------------------------------------------------------------------

    def _add(self, p: SimParameter) -> None:
        self._params[p.name] = p

    def _register_all(self) -> None:
        self._register_simulation_globals()
        self._register_vessel()
        self._register_port()
        self._register_container()
        self._register_demand()
        self._register_booking()
        self._register_import_return()
        self._register_equipment()
        self._register_leasing()
        self._register_repositioning()
        self._register_disruption()
        self._register_failure()
        self._register_recovery()
        self._register_backlog()
        self._register_forecast()
        self._register_visibility()
        self._register_timeline()
        self._register_cost()

    # ------------------------------------------------------------------
    # §2 — Simulation globals
    # ------------------------------------------------------------------

    def _register_simulation_globals(self) -> None:
        self._add(SimParameter(
            name="RANDOM_SEED",
            model="simulation",
            description="Global integer seed governing all stochastic draws. "
                        "Same seed + same world + same scenario → identical trajectory.",
            value=42,
            default=42,
            unit="integer",
            param_type=ParameterType.NUMBER,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="WORLD_ID",
            model="simulation",
            description="Identifier of the world dataset used for this simulation run.",
            value="world-2",
            default="world-2",
            unit="string",
            param_type=ParameterType.STRING,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="SIMULATION_MAX_DELTA_HOURS",
            model="simulation",
            description="Maximum allowed time advancement per step (Doc 2 §2.2: 0 < Δt ≤ 24h).",
            value=24.0,
            default=24.0,
            unit="hours",
            min_value=0.0,
            max_value=24.0,
            param_type=ParameterType.NUMBER,
            scope=ParameterScope.GLOBAL,
            admin_editable=False,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="FORECAST_HORIZON_DAYS",
            model="simulation",
            description="How many days ahead the simulator maintains internal future entities.",
            value=90,
            default=90,
            unit="days",
            min_value=14,
            max_value=365,
            param_type=ParameterType.NUMBER,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))

    # ------------------------------------------------------------------
    # §4 — Vessel & Voyage Model
    # ------------------------------------------------------------------

    def _register_vessel(self) -> None:
        self._add(SimParameter(
            name="VESSEL_BASE_SPEED_KNOTS",
            model="vessel",
            description="Design cruising speed. V_base in Doc 2 §4.4. "
                        "Scope: VESSEL_CLASS.",
            value=18.0,
            default=18.0,
            unit="knots",
            min_value=5.0,
            max_value=30.0,
            scope=ParameterScope.VESSEL_CLASS,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="VESSEL_SPEED_VARIATION",
            model="vessel",
            description="Standard deviation of actual speed around V_base.",
            value=1.5,
            default=1.5,
            unit="knots",
            min_value=0.0,
            max_value=5.0,
            scope=ParameterScope.VESSEL_CLASS,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="VESSEL_TURNAROUND_TIME_HOURS",
            model="vessel",
            description="Minimum port turnaround time after cargo operations complete.",
            value=12.0,
            default=12.0,
            unit="hours",
            min_value=2.0,
            max_value=72.0,
            scope=ParameterScope.VESSEL_CLASS,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="VESSEL_DELAY_PROBABILITY",
            model="vessel",
            description="Baseline probability that a voyage leg incurs a schedule delay.",
            value=0.15,
            default=0.15,
            unit="probability",
            min_value=0.0,
            max_value=1.0,
            param_type=ParameterType.NUMBER,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="VESSEL_MEAN_TIME_BETWEEN_FAILURES",
            model="vessel",
            description="Mean time between mechanical failures (exponential inter-arrival). "
                        "Used for time-to-event scheduling, not per-hour polling.",
            value=720.0,
            default=720.0,
            unit="hours",
            min_value=24.0,
            max_value=8760.0,
            scope=ParameterScope.VESSEL_CLASS,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="VESSEL_RECOVERY_TIME_HOURS",
            model="vessel",
            description="Mean recovery time after a mechanical failure.",
            value=48.0,
            default=48.0,
            unit="hours",
            min_value=4.0,
            max_value=720.0,
            scope=ParameterScope.VESSEL_CLASS,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="WEATHER_SPEED_FACTOR",
            model="vessel",
            description="Baseline weather speed reduction factor F_weather ∈ (0,1]. "
                        "Applied as V_eff = V_base × F_weather × F_operational.",
            value=1.0,
            default=1.0,
            unit="factor",
            min_value=0.1,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="WEATHER_DELAY_PROBABILITY",
            model="vessel",
            description="Probability of an additional discrete delay event during bad weather.",
            value=0.10,
            default=0.10,
            unit="probability",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))

    # ------------------------------------------------------------------
    # §5 — Port & Terminal Model
    # ------------------------------------------------------------------

    def _register_port(self) -> None:
        self._add(SimParameter(
            name="PORT_BERTH_COUNT",
            model="port",
            description="Number of berths available for vessel berthing. Scope: PORT.",
            value=4,
            default=4,
            unit="berths",
            min_value=1,
            max_value=50,
            param_type=ParameterType.NUMBER,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="PORT_CRANE_COUNT",
            model="port",
            description="Number of ship-to-shore cranes. Scope: PORT.",
            value=6,
            default=6,
            unit="cranes",
            min_value=1,
            max_value=30,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="PORT_YARD_CAPACITY",
            model="port",
            description="Maximum TEU that the container yard can hold. Scope: PORT.",
            value=10000,
            default=10000,
            unit="TEU",
            min_value=100,
            max_value=200000,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="PORT_LOADING_RATE",
            model="port",
            description="Crane moves per hour during vessel loading. Scope: PORT.",
            value=25.0,
            default=25.0,
            unit="moves/hour",
            min_value=1.0,
            max_value=100.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="PORT_DISCHARGE_RATE",
            model="port",
            description="Crane moves per hour during vessel discharge. Scope: PORT.",
            value=25.0,
            default=25.0,
            unit="moves/hour",
            min_value=1.0,
            max_value=100.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="PORT_BASE_HANDLING_TIME",
            model="port",
            description="Base time T_base for handling one TEU without congestion. "
                        "T_handling = T_base × F_congestion (Doc 2 §5.5).",
            value=0.04,
            default=0.04,
            unit="hours/TEU",
            min_value=0.01,
            max_value=1.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="PORT_CONGESTION_THRESHOLD",
            model="port",
            description="Utilization threshold U_c above which congestion factor activates. "
                        "Doc 2 §5.5: F_cong = 1 when U ≤ U_c.",
            value=0.80,
            default=0.80,
            unit="ratio",
            min_value=0.3,
            max_value=1.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="PORT_CONGESTION_FACTOR",
            model="port",
            description="Severity scalar α in nonlinear congestion formula. "
                        "F_cong = 1 + α × ((U - U_c)/(1 - U_c))^β (Doc 2 §5.5).",
            value=2.0,
            default=2.0,
            unit="multiplier",
            min_value=0.1,
            max_value=10.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="PORT_CONGESTION_EXPONENT",
            model="port",
            description="Nonlinearity exponent β in congestion formula. "
                        "Higher values make congestion spike more sharply at full utilization.",
            value=2.0,
            default=2.0,
            unit="exponent",
            min_value=1.0,
            max_value=5.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))

    # ------------------------------------------------------------------
    # §6 — Container & Equipment Model
    # ------------------------------------------------------------------

    def _register_container(self) -> None:
        self._add(SimParameter(
            name="CONTAINER_DAMAGE_PROBABILITY",
            model="container",
            description="Probability of a container being damaged during a handling event. "
                        "Damage ~ Bernoulli(p_damage) per Doc 2 §6.5.",
            value=0.002,
            default=0.002,
            unit="probability",
            min_value=0.0,
            max_value=0.1,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="CONTAINER_DAMAGE_SEVERITY",
            model="container",
            description="Probability that damage is severe enough to make container UNAVAILABLE "
                        "(vs. MAINTENANCE/repairable).",
            value=0.1,
            default=0.1,
            unit="probability",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="CONTAINER_REPAIR_TIME",
            model="container",
            description="Mean time to repair a damaged container back to GOOD condition.",
            value=3.0,
            default=3.0,
            unit="days",
            min_value=0.5,
            max_value=30.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="CONTAINER_MAINTENANCE_PROBABILITY",
            model="container",
            description="Probability of a container entering routine scheduled maintenance.",
            value=0.005,
            default=0.005,
            unit="probability",
            min_value=0.0,
            max_value=0.1,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="CONTAINER_MAINTENANCE_TIME",
            model="container",
            description="Mean duration of scheduled maintenance.",
            value=2.0,
            default=2.0,
            unit="days",
            min_value=0.5,
            max_value=14.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))

    # ------------------------------------------------------------------
    # §7 — Demand Model
    # ------------------------------------------------------------------

    def _register_demand(self) -> None:
        self._add(SimParameter(
            name="DEMAND_BASE_RATE",
            model="demand",
            description="Baseline demand volume λ_base per OD pair per equipment type per period. "
                        "Used in: λ = D_base × F_trend × F_seasonal × F_scenario (Doc 2 §7.4). "
                        "Scope: OD_PAIR or ROUTE+EQUIPMENT.",
            value=5.0,
            default=5.0,
            unit="containers/day",
            min_value=0.0,
            max_value=1000.0,
            scope=ParameterScope.ROUTE_EQUIPMENT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="DEMAND_GROWTH_RATE",
            model="demand",
            description="F_trend: weekly percentage growth/contraction in demand.",
            value=0.0,
            default=0.0,
            unit="fraction/week",
            min_value=-0.5,
            max_value=0.5,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="DEMAND_SEASONAL_FACTOR",
            model="demand",
            description="F_seasonal: multiplicative seasonal adjustment applied to base demand.",
            value=1.0,
            default=1.0,
            unit="factor",
            min_value=0.1,
            max_value=3.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="DEMAND_VARIANCE",
            model="demand",
            description="Stochastic variance around the Poisson mean demand.",
            value=1.0,
            default=1.0,
            unit="factor",
            min_value=0.0,
            max_value=5.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="DEMAND_SPIKE_PROBABILITY",
            model="demand",
            description="Probability of a demand spike event occurring in a given period.",
            value=0.05,
            default=0.05,
            unit="probability",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="DEMAND_SPIKE_FACTOR",
            model="demand",
            description="F_scenario multiplier applied during a demand spike. "
                        "Default 1.35 = +35% above baseline (Doc 2 §23.1 DEMAND_SPIKE).",
            value=1.35,
            default=1.35,
            unit="factor",
            min_value=1.0,
            max_value=5.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="DEMAND_GENERATION_INTERVAL",
            model="demand",
            description="How often (in simulation hours) the demand model fires to generate new demand.",
            value=24.0,
            default=24.0,
            unit="hours",
            min_value=1.0,
            max_value=168.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))

    # ------------------------------------------------------------------
    # §8 — Booking Generation Model
    # ------------------------------------------------------------------

    def _register_booking(self) -> None:
        self._add(SimParameter(
            name="BOOKING_CANCELLATION_PROBABILITY",
            model="booking",
            description="Probability that an unconfirmed booking is cancelled. "
                        "Cancel ~ Bernoulli(p_cancel) per Doc 2 §8.5.",
            value=0.05,
            default=0.05,
            unit="probability",
            min_value=0.0,
            max_value=0.5,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="BOOKING_MODIFICATION_PROBABILITY",
            model="booking",
            description="Probability that a booking quantity or date is modified before cutoff.",
            value=0.08,
            default=0.08,
            unit="probability",
            min_value=0.0,
            max_value=0.5,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="BOOKING_LEAD_TIME",
            model="booking",
            description="Typical days ahead of departure that a booking is created.",
            value=21.0,
            default=21.0,
            unit="days",
            min_value=1.0,
            max_value=90.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="BOOKING_SIZE_DISTRIBUTION",
            model="booking",
            description="Distribution governing containers per booking. "
                        "Supported: 'fixed:N', 'poisson:lambda', 'uniform:min:max'.",
            value="poisson:2.5",
            default="poisson:2.5",
            unit="distribution",
            param_type=ParameterType.DISTRIBUTION,
            scope=ParameterScope.ROUTE_EQUIPMENT,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=True,
        ))

    # ------------------------------------------------------------------
    # §10 — Import Return & Equipment Availability Model
    # ------------------------------------------------------------------

    def _register_import_return(self) -> None:
        self._add(SimParameter(
            name="IMPORT_RETURN_MEAN_DAYS",
            model="import_return",
            description="Mean customer-use duration before returning empty container. "
                        "T_return = T_delivery + T_customer_use (Doc 2 §10.2). "
                        "Scope: EQUIPMENT_TYPE.",
            value=5.0,
            default=5.0,
            unit="days",
            min_value=1.0,
            max_value=60.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="IMPORT_RETURN_VARIANCE",
            model="import_return",
            description="Variance of customer return time distribution.",
            value=2.0,
            default=2.0,
            unit="days²",
            min_value=0.0,
            max_value=25.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="IMPORT_RETURN_MIN_DAYS",
            model="import_return",
            description="Minimum possible customer-use duration (distribution lower bound).",
            value=1.0,
            default=1.0,
            unit="days",
            min_value=0.5,
            max_value=7.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="IMPORT_RETURN_MAX_DAYS",
            model="import_return",
            description="Maximum possible customer-use duration (distribution upper bound).",
            value=21.0,
            default=21.0,
            unit="days",
            min_value=7.0,
            max_value=90.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="IMPORT_RETURN_DELAY_PROBABILITY",
            model="import_return",
            description="Probability of additional return delay beyond normal distribution.",
            value=0.05,
            default=0.05,
            unit="probability",
            min_value=0.0,
            max_value=0.5,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="IMPORT_RETURN_DELAY_DAYS",
            model="import_return",
            description="Extra delay days when an import return delay event occurs.",
            value=5.0,
            default=5.0,
            unit="days",
            min_value=1.0,
            max_value=30.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))

    # ------------------------------------------------------------------
    # §11 — Equipment Supply & Scarcity Model
    # ------------------------------------------------------------------

    def _register_equipment(self) -> None:
        self._add(SimParameter(
            name="EQUIPMENT_SHORTAGE_THRESHOLD",
            model="equipment",
            description="Shortage ratio above which a EQUIPMENT_SHORTAGE event is emitted. "
                        "Shortage = max(0, Required - Available) (Doc 2 §11.4).",
            value=0.0,
            default=0.0,
            unit="TEU",
            min_value=0.0,
            max_value=1000.0,
            scope=ParameterScope.PORT_EQUIPMENT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="EQUIPMENT_AVAILABILITY_FACTOR",
            model="equipment",
            description="Fraction of physical inventory that is operationally available "
                        "(accounts for units under maintenance, customs hold, etc.).",
            value=0.95,
            default=0.95,
            unit="factor",
            min_value=0.1,
            max_value=1.0,
            scope=ParameterScope.PORT_EQUIPMENT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))

    # ------------------------------------------------------------------
    # §12 — Leasing Model
    # ------------------------------------------------------------------

    def _register_leasing(self) -> None:
        self._add(SimParameter(
            name="LEASE_COST_PER_DAY",
            model="leasing",
            description="Daily lease rate per container. "
                        "LeaseCost = Q × Rate × Duration (Doc 2 §12.4).",
            value=8.0,
            default=8.0,
            unit="USD/container/day",
            min_value=0.5,
            max_value=100.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="LEASE_MIN_DURATION",
            model="leasing",
            description="Minimum lease commitment duration.",
            value=14,
            default=14,
            unit="days",
            min_value=1,
            max_value=90,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="LEASE_MAX_DURATION",
            model="leasing",
            description="Maximum lease duration.",
            value=180,
            default=180,
            unit="days",
            min_value=30,
            max_value=365,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="LEASE_AVAILABLE_CAPACITY",
            model="leasing",
            description="Maximum containers that can be leased per location per horizon.",
            value=200,
            default=200,
            unit="containers",
            min_value=0,
            max_value=5000,
            scope=ParameterScope.PORT_EQUIPMENT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="LEASE_START_DELAY",
            model="leasing",
            description="Lead time from lease order to equipment being available.",
            value=3.0,
            default=3.0,
            unit="days",
            min_value=0.5,
            max_value=21.0,
            scope=ParameterScope.PORT_EQUIPMENT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="LEASE_COST_VARIATION",
            model="leasing",
            description="Standard deviation of lease cost around the base rate.",
            value=1.0,
            default=1.0,
            unit="USD/container/day",
            min_value=0.0,
            max_value=20.0,
            scope=ParameterScope.EQUIPMENT_TYPE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))

    # ------------------------------------------------------------------
    # §13 — Repositioning Model
    # ------------------------------------------------------------------

    def _register_repositioning(self) -> None:
        self._add(SimParameter(
            name="REPOSITIONING_TRANSIT_TIME",
            model="repositioning",
            description="Days in transit when repositioning empty containers.",
            value=7.0,
            default=7.0,
            unit="days",
            min_value=1.0,
            max_value=60.0,
            scope=ParameterScope.ROUTE_EQUIPMENT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="REPOSITIONING_HANDLING_TIME",
            model="repositioning",
            description="Port handling time to load/unload repositioning empties.",
            value=0.5,
            default=0.5,
            unit="hours/container",
            min_value=0.1,
            max_value=4.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="REPOSITIONING_COST",
            model="repositioning",
            description="Cost per container repositioned. "
                        "RepositioningCost = Q × CostPerContainer (Doc 2 §22.5).",
            value=500.0,
            default=500.0,
            unit="USD/container",
            min_value=0.0,
            max_value=5000.0,
            scope=ParameterScope.ROUTE_EQUIPMENT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="REPOSITIONING_CAPACITY",
            model="repositioning",
            description="Maximum containers that can be repositioned per vessel leg.",
            value=50,
            default=50,
            unit="containers",
            min_value=0,
            max_value=500,
            scope=ParameterScope.ROUTE,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))

    # ------------------------------------------------------------------
    # §14 — Disruption Models
    # ------------------------------------------------------------------

    def _register_disruption(self) -> None:
        self._add(SimParameter(
            name="STORM_OCCURRENCE_PROBABILITY",
            model="disruption",
            description="Baseline probability of a storm event per week.",
            value=0.05,
            default=0.05,
            unit="probability/week",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="STORM_DURATION_HOURS",
            model="disruption",
            description="Mean duration of a storm event.",
            value=36.0,
            default=36.0,
            unit="hours",
            min_value=6.0,
            max_value=168.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="STORM_SEVERITY",
            model="disruption",
            description="Storm severity s ∈ [0,1]. Used in F_weather = 1 - α_s × s (Doc 2 §14.4).",
            value=0.5,
            default=0.5,
            unit="severity [0,1]",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="STORM_SPEED_FACTOR",
            model="disruption",
            description="α_s in storm model F_weather = 1 - α_s × s. "
                        "Controls how much severity translates to speed reduction.",
            value=0.6,
            default=0.6,
            unit="factor",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="STORM_DELAY_FACTOR",
            model="disruption",
            description="Additional delay multiplier applied to schedule variance during a storm.",
            value=1.5,
            default=1.5,
            unit="factor",
            min_value=1.0,
            max_value=5.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="PORT_STRIKE_PROBABILITY",
            model="disruption",
            description="Probability of a port strike event per month.",
            value=0.01,
            default=0.01,
            unit="probability/month",
            min_value=0.0,
            max_value=0.5,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="PORT_STRIKE_DURATION",
            model="disruption",
            description="Mean duration of a port strike.",
            value=48.0,
            default=48.0,
            unit="hours",
            min_value=2.0,
            max_value=336.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="PORT_STRIKE_CAPACITY_FACTOR",
            model="disruption",
            description="Fraction of normal port capacity available during a strike.",
            value=0.1,
            default=0.1,
            unit="factor",
            min_value=0.0,
            max_value=0.5,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))

    # ------------------------------------------------------------------
    # §19 — Failure & Exception Models
    # ------------------------------------------------------------------

    def _register_failure(self) -> None:
        self._add(SimParameter(
            name="FAILURE_PROBABILITY",
            model="failure",
            description="Generic fallback failure probability per event. "
                        "Model-specific parameters override this.",
            value=0.01,
            default=0.01,
            unit="probability",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="FAILURE_SEVERITY",
            model="failure",
            description="Fraction of failures classified as severe (causing UNAVAILABLE state).",
            value=0.1,
            default=0.1,
            unit="fraction",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="FAILURE_RECOVERY_TIME",
            model="failure",
            description="Mean recovery time after a generic failure.",
            value=24.0,
            default=24.0,
            unit="hours",
            min_value=1.0,
            max_value=720.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))

    # ------------------------------------------------------------------
    # §20 — Recovery Models
    # ------------------------------------------------------------------

    def _register_recovery(self) -> None:
        self._add(SimParameter(
            name="RECOVERY_TIME_MEAN",
            model="recovery",
            description="Mean operational recovery time.",
            value=24.0,
            default=24.0,
            unit="hours",
            min_value=1.0,
            max_value=720.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="RECOVERY_TIME_VARIANCE",
            model="recovery",
            description="Variance of recovery time distribution.",
            value=6.0,
            default=6.0,
            unit="hours²",
            min_value=0.0,
            max_value=100.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="RECOVERY_SUCCESS_PROBABILITY",
            model="recovery",
            description="Probability that a single recovery attempt is successful.",
            value=0.95,
            default=0.95,
            unit="probability",
            min_value=0.5,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))

    # ------------------------------------------------------------------
    # §21 — Backlog Model
    # ------------------------------------------------------------------

    def _register_backlog(self) -> None:
        self._add(SimParameter(
            name="BACKLOG_PROCESSING_RATE",
            model="backlog",
            description="Baseline backlog items cleared per hour at nominal capacity.",
            value=50.0,
            default=50.0,
            unit="items/hour",
            min_value=1.0,
            max_value=1000.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="BACKLOG_DELAY_FACTOR",
            model="backlog",
            description="Additional delay per backlog item on handling time.",
            value=0.01,
            default=0.01,
            unit="hours/item",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="BACKLOG_CONGESTION_FACTOR",
            model="backlog",
            description="How strongly backlog contributes to port congestion index.",
            value=0.5,
            default=0.5,
            unit="factor",
            min_value=0.0,
            max_value=5.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))

    # ------------------------------------------------------------------
    # §16 — Forecasting Model
    # ------------------------------------------------------------------

    def _register_forecast(self) -> None:
        self._add(SimParameter(
            name="FORECAST_HORIZON",
            model="forecasting",
            description="How many days ahead forecasts are generated.",
            value=28,
            default=28,
            unit="days",
            min_value=7,
            max_value=90,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="FORECAST_UPDATE_INTERVAL",
            model="forecasting",
            description="How often (simulation hours) forecasts are recalculated.",
            value=24.0,
            default=24.0,
            unit="hours",
            min_value=1.0,
            max_value=168.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="FORECAST_NOISE",
            model="forecasting",
            description="Standard deviation of forecast error added to the base forecast.",
            value=0.15,
            default=0.15,
            unit="fraction of mean",
            min_value=0.0,
            max_value=1.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="FORECAST_HISTORY_WINDOW",
            model="forecasting",
            description="Days of historical demand used to compute the base forecast.",
            value=14,
            default=14,
            unit="days",
            min_value=7,
            max_value=84,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))

    # ------------------------------------------------------------------
    # §17 — Information / Visibility Model
    # ------------------------------------------------------------------

    def _register_visibility(self) -> None:
        self._add(SimParameter(
            name="EVENT_INFORMATION_DELAY",
            model="visibility",
            description="Delay between event occurrence and observation. "
                        "T_observation = T_occurrence + D_information (Doc 2 §17.3).",
            value=0.5,
            default=0.5,
            unit="hours",
            min_value=0.0,
            max_value=24.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="EVENT_INGESTION_DELAY",
            model="visibility",
            description="Delay between observation and CargoPilot ingestion. "
                        "T_ingestion = T_observation + D_ingestion (Doc 2 §17.3).",
            value=0.1,
            default=0.1,
            unit="hours",
            min_value=0.0,
            max_value=12.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="VESSEL_POSITION_UPDATE_INTERVAL",
            model="visibility",
            description="Interval at which vessel position is published to CargoPilot.",
            value=6.0,
            default=6.0,
            unit="hours",
            min_value=0.5,
            max_value=24.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="PORT_STATUS_UPDATE_INTERVAL",
            model="visibility",
            description="Interval at which port congestion/berth status is published.",
            value=4.0,
            default=4.0,
            unit="hours",
            min_value=0.5,
            max_value=24.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))

    # ------------------------------------------------------------------
    # §18 — Operational Timeline Model
    # ------------------------------------------------------------------

    def _register_timeline(self) -> None:
        self._add(SimParameter(
            name="EMPTY_RELEASE_LEAD_TIME",
            model="timeline",
            description="Days before departure that empty containers are released. "
                        "T_emptyRelease = T_departure - EMPTY_RELEASE_LEAD_TIME (Doc 2 §18.4).",
            value=5.0,
            default=5.0,
            unit="days",
            min_value=1.0,
            max_value=21.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="BOOKING_CUTOFF_LEAD_TIME",
            model="timeline",
            description="Days before departure that booking cutoff occurs.",
            value=7.0,
            default=7.0,
            unit="days",
            min_value=1.0,
            max_value=21.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="GATE_CUTOFF_LEAD_TIME",
            model="timeline",
            description="Days before departure that gate-in cutoff occurs.",
            value=1.0,
            default=1.0,
            unit="days",
            min_value=0.5,
            max_value=5.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="SI_CUTOFF_LEAD_TIME",
            model="timeline",
            description="Days before departure that Shipping Instruction cutoff occurs.",
            value=2.0,
            default=2.0,
            unit="days",
            min_value=0.5,
            max_value=7.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="VGM_CUTOFF_LEAD_TIME",
            model="timeline",
            description="Days before departure that VGM submission cutoff occurs.",
            value=1.5,
            default=1.5,
            unit="days",
            min_value=0.5,
            max_value=5.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=False,
            scenario_override=False,
        ))

    # ------------------------------------------------------------------
    # §22 — Cost Models
    # ------------------------------------------------------------------

    def _register_cost(self) -> None:
        self._add(SimParameter(
            name="VESSEL_DELAY_COST_PER_HOUR",
            model="cost",
            description="Cost per hour of vessel delay. "
                        "DelayCost = Duration × CostPerHour (Doc 2 §22.3).",
            value=5000.0,
            default=5000.0,
            unit="USD/hour",
            min_value=0.0,
            max_value=100000.0,
            scope=ParameterScope.VESSEL_CLASS,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="PORT_HANDLING_COST",
            model="cost",
            description="Cost per TEU handled at a port (lift-on + lift-off).",
            value=100.0,
            default=100.0,
            unit="USD/TEU",
            min_value=0.0,
            max_value=2000.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="STORAGE_COST_PER_DAY",
            model="cost",
            description="Cost per container per day for yard storage. "
                        "StorageCost = Count × Days × CostPerDay (Doc 2 §22.6).",
            value=5.0,
            default=5.0,
            unit="USD/container/day",
            min_value=0.0,
            max_value=100.0,
            scope=ParameterScope.PORT,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))
        self._add(SimParameter(
            name="SHORTAGE_COST_PER_CONTAINER",
            model="cost",
            description="Penalty cost per container that cannot be fulfilled due to shortage.",
            value=1000.0,
            default=1000.0,
            unit="USD/container",
            min_value=0.0,
            max_value=50000.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="DISRUPTION_COST",
            model="cost",
            description="Fixed cost charged per disruption event activated.",
            value=50000.0,
            default=50000.0,
            unit="USD/event",
            min_value=0.0,
            max_value=1000000.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=True,
        ))
        self._add(SimParameter(
            name="RECOVERY_COST",
            model="cost",
            description="Operational cost incurred during a recovery process.",
            value=10000.0,
            default=10000.0,
            unit="USD/recovery",
            min_value=0.0,
            max_value=500000.0,
            scope=ParameterScope.GLOBAL,
            admin_editable=True,
            runtime_editable=True,
            scenario_override=False,
        ))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[ParameterRegistry] = None


def get_registry() -> ParameterRegistry:
    """Return the module-level singleton parameter registry."""
    global _registry
    if _registry is None:
        _registry = ParameterRegistry()
    return _registry


def reset_registry() -> ParameterRegistry:
    """Reset registry to defaults. Used at simulation start / reset."""
    global _registry
    _registry = ParameterRegistry()
    return _registry
