"""
World Seeder
=============
Builds the immutable World Baseline snapshot for World 2 fixtures,
handles deterministic seeding, serialization, deserialization, and PostgreSQL persistence.

Architecture:
    WORLD 1
       │
       ▼
  IMMUTABLE BASELINE (WorldBaseline)
  ├── 55 Ports (with yard occupancy, berths, congestion)
  ├── 18 Vessels (8 IN_TRANSIT, 5 IN_PORT, 3 SCHEDULED, 1 WAITING_BERTH, 1 AVAILABLE)
  ├── 24 Voyages (18 active assignments + 6 future scheduled)
  ├── ~12,000 Containers (lifecycle distributed: EMPTY, LOADED, ALLOCATED, REPOSITIONING)
  ├── ~1,500 Bookings (SUBMITTED, CONFIRMED, ALLOCATED, LOCKED)
  ├── ~200 Allocations (CargoPilot-owned initial snapshot)
  ├── 14-day Demand History & Current Demand (~30 OD pairs)
  ├── 165 Equipment Balances (subtracting loaded containers)
  └── Initial Lease & Repositioning orders
       │
       ▼ cloned per run (never mutated)
     Run A, Run B, ...
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.parameters import ParameterRegistry
from app.db.sim_models import (
    SimulationRun,
    WorldBaseline,
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
    BookingState,
    AllocationState,
    LeaseState,
    RepositioningState,
    BacklogState,
    DisruptionState,
    KPIAccumulator,
    Visibility,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stable Deterministic Seed Generator
# ---------------------------------------------------------------------------

def stable_world_seed(world_id: str, seeder_version: str) -> int:
    """
    Generate a deterministic positive integer seed using SHA-256 (< 2^56, fits signed int64).
    Avoids Python's non-deterministic per-process hash() randomization.
    """
    raw = f"{world_id}:{seeder_version}".encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return int.from_bytes(digest[:7], "big")


# ---------------------------------------------------------------------------
# Simulation-specific supplements for World 2 data
# ---------------------------------------------------------------------------

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
    ("USLAX", "CNSHA"): 5500,
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
}

PORT_COORDINATES: Dict[str, Tuple[float, float]] = {
    # UNLOCODE: (latitude, longitude)
    "CNSHA": (31.23,   121.47),   # Shanghai, China
    "CNNGB": (29.87,   121.55),   # Ningbo, China
    "CNTAO": (36.07,   120.33),   # Qingdao, China
    "CNGUZ": (23.11,   113.27),   # Guangzhou, China
    "CNSZX": (22.54,   113.94),   # Shenzhen, China
    "HKHKG": (22.29,   114.16),   # Hong Kong
    "JPTYO": (35.65,   139.77),   # Tokyo, Japan
    "JPOSA": (34.65,   135.50),   # Osaka, Japan
    "KRPUS": (35.10,   129.04),   # Busan, South Korea
    "TWKHH": (22.62,   120.28),   # Kaohsiung, Taiwan
    "SGSIN": (1.264,   103.82),   # Singapore
    "MYPKG": (5.41,    100.34),   # Port Klang, Malaysia
    "MYPEN": (5.42,    100.33),   # Penang, Malaysia
    "THBKK": (13.50,   100.92),   # Bangkok, Thailand
    "VNHPH": (20.84,   106.69),   # Hai Phong, Vietnam
    "VNSAG": (10.77,   106.70),   # Ho Chi Minh, Vietnam
    "IDJKT": (-6.10,   106.88),   # Jakarta, Indonesia
    "PHMNL": (14.59,   120.97),   # Manila, Philippines
    "LKCMB": (6.93,    79.85),    # Colombo, Sri Lanka
    "INMAA": (13.08,   80.27),    # Chennai, India
    "INBOM": (18.93,   72.83),    # Mumbai, India
    "INHAL": (23.00,   70.20),    # Kandla, India
    "BDCGP": (22.33,   91.82),    # Chittagong, Bangladesh
    "PKKAR": (24.86,   66.99),    # Karachi, Pakistan
    "AEDXB": (25.26,   55.33),    # Dubai, UAE
    "OMPOR": (23.63,   58.59),    # Port Sultan Qaboos, Oman
    "IQUMQ": (30.48,   47.80),    # Umm Qasr, Iraq
    "IQBAS": (30.51,   47.82),    # Basra, Iraq
    "KWKWI": (29.36,   47.98),    # Kuwait City, Kuwait
    "SADAM": (26.43,   50.10),    # Dammam, Saudi Arabia
    "EGPSD": (29.87,   32.55),    # Port Said, Egypt
    "MAPTM": (35.77,   -5.80),    # Tangier, Morocco
    "NGAPP": (6.45,    3.38),     # Apapa, Lagos, Nigeria
    "KEYSM": (-4.07,   39.67),    # Mombasa, Kenya
    "ZADUR": (-29.87,  31.03),    # Durban, South Africa
    "NLRTM": (51.92,   4.48),     # Rotterdam, Netherlands
    "DEHAM": (53.54,   9.99),     # Hamburg, Germany
    "BEANR": (51.23,   4.40),     # Antwerp, Belgium
    "GBFXT": (51.94,   1.31),     # Felixstowe, UK
    "FRLEH": (49.49,   0.11),     # Le Havre, France
    "ESBCN": (41.38,   2.18),     # Barcelona, Spain
    "ITGOA": (44.41,   8.93),     # Genoa, Italy
    "GRPIR": (37.94,   23.64),    # Piraeus, Greece
    "PLGDY": (54.52,   18.53),    # Gdynia, Poland
    "USLAX": (33.73,  -118.26),   # Los Angeles, USA
    "USNYC": (40.66,   -74.04),   # New York, USA
    "USSAV": (31.97,   -81.10),   # Savannah, USA
    "USHOU": (29.72,   -95.27),   # Houston, USA
    "PAMIT": (8.96,    -79.56),   # Manzanillo, Panama
    "BRSSZ": (-23.96,  -46.31),   # Santos, Brazil
    "BRVIX": (-20.32,  -40.34),   # Vitoria, Brazil
    "COBUN": (10.39,   -75.52),   # Buenaventura, Colombia
    "AUMEL": (-37.82,  144.93),   # Melbourne, Australia
    "AUSYD": (-33.87,  151.21),   # Sydney, Australia
    "NZAKL": (-36.84,  174.77),   # Auckland, New Zealand
}

PORT_NAMES: Dict[str, str] = {
    "CNSHA": "Shanghai",       "CNNGB": "Ningbo",          "CNTAO": "Qingdao",
    "CNGUZ": "Guangzhou",      "CNSZX": "Shenzhen",        "HKHKG": "Hong Kong",
    "JPTYO": "Tokyo",          "JPOSA": "Osaka",           "KRPUS": "Busan",
    "TWKHH": "Kaohsiung",      "SGSIN": "Singapore",       "MYPKG": "Port Klang",
    "MYPEN": "Penang",         "THBKK": "Bangkok",         "VNHPH": "Hai Phong",
    "VNSAG": "Ho Chi Minh",    "IDJKT": "Jakarta",         "PHMNL": "Manila",
    "LKCMB": "Colombo",        "INMAA": "Chennai",         "INBOM": "Mumbai",
    "INHAL": "Kandla",         "BDCGP": "Chittagong",      "PKKAR": "Karachi",
    "AEDXB": "Dubai",          "OMPOR": "Muscat",          "IQUMQ": "Umm Qasr",
    "IQBAS": "Basra",          "KWKWI": "Kuwait",          "SADAM": "Dammam",
    "EGPSD": "Port Said",      "MAPTM": "Tangier",         "NGAPP": "Lagos",
    "KEYSM": "Mombasa",        "ZADUR": "Durban",          "NLRTM": "Rotterdam",
    "DEHAM": "Hamburg",        "BEANR": "Antwerp",         "GBFXT": "Felixstowe",
    "FRLEH": "Le Havre",       "ESBCN": "Barcelona",       "ITGOA": "Genoa",
    "GRPIR": "Piraeus",        "PLGDY": "Gdynia",          "USLAX": "Los Angeles",
    "USNYC": "New York",       "USSAV": "Savannah",        "USHOU": "Houston",
    "PAMIT": "Panama",         "BRSSZ": "Santos",          "BRVIX": "Vitoria",
    "COBUN": "Buenaventura",   "AUMEL": "Melbourne",       "AUSYD": "Sydney",
    "NZAKL": "Auckland",
}

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

WORLD2_PORTS = list(PORT_TIER.keys())

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

VESSEL_SPEED_BY_CAPACITY: Dict[str, float] = {
    "ULCV": 19.0,
    "POST_PANAMAX": 20.0,
    "PANAMAX": 19.5,
    "CONTAINER_SHIP": 18.0,
    "FEEDER": 16.0,
}


def _vessel_class(teu: int) -> str:
    if teu >= 15000: return "ULCV"
    if teu >= 8000:  return "POST_PANAMAX"
    if teu >= 4000:  return "PANAMAX"
    if teu >= 2000:  return "CONTAINER_SHIP"
    return "FEEDER"


def _port_berths(tier: float) -> int:
    if tier >= 0.90: return 12
    if tier >= 0.75: return 8
    if tier >= 0.60: return 6
    if tier >= 0.45: return 4
    return 2


def _port_yard_capacity(tier: float) -> int:
    return max(500, int(tier * 80000))


def _initial_equipment(tier: float, eq_type: str) -> int:
    base = {"20DC": 500, "40DC": 800, "40HC": 600}
    return max(50, int(tier * base.get(eq_type, 400)))


def get_distance(origin: str, destination: str) -> float:
    d = PORT_DISTANCES_NM.get((origin, destination))
    if d is not None:
        return d
    d = PORT_DISTANCES_NM.get((destination, origin))
    if d is not None:
        return d
    return 1000.0


def compute_travel_time_hours(origin: str, destination: str, speed_knots: float) -> float:
    distance = get_distance(origin, destination)
    if speed_knots <= 0:
        raise ValueError(f"speed_knots must be positive, got {speed_knots}")
    return distance / speed_knots


# ---------------------------------------------------------------------------
# World Seeder Class
# ---------------------------------------------------------------------------

class WorldSeeder:
    """
    Constructs and serializes/deserializes immutable World Baselines.
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def build_baseline(
        self,
        world_id: str = "world-2",
        seeder_version: str = "v1",
        baseline_time: Optional[datetime] = None,
    ) -> WorldState:
        """
        Build the immutable World Baseline snapshot representing Day-0 operational reality.
        Deterministic based on SHA-256 stable seed.
        """
        seed_val = stable_world_seed(world_id, seeder_version)
        rng = random.Random(seed_val)
        sim_start = baseline_time or datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)

        state = WorldState(
            run_id=uuid.UUID(int=0),
            simulation_time=sim_start,
            world_id=world_id,
            world_baseline_id=None,
        )

        # 1. Ports with state
        self._seed_ports_with_state(state, rng)

        # 2. Vessels & Voyages (24 voyages: 18 active + 6 future scheduled)
        self._seed_vessels_with_voyages(state, rng, sim_start)

        # 3. Containers (~12,000 across lifecycles)
        self._seed_containers(state, rng)

        # 4. Bookings & Allocations (~1,500 bookings, ~200 allocations)
        self._seed_bookings_and_allocations(state, rng, sim_start)

        # 5. Demand history & current demand
        self._seed_demand_history(state, rng, sim_start)

        # 6. Equipment balances (165 buckets, subtracting loaded units)
        self._seed_equipment_with_realism(state, rng)

        logger.info(
            "Built immutable baseline for %s (v%s): %d ports, %d vessels, %d voyages, %d containers, %d bookings",
            world_id, seeder_version, len(state.ports), len(state.vessels), len(state.voyages), len(state.containers), len(state.bookings)
        )
        return state

    # ------------------------------------------------------------------
    # Sub-Seeders
    # ------------------------------------------------------------------

    def _seed_ports_with_state(self, state: WorldState, rng: random.Random) -> None:
        """Seed all 55 ports with realistic yard occupancy, berths, and congestion."""
        for unlocode in WORLD2_PORTS:
            tier = PORT_TIER.get(unlocode, 0.40)
            berths_tot = _port_berths(tier)
            yard_cap = _port_yard_capacity(tier)

            # Yard occupancy between 40% and 75%
            yard_occ = round(rng.uniform(0.40, 0.75) * yard_cap, 1)
            utilization = yard_occ / yard_cap if yard_cap > 0 else 0.0

            # Berths occupied (randomized 0 to berths_total - 1)
            berths_occ = rng.randint(0, max(0, berths_tot - 1))

            # Congestion index calculation (Doc 2 §5.5)
            u_c = 0.75
            if utilization <= u_c:
                cong = 1.0
            else:
                cong = 1.0 + 1.5 * (((utilization - u_c) / (1.0 - u_c)) ** 2.0)

            queue: List[str] = []

            # Specific Port requirement: KRPUS has all 4 berths occupied, V006 waiting in queue
            if unlocode == "KRPUS":
                berths_tot = 4
                berths_occ = 4
                queue = ["V006"]

            state.ports[unlocode] = PortState(
                port_id=unlocode,
                unlocode=unlocode,
                name=PORT_NAMES.get(unlocode, unlocode),
                latitude=PORT_COORDINATES.get(unlocode, (0.0, 0.0))[0],
                longitude=PORT_COORDINATES.get(unlocode, (0.0, 0.0))[1],
                berths_total=berths_tot,
                berths_occupied=berths_occ,
                vessel_queue=queue,
                yard_capacity_teu=yard_cap,
                yard_occupancy_teu=yard_occ,
                congestion_index=round(cong, 3),
                is_strike_active=False,
                strike_capacity_factor=1.0,
                is_closed=False,
            )

    def _seed_vessels_with_voyages(
        self, state: WorldState, rng: random.Random, sim_start: datetime
    ) -> None:
        """
        Place 18 vessels into deterministic Day 0 statuses:
        - 8 IN_TRANSIT: V001, V003, V005, V008, V010, V012, V015, V018
        - 5 IN_PORT: V002, V007, V011, V014, V017
        - 3 SCHEDULED: V004, V009, V016
        - 1 WAITING_FOR_BERTH: V006
        - 1 AVAILABLE: V013
        Total = 18 vessels.

        Create 24 voyages:
        - 18 active / assigned voyage legs
        - 6 future scheduled voyage legs
        Total = 24 voyages.
        """
        # Vessel definitions dictionary
        vessel_specs = {
            # IN_TRANSIT (8)
            "V001": {
                "name": "MV Ever Quantum", "teu": 20000, "status": "IN_TRANSIT",
                "origin": "CNSHA", "dest": "SGSIN", "frac": 0.15, "eta_h": 38.0,
                "current_port": None, "dist": 2200.0, "speed": 19.0,
            },
            "V003": {
                "name": "MV Pacific Titan", "teu": 14000, "status": "IN_TRANSIT",
                "origin": "SGSIN", "dest": "EGPSD", "frac": 0.08, "eta_h": 72.0,
                "current_port": None, "dist": 5100.0, "speed": 20.0,
            },
            "V005": {
                "name": "MV Global Express", "teu": 12000, "status": "IN_TRANSIT",
                "origin": "USLAX", "dest": "CNSHA", "frac": 0.22, "eta_h": 96.0,
                "current_port": None, "dist": 5500.0, "speed": 20.0,
            },
            "V008": {
                "name": "MV Mediterranean Star", "teu": 8000, "status": "IN_TRANSIT",
                "origin": "EGPSD", "dest": "NLRTM", "frac": 0.35, "eta_h": 46.0,
                "current_port": None, "dist": 4100.0, "speed": 20.0,
            },
            "V010": {
                "name": "MV Southern Cross", "teu": 6800, "status": "IN_TRANSIT",
                "origin": "HKHKG", "dest": "MYPKG", "frac": 0.60, "eta_h": 24.0,
                "current_port": None, "dist": 1800.0, "speed": 19.5,
            },
            "V012": {
                "name": "MV Eastern Pioneer", "teu": 5500, "status": "IN_TRANSIT",
                "origin": "INBOM", "dest": "AEDXB", "frac": 0.78, "eta_h": 18.0,
                "current_port": None, "dist": 1200.0, "speed": 19.5,
            },
            "V015": {
                "name": "MV Bengal Star", "teu": 2800, "status": "IN_TRANSIT",
                "origin": "BDCGP", "dest": "INMAA", "frac": 0.72, "eta_h": 20.0,
                "current_port": None, "dist": 800.0, "speed": 18.0,
            },
            "V018": {
                "name": "MV Cape Trader", "teu": 2000, "status": "IN_TRANSIT",
                "origin": "NGAPP", "dest": "KEYSM", "frac": 0.45, "eta_h": 34.0,
                "current_port": None, "dist": 2800.0, "speed": 18.0,
            },
            # IN_PORT (5)
            "V002": {
                "name": "MV Asia Colossus", "teu": 18000, "status": "IN_PORT",
                "origin": "EGPSD", "dest": "NLRTM", "turnaround_h": 12.0,
                "current_port": "NLRTM", "speed": 19.0,
            },
            "V007": {
                "name": "MV Atlantic Bridge", "teu": 8500, "status": "IN_PORT",
                "origin": "NLRTM", "dest": "DEHAM", "turnaround_h": 8.0,
                "current_port": "DEHAM", "speed": 20.0,
            },
            "V011": {
                "name": "MV Pacific Trader", "teu": 6000, "status": "IN_PORT",
                "origin": "USLAX", "dest": "USNYC", "turnaround_h": 18.0,
                "current_port": "USNYC", "speed": 19.5,
            },
            "V014": {
                "name": "MV Pearl River", "teu": 3200, "status": "IN_PORT",
                "origin": "CNSHA", "dest": "CNNGB", "turnaround_h": 6.0,
                "current_port": "CNNGB", "speed": 18.0,
            },
            "V017": {
                "name": "MV Arabian Falcon", "teu": 2200, "status": "IN_PORT",
                "origin": "INBOM", "dest": "AEDXB", "turnaround_h": 10.0,
                "current_port": "AEDXB", "speed": 18.0,
            },
            # SCHEDULED (3)
            "V004": {
                "name": "MV Eastern Giant", "teu": 13500, "status": "SCHEDULED",
                "origin": "CNSHA", "dest": "SGSIN", "departs_h": 6.0,
                "current_port": "CNSHA", "speed": 19.5,
            },
            "V009": {
                "name": "MV Indian Ocean", "teu": 7500, "status": "SCHEDULED",
                "origin": "SGSIN", "dest": "LKCMB", "departs_h": 10.0,
                "current_port": "SGSIN", "speed": 19.5,
            },
            "V016": {
                "name": "MV Malabar Express", "teu": 2500, "status": "SCHEDULED",
                "origin": "PKKAR", "dest": "AEDXB", "departs_h": 12.0,
                "current_port": "PKKAR", "speed": 18.0,
            },
            # WAITING_FOR_BERTH (1)
            "V006": {
                "name": "MV Ocean Pioneer", "teu": 11500, "status": "WAITING_FOR_BERTH",
                "origin": "CNNGB", "dest": "KRPUS",
                "current_port": "KRPUS", "speed": 19.5,
            },
            # AVAILABLE (1)
            "V013": {
                "name": "MV Silk Road", "teu": 3500, "status": "AVAILABLE",
                "origin": "SGSIN", "dest": "IDJKT",
                "current_port": "SGSIN", "speed": 18.0,
            },
        }

        # Seed the 18 active / assigned voyages
        for vid, spec in vessel_specs.items():
            voyage_id = f"VOY-{vid}-01"
            speed = spec.get("speed", 18.0)
            orig = spec["origin"]
            dest = spec["dest"]
            dist = spec.get("dist", get_distance(orig, dest))
            total_duration_h = dist / speed if speed > 0 else 24.0

            eta_dt: Optional[datetime] = None
            pos_frac = 0.0
            dist_rem = 0.0
            remaining_turnaround = 0.0
            sched_dep = sim_start
            sched_arr = sim_start + timedelta(hours=total_duration_h)
            act_dep: Optional[datetime] = None

            if spec["status"] == "IN_TRANSIT":
                pos_frac = spec.get("frac", 0.3)
                dist_rem = round(dist * (1.0 - pos_frac), 1)
                eta_h = spec.get("eta_h", dist_rem / speed)
                eta_dt = sim_start + timedelta(hours=eta_h)
                elapsed_h = dist * pos_frac / speed
                sched_dep = sim_start - timedelta(hours=elapsed_h)
                act_dep = sched_dep
                sched_arr = eta_dt
            elif spec["status"] == "IN_PORT":
                remaining_turnaround = spec.get("turnaround_h", 12.0)
                sched_dep = sim_start - timedelta(hours=24.0)
                act_dep = sched_dep
                eta_dt = sim_start - timedelta(hours=12.0)
                sched_arr = eta_dt
            elif spec["status"] == "SCHEDULED":
                dep_h = spec.get("departs_h", 6.0)
                sched_dep = sim_start + timedelta(hours=dep_h)
                sched_arr = sched_dep + timedelta(hours=total_duration_h)
                eta_dt = sched_arr
            elif spec["status"] == "WAITING_FOR_BERTH":
                sched_dep = sim_start - timedelta(hours=24.0)
                act_dep = sched_dep
                eta_dt = sim_start - timedelta(hours=2.0)
                sched_arr = eta_dt
            elif spec["status"] == "AVAILABLE":
                sched_dep = sim_start + timedelta(days=2)
                sched_arr = sched_dep + timedelta(hours=total_duration_h)
                eta_dt = sched_arr

            # Voyage record
            voyage = VoyageState(
                voyage_id=voyage_id,
                vessel_id=vid,
                origin_port_id=orig,
                destination_port_id=dest,
                scheduled_departure=sched_dep,
                scheduled_arrival=sched_arr,
                actual_departure=act_dep,
                estimated_arrival=eta_dt,
                status="ACTIVE" if spec["status"] in ("IN_TRANSIT", "IN_PORT", "WAITING_FOR_BERTH") else "SCHEDULED",
                route_distance_nm=dist,
                capacity_teu=float(spec["teu"]),
                booked_teu=round(float(spec["teu"]) * 0.75, 1),
                remaining_turnaround_hours=remaining_turnaround,
                visibility=Visibility.KNOWN_TO_CARGOPILOT,
            )
            state.voyages[voyage_id] = voyage

            # Vessel record
            vessel = VesselState(
                vessel_id=vid,
                name=spec["name"],
                status=spec["status"],
                current_voyage_id=voyage_id,
                current_port_id=spec.get("current_port"),
                origin_port_id=orig,
                destination_port_id=dest,
                position_fraction=pos_frac,
                distance_remaining_nm=dist_rem,
                current_speed_knots=speed,
                base_speed_knots=speed,
                eta=eta_dt,
                eta_visibility=Visibility.KNOWN_TO_CARGOPILOT if spec["status"] == "IN_TRANSIT" else Visibility.INTERNAL_SIMULATION_KNOWN,
                schedule_variance_hours=0.0,
                current_load_teu=0.0,  # updated during container seeding
                capacity_teu=float(spec["teu"]),
                condition="GOOD",
            )
            state.vessels[vid] = vessel

        # Seed 6 future scheduled voyages (total 18 + 6 = 24)
        future_voyages_specs = [
            ("VOY-FUT-01", "V001", "SGSIN", "EGPSD", 48.0, 5100.0, 20000.0),
            ("VOY-FUT-02", "V002", "NLRTM", "DEHAM", 14.0, 280.0, 18000.0),
            ("VOY-FUT-03", "V004", "SGSIN", "LKCMB", 120.0, 1600.0, 13500.0),
            ("VOY-FUT-04", "V007", "DEHAM", "BEANR", 10.0, 400.0, 8500.0),
            ("VOY-FUT-05", "V014", "CNNGB", "KRPUS", 8.0, 530.0, 3200.0),
            ("VOY-FUT-06", "V017", "AEDXB", "IQUMQ", 12.0, 1200.0, 2200.0),
        ]

        for voy_id, vid, orig, dest, dep_offset_h, dist_nm, cap in future_voyages_specs:
            dep_time = sim_start + timedelta(hours=dep_offset_h)
            speed = 19.0
            arr_time = dep_time + timedelta(hours=dist_nm / speed)
            state.voyages[voy_id] = VoyageState(
                voyage_id=voy_id,
                vessel_id=vid,
                origin_port_id=orig,
                destination_port_id=dest,
                scheduled_departure=dep_time,
                scheduled_arrival=arr_time,
                actual_departure=None,
                estimated_arrival=arr_time,
                status="SCHEDULED",
                route_distance_nm=dist_nm,
                capacity_teu=cap,
                booked_teu=round(cap * 0.40, 1),
                remaining_turnaround_hours=0.0,
                visibility=Visibility.INTERNAL_SIMULATION_KNOWN,
            )

    def _seed_containers(self, state: WorldState, rng: random.Random) -> None:
        """
        Seed ~12,000 containers across lifecycles:
        - ~40% EMPTY_AVAILABLE (~4,800) distributed across 55 ports
        - ~30% LOADED (~3,600) on 8 IN_TRANSIT vessels
        - ~20% ALLOCATED (~2,400) at origin ports
        - ~10% IN_TRANSIT repositioning (~1,200)
        """
        eq_types = ["20DC", "40DC", "40HC"]
        eq_weights = [0.50, 0.30, 0.20]

        total_containers = 12000
        transit_vessels = [v for v in state.vessels.values() if v.status == "IN_TRANSIT"]

        # Container counts allocation on transit vessels (~3,600 total)
        vessel_container_targets = {
            "V001": 800,
            "V003": 600,
            "V005": 500,
            "V008": 450,
            "V010": 350,
            "V012": 350,
            "V015": 250,
            "V018": 300,
        }

        # Precompute port tier cumulative weights for empty container distribution
        ports_list = WORLD2_PORTS
        port_weights = [PORT_TIER.get(p, 0.40) for p in ports_list]
        total_port_wt = sum(port_weights)
        port_probs = [w / total_port_wt for w in port_weights]

        # 1. EMPTY_AVAILABLE (4,800)
        c_idx = 1
        for _ in range(4800):
            cid = f"C-{c_idx:05d}"
            eq_t = rng.choices(eq_types, weights=eq_weights)[0]
            port = rng.choices(ports_list, weights=port_probs)[0]
            state.containers[cid] = ContainerState(
                container_id=cid,
                equipment_type=eq_t,
                status="EMPTY_AVAILABLE",
                condition="GOOD",
                current_location_id=port,
                current_voyage_id=None,
                booking_id=None,
                allocation_id=None,
            )
            c_idx += 1

        # 2. LOADED on in-transit vessels (3,600)
        for v in transit_vessels:
            count = vessel_container_targets.get(v.vessel_id, 300)
            v_teu = 0.0
            for _ in range(count):
                cid = f"C-{c_idx:05d}"
                eq_t = rng.choices(eq_types, weights=eq_weights)[0]
                teu_val = 1.0 if eq_t == "20DC" else 2.0
                v_teu += teu_val
                state.containers[cid] = ContainerState(
                    container_id=cid,
                    equipment_type=eq_t,
                    status="LOADED",
                    condition="GOOD",
                    current_location_id=None,
                    current_voyage_id=v.current_voyage_id,
                    booking_id=f"BKG-LOADED-{c_idx}",
                    allocation_id=f"ALLOC-LOADED-{c_idx}",
                )
                c_idx += 1
            v.current_load_teu = v_teu

        # 3. ALLOCATED at origin ports (2,400)
        for _ in range(2400):
            cid = f"C-{c_idx:05d}"
            eq_t = rng.choices(eq_types, weights=eq_weights)[0]
            port = rng.choices(ports_list, weights=port_probs)[0]
            state.containers[cid] = ContainerState(
                container_id=cid,
                equipment_type=eq_t,
                status="ALLOCATED",
                condition="GOOD",
                current_location_id=port,
                current_voyage_id=None,
                booking_id=f"BKG-ALLOC-{c_idx}",
                allocation_id=f"ALLOC-{c_idx}",
            )
            c_idx += 1

        # 4. IN_TRANSIT repositioning / customer (1,200)
        for _ in range(1200):
            cid = f"C-{c_idx:05d}"
            eq_t = rng.choices(eq_types, weights=eq_weights)[0]
            port = rng.choices(ports_list, weights=port_probs)[0]
            state.containers[cid] = ContainerState(
                container_id=cid,
                equipment_type=eq_t,
                status="IN_TRANSIT",
                condition="GOOD",
                current_location_id=port,
                current_voyage_id=None,
                booking_id=None,
                allocation_id=None,
            )
            c_idx += 1

    def _seed_bookings_and_allocations(
        self, state: WorldState, rng: random.Random, sim_start: datetime
    ) -> None:
        """
        Seed ~1,500 bookings:
        - ~400 SUBMITTED
        - ~600 CONFIRMED
        - ~400 ALLOCATED (with ~200 CargoPilot AllocationState objects)
        - ~100 LOCKED (within 7-day cutoff)
        """
        od_pairs = [
            ("CNSHA", "SGSIN"), ("SGSIN", "EGPSD"), ("EGPSD", "NLRTM"),
            ("CNSHA", "USLAX"), ("USLAX", "USNYC"), ("NLRTM", "DEHAM"),
            ("HKHKG", "MYPKG"), ("INBOM", "AEDXB"), ("BDCGP", "INMAA"),
            ("PKKAR", "AEDXB"), ("CNSZX", "MYPKG"), ("TWKHH", "USLAX"),
            ("LKCMB", "EGPSD"), ("CNNGB", "KRPUS"), ("DEHAM", "BEANR"),
        ]
        eq_types = ["20DC", "40DC", "40HC"]

        booking_statuses = (
            ["SUBMITTED"] * 400 +
            ["CONFIRMED"] * 600 +
            ["ALLOCATED"] * 400 +
            ["LOCKED"] * 100
        )

        b_idx = 1
        alloc_idx = 1

        for b_status in booking_statuses:
            bid = f"BKG-{b_idx:05d}"
            orig, dest = rng.choice(od_pairs)
            eq_t = rng.choice(eq_types)
            qty = rng.randint(1, 10)

            # Ready time & cutoff
            if b_status == "LOCKED":
                cargo_ready = sim_start + timedelta(days=rng.randint(1, 6))
                bkg_time = sim_start - timedelta(days=rng.randint(8, 14))
                cutoff = sim_start + timedelta(days=rng.randint(1, 6))
                lock_st = "LOCKED"
            elif b_status == "ALLOCATED":
                cargo_ready = sim_start + timedelta(days=rng.randint(7, 20))
                bkg_time = sim_start - timedelta(days=rng.randint(2, 7))
                cutoff = cargo_ready - timedelta(days=7)
                lock_st = "UNLOCKED"
            elif b_status == "CONFIRMED":
                cargo_ready = sim_start + timedelta(days=rng.randint(10, 30))
                bkg_time = sim_start - timedelta(days=rng.randint(1, 4))
                cutoff = cargo_ready - timedelta(days=7)
                lock_st = "UNLOCKED"
            else: # SUBMITTED
                cargo_ready = sim_start + timedelta(days=rng.randint(14, 40))
                bkg_time = sim_start - timedelta(hours=rng.randint(1, 24))
                cutoff = cargo_ready - timedelta(days=7)
                lock_st = "UNLOCKED"

            alloc_id = None
            assigned_voyage = f"VOY-V00{rng.randint(1, 9):02d}-01"

            if b_status in ("ALLOCATED", "LOCKED") and alloc_idx <= 200:
                alloc_id = f"ALLOC-{alloc_idx:04d}"
                state.allocations[alloc_id] = AllocationState(
                    allocation_id=alloc_id,
                    booking_id=bid,
                    container_id=f"C-{(8400 + alloc_idx):05d}",
                    voyage_id=assigned_voyage,
                    status="LOCKED" if lock_st == "LOCKED" else "ALLOCATED",
                    locked=(lock_st == "LOCKED"),
                )
                alloc_idx += 1

            state.bookings[bid] = BookingState(
                booking_id=bid,
                origin_port_id=orig,
                destination_port_id=dest,
                equipment_type=eq_t,
                quantity=qty,
                cargo_ready_time=cargo_ready,
                booking_time=bkg_time,
                status=b_status,
                lock_status=lock_st,
                voyage_id=assigned_voyage if alloc_id else None,
                allocation_id=alloc_id,
                cutoff_time=cutoff,
            )
            b_idx += 1

        # Add initial active lease orders (CargoPilot-owned snapshot)
        state.leases["LEASE-001"] = LeaseState(
            lease_id="LEASE-001",
            location_id="CNSHA",
            equipment_type="40HC",
            quantity=150,
            daily_rate=4.50,
            start_time=sim_start - timedelta(days=5),
            duration_days=30.0,
            status="ACTIVE",
            equipment_available_at=sim_start - timedelta(days=4),
        )
        state.leases["LEASE-002"] = LeaseState(
            lease_id="LEASE-002",
            location_id="SGSIN",
            equipment_type="20DC",
            quantity=100,
            daily_rate=2.80,
            start_time=sim_start - timedelta(days=2),
            duration_days=14.0,
            status="ACTIVE",
            equipment_available_at=sim_start - timedelta(days=1),
        )

        # Add initial active repositioning orders
        state.repositioning_orders["REPO-001"] = RepositioningState(
            reposition_id="REPO-001",
            source_location_id="USLAX",
            destination_location_id="CNSHA",
            equipment_type="40DC",
            quantity=80,
            departure_time=sim_start - timedelta(days=3),
            estimated_arrival=sim_start + timedelta(days=8),
            status="IN_TRANSIT",
        )

    def _seed_demand_history(
        self, state: WorldState, rng: random.Random, sim_start: datetime
    ) -> None:
        """Seed 14 days of Poisson-sampled historical demand and current demand."""
        top_od_pairs = [
            ("CNSHA", "SGSIN"), ("SGSIN", "EGPSD"), ("EGPSD", "NLRTM"),
            ("CNSHA", "USLAX"), ("USLAX", "USNYC"), ("NLRTM", "DEHAM"),
            ("HKHKG", "MYPKG"), ("INBOM", "AEDXB"), ("BDCGP", "INMAA"),
            ("PKKAR", "AEDXB"), ("CNSZX", "MYPKG"), ("TWKHH", "USLAX"),
            ("LKCMB", "EGPSD"), ("CNNGB", "KRPUS"), ("DEHAM", "BEANR"),
            ("CNSHA", "CNNGB"), ("JPTYO", "USLAX"), ("KRPUS", "SGSIN"),
            ("SGSIN", "LKCMB"), ("BEANR", "USNYC"), ("USNYC", "USSAV"),
            ("EGPSD", "MAPTM"), ("MAPTM", "NGAPP"), ("NGAPP", "KEYSM"),
            ("AEDXB", "IQUMQ"), ("IDJKT", "PHMNL"), ("PHMNL", "VNSAG"),
            ("VNSAG", "THBKK"), ("AUMEL", "AUSYD"), ("BRSSZ", "BRVIX"),
        ]
        eq_types = ["20DC", "40DC", "40HC"]

        current_dem: Dict[Tuple[str, str, str], float] = {}
        hist_dem: Dict[Tuple[str, str, str, int], float] = {}

        for orig, dest in top_od_pairs:
            tier_o = PORT_TIER.get(orig, 0.4)
            tier_d = PORT_TIER.get(dest, 0.4)
            mean_demand = max(5.0, (tier_o * tier_d) * 60.0)

            for eq_t in eq_types:
                # Current demand
                cur_val = max(1.0, round(rng.gauss(mean_demand, math.sqrt(mean_demand))))
                current_dem[(orig, dest, eq_t)] = cur_val

                # 14 days historical demand
                for day in range(-14, 0):
                    hist_val = max(0.0, round(rng.gauss(mean_demand, math.sqrt(mean_demand))))
                    hist_dem[(orig, dest, eq_t, day)] = hist_val

        state.demand = DemandState(
            current_demand=current_dem,
            historical_demand=hist_dem,
        )

    def _seed_equipment_with_realism(self, state: WorldState, rng: random.Random) -> None:
        """
        Seed 165 equipment balances (55 ports × 3 equipment types).
        Counts match actual containers located at each port.
        Target safety stocks set with a few intentional deficit ports.
        """
        equipment_types = ["20DC", "40DC", "40HC"]

        # Aggregate container counts by (location, equipment_type, status)
        counts: Dict[Tuple[str, str, str], int] = {}
        for c in state.containers.values():
            if c.current_location_id:
                key = (c.current_location_id, c.equipment_type, c.status)
                counts[key] = counts.get(key, 0) + 1

        for unlocode in WORLD2_PORTS:
            tier = PORT_TIER.get(unlocode, 0.40)
            for eq_t in equipment_types:
                avail = counts.get((unlocode, eq_t, "EMPTY_AVAILABLE"), 0)
                alloc = counts.get((unlocode, eq_t, "ALLOCATED"), 0)
                in_trans = counts.get((unlocode, eq_t, "IN_TRANSIT"), 0)

                target = int(max(avail, 20) * 0.85)

                # Induce slight deficit in 3 smaller ports for CP optimization challenge
                if unlocode in ("MAPTM", "KEYSM", "IQUMQ") and eq_t == "40HC":
                    target = avail + 35

                state.equipment[(unlocode, eq_t)] = EquipmentBalance(
                    location_id=unlocode,
                    equipment_type=eq_t,
                    available=avail,
                    allocated=alloc,
                    in_transit=in_trans,
                    unavailable=0,
                    target=target,
                )

    # ------------------------------------------------------------------
    # Serialization & Deserialization
    # ------------------------------------------------------------------

    def serialize_baseline(self, state: WorldState) -> Dict[str, Any]:
        """Serialize WorldState baseline into a JSON-compatible dictionary."""
        def dt_iso(dt: Optional[datetime]) -> Optional[str]:
            return dt.isoformat() if dt else None

        # Ports
        ports_data = {
            pid: {
                "port_id": p.port_id,
                "unlocode": p.unlocode,
                "name": p.name,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "berths_total": p.berths_total,
                "berths_occupied": p.berths_occupied,
                "vessel_queue": p.vessel_queue,
                "yard_capacity_teu": p.yard_capacity_teu,
                "yard_occupancy_teu": p.yard_occupancy_teu,
                "congestion_index": p.congestion_index,
                "is_strike_active": p.is_strike_active,
                "strike_capacity_factor": p.strike_capacity_factor,
                "is_closed": p.is_closed,
            }
            for pid, p in state.ports.items()
        }

        # Vessels
        vessels_data = {
            vid: {
                "vessel_id": v.vessel_id,
                "name": v.name,
                "status": v.status,
                "current_voyage_id": v.current_voyage_id,
                "current_port_id": v.current_port_id,
                "origin_port_id": v.origin_port_id,
                "destination_port_id": v.destination_port_id,
                "position_fraction": v.position_fraction,
                "distance_remaining_nm": v.distance_remaining_nm,
                "current_speed_knots": v.current_speed_knots,
                "base_speed_knots": v.base_speed_knots,
                "eta": dt_iso(v.eta),
                "eta_visibility": v.eta_visibility.value,
                "schedule_variance_hours": v.schedule_variance_hours,
                "current_load_teu": v.current_load_teu,
                "capacity_teu": v.capacity_teu,
                "condition": v.condition,
                "next_failure_at": v.next_failure_at,
            }
            for vid, v in state.vessels.items()
        }

        # Voyages
        voyages_data = {
            vyid: {
                "voyage_id": vy.voyage_id,
                "vessel_id": vy.vessel_id,
                "origin_port_id": vy.origin_port_id,
                "destination_port_id": vy.destination_port_id,
                "scheduled_departure": dt_iso(vy.scheduled_departure),
                "scheduled_arrival": dt_iso(vy.scheduled_arrival),
                "actual_departure": dt_iso(vy.actual_departure),
                "estimated_arrival": dt_iso(vy.estimated_arrival),
                "actual_arrival": dt_iso(vy.actual_arrival),
                "status": vy.status,
                "route_distance_nm": vy.route_distance_nm,
                "capacity_teu": vy.capacity_teu,
                "booked_teu": vy.booked_teu,
                "remaining_turnaround_hours": vy.remaining_turnaround_hours,
                "visibility": vy.visibility.value,
            }
            for vyid, vy in state.voyages.items()
        }

        # Containers
        containers_data = {
            cid: {
                "container_id": c.container_id,
                "equipment_type": c.equipment_type,
                "status": c.status,
                "condition": c.condition,
                "current_location_id": c.current_location_id,
                "current_voyage_id": c.current_voyage_id,
                "booking_id": c.booking_id,
                "allocation_id": c.allocation_id,
                "available_from": dt_iso(c.available_from),
            }
            for cid, c in state.containers.items()
        }

        # Bookings
        bookings_data = {
            bid: {
                "booking_id": b.booking_id,
                "origin_port_id": b.origin_port_id,
                "destination_port_id": b.destination_port_id,
                "equipment_type": b.equipment_type,
                "quantity": b.quantity,
                "cargo_ready_time": dt_iso(b.cargo_ready_time),
                "booking_time": dt_iso(b.booking_time),
                "status": b.status,
                "lock_status": b.lock_status,
                "voyage_id": b.voyage_id,
                "allocation_id": b.allocation_id,
                "cutoff_time": dt_iso(b.cutoff_time),
            }
            for bid, b in state.bookings.items()
        }

        # Allocations
        allocations_data = {
            aid: {
                "allocation_id": a.allocation_id,
                "booking_id": a.booking_id,
                "container_id": a.container_id,
                "voyage_id": a.voyage_id,
                "status": a.status,
                "locked": a.locked,
            }
            for aid, a in state.allocations.items()
        }

        # Equipment balances
        equipment_data = [
            {
                "location_id": eb.location_id,
                "equipment_type": eb.equipment_type,
                "available": eb.available,
                "allocated": eb.allocated,
                "in_transit": eb.in_transit,
                "unavailable": eb.unavailable,
                "target": eb.target,
            }
            for eb in state.equipment.values()
        ]

        # Demand
        current_dem_data = [
            [k[0], k[1], k[2], v] for k, v in state.demand.current_demand.items()
        ]
        hist_dem_data = [
            [k[0], k[1], k[2], k[3], v] for k, v in state.demand.historical_demand.items()
        ]

        # Leases
        leases_data = {
            lid: {
                "lease_id": l.lease_id,
                "location_id": l.location_id,
                "equipment_type": l.equipment_type,
                "quantity": l.quantity,
                "daily_rate": l.daily_rate,
                "start_time": dt_iso(l.start_time),
                "duration_days": l.duration_days,
                "status": l.status,
                "equipment_available_at": dt_iso(l.equipment_available_at),
            }
            for lid, l in state.leases.items()
        }

        # Repositioning orders
        repo_data = {
            rid: {
                "reposition_id": r.reposition_id,
                "source_location_id": r.source_location_id,
                "destination_location_id": r.destination_location_id,
                "equipment_type": r.equipment_type,
                "quantity": r.quantity,
                "departure_time": dt_iso(r.departure_time),
                "estimated_arrival": dt_iso(r.estimated_arrival),
                "status": r.status,
            }
            for rid, r in state.repositioning_orders.items()
        }

        return {
            "world_id": state.world_id,
            "simulation_time": dt_iso(state.simulation_time),
            "ports": ports_data,
            "vessels": vessels_data,
            "voyages": voyages_data,
            "containers": containers_data,
            "bookings": bookings_data,
            "allocations": allocations_data,
            "equipment": equipment_data,
            "demand": {
                "current": current_dem_data,
                "historical": hist_dem_data,
            },
            "leases": leases_data,
            "repositioning_orders": repo_data,
        }

    def deserialize_baseline(
        self,
        data: Dict[str, Any],
        baseline_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ) -> WorldState:
        """Reconstruct WorldState from serialized baseline dictionary."""
        def parse_dt(s: Optional[str]) -> Optional[datetime]:
            if not s:
                return None
            return datetime.fromisoformat(s)

        sim_time = parse_dt(data["simulation_time"]) or datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
        world_id = data.get("world_id", "world-2")

        state = WorldState(
            run_id=run_id or uuid.UUID(int=0),
            simulation_time=sim_time,
            world_id=world_id,
            world_baseline_id=str(baseline_id) if baseline_id else None,
        )

        # Ports
        for pid, p in data.get("ports", {}).items():
            state.ports[pid] = PortState(
                port_id=p["port_id"],
                unlocode=p["unlocode"],
                name=p["name"],
                latitude=p["latitude"],
                longitude=p["longitude"],
                berths_total=p["berths_total"],
                berths_occupied=p["berths_occupied"],
                vessel_queue=p.get("vessel_queue", []),
                yard_capacity_teu=p["yard_capacity_teu"],
                yard_occupancy_teu=p["yard_occupancy_teu"],
                congestion_index=p["congestion_index"],
                is_strike_active=p.get("is_strike_active", False),
                strike_capacity_factor=p.get("strike_capacity_factor", 1.0),
                is_closed=p.get("is_closed", False),
            )

        # Vessels
        for vid, v in data.get("vessels", {}).items():
            state.vessels[vid] = VesselState(
                vessel_id=v["vessel_id"],
                name=v["name"],
                status=v["status"],
                current_voyage_id=v.get("current_voyage_id"),
                current_port_id=v.get("current_port_id"),
                origin_port_id=v.get("origin_port_id"),
                destination_port_id=v.get("destination_port_id"),
                position_fraction=v.get("position_fraction", 0.0),
                distance_remaining_nm=v.get("distance_remaining_nm", 0.0),
                current_speed_knots=v.get("current_speed_knots", 18.0),
                base_speed_knots=v.get("base_speed_knots", 18.0),
                eta=parse_dt(v.get("eta")),
                eta_visibility=Visibility(v.get("eta_visibility", Visibility.INTERNAL_SIMULATION_KNOWN.value)),
                schedule_variance_hours=v.get("schedule_variance_hours", 0.0),
                current_load_teu=v.get("current_load_teu", 0.0),
                capacity_teu=v.get("capacity_teu", 0.0),
                condition=v.get("condition", "GOOD"),
                next_failure_at=v.get("next_failure_at"),
            )

        # Voyages
        for vyid, vy in data.get("voyages", {}).items():
            state.voyages[vyid] = VoyageState(
                voyage_id=vy["voyage_id"],
                vessel_id=vy["vessel_id"],
                origin_port_id=vy["origin_port_id"],
                destination_port_id=vy["destination_port_id"],
                scheduled_departure=parse_dt(vy["scheduled_departure"]),
                scheduled_arrival=parse_dt(vy["scheduled_arrival"]),
                actual_departure=parse_dt(vy.get("actual_departure")),
                estimated_arrival=parse_dt(vy.get("estimated_arrival")),
                actual_arrival=parse_dt(vy.get("actual_arrival")),
                status=vy.get("status", "SCHEDULED"),
                route_distance_nm=vy.get("route_distance_nm", 0.0),
                capacity_teu=vy.get("capacity_teu", 0.0),
                booked_teu=vy.get("booked_teu", 0.0),
                remaining_turnaround_hours=vy.get("remaining_turnaround_hours", 0.0),
                visibility=Visibility(vy.get("visibility", Visibility.INTERNAL_SIMULATION_KNOWN.value)),
            )

        # Containers
        for cid, c in data.get("containers", {}).items():
            state.containers[cid] = ContainerState(
                container_id=c["container_id"],
                equipment_type=c["equipment_type"],
                status=c["status"],
                condition=c.get("condition", "GOOD"),
                current_location_id=c.get("current_location_id"),
                current_voyage_id=c.get("current_voyage_id"),
                booking_id=c.get("booking_id"),
                allocation_id=c.get("allocation_id"),
                available_from=parse_dt(c.get("available_from")),
            )

        # Bookings
        for bid, b in data.get("bookings", {}).items():
            state.bookings[bid] = BookingState(
                booking_id=b["booking_id"],
                origin_port_id=b["origin_port_id"],
                destination_port_id=b["destination_port_id"],
                equipment_type=b["equipment_type"],
                quantity=b["quantity"],
                cargo_ready_time=parse_dt(b["cargo_ready_time"]),
                booking_time=parse_dt(b["booking_time"]),
                status=b.get("status", "SUBMITTED"),
                lock_status=b.get("lock_status", "UNLOCKED"),
                voyage_id=b.get("voyage_id"),
                allocation_id=b.get("allocation_id"),
                cutoff_time=parse_dt(b.get("cutoff_time")),
            )

        # Allocations
        for aid, a in data.get("allocations", {}).items():
            state.allocations[aid] = AllocationState(
                allocation_id=a["allocation_id"],
                booking_id=a["booking_id"],
                container_id=a["container_id"],
                voyage_id=a["voyage_id"],
                status=a.get("status", "ALLOCATED"),
                locked=a.get("locked", False),
            )

        # Equipment balances
        for eb in data.get("equipment", []):
            loc = eb["location_id"]
            eq_t = eb["equipment_type"]
            state.equipment[(loc, eq_t)] = EquipmentBalance(
                location_id=loc,
                equipment_type=eq_t,
                available=eb.get("available", 0),
                allocated=eb.get("allocated", 0),
                in_transit=eb.get("in_transit", 0),
                unavailable=eb.get("unavailable", 0),
                target=eb.get("target", 0),
            )

        # Demand
        dem_data = data.get("demand", {})
        cur_dem = {(item[0], item[1], item[2]): item[3] for item in dem_data.get("current", [])}
        hist_dem = {(item[0], item[1], item[2], item[3]): item[4] for item in dem_data.get("historical", [])}
        state.demand = DemandState(current_demand=cur_dem, historical_demand=hist_dem)

        # Leases
        for lid, l in data.get("leases", {}).items():
            state.leases[lid] = LeaseState(
                lease_id=l["lease_id"],
                location_id=l["location_id"],
                equipment_type=l["equipment_type"],
                quantity=l["quantity"],
                daily_rate=l["daily_rate"],
                start_time=parse_dt(l["start_time"]),
                duration_days=l["duration_days"],
                status=l.get("status", "PENDING"),
                equipment_available_at=parse_dt(l.get("equipment_available_at")),
            )

        # Repositioning
        for rid, r in data.get("repositioning_orders", {}).items():
            state.repositioning_orders[rid] = RepositioningState(
                reposition_id=r["reposition_id"],
                source_location_id=r["source_location_id"],
                destination_location_id=r["destination_location_id"],
                equipment_type=r["equipment_type"],
                quantity=r["quantity"],
                departure_time=parse_dt(r["departure_time"]),
                estimated_arrival=parse_dt(r["estimated_arrival"]),
                status=r.get("status", "IN_TRANSIT"),
            )

        return state

    # ------------------------------------------------------------------
    # PostgreSQL Persistence
    # ------------------------------------------------------------------

    async def persist_run(
        self,
        session: AsyncSession,
        run_id: UUID,
        world_id: str,
        scenario_id: str,
        random_seed: int,
        start_time: datetime,
        config_hash: str,
        baseline_id: Optional[UUID] = None,
    ) -> SimulationRun:
        """Write the SimulationRun record to PostgreSQL."""
        db_run = SimulationRun(
            id=run_id,
            world_id=world_id,
            baseline_id=baseline_id,
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
        self, session: AsyncSession, run_id: UUID, state: WorldState
    ) -> None:
        """Write initial VesselSimState rows to PostgreSQL."""
        for vessel_id, v in state.vessels.items():
            row = VesselSimState(
                run_id=run_id,
                vessel_id=vessel_id,
                name=v.name,
                status=v.status,
                current_voyage_id=v.current_voyage_id,
                current_port_id=v.current_port_id,
                origin_port_id=v.origin_port_id,
                destination_port_id=v.destination_port_id,
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
        self, session: AsyncSession, run_id: UUID, state: WorldState
    ) -> None:
        """Write initial PortSimState rows to PostgreSQL."""
        for port_id, p in state.ports.items():
            row = PortSimState(
                run_id=run_id,
                port_id=port_id,
                name=p.name,
                latitude=p.latitude,
                longitude=p.longitude,
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
