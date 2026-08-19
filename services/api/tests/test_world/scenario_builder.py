from datetime import datetime, date, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.db import models, enums
from tests.test_world.reference_data import load_reference_ports, load_reference_vessels


class ScenarioBuilder:
    """Builds miniature world database state for CargoPilot test scenarios."""

    def __init__(self, db: Session):
        self.db = db
        self.companies: Dict[str, models.Company] = {}
        self.locations: Dict[str, models.Location] = {}
        self.vessels: Dict[str, models.Vessel] = {}
        self.services: Dict[str, models.Service] = {}
        self.voyages: Dict[str, models.Voyage] = {}
        self.legs: Dict[str, models.VoyageLeg] = {}

    def setup_base_world(self):
        """Seed 3 Companies, 5 Ports, 3 Vessels, Services, and default containers."""
        # 1. Companies
        carrier = models.Company(
            name="Global Carrier Line",
            company_type=enums.CompanyType.CARRIER,
            is_self=True,
            hq_country="Singapore",
        )
        customer = models.Company(
            name="Acme Trading Co",
            company_type=enums.CompanyType.CUSTOMER,
            is_self=False,
        )
        lessor = models.Company(
            name="Global Container Lease Ltd",
            company_type=enums.CompanyType.LESSOR,
            is_self=False,
        )
        self.db.add_all([carrier, customer, lessor])
        self.db.commit()
        self.companies = {"carrier": carrier, "customer": customer, "lessor": lessor}

        # 2. Reference Ports
        ports_data = load_reference_ports()
        for p in ports_data:
            loc = models.Location(
                name=p["name"],
                location_type=enums.LocationType(p["locationType"]),
                unlocode=p["unlocode"],
                country=p["country"],
                region=p.get("region"),
                latitude=p.get("latitude"),
                longitude=p.get("longitude"),
                storage_capacity=p.get("storageCapacity"),
                repair_capability=p.get("repairCapability"),
                operational_status=enums.OperationalStatus(p["operationalStatus"]),
            )
            self.db.add(loc)
            self.db.commit()
            self.locations[p["unlocode"]] = loc

        # 3. Reference Vessels
        vessels_data = load_reference_vessels()
        for v in vessels_data:
            vessel = models.Vessel(
                imo_number=v["imoNumber"],
                name=v["name"],
                owner_company_id=carrier.id,
                operator_company_id=carrier.id,
                vessel_type=enums.VesselType(v["vesselType"]),
                container_capacity=v["containerCapacity"],
                status=enums.VesselStatus(v["status"]),
            )
            self.db.add(vessel)
            self.db.commit()
            self.vessels[v["imoNumber"]] = vessel

        # 4. Service & Voyages
        svc_ame = models.Service(
            name="Asia-Middle East Express",
            operator_company_id=carrier.id,
            status=enums.ServiceStatus.ACTIVE,
        )
        self.db.add(svc_ame)
        self.db.commit()
        self.services["AME"] = svc_ame

        now = datetime.utcnow()
        voyage1 = models.Voyage(
            service_id=svc_ame.id,
            vessel_id=self.vessels["IMO9811000"].id,
            voyage_number="V100",
            departure_time=now,
            arrival_time=now + timedelta(days=10),
            status=enums.VoyageStatus.SCHEDULED,
        )
        self.db.add(voyage1)
        self.db.commit()
        self.voyages["V100"] = voyage1

        # Port calls: Shanghai (1) -> Singapore (2) -> Dubai (3)
        call1 = models.VoyagePortCall(
            voyage_id=voyage1.id,
            port_id=self.locations["CNSHA"].id,
            sequence=1,
            arrival_time=now,
            departure_time=now + timedelta(hours=12),
        )
        call2 = models.VoyagePortCall(
            voyage_id=voyage1.id,
            port_id=self.locations["SGSIN"].id,
            sequence=2,
            arrival_time=now + timedelta(days=4),
            departure_time=now + timedelta(days=4, hours=12),
        )
        call3 = models.VoyagePortCall(
            voyage_id=voyage1.id,
            port_id=self.locations["AEDXB"].id,
            sequence=3,
            arrival_time=now + timedelta(days=9),
            departure_time=now + timedelta(days=9, hours=12),
        )
        self.db.add_all([call1, call2, call3])
        self.db.commit()

        leg1 = models.VoyageLeg(
            voyage_id=voyage1.id,
            from_port_call_id=call1.id,
            to_port_call_id=call2.id,
            total_capacity=500,
            booked_capacity=200,
        )
        leg2 = models.VoyageLeg(
            voyage_id=voyage1.id,
            from_port_call_id=call2.id,
            to_port_call_id=call3.id,
            total_capacity=500,
            booked_capacity=200,
        )
        self.db.add_all([leg1, leg2])
        self.db.commit()
        self.legs["SHA-SIN"] = leg1
        self.legs["SIN-DXB"] = leg2

        # 5. Seed Containers (25 containers across ports)
        for i in range(1, 26):
            loc_key = "CNSHA" if i <= 15 else "AEDXB"
            cnt = models.Container(
                container_number=f"MSCU9900{i:03d}",
                container_type=enums.ContainerType.DRY_40FT,
                owner_company_id=carrier.id,
                current_location_id=self.locations[loc_key].id,
                status=enums.ContainerStatus.AVAILABLE,
                condition=enums.ContainerCondition.CARGO_WORTHY,
                available_from=now,
            )
            self.db.add(cnt)
        self.db.commit()

    def build_scenario_capacity_shortage(self):
        """Scenario 2: High booked capacity leaves minimal space for empty repositioning."""
        self.setup_base_world()
        leg1 = self.legs["SHA-SIN"]
        leg1.booked_capacity = 480  # Only 20 TEU available out of 500
        self.db.commit()

    def build_scenario_demand_spike(self):
        """Scenario 5: Demand surge in Dubai with low available inventory."""
        self.setup_base_world()
        # Add high demand forecast for Dubai
        fc = models.DemandForecast(
            company_id=self.companies["carrier"].id,
            location_id=self.locations["AEDXB"].id,
            container_type=enums.ContainerType.DRY_40FT,
            week=date.today(),
            quantity=80,
            confidence=0.90,
        )
        self.db.add(fc)
        self.db.commit()
