import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import models
from app.db.enums import (
    CompanyType,
    ContainerType,
    ContainerStatus,
    ContainerCondition,
    BookingPriority,
    BookingStatus,
    LocationType,
    OperationalStatus,
    VesselType,
    VesselStatus,
    VoyageStatus,
)
from app.test_worlds.world_1.fixtures import (
    World1Data,
    PortFixture,
    VesselFixture,
    VoyageLegFixture,
    BookingFixture,
    ContainerTypeSpec,
    get_world_1_dataset,
)

BASE_DATE = date(2026, 8, 1)


def reseed_world_1_db(db: Session) -> Dict[str, int]:
    """
    Clears all tables in cargo_pilot_test.db and seeds the canonical World 1 dataset.
    Returns counts of inserted records.
    """
    # 1. Truncate/Delete all tables in reverse dependency order
    table_deletions = [
        models.OptimizationBookingAllocation,
        models.OptimizationReposition,
        models.OptimizationLease,
        models.OptimizationInventory,
        models.OptimizationDemand,
        models.OptimizationRun,
        models.EquipmentAssignment,
        models.Booking,
        models.ContainerEvent,
        models.ContainerVoyageAssignment,
        models.ContainerCommitment,
        models.ExpectedContainerMovement,
        models.Container,
        models.VoyageLeg,
        models.VoyagePortCall,
        models.Voyage,
        models.Service,
        models.Vessel,
        models.CompanyLocation,
        models.Location,
        models.Company,
    ]

    for model_cls in table_deletions:
        db.query(model_cls).delete()
    db.commit()

    canonical_data = get_world_1_dataset()

    # 2. Seed Carrier & Customer Companies
    carrier = models.Company(
        name="CargoPilot Global Lines",
        company_type=CompanyType.CARRIER,
        is_self=True,
        hq_country="SG",
    )
    customer = models.Company(
        name="Global Forwarding Corp",
        company_type=CompanyType.CUSTOMER,
        is_self=False,
        hq_country="CN",
    )
    db.add_all([carrier, customer])
    db.flush()

    # 3. Seed 4 Ports / Locations
    location_map: Dict[str, models.Location] = {}
    for p in canonical_data.ports.values():
        loc = models.Location(
            name=p.name,
            location_type=LocationType.PORT,
            unlocode=p.unlocode,
            country=p.country,
            region=p.region,
            latitude=p.latitude,
            longitude=p.longitude,
            storage_capacity=p.storage_capacity_teu,
            safety_stock_teu=p.safety_stock_teu,
            devanning_lead_time_days=p.devanning_lead_time_days,
            lift_on_cost=p.lift_on_cost,
            lift_off_cost=p.lift_off_cost,
            operational_status=OperationalStatus.ACTIVE,
        )
        db.add(loc)
        location_map[p.unlocode] = loc
    db.flush()

    # Associate carrier with locations
    for loc in location_map.values():
        db.add(models.CompanyLocation(company_id=carrier.id, location_id=loc.id))
    db.flush()

    # 4. Seed 2 Vessels
    vessel_map: Dict[str, models.Vessel] = {}
    for v in canonical_data.vessels:
        vessel_obj = models.Vessel(
            name=v.name,
            imo_number=v.imo_number,
            vessel_type=v.vessel_type,
            container_capacity=v.container_capacity_teu,
            deadweight_capacity_mt=v.deadweight_capacity_mt,
            reefer_plugs=v.reefer_plugs,
            owner_company_id=carrier.id,
            operator_company_id=carrier.id,
            status=VesselStatus.ACTIVE,
        )
        db.add(vessel_obj)
        vessel_map[v.name] = vessel_obj
    db.flush()

    from app.scheduling.schedule_planner import generate_and_assign_fleet_schedule
    # 5 & 6. Run Upstream Service Schedule -> Voyage Generation -> Vessel Assignment Run
    schedule_res = generate_and_assign_fleet_schedule(db=db, horizon_days=canonical_data.horizon_days, firm_horizon_days=14, base_date=BASE_DATE)

    # 7. Seed 8 Bookings
    booking_objs = []
    for b in canonical_data.bookings:
        orig_loc = location_map[b.origin_unlocode]
        dest_loc = location_map[b.destination_unlocode]

        ready_dt = datetime.combine(BASE_DATE + timedelta(days=b.cargo_ready_day), datetime.min.time(), tzinfo=timezone.utc)
        cutoff_dt = datetime.combine(BASE_DATE + timedelta(days=b.cutoff_day), datetime.min.time(), tzinfo=timezone.utc)
        deadline_dt = datetime.combine(BASE_DATE + timedelta(days=b.delivery_deadline_day), datetime.min.time(), tzinfo=timezone.utc)

        b_obj = models.Booking(
            customer_company_id=customer.id,
            carrier_company_id=carrier.id,
            origin_location_id=orig_loc.id,
            destination_location_id=dest_loc.id,
            container_type=b.container_type,
            quantity=b.quantity,
            cargo_weight_mt=b.cargo_weight_mt,
            requested_pickup_date=ready_dt,
            required_delivery_date=deadline_dt,
            booking_cutoff_at=cutoff_dt,
            priority=b.priority,
            status=BookingStatus.CONFIRMED,
        )
        db.add(b_obj)
        booking_objs.append(b_obj)
    db.flush()

    # 8. Seed Initial Physical Container Assets
    container_count = 0
    for (port_code, ctype), qty in canonical_data.initial_inventory.items():
        loc = location_map[port_code]
        type_code = "20D" if ctype == ContainerType.DRY_20FT else "40D" if ctype == ContainerType.DRY_40FT else "40H"
        # Generate unique Container rows
        for i in range(qty):
            c_number = f"CP{port_code[:3]}{type_code}{i+1:04d}"
            db.add(
                models.Container(
                    container_number=c_number,
                    container_type=ctype,
                    owner_company_id=carrier.id,
                    current_location_id=loc.id,
                    status=ContainerStatus.AVAILABLE,
                    condition=ContainerCondition.CARGO_WORTHY,
                    controlled_by_carrier=True,
                )
            )
            container_count += 1

    db.commit()

    return {
        "ports": len(location_map),
        "vessels": len(vessel_map),
        "voyages": schedule_res.get("generated_voyages", 6),
        "voyage_legs": schedule_res.get("generated_legs", 18),
        "bookings": len(booking_objs),
        "containers": container_count,
    }


def load_world_1_from_db(db: Session) -> World1Data:
    """
    Reads all World 1 operational assets dynamically from cargo_pilot_test.db SQLite tables.
    Allows real-time reflection of admin edits, added voyages, modified bookings, and altered inventories!
    """
    canonical_base = get_world_1_dataset()

    # 1. Load Locations / Ports
    locations = db.query(models.Location).filter(models.Location.location_type == LocationType.PORT).all()
    ports_dict: Dict[str, PortFixture] = {}
    for loc in locations:
        code = loc.unlocode or loc.name[:5].upper()
        ports_dict[code] = PortFixture(
            unlocode=code,
            name=loc.name,
            country=loc.country,
            region=loc.region or "Asia-Pacific",
            latitude=loc.latitude or 0.0,
            longitude=loc.longitude or 0.0,
            storage_capacity_teu=loc.storage_capacity or 5000,
            safety_stock_teu=loc.safety_stock_teu,
            devanning_lead_time_days=loc.devanning_lead_time_days,
            lift_on_cost=loc.lift_on_cost,
            lift_off_cost=loc.lift_off_cost,
        )

    # 2. Load Vessels
    vessels = db.query(models.Vessel).all()
    vessels_list: List[VesselFixture] = []
    for v in vessels:
        vessels_list.append(
            VesselFixture(
                imo_number=v.imo_number,
                name=v.name,
                vessel_type=v.vessel_type,
                container_capacity_teu=v.container_capacity,
                deadweight_capacity_mt=v.deadweight_capacity_mt,
                reefer_plugs=v.reefer_plugs or 100,
            )
        )

    # 3. Load Voyage Legs
    legs_query = (
        db.query(models.VoyageLeg)
        .join(models.Voyage)
        .filter(models.Voyage.is_blank_sailing == False)  # Blank sailings are excluded dynamically from network!
        .all()
    )

    voyage_legs_list: List[VoyageLegFixture] = []
    for l in legs_query:
        voyage_num = l.voyage.voyage_number
        vessel_name = l.voyage.vessel.name if l.voyage.vessel else "MV Pacific Trader"
        from_unlocode = l.from_port_call.port.unlocode if l.from_port_call and l.from_port_call.port else "CNSHA"
        to_unlocode = l.to_port_call.port.unlocode if l.to_port_call and l.to_port_call.port else "SGSIN"

        dep_dt = l.from_port_call.departure_time if l.from_port_call else l.voyage.departure_time
        arr_dt = l.to_port_call.arrival_time if l.to_port_call else l.voyage.arrival_time

        dep_day = (dep_dt.date() - BASE_DATE).days if dep_dt else 0
        arr_day = (arr_dt.date() - BASE_DATE).days if arr_dt else dep_day + 5
        transit_days = max(1, arr_day - dep_day)

        leg_id_str = f"LEG-{voyage_num.replace('VOY_', '')}-{l.from_port_call.sequence if l.from_port_call else 1}"

        voyage_legs_list.append(
            VoyageLegFixture(
                leg_id=leg_id_str,
                voyage_number=voyage_num,
                vessel_name=vessel_name,
                from_port_unlocode=from_unlocode,
                to_port_unlocode=to_unlocode,
                departure_day=dep_day,
                arrival_day=arr_day,
                transit_days=transit_days,
                capacity_teu=l.total_capacity,
                capacity_weight_mt=l.deadweight_capacity_mt,
                booked_capacity_teu=l.booked_capacity,
                booked_weight_mt=l.booked_weight_mt,
            )
        )

    # 4. Load Bookings
    bookings_query = db.query(models.Booking).all()
    bookings_list: List[BookingFixture] = []
    for idx, b in enumerate(bookings_query):
        orig_code = b.origin_location.unlocode if b.origin_location else "CNSHA"
        dest_code = b.destination_location.unlocode if b.destination_location else "AEDXB"

        ready_day = (b.requested_pickup_date.date() - BASE_DATE).days if b.requested_pickup_date else 0
        cutoff_day = (b.booking_cutoff_at.date() - BASE_DATE).days if b.booking_cutoff_at else ready_day + 1
        deadline_day = (b.required_delivery_date.date() - BASE_DATE).days if b.required_delivery_date else ready_day + 20

        b_id_str = f"BK-{idx+1:02d}"

        bookings_list.append(
            BookingFixture(
                booking_id=b_id_str,
                origin_unlocode=orig_code,
                destination_unlocode=dest_code,
                container_type=b.container_type,
                quantity=b.quantity,
                cargo_ready_day=ready_day,
                cutoff_day=cutoff_day,
                delivery_deadline_day=deadline_day,
                priority=b.priority or BookingPriority.NORMAL,
                cargo_weight_mt=b.cargo_weight_mt or 15.0,
            )
        )

    # 5. Load Initial Inventories by counting physical container rows in DB
    initial_inv: Dict[Tuple[str, ContainerType], int] = {}
    for port_code in ports_dict.keys():
        for ctype in canonical_base.container_types.keys():
            count = (
                db.query(func.count(models.Container.id))
                .join(models.Location, models.Container.current_location_id == models.Location.id)
                .filter(
                    models.Location.unlocode == port_code,
                    models.Container.container_type == ctype,
                    models.Container.status == ContainerStatus.AVAILABLE,
                )
                .scalar()
            )
            initial_inv[(port_code, ctype)] = count if count is not None and count > 0 else canonical_base.initial_inventory.get((port_code, ctype), 0)

    # Merge into live World1Data
    return World1Data(
        base_date=BASE_DATE,
        horizon_days=canonical_base.horizon_days,
        ports=ports_dict if ports_dict else canonical_base.ports,
        container_types=canonical_base.container_types,
        vessels=vessels_list if vessels_list else canonical_base.vessels,
        voyage_legs=voyage_legs_list if voyage_legs_list else canonical_base.voyage_legs,
        bookings=bookings_list if bookings_list else canonical_base.bookings,
        initial_inventory=initial_inv if initial_inv else canonical_base.initial_inventory,
        repositioning_costs=canonical_base.repositioning_costs,
        leasing_costs=canonical_base.leasing_costs,
        holding_costs=canonical_base.holding_costs,
        shortage_penalties=canonical_base.shortage_penalties,
        safety_stock_penalty=canonical_base.safety_stock_penalty,
    )
