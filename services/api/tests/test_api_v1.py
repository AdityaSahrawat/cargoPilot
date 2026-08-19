import os
import sys
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from app.db.database import Base, get_db
from app.db import models, enums


@pytest.fixture(scope="function")
def client():
    # Use StaticPool to share single in-memory database across sessions
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed sample company & locations
    db = TestingSessionLocal()

    carrier = models.Company(
        name="Example Carrier",
        company_type=enums.CompanyType.CARRIER,
        is_self=True,
        hq_country="India",
        alliance="Example Alliance",
    )
    customer = models.Company(
        name="Customer Corp",
        company_type=enums.CompanyType.CUSTOMER,
        is_self=False,
    )
    lessor = models.Company(
        name="Lessor Corp",
        company_type=enums.CompanyType.LESSOR,
        is_self=False,
    )
    db.add_all([carrier, customer, lessor])
    db.commit()

    loc_mumbai = models.Location(
        name="Mumbai",
        location_type=enums.LocationType.PORT,
        unlocode="INBOM",
        country="India",
        region="West",
        latitude=18.95,
        longitude=72.95,
        operational_status=enums.OperationalStatus.ACTIVE,
    )
    loc_dubai = models.Location(
        name="Dubai",
        location_type=enums.LocationType.PORT,
        unlocode="AEDXB",
        country="UAE",
        operational_status=enums.OperationalStatus.ACTIVE,
    )
    db.add_all([loc_mumbai, loc_dubai])
    db.commit()

    # Vessel & Service
    vessel = models.Vessel(
        imo_number="1234567",
        name="Example Vessel",
        owner_company_id=carrier.id,
        operator_company_id=carrier.id,
        vessel_type=enums.VesselType.CONTAINER_SHIP,
        container_capacity=8000,
        status=enums.VesselStatus.ACTIVE,
    )
    service = models.Service(
        name="Asia-ME Service",
        operator_company_id=carrier.id,
        status=enums.ServiceStatus.ACTIVE,
    )
    db.add_all([vessel, service])
    db.commit()

    # Voyage & Port Calls & Leg
    now = datetime.utcnow()
    voyage = models.Voyage(
        service_id=service.id,
        vessel_id=vessel.id,
        voyage_number="V123",
        departure_time=now,
        arrival_time=now + timedelta(days=7),
        status=enums.VoyageStatus.SCHEDULED,
    )
    db.add(voyage)
    db.commit()

    call1 = models.VoyagePortCall(
        voyage_id=voyage.id,
        port_id=loc_mumbai.id,
        sequence=1,
        arrival_time=now,
        departure_time=now + timedelta(hours=12),
    )
    call2 = models.VoyagePortCall(
        voyage_id=voyage.id,
        port_id=loc_dubai.id,
        sequence=2,
        arrival_time=now + timedelta(days=3),
        departure_time=now + timedelta(days=3, hours=12),
    )
    db.add_all([call1, call2])
    db.commit()

    leg = models.VoyageLeg(
        voyage_id=voyage.id,
        from_port_call_id=call1.id,
        to_port_call_id=call2.id,
        total_capacity=500,
        booked_capacity=350,
    )
    db.add(leg)
    db.commit()

    # Container
    cnt = models.Container(
        container_number="MSCU1234567",
        container_type=enums.ContainerType.DRY_40FT,
        owner_company_id=carrier.id,
        current_location_id=loc_mumbai.id,
        status=enums.ContainerStatus.AVAILABLE,
        condition=enums.ContainerCondition.CARGO_WORTHY,
        available_from=now,
    )
    db.add(cnt)
    db.commit()

    # Booking
    booking = models.Booking(
        customer_company_id=customer.id,
        carrier_company_id=carrier.id,
        origin_location_id=loc_mumbai.id,
        destination_location_id=loc_dubai.id,
        container_type=enums.ContainerType.DRY_40FT,
        quantity=20,
        requested_pickup_date=now,
        voyage_id=voyage.id,
        status=enums.BookingStatus.CONFIRMED,
    )
    db.add(booking)
    db.commit()

    # Lease
    lease = models.Lease(
        lessor_company_id=lessor.id,
        lessee_company_id=carrier.id,
        container_type=enums.ContainerType.DRY_40FT,
        quantity=100,
        start_date=now,
        pickup_location_id=loc_dubai.id,
        return_location_id=loc_dubai.id,
        cost_per_unit=40.0,
    )
    db.add(lease)
    db.commit()

    db.close()

    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_group_1_company_and_locations(client):
    res = client.get("/api/v1/company")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Example Carrier"
    assert data["companyType"] == "CARRIER"

    res = client.get("/api/v1/locations")
    assert res.status_code == 200
    locs = res.json()
    assert len(locs) >= 2
    assert locs[0]["name"] in ["Mumbai", "Dubai"]

    loc_id = locs[0]["id"]
    res = client.get(f"/api/v1/locations/{loc_id}")
    assert res.status_code == 200
    assert res.json()["id"] == loc_id


def test_group_2_containers_and_inventory(client):
    res = client.get("/api/v1/containers")
    assert res.status_code == 200
    data = res.json()
    assert "data" in data
    assert data["total"] == 1
    cnt = data["data"][0]
    assert cnt["containerNumber"] == "MSCU1234567"
    assert cnt["containerType"] == "40FT_DRY"

    cnt_id = cnt["id"]
    res = client.get(f"/api/v1/containers/{cnt_id}")
    assert res.status_code == 200
    assert res.json()["id"] == cnt_id

    res = client.get("/api/v1/inventory")
    assert res.status_code == 200
    inv = res.json()
    assert len(inv) >= 1
    assert "available" in inv[0]


def test_group_3_vessels_services_voyages(client):
    # Vessels
    res = client.get("/api/v1/vessels")
    assert res.status_code == 200
    vessels = res.json()
    assert len(vessels) == 1
    vessel_id = vessels[0]["id"]

    res = client.get(f"/api/v1/vessels/{vessel_id}")
    assert res.status_code == 200

    # Services
    res = client.get("/api/v1/services")
    assert res.status_code == 200
    services = res.json()
    assert len(services) == 1
    service_id = services[0]["id"]

    res = client.get(f"/api/v1/services/{service_id}")
    assert res.status_code == 200

    # Voyages
    res = client.get("/api/v1/voyages")
    assert res.status_code == 200
    voyages = res.json()
    assert len(voyages) == 1
    voyage_id = voyages[0]["id"]

    res = client.get(f"/api/v1/voyages/{voyage_id}")
    assert res.status_code == 200

    res = client.get(f"/api/v1/voyages/{voyage_id}/port-calls")
    assert res.status_code == 200
    calls = res.json()
    assert len(calls) == 2

    res = client.get(f"/api/v1/voyages/{voyage_id}/legs")
    assert res.status_code == 200
    legs = res.json()
    assert len(legs) == 1
    assert legs[0]["availableCapacity"] == 150


def test_group_4_bookings_and_assignments(client):
    res = client.get("/api/v1/bookings")
    assert res.status_code == 200
    bookings = res.json()["data"]
    assert len(bookings) == 1
    booking_id = bookings[0]["id"]

    res = client.get(f"/api/v1/bookings/{booking_id}")
    assert res.status_code == 200

    cnt_res = client.get("/api/v1/containers")
    cnt_id = cnt_res.json()["data"][0]["id"]

    # Assign
    res = client.post("/api/v1/assignments", json={"containerId": cnt_id, "bookingId": booking_id})
    assert res.status_code == 201
    assign_id = res.json()["id"]

    res = client.get(f"/api/v1/bookings/{booking_id}/assignments")
    assert res.status_code == 200
    assert len(res.json()) == 1

    res = client.get("/api/v1/assignments")
    assert res.status_code == 200
    assert len(res.json()) == 1

    # Release
    res = client.post(f"/api/v1/assignments/{assign_id}/release")
    assert res.status_code == 200
    assert res.json()["releasedAt"] is not None


def test_group_5_container_events(client):
    cnt_res = client.get("/api/v1/containers")
    cnt_id = cnt_res.json()["data"][0]["id"]
    loc_res = client.get("/api/v1/locations")
    loc_id = loc_res.json()[0]["id"]

    event_payload = {
        "containerId": cnt_id,
        "eventType": "GATE_IN",
        "timestamp": datetime.utcnow().isoformat(),
        "locationId": loc_id,
        "metadataJson": {"seal": "SL-100"},
    }

    res = client.post("/api/v1/container-events", json=event_payload)
    assert res.status_code == 201
    assert res.json()["eventType"] == "GATE_IN"

    res = client.get(f"/api/v1/containers/{cnt_id}/events")
    assert res.status_code == 200
    events = res.json()
    assert len(events) == 1


def test_group_6_leasing(client):
    res = client.get("/api/v1/leases")
    assert res.status_code == 200
    leases = res.json()
    assert len(leases) == 1
    lease_id = leases[0]["id"]

    res = client.get(f"/api/v1/leases/{lease_id}")
    assert res.status_code == 200


def test_group_7_demand_and_forecast(client):
    loc_res = client.get("/api/v1/locations")
    loc_id = loc_res.json()[0]["id"]

    fc_payload = {
        "locationId": loc_id,
        "containerType": "40FT_DRY",
        "week": "2026-W40",
        "quantity": 35,
        "confidence": 0.75,
    }

    res = client.post("/api/v1/demand/forecast", json=fc_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["quantity"] == 35
    fc_id = data["id"]

    res = client.get("/api/v1/demand/forecast")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    res = client.patch(f"/api/v1/demand/forecast/{fc_id}", json={"quantity": 40})
    assert res.status_code == 200
    assert res.json()["quantity"] == 40


def test_group_8_optimization(client):
    run_req = {
        "startWeek": "2026-W35",
        "horizonWeeks": 10,
    }

    res = client.post("/api/v1/optimization/runs", json=run_req)
    assert res.status_code == 201
    run_data = res.json()
    run_id = run_data["runId"]

    res = client.get("/api/v1/optimization/runs")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    res = client.get(f"/api/v1/optimization/runs/{run_id}")
    assert res.status_code == 200
    assert res.json()["status"] == "COMPLETED"

    res = client.get(f"/api/v1/optimization/runs/{run_id}/plan")
    assert res.status_code == 200
    plan = res.json()
    assert "repositioning" in plan
    assert "leasing" in plan
    assert "inventory" in plan
    assert "demand" in plan

    res = client.post(f"/api/v1/optimization/runs/{run_id}/approve", json={"comment": "Approved"})
    assert res.status_code == 200
    assert res.json()["status"] == "APPROVED"


def test_group_9_dashboard(client):
    res = client.get("/api/v1/dashboard/overview")
    assert res.status_code == 200
    overview = res.json()
    assert "activeBookings" in overview
    assert "upcomingVoyages" in overview

    res = client.get("/api/v1/dashboard/alerts")
    assert res.status_code == 200
    alerts = res.json()
    assert isinstance(alerts, list)
