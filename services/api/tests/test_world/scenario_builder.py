from datetime import datetime, date, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.db import models, enums
from tests.test_world.reference_data import (
    load_reference_ports,
    load_reference_vessels,
    load_reference_containers,
    load_reference_container_commitments,
    load_reference_location_closures,
    load_reference_network_routes,
)


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
        self.containers: Dict[str, models.Container] = {}

    def setup_base_world(self):
        """Seed 3 Companies, Ports, Vessels, Services, Containers, Commitments, Routes & Closures."""
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
        other_carrier = models.Company(
            name="Alliance Transport Line",
            company_type=enums.CompanyType.ALLIANCE_PARTNER,
            is_self=False,
        )
        self.db.add_all([carrier, customer, lessor, other_carrier])
        self.db.commit()
        self.companies = {
            "carrier": carrier,
            "customer": customer,
            "lessor": lessor,
            "other_carrier": other_carrier,
        }

        # 2. Reference Ports & Depots
        ports_data = load_reference_ports()
        for p in ports_data:
            parent_loc = self.locations.get(p.get("parentUnlocode")) if p.get("parentUnlocode") else None
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
                operating_hours=p.get("operatingHours"),
                pickup_hours=p.get("pickupHours"),
                return_hours=p.get("returnHours"),
                closed_days=p.get("closedDays"),
                parent_location_id=parent_loc.id if parent_loc else None,
                operational_status=enums.OperationalStatus(p["operationalStatus"]),
            )
            self.db.add(loc)
            self.db.commit()
            self.locations[p["unlocode"]] = loc

        # Seed Location Closure Windows
        closures_data = load_reference_location_closures()
        for cw in closures_data:
            target_loc = self.locations.get(cw["unlocode"])
            if target_loc:
                cw_obj = models.LocationClosureWindow(
                    location_id=target_loc.id,
                    start_time=datetime.fromisoformat(cw["startTime"].replace("Z", "+00:00")),
                    end_time=datetime.fromisoformat(cw["endTime"].replace("Z", "+00:00")),
                    reason=cw.get("reason"),
                )
                self.db.add(cw_obj)
        self.db.commit()

        # Seed Network Routes
        routes_data = load_reference_network_routes()
        for r in routes_data:
            from_loc = self.locations.get(r["fromUnlocode"])
            to_loc = self.locations.get(r["toUnlocode"])
            if from_loc and to_loc:
                nr = models.NetworkRoute(
                    from_location_id=from_loc.id,
                    to_location_id=to_loc.id,
                    transport_mode=r.get("transportMode", "TRUCK"),
                    lead_time_days=r.get("leadTimeDays", 1),
                    cost_per_container=r.get("costPerContainer", 1000.0),
                    daily_capacity=r.get("dailyCapacity", 50),
                    is_connected=r.get("isConnected", True),
                )
                self.db.add(nr)
        self.db.commit()

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

        # 5. Seed Specific Test Containers (CONT_001 to CONT_010)
        containers_data = load_reference_containers()
        for c in containers_data:
            owner_id = carrier.id if c["controlledByCarrier"] else other_carrier.id
            loc = self.locations.get(c["unlocode"])
            cnt = models.Container(
                container_number=c["containerNumber"],
                container_type=enums.ContainerType(c["containerType"]),
                owner_company_id=owner_id,
                current_location_id=loc.id if loc else None,
                status=enums.ContainerStatus(c["status"]),
                condition=enums.ContainerCondition(c["condition"]),
                controlled_by_carrier=c["controlledByCarrier"],
                customs_hold=c["customsHold"],
                available_from=datetime.fromisoformat(c["availableFrom"].replace("Z", "+00:00")),
            )
            self.db.add(cnt)
            self.db.commit()
            self.containers[c["id"]] = cnt

        # Seed commitments (COM_001 for CONT_004)
        commitments_data = load_reference_container_commitments()
        for cm in commitments_data:
            cnt_obj = self.containers.get(cm["containerId"])
            req_loc = self.locations.get(cm["requiredUnlocode"])
            if cnt_obj:
                comm = models.ContainerCommitment(
                    container_id=cnt_obj.id,
                    commitment_type=enums.CommitmentType(cm["commitmentType"]),
                    reference_id=cm["referenceId"],
                    required_location_id=req_loc.id if req_loc else None,
                    required_at=datetime.fromisoformat(cm["requiredAt"].replace("Z", "+00:00")),
                    status=enums.CommitmentStatus(cm["status"]),
                )
                self.db.add(comm)
        self.db.commit()

        # Seed additional containers up to 25 for total fleet size compatibility
        for i in range(11, 26):
            loc_key = "CNSHA" if i <= 18 else "AEDXB"
            cnt = models.Container(
                container_number=f"MSCU9900{i:03d}",
                container_type=enums.ContainerType.DRY_40FT,
                owner_company_id=carrier.id,
                current_location_id=self.locations[loc_key].id,
                status=enums.ContainerStatus.AVAILABLE,
                condition=enums.ContainerCondition.CARGO_WORTHY,
                controlled_by_carrier=True,
                customs_hold=False,
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
