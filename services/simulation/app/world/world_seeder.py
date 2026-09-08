"""
World Seeder
=============
Loads World 2 fixture data into the initial WorldState and seeds
the simulator-owned PostgreSQL tables.

Architectural Rule 1 (Persistence):
    WorldState is loaded FROM PostgreSQL at step start.
    This seeder runs ONCE at simulation start (or when a new run is created)
    to populate the simulator-owned tables from World 2 fixtures.

Architectural Rule 3 (Visibility):
    Voyages within the current planning window are seeded as KNOWN_TO_CARGOPILOT.
    Future voyages beyond it start as INTERNAL_SIMULATION_KNOWN.

World 2 data (fixtures_v2.py):
    - 55 ports (global network, 6 regions)
    - 18 vessels (ULCV to feeder, 2000–20000 TEU)
    - 18 service lines (383+ legs over 84-day horizon)

Simulation-specific supplements added here:
    - Nautical distances between port pairs (simplified great-circle approximations)
    - Vessel base speeds by vessel type/class
    - Port berth counts, crane counts, yard capacity by tier
    - Initial equipment inventory by port
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.parameters import ParameterRegistry
from app.config.scenario_configs import ScenarioConfig
from app.db.sim_models import (
    SimulationRun,
    SimulationParameter,
    VesselSimState,
    PortSimState,
)
from app.world.world_state import (
    WorldState,
    VesselState,
    PortState,
    VoyageState,
    ContainerState,
    EquipmentBalance,
    DemandState,
    KPIAccumulator,
    Visibility,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Simulation-specific supplements for World 2 data
# ---------------------------------------------------------------------------

# Approximate nautical distances (NM) between key port pairs.
# Simplified estimates; good enough for V1 simulation timing.
PORT_DISTANCES_NM: Dict[Tuple[str, str], float] = {
    # Asia ↔ Europe
    ("CNSHA", "CNNGB"): 120,
    ("CNNGB", "KRPUS"): 530,
    ("KRPUS", "SGSIN"): 2650,
    ("SGSIN", "LKCMB"): 1600,
    ("LKCMB", "EGPSD"): 3500,
    ("EGPSD", "NLRTM"): 4100,
    ("NLRTM", "DEHAM"): 280,
    ("DEHAM", "BEANR"): 400,
    ("CNTAO", "CNSHA"): 470,
    ("HKHKG", "CNSZX"): 50,
    ("CNSZX", "MYPKG"): 1800,
    ("MYPKG", "LKCMB"): 700,
    ("GBFXT", "NLRTM"): 120,
    ("FRLEH", "GBFXT"): 280,
    # Transpacific
    ("CNSHA", "TWKHH"): 800,
    ("TWKHH", "USLAX"): 6500,
    ("USLAX", "USNYC"): 4700,
    # Asia ↔ Middle East
    ("CNSHA", "SGSIN"): 2200,
    ("SGSIN", "INMAA"): 2200,
    ("INMAA", "INBOM"): 800,
    ("INBOM", "AEDXB"): 1200,
    ("CNGUZ", "HKHKG"): 160,
    ("HKHKG", "SGSIN"): 1500,
    ("SGSIN", "MYPKG"): 900,
    ("PKKAR", "AEDXB"): 600,
    # Intra-Asia
    ("SGSIN", "IDJKT"): 550,
    ("IDJKT", "PHMNL"): 1800,
    ("PHMNL", "VNSAG"): 1000,
    ("VNSAG", "THBKK"): 600,
    ("THBKK", "MYPEN"): 700,
    ("MYPEN", "SGSIN"): 650,
    ("SGSIN", "VNHPH"): 1200,
    # Europe ↔ Americas
    ("NLRTM", "USNYC"): 3450,
    ("USNYC", "USSAV"): 650,
    ("USSAV", "USHOU"): 1200,
    ("USHOU", "PAMIT"): 1500,
    ("PAMIT", "BRSSZ"): 3400,
    ("BRSSZ", "BRVIX"): 300,
    ("BRVIX", "COBUN"): 500,
    # Africa
    ("EGPSD", "MAPTM"): 2400,
    ("MAPTM", "NGAPP"): 3200,
    ("NGAPP", "KEYSM"): 2800,
    ("KEYSM", "ZADUR"): 2500,
    # South Asia feeders
    ("LKCMB", "BDCGP"): 900,
    ("BDCGP", "INMAA"): 800,
    ("INMAA", "PKKAR"): 1300,
    # Middle East Gulf
    ("AEDXB", "IQUMQ"): 1200,
    ("IQUMQ", "SADAM"): 400,
    ("SADAM", "KWKWI"): 250,
    ("KWKWI", "IQBAS"): 180,
    ("IQBAS", "AEDXB"): 600,
    # Oceania
    ("SGSIN", "PHMNL"): 1300,
    ("PHMNL", "AUMEL"): 4200,
    ("AUMEL", "AUSYD"): 600,
    ("AUSYD", "NZAKL"): 1340,
    # West Europe
    ("NLRTM", "PLGDY"): 680,
    ("PLGDY", "GBFXT"): 1100,
    ("ESBCN", "ITGOA"): 800,
    ("ITGOA", "GRPIR"): 900,
    # South America
    ("USNYC", "USSAV"): 650,
}


def get_distance(origin: str, destination: str) -> float:
    """Return NM distance for a port pair. Symmetric lookup."""
    d = PORT_DISTANCES_NM.get((origin, destination))
    if d is not None:
        return d
    d = PORT_DISTANCES_NM.get((destination, origin))
    if d is not None:
        return d
    # Fallback estimate: 1000 NM for unknown pairs
    logger.warning("No distance defined for %s→%s, using 1000 NM estimate", origin, destination)
    return 1000.0


# Vessel base speed by TEU capacity class (knots)
VESSEL_SPEED_BY_CAPACITY: Dict[str, float] = {
    "ULCV": 19.0,        # ≥15000 TEU
    "POST_PANAMAX": 20.0, # 8000-15000 TEU
    "PANAMAX": 19.5,     # 4000-8000 TEU
    "CONTAINER_SHIP": 18.0, # 2000-4000 TEU
    "FEEDER": 16.0,      # <2000 TEU
}

VESSEL_CLASS_BY_CAPACITY: Dict[str, str] = {
    "ULCV": "ULCV",
    "POST_PANAMAX": "POST_PANAMAX",
    "PANAMAX": "PANAMAX",
    "CONTAINER_SHIP": "CONTAINER_SHIP",
    "FEEDER": "FEEDER",
}

def _vessel_class(teu: int) -> str:
    if teu >= 15000: return "ULCV"
    if teu >= 8000:  return "POST_PANAMAX"
    if teu >= 4000:  return "PANAMAX"
    if teu >= 2000:  return "CONTAINER_SHIP"
    return "FEEDER"


# Port berth count, crane count, yard capacity by port tier [0,1]
# PORT_TIER values from fixtures_v2.py _PORT_TIER
PORT_TIER: Dict[str, float] = {
    "CNSHA": 1.00, "SGSIN": 1.00, "NLRTM": 0.95, "USLAX": 0.90, "AEDXB": 0.88,
    "CNNGB": 0.82, "CNTAO": 0.78, "HKHKG": 0.80, "KRPUS": 0.80, "DEHAM": 0.82,
    "BEANR": 0.75, "USNYC": 0.75, "GBFXT": 0.70, "TWKHH": 0.70, "CNGUZ": 0.65,
    "CNSZX": 0.76, "JPTYO": 0.65, "JPOSA": 0.60, "MYPKG": 0.60, "LKCMB": 0.58,
    "INMAA": 0.55, "INBOM": 0.57, "THBKK": 0.54, "EGPSD": 0.55, "FRLEH": 0.52,
    "USSAV": 0.55, "USHOU": 0.58, "GRPIR": 0.50, "ESBCN": 0.50, "ITGOA": 0.45,
    "PLGDY": 0.45, "MYPEN": 0.40, "BRSSZ": 0.45, "VNHPH": 0.38, "VNSAG": 0.40,
    "IDJKT": 0.48, "PHMNL": 0.46, "BDCGP": 0.38, "INHAL": 0.40, "PKKAR": 0.38,
    "MAPTM": 0.35, "NGAPP": 0.35, "KEYSM": 0.28, "ZADUR": 0.34, "OMPOR": 0.24,
    "IQUMQ": 0.22, "SADAM": 0.28, "IQBAS": 0.22, "KWKWI": 0.24, "AUMEL": 0.46,
    "AUSYD": 0.42, "NZAKL": 0.34, "BRVIX": 0.24, "COBUN": 0.22, "PAMIT": 0.30,
}


def _port_berths(tier: float) -> int:
    """Derive berth count from tier."""
    if tier >= 0.90: return 12
    if tier >= 0.75: return 8
    if tier >= 0.60: return 6
    if tier >= 0.45: return 4
    return 2


def _port_yard_capacity(tier: float) -> int:
    """Derive yard capacity (TEU) from tier."""
    return max(500, int(tier * 80000))


def _initial_equipment(tier: float, eq_type: str) -> int:
    """Derive initial equipment inventory from tier."""
    base = {"20DC": 500, "40DC": 800, "40HC": 600}
    return max(50, int(tier * base.get(eq_type, 400)))


# ---------------------------------------------------------------------------
# 18 vessel definitions from World 2
# ---------------------------------------------------------------------------

WORLD2_VESSELS = [
    {"name": "MV Ever Quantum",       "teu": 20000, "id": "V001"},
    {"name": "MV Asia Colossus",      "teu": 18000, "id": "V002"},
    {"name": "MV Pacific Titan",      "teu": 14000, "id": "V003"},
    {"name": "MV Eastern Giant",      "teu": 13500, "id": "V004"},
    {"name": "MV Global Express",     "teu": 12000, "id": "V005"},
    {"name": "MV Ocean Pioneer",      "teu": 11500, "id": "V006"},
    {"name": "MV Atlantic Bridge",    "teu": 8500,  "id": "V007"},
    {"name": "MV Mediterranean Star", "teu": 8000,  "id": "V008"},
    {"name": "MV Indian Ocean",       "teu": 7500,  "id": "V009"},
    {"name": "MV Southern Cross",     "teu": 6800,  "id": "V010"},
    {"name": "MV Pacific Trader",     "teu": 6000,  "id": "V011"},
    {"name": "MV Eastern Pioneer",    "teu": 5500,  "id": "V012"},
    {"name": "MV Silk Road",          "teu": 3500,  "id": "V013"},
    {"name": "MV Pearl River",        "teu": 3200,  "id": "V014"},
    {"name": "MV Bengal Star",        "teu": 2800,  "id": "V015"},
    {"name": "MV Malabar Express",    "teu": 2500,  "id": "V016"},
    {"name": "MV Arabian Falcon",     "teu": 2200,  "id": "V017"},
    {"name": "MV Cape Trader",        "teu": 2000,  "id": "V018"},
]

# 55 ports from World 2 with their UNLOCODEs
WORLD2_PORTS = [
    "CNSHA", "SGSIN", "NLRTM", "USLAX", "AEDXB",
    "CNNGB", "CNTAO", "HKHKG", "KRPUS", "DEHAM",
    "BEANR", "USNYC", "GBFXT", "TWKHH", "CNGUZ",
    "CNSZX", "JPTYO", "JPOSA", "MYPKG", "LKCMB",
    "INMAA", "INBOM", "THBKK", "EGPSD", "FRLEH",
    "USSAV", "USHOU", "GRPIR", "ESBCN", "ITGOA",
    "PLGDY", "MYPEN", "BRSSZ", "VNHPH", "VNSAG",
    "IDJKT", "PHMNL", "BDCGP", "INHAL", "PKKAR",
    "MAPTM", "NGAPP", "KEYSM", "ZADUR", "OMPOR",
    "IQUMQ", "SADAM", "IQBAS", "KWKWI", "AUMEL",
    "AUSYD", "NZAKL", "BRVIX", "COBUN", "PAMIT",
]


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------

class WorldSeeder:
    """
    Seeds the initial WorldState from World 2 fixture data.

    Called once when a new SimulationRun is created.
    Writes to simulator-owned PostgreSQL tables (vessel_sim_state, port_sim_state).
    Returns an in-process WorldState ready for the first simulation step.

    Architectural Rule 1:
        After seeding, WorldState is the working cache.
        Subsequent steps load from PostgreSQL, not re-seed.
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def build_world_state(
        self,
        run_id: UUID,
        world_id: str,
        start_time: datetime,
    ) -> WorldState:
        """
        Build the initial WorldState (S(t=0)) from World 2 data.

        Args:
            run_id: Simulation run UUID.
            world_id: 'world-2'
            start_time: Virtual clock T_sim start time.

        Returns:
            Populated WorldState ready for first simulation step.
        """
        logger.info("Seeding World 2 → WorldState for run %s", run_id)

        state = WorldState(
            run_id=run_id,
            simulation_time=start_time,
            world_id=world_id,
        )

        self._seed_ports(state)
        self._seed_vessels(state, start_time)
        self._seed_equipment(state)
        self._seed_demand_baselines(state)

        logger.info(
            "World 2 seeded: %d ports, %d vessels, %d equipment balances",
            len(state.ports),
            len(state.vessels),
            len(state.equipment),
        )
        return state

    # ------------------------------------------------------------------
    # Internal seeding methods
    # ------------------------------------------------------------------

    def _seed_ports(self, state: WorldState) -> None:
        """Seed all 55 World 2 ports."""
        for unlocode in WORLD2_PORTS:
            tier = PORT_TIER.get(unlocode, 0.40)
            state.ports[unlocode] = PortState(
                port_id=unlocode,
                unlocode=unlocode,
                berths_total=_port_berths(tier),
                berths_occupied=0,
                vessel_queue=[],
                yard_capacity_teu=_port_yard_capacity(tier),
                yard_occupancy_teu=0.0,
                congestion_index=0.0,
                is_strike_active=False,
                strike_capacity_factor=1.0,
                is_closed=False,
            )

    def _seed_vessels(self, state: WorldState, start_time: datetime) -> None:
        """Seed all 18 World 2 vessels."""
        for v in WORLD2_VESSELS:
            vessel_class = _vessel_class(v["teu"])
            speed = VESSEL_SPEED_BY_CAPACITY.get(vessel_class, 18.0)
            state.vessels[v["id"]] = VesselState(
                vessel_id=v["id"],
                status="AVAILABLE",
                current_voyage_id=None,
                current_port_id=None,
                position_fraction=0.0,
                distance_remaining_nm=0.0,
                current_speed_knots=speed,
                base_speed_knots=speed,
                eta=None,
                eta_visibility=Visibility.INTERNAL_SIMULATION_KNOWN,
                schedule_variance_hours=0.0,
                current_load_teu=0.0,
                capacity_teu=float(v["teu"]),
                condition="GOOD",
            )

    def _seed_equipment(self, state: WorldState) -> None:
        """
        Seed initial equipment inventory at all ports.
        Quantities derived from port tier (higher-tier ports hold more equipment).
        """
        equipment_types = ["20DC", "40DC", "40HC"]
        for unlocode in WORLD2_PORTS:
            tier = PORT_TIER.get(unlocode, 0.40)
            for eq_type in equipment_types:
                available = _initial_equipment(tier, eq_type)
                target = int(available * 0.8)   # target = 80% of initial as safety stock
                state.equipment[(unlocode, eq_type)] = EquipmentBalance(
                    location_id=unlocode,
                    equipment_type=eq_type,
                    available=available,
                    allocated=0,
                    in_transit=0,
                    unavailable=0,
                    target=target,
                )

    def _seed_demand_baselines(self, state: WorldState) -> None:
        """
        Initialize demand state with zeroed current demand.
        The demand model fires on its schedule and populates this.
        """
        state.demand = DemandState(
            current_demand={},
            historical_demand={},
        )

    # ------------------------------------------------------------------
    # DB persistence helpers
    # ------------------------------------------------------------------

    async def persist_run(
        self,
        session: AsyncSession,
        run_id: UUID,
        world_id: str,
        scenario_id: str,
        random_seed: int,
        start_time: datetime,
        registry: ParameterRegistry,
    ) -> SimulationRun:
        """
        Write the SimulationRun record to PostgreSQL.
        Called during simulation start, before the first step.
        """
        config_hash = self._hash_config(registry)
        db_run = SimulationRun(
            id=run_id,
            world_id=world_id,
            scenario_id=scenario_id,
            random_seed=random_seed,
            config_hash=config_hash,
            start_time=start_time,
            current_sim_time=start_time,
            status="RUNNING",
        )
        session.add(db_run)
        return db_run

    async def persist_vessel_states(
        self,
        session: AsyncSession,
        run_id: UUID,
        state: WorldState,
    ) -> None:
        """Write initial VesselSimState rows to PostgreSQL."""
        for vessel_id, v in state.vessels.items():
            row = VesselSimState(
                run_id=run_id,
                vessel_id=vessel_id,
                status=v.status,
                current_voyage_id=v.current_voyage_id,
                current_port_id=v.current_port_id,
                position_fraction=v.position_fraction,
                distance_remaining_nm=v.distance_remaining_nm,
                current_speed_knots=v.current_speed_knots,
                eta=v.eta,
                eta_visibility=v.eta_visibility.value,
                schedule_variance_hours=v.schedule_variance_hours,
                current_load_teu=v.current_load_teu,
                condition=v.condition,
                simulation_time=state.simulation_time,
            )
            session.add(row)

    async def persist_port_states(
        self,
        session: AsyncSession,
        run_id: UUID,
        state: WorldState,
    ) -> None:
        """Write initial PortSimState rows to PostgreSQL."""
        for port_id, p in state.ports.items():
            row = PortSimState(
                run_id=run_id,
                port_id=port_id,
                berths_total=p.berths_total,
                berths_occupied=p.berths_occupied,
                yard_capacity_teu=p.yard_capacity_teu,
                yard_occupancy_teu=p.yard_occupancy_teu,
                vessel_queue_count=len(p.vessel_queue),
                congestion_index=p.congestion_index,
                is_strike_active=p.is_strike_active,
                strike_capacity_factor=p.strike_capacity_factor,
                simulation_time=state.simulation_time,
            )
            session.add(row)

    def _hash_config(self, registry: ParameterRegistry) -> str:
        """Compute a deterministic hash of all parameter values at run start."""
        params = {p.name: p.value for p in registry.all_params()}
        raw = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def compute_travel_time_hours(
    origin: str,
    destination: str,
    speed_knots: float,
) -> float:
    """
    T_travel = D / V_eff   (Doc 2 §4.4)

    Args:
        origin: Origin port UNLOCODE.
        destination: Destination port UNLOCODE.
        speed_knots: Effective speed V_eff.

    Returns:
        Travel time in hours.
    """
    distance = get_distance(origin, destination)
    if speed_knots <= 0:
        raise ValueError(f"speed_knots must be positive, got {speed_knots}")
    return distance / speed_knots
