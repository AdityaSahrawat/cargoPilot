import os
import sys
import uuid
from datetime import datetime, date, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure app module is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.database import Base
from app.db import models, schemas, enums


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite database session for testing schema integrity."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_full_v1_database_schema(db_session):
    # 1. Company
    carrier = models.Company(
        name="Global Ocean Lines",
        company_type=enums.CompanyType.CARRIER,
        is_self=True,
        hq_country="SG",
        alliance="Ocean Alliance",
    )
    customer = models.Company(
        name="Acme Importers",
        company_type=enums.CompanyType.CUSTOMER,
        is_self=False,
        hq_country="US",
    )
    lessor = models.Company(
        name="ContainerLease Co",
        company_type=enums.CompanyType.LESSOR,
        is_self=False,
        hq_country="DE",
    )
    db_session.add_all([carrier, customer, lessor])
    db_session.commit()

    # Verify Pydantic schema validation
    carrier_pydantic = schemas.CompanyResponse.model_validate(carrier)
    assert carrier_pydantic.name == "Global Ocean Lines"
    assert carrier_pydantic.is_self is True

    # 2. Location & CompanyLocation
    port_shanghai = models.Location(
        name="Port of Shanghai",
        location_type=enums.LocationType.PORT,
        unlocode="CNSHA",
        country="CN",
        latitude=31.2304,
        longitude=121.4737,
        operational_status=enums.OperationalStatus.ACTIVE,
    )
    port_singapore = models.Location(
        name="Port of Singapore",
        location_type=enums.LocationType.PORT,
        unlocode="SGSIN",
        country="SG",
        latitude=1.3521,
        longitude=103.8198,
        operational_status=enums.OperationalStatus.ACTIVE,
    )
    depot_dubai = models.Location(
        name="Dubai Central Depot",
        location_type=enums.LocationType.DEPOT,
        unlocode="AEDXB",
        country="AE",
        storage_capacity=5000,
        repair_capability=True,
        operational_status=enums.OperationalStatus.ACTIVE,
    )
    db_session.add_all([port_shanghai, port_singapore, depot_dubai])
    db_session.commit()

    comp_loc = models.CompanyLocation(
        company_id=carrier.id,
        location_id=port_singapore.id,
        is_home_port=True,
    )
    db_session.add(comp_loc)
    db_session.commit()
    assert len(carrier.company_locations) == 1

    # 3. Vessel & Service & Voyage & PortCalls & Legs
    vessel = models.Vessel(
        imo_number="IMO9876543",
        name="CargoPilot Express",
        owner_company_id=carrier.id,
        operator_company_id=carrier.id,
        vessel_type=enums.VesselType.ULCV,
        container_capacity=18000,
        status=enums.VesselStatus.ACTIVE,
    )
    service = models.Service(
        name="Asia - Middle East Express",
        operator_company_id=carrier.id,
        status=enums.ServiceStatus.ACTIVE,
    )
    db_session.add_all([vessel, service])
    db_session.commit()

    now = datetime.utcnow()
    voyage = models.Voyage(
        service_id=service.id,
        vessel_id=vessel.id,
        voyage_number="V001",
        departure_time=now,
        arrival_time=now + timedelta(days=10),
        status=enums.VoyageStatus.IN_PROGRESS,
    )
    db_session.add(voyage)
    db_session.commit()

    port_call1 = models.VoyagePortCall(
        voyage_id=voyage.id,
        port_id=port_shanghai.id,
        sequence=1,
        arrival_time=now,
        departure_time=now + timedelta(hours=12),
    )
    port_call2 = models.VoyagePortCall(
        voyage_id=voyage.id,
        port_id=port_singapore.id,
        sequence=2,
        arrival_time=now + timedelta(days=5),
        departure_time=now + timedelta(days=5, hours=12),
    )
    db_session.add_all([port_call1, port_call2])
    db_session.commit()

    leg = models.VoyageLeg(
        voyage_id=voyage.id,
        from_port_call_id=port_call1.id,
        to_port_call_id=port_call2.id,
        total_capacity=5000,
        booked_capacity=3200,
    )
    db_session.add(leg)
    db_session.commit()

    # Check hybrid property
    assert leg.available_capacity == 1800
    leg_pydantic = schemas.VoyageLegResponse.model_validate(leg)
    assert leg_pydantic.available_capacity == 1800

    # 4. Container & Events
    container = models.Container(
        container_number="MSCU1234567",
        container_type=enums.ContainerType.DRY_40FT,
        owner_company_id=carrier.id,
        current_location_id=port_shanghai.id,
        status=enums.ContainerStatus.AVAILABLE,
        condition=enums.ContainerCondition.CARGO_WORTHY,
        available_from=now,
    )
    db_session.add(container)
    db_session.commit()

    event = models.ContainerEvent(
        container_id=container.id,
        event_type=enums.ContainerEventType.GATE_IN,
        timestamp=now,
        location_id=port_shanghai.id,
        metadata_json={"driver": "John Doe", "seal": "SL-9988"},
    )
    db_session.add(event)
    db_session.commit()
    assert len(container.events) == 1

    # 5. Booking & EquipmentAssignment
    booking = models.Booking(
        customer_company_id=customer.id,
        carrier_company_id=carrier.id,
        origin_location_id=port_shanghai.id,
        destination_location_id=port_singapore.id,
        container_type=enums.ContainerType.DRY_40FT,
        quantity=5,
        requested_pickup_date=now + timedelta(days=1),
        voyage_id=voyage.id,
        priority=enums.BookingPriority.HIGH,
        status=enums.BookingStatus.CONFIRMED,
    )
    db_session.add(booking)
    db_session.commit()

    assignment = models.EquipmentAssignment(
        container_id=container.id,
        booking_id=booking.id,
        assigned_at=now,
    )
    db_session.add(assignment)
    db_session.commit()
    assert assignment.container.container_number == "MSCU1234567"

    # 6. Lease
    lease = models.Lease(
        lessor_company_id=lessor.id,
        lessee_company_id=carrier.id,
        container_type=enums.ContainerType.DRY_40FT,
        quantity=100,
        start_date=now,
        pickup_location_id=port_shanghai.id,
        cost_per_unit=12.50,
    )
    db_session.add(lease)
    db_session.commit()
    assert lease.cost_per_unit == 12.50

    # 7. DemandForecast
    forecast = models.DemandForecast(
        company_id=carrier.id,
        location_id=depot_dubai.id,
        container_type=enums.ContainerType.DRY_40FT,
        week=date(2026, 9, 1),
        quantity=35,
        confidence=0.85,
    )
    db_session.add(forecast)
    db_session.commit()

    # 8. OptimizationRun & Results
    opt_run = models.OptimizationRun(
        company_id=carrier.id,
        start_week=date(2026, 9, 1),
        horizon_weeks=8,
        status=enums.OptimizationStatus.COMPLETED,
        objective_value=145200.50,
    )
    db_session.add(opt_run)
    db_session.commit()

    opt_repo = models.OptimizationReposition(
        run_id=opt_run.id,
        voyage_leg_id=leg.id,
        container_type=enums.ContainerType.DRY_40FT,
        quantity=50,
        departure_week=date(2026, 9, 1),
    )
    opt_lease = models.OptimizationLease(
        run_id=opt_run.id,
        lease_id=lease.id,
        location_id=port_shanghai.id,
        container_type=enums.ContainerType.DRY_40FT,
        quantity=20,
        week=date(2026, 9, 1),
    )
    opt_inv = models.OptimizationInventory(
        run_id=opt_run.id,
        location_id=port_shanghai.id,
        container_type=enums.ContainerType.DRY_40FT,
        week=date(2026, 9, 1),
        quantity=150,
    )
    opt_dem = models.OptimizationDemand(
        run_id=opt_run.id,
        location_id=port_shanghai.id,
        container_type=enums.ContainerType.DRY_40FT,
        week=date(2026, 9, 1),
        confirmed_served=30,
        forecast_served=20,
        forecast_backlog=5,
        confirmed_shortage=0,
    )
    db_session.add_all([opt_repo, opt_lease, opt_inv, opt_dem])
    db_session.commit()

    assert len(opt_run.repositions) == 1
    assert len(opt_run.leases) == 1
    assert len(opt_run.inventories) == 1
    assert len(opt_run.demands) == 1
