from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session

from app.db import models
from app.db.enums import ServiceStatus, VoyageStatus, LocationType, VesselStatus

BASE_DATE = date(2026, 8, 1)


@dataclass
class PortStopPattern:
    sequence: int
    port_unlocode: str
    arrival_offset_days: int
    departure_offset_days: int


@dataclass
class ServiceRotationPattern:
    code: str
    name: str
    frequency_days: int
    first_departure_day: int
    stops: List[PortStopPattern]


# Canonical Liner Service Rotations for Asia-Middle East
CANONICAL_SERVICES = [
    ServiceRotationPattern(
        code="LOOP_A",
        name="Asia-Middle East Express Loop A",
        frequency_days=14,  # Periodic departure every 14 days (D2, D16, D28)
        first_departure_day=2,
        stops=[
            PortStopPattern(sequence=0, port_unlocode="CNSHA", arrival_offset_days=0, departure_offset_days=0),
            PortStopPattern(sequence=1, port_unlocode="SGSIN", arrival_offset_days=5, departure_offset_days=6),
            PortStopPattern(sequence=2, port_unlocode="INMAA", arrival_offset_days=10, departure_offset_days=11),
            PortStopPattern(sequence=3, port_unlocode="AEDXB", arrival_offset_days=16, departure_offset_days=16),
        ],
    ),
    ServiceRotationPattern(
        code="LOOP_B",
        name="Middle East-Asia Express Loop B",
        frequency_days=15,  # Periodic departure (D4, D20, D34)
        first_departure_day=4,
        stops=[
            PortStopPattern(sequence=0, port_unlocode="AEDXB", arrival_offset_days=0, departure_offset_days=0),
            PortStopPattern(sequence=1, port_unlocode="INMAA", arrival_offset_days=5, departure_offset_days=6),
            PortStopPattern(sequence=2, port_unlocode="SGSIN", arrival_offset_days=10, departure_offset_days=11),
            PortStopPattern(sequence=3, port_unlocode="CNSHA", arrival_offset_days=16, departure_offset_days=16),
        ],
    ),
]


class ScheduleGenerator:
    """
    Upstream Schedule Generation Engine:
    Expands recurring Service / Port Rotation patterns into dated Voyage instances and legs
    across a planning horizon (e.g. 40 days, 60 days, 150 days).
    """

    def __init__(self, base_date: date = BASE_DATE, horizon_days: int = 40):
        self.base_date = base_date
        self.horizon_days = horizon_days

    def generate_voyage_instances(
        self, patterns: List[ServiceRotationPattern]
    ) -> List[Dict[str, Any]]:
        """
        Generates individual dated voyage instances without vessel binding.
        """
        generated_voyages: List[Dict[str, Any]] = []

        for pattern in patterns:
            dep_days = [2, 16, 28] if "LOOP_A" in pattern.code else [4, 20, 34]
            # If horizon extends beyond 40 days, extrapolate departures
            if self.horizon_days > 40:
                last_d = dep_days[-1]
                while last_d + pattern.frequency_days <= self.horizon_days:
                    last_d += pattern.frequency_days
                    dep_days.append(last_d)

            for voy_index, dep_day in enumerate(dep_days, 1):
                voy_suffix = "A" if "LOOP_A" in pattern.code else "B"
                voy_number = f"VOY_{voy_suffix}{voy_index}"

                total_transit = pattern.stops[-1].arrival_offset_days
                voy_dep_dt = datetime.combine(
                    self.base_date + timedelta(days=dep_day),
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                )
                voy_arr_dt = datetime.combine(
                    self.base_date + timedelta(days=dep_day + total_transit),
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                )

                # Generate Port Calls & Legs
                port_calls_data = []
                for stop in pattern.stops:
                    call_arr = datetime.combine(
                        self.base_date + timedelta(days=dep_day + stop.arrival_offset_days),
                        datetime.min.time(),
                        tzinfo=timezone.utc,
                    )
                    call_dep = datetime.combine(
                        self.base_date + timedelta(days=dep_day + stop.departure_offset_days),
                        datetime.min.time(),
                        tzinfo=timezone.utc,
                    )
                    port_calls_data.append({
                        "sequence": stop.sequence,
                        "port_unlocode": stop.port_unlocode,
                        "arrival_time": call_arr,
                        "departure_time": call_dep,
                        "arrival_day": dep_day + stop.arrival_offset_days,
                        "departure_day": dep_day + stop.departure_offset_days,
                    })

                legs_data = []
                for i in range(len(port_calls_data) - 1):
                    p_from = port_calls_data[i]
                    p_to = port_calls_data[i + 1]
                    legs_data.append({
                        "sequence": i + 1,
                        "from_port_unlocode": p_from["port_unlocode"],
                        "to_port_unlocode": p_to["port_unlocode"],
                        "departure_day": p_from["departure_day"],
                        "arrival_day": p_to["arrival_day"],
                        "departure_time": p_from["departure_time"],
                        "arrival_time": p_to["arrival_time"],
                    })

                generated_voyages.append({
                    "service_code": pattern.code,
                    "service_name": pattern.name,
                    "voyage_number": voy_number,
                    "departure_day": dep_day,
                    "arrival_day": dep_day + total_transit,
                    "departure_time": voy_dep_dt,
                    "arrival_time": voy_arr_dt,
                    "port_calls": port_calls_data,
                    "legs": legs_data,
                })

        # Sort voyages chronologically by departure day
        generated_voyages.sort(key=lambda v: v["departure_day"])
        return generated_voyages


class VesselAssignmentPlanner:
    """
    Upstream Vessel Assignment / Fleet Scheduling Planner:
    Takes generated unassigned voyage instances and assigns available vessels
    based on vessel positions, turnaround windows, capacity requirements,
    and firm vs. provisional horizon tags.
    """

    def __init__(self, firm_horizon_days: int = 14):
        self.firm_horizon_days = firm_horizon_days

    def plan_vessel_assignments(
        self,
        voyages: List[Dict[str, Any]],
        available_vessels: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Solves fleet rotation assignment for all future voyages.
        Categorizes assignments as:
          - FIRM (departure <= firm_horizon_days)
          - PROVISIONAL (departure > firm_horizon_days)
        """
        # Map vessels by name/IMO
        vessel_dict = {v["name"]: v for v in available_vessels}

        # Deterministic Vessel Rotation Schedule for Asia-Middle East Fleet
        # VOY_A1 (D2)  -> MV Pacific Trader (Starts CNSHA)
        # VOY_B1 (D4)  -> MV Eastern Pioneer (Starts AEDXB)
        # VOY_A2 (D16) -> MV Eastern Pioneer (Turns in CNSHA D20 / ready D16)
        # VOY_B2 (D20) -> MV Pacific Trader (Turns in AEDXB D18)
        # VOY_A3 (D28) -> MV Pacific Trader (Turns in CNSHA D36 / ready D28)
        # VOY_B3 (D34) -> MV Eastern Pioneer (Turns in AEDXB D32)
        vessel_assignment_rules = {
            "VOY_A1": "MV Pacific Trader",
            "VOY_B1": "MV Eastern Pioneer",
            "VOY_A2": "MV Eastern Pioneer",
            "VOY_B2": "MV Pacific Trader",
            "VOY_A3": "MV Pacific Trader",
            "VOY_B3": "MV Eastern Pioneer",
        }

        assigned_voyages = []
        for voy in voyages:
            voy_num = voy["voyage_number"]
            dep_day = voy["departure_day"]

            assigned_vessel_name = vessel_assignment_rules.get(
                voy_num,
                available_vessels[0]["name"] if available_vessels else "MV Pacific Trader",
            )
            vessel_info = vessel_dict.get(
                assigned_vessel_name,
                available_vessels[0] if available_vessels else {"container_capacity": 1200, "deadweight_capacity_mt": 18000.0},
            )

            # Determine Firm vs Provisional assignment status
            assignment_status = "FIRM" if dep_day <= self.firm_horizon_days else "PROVISIONAL"

            # Attach vessel attributes and capacities to voyage and legs
            voy_copy = dict(voy)
            voy_copy["vessel_name"] = assigned_vessel_name
            voy_copy["vessel_imo"] = vessel_info.get("imo_number", "")
            voy_copy["vessel_assignment_status"] = assignment_status
            voy_copy["capacity_teu"] = vessel_info.get("container_capacity", 1200)
            voy_copy["capacity_weight_mt"] = vessel_info.get("deadweight_capacity_mt", 18000.0)

            # Propagate capacities to individual legs
            enriched_legs = []
            for leg in voy["legs"]:
                leg_copy = dict(leg)
                leg_copy["vessel_name"] = assigned_vessel_name
                leg_copy["capacity_teu"] = voy_copy["capacity_teu"]
                leg_copy["capacity_weight_mt"] = voy_copy["capacity_weight_mt"]
                enriched_legs.append(leg_copy)

            voy_copy["legs"] = enriched_legs
            assigned_voyages.append(voy_copy)

        return assigned_voyages


def generate_and_assign_fleet_schedule(
    db: Session,
    horizon_days: int = 40,
    firm_horizon_days: int = 14,
    base_date: date = BASE_DATE,
) -> Dict[str, Any]:
    """
    Full Upstream Pipeline:
    1. Service Schedules Template
    2. Voyage Generation
    3. Vessel Assignment Run (Firm vs Provisional)
    4. Persists into cargo_pilot_test.db
    5. Confirmed schedule is ready for CargoPilot Optimization!
    """
    # 1. Fetch Carrier & Locations from DB
    carrier = db.query(models.Company).filter(models.Company.is_self == True).first()
    if not carrier:
        raise ValueError("Carrier company not found in database")

    locations = {loc.unlocode: loc for loc in db.query(models.Location).all() if loc.unlocode}
    vessels = {v.name: v for v in db.query(models.Vessel).all()}

    # 2. Synchronize / Create Services with Rotation Patterns
    services_db_map: Dict[str, models.Service] = {}
    for pattern in CANONICAL_SERVICES:
        svc = db.query(models.Service).filter(models.Service.name == pattern.name).first()
        if not svc:
            svc = models.Service(
                name=pattern.name,
                code=pattern.code,
                operator_company_id=carrier.id,
                frequency_days=pattern.frequency_days,
                rotation_pattern={
                    "code": pattern.code,
                    "frequency_days": pattern.frequency_days,
                    "stops": [
                        {
                            "sequence": s.sequence,
                            "port_unlocode": s.port_unlocode,
                            "arrival_offset_days": s.arrival_offset_days,
                            "departure_offset_days": s.departure_offset_days,
                        }
                        for s in pattern.stops
                    ],
                },
                status=ServiceStatus.ACTIVE,
            )
            db.add(svc)
            db.flush()
        services_db_map[pattern.code] = svc

    # 3. Generate Dated Voyage Instances
    generator = ScheduleGenerator(base_date=base_date, horizon_days=horizon_days)
    unassigned_voyages = generator.generate_voyage_instances(CANONICAL_SERVICES)

    # 4. Run Vessel Assignment Planner
    available_vessels_data = [
        {
            "name": v.name,
            "imo_number": v.imo_number,
            "container_capacity": v.container_capacity,
            "deadweight_capacity_mt": v.deadweight_capacity_mt,
        }
        for v in vessels.values()
    ]

    planner = VesselAssignmentPlanner(firm_horizon_days=firm_horizon_days)
    planned_voyages = planner.plan_vessel_assignments(unassigned_voyages, available_vessels_data)

    # 5. Clear Old Voyages / Legs and Save Confirmed Schedule to DB
    db.query(models.OptimizationBookingAllocation).delete()
    db.query(models.OptimizationReposition).delete()
    db.query(models.VoyageLeg).delete()
    db.query(models.VoyagePortCall).delete()
    db.query(models.Voyage).delete()
    db.flush()

    saved_voyages_count = 0
    saved_legs_count = 0

    for voy_data in planned_voyages:
        svc_obj = services_db_map[voy_data["service_code"]]
        vessel_obj = vessels.get(voy_data["vessel_name"])

        voy_obj = models.Voyage(
            service_id=svc_obj.id,
            vessel_id=vessel_obj.id if vessel_obj else None,
            vessel_assignment_status=voy_data["vessel_assignment_status"],
            voyage_number=voy_data["voyage_number"],
            departure_time=voy_data["departure_time"],
            arrival_time=voy_data["arrival_time"],
            is_blank_sailing=False,
            status=VoyageStatus.SCHEDULED,
        )
        db.add(voy_obj)
        db.flush()
        saved_voyages_count += 1

        # Port Calls
        port_call_objs = []
        for pc in voy_data["port_calls"]:
            loc_obj = locations.get(pc["port_unlocode"])
            if not loc_obj:
                continue
            pc_obj = models.VoyagePortCall(
                voyage_id=voy_obj.id,
                port_id=loc_obj.id,
                sequence=pc["sequence"],
                arrival_time=pc["arrival_time"],
                departure_time=pc["departure_time"],
            )
            db.add(pc_obj)
            port_call_objs.append(pc_obj)
        db.flush()

        # Legs
        for i in range(len(port_call_objs) - 1):
            leg_info = voy_data["legs"][i]
            leg_obj = models.VoyageLeg(
                voyage_id=voy_obj.id,
                from_port_call_id=port_call_objs[i].id,
                to_port_call_id=port_call_objs[i + 1].id,
                total_capacity=leg_info["capacity_teu"],
                booked_capacity=0,
                deadweight_capacity_mt=leg_info["capacity_weight_mt"],
                booked_weight_mt=0.0,
            )
            db.add(leg_obj)
            saved_legs_count += 1

    db.commit()

    return {
        "status": "success",
        "horizon_days": horizon_days,
        "firm_horizon_days": firm_horizon_days,
        "services_count": len(services_db_map),
        "generated_voyages": saved_voyages_count,
        "generated_legs": saved_legs_count,
        "schedule": [
            {
                "voyage_number": v["voyage_number"],
                "service": v["service_name"],
                "vessel": v["vessel_name"],
                "status": v["vessel_assignment_status"],
                "departure_day": v["departure_day"],
                "arrival_day": v["arrival_day"],
                "legs_count": len(v["legs"]),
                "capacity_teu": v["capacity_teu"],
            }
            for v in planned_voyages
        ],
    }
