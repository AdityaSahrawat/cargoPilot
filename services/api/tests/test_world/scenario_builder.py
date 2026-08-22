from datetime import datetime, date, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.db import models, enums
from tests.test_world.reference_data import (
    load_reference_ports,
    load_reference_vessels,
    load_reference_services,
    load_reference_voyages,
    load_reference_voyage_legs,
    load_reference_containers,
    load_reference_container_commitments,
    load_reference_container_assignments,
    load_reference_expected_container_movements,
    load_reference_leases,
    load_reference_procurement_orders,
    load_reference_procurement_recommendations,
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
        """Seed Companies, Ports, Vessels, Services, Voyages, Containers, Leases, Procurement, Commitments, Expected Movements, Routes & Closures."""
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
        lessor2 = models.Company(
            name="AsiaContainer Rentals",
            company_type=enums.CompanyType.LESSOR,
            is_self=False,
        )
        other_carrier = models.Company(
            name="Alliance Transport Line",
            company_type=enums.CompanyType.ALLIANCE_PARTNER,
            is_self=False,
        )
        self.db.add_all([carrier, customer, lessor, lessor2, other_carrier])
        self.db.commit()
        self.companies = {
            "carrier": carrier,
            "customer": customer,
            "lessor": lessor,
            "lessor2": lessor2,
            "other_carrier": other_carrier,
            "COMP_LESSOR_01": lessor,
            "COMP_LESSOR_02": lessor2,
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
        vessel_by_imo = {}
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
            vessel_by_imo[v["imoNumber"]] = vessel

        # 4. Service & Voyages
        services_data = load_reference_services()
        service_by_id = {}
        for s in services_data:
            svc = models.Service(
                name=s["name"],
                operator_company_id=carrier.id,
                status=enums.ServiceStatus(s["status"]),
            )
            self.db.add(svc)
            self.db.commit()
            service_by_id[s["id"]] = svc
            self.services[s["id"]] = svc

        voyages_data = load_reference_voyages()
        for vy in voyages_data:
            svc_obj = service_by_id.get(vy["serviceId"])
            ves_obj = vessel_by_imo.get(vy["vesselImo"])
            exp_arr = datetime.fromisoformat(vy["expectedArrivalTime"].replace("Z", "+00:00")) if vy.get("expectedArrivalTime") else None
            voyage = models.Voyage(
                service_id=svc_obj.id if svc_obj else list(service_by_id.values())[0].id,
                vessel_id=ves_obj.id if ves_obj else list(vessel_by_imo.values())[0].id,
                voyage_number=vy["voyageNumber"],
                departure_time=datetime.fromisoformat(vy["departureTime"].replace("Z", "+00:00")),
                arrival_time=datetime.fromisoformat(vy["arrivalTime"].replace("Z", "+00:00")),
                expected_arrival_time=exp_arr,
                is_blank_sailing=vy.get("isBlankSailing", False),
                status=enums.VoyageStatus(vy["status"]),
            )
            self.db.add(voyage)
            self.db.commit()
            self.voyages[vy["id"]] = voyage

            # Add port calls if operating voyage
            if not vy.get("isBlankSailing", False):
                dep_dt = datetime.fromisoformat(vy["departureTime"].replace("Z", "+00:00"))
                arr_dt = datetime.fromisoformat(vy["arrivalTime"].replace("Z", "+00:00"))
                call_from = models.VoyagePortCall(
                    voyage_id=voyage.id,
                    port_id=self.locations["INMAA"].id,
                    sequence=1,
                    arrival_time=dep_dt - timedelta(hours=4),
                    departure_time=dep_dt,
                )
                call_to = models.VoyagePortCall(
                    voyage_id=voyage.id,
                    port_id=self.locations["AEDXB"].id,
                    sequence=2,
                    arrival_time=arr_dt,
                    departure_time=arr_dt + timedelta(hours=4),
                )
                self.db.add_all([call_from, call_to])
                self.db.commit()

        # Seed Voyage Legs
        legs_data = load_reference_voyage_legs()
        for lg in legs_data:
            vy_obj = self.voyages.get(lg["voyageId"])
            if vy_obj and vy_obj.port_calls and len(vy_obj.port_calls) >= 2:
                leg = models.VoyageLeg(
                    voyage_id=vy_obj.id,
                    from_port_call_id=vy_obj.port_calls[0].id,
                    to_port_call_id=vy_obj.port_calls[1].id,
                    total_capacity=lg["totalCapacity"],
                    booked_capacity=lg["bookedCapacity"],
                    accessible_capacity=lg.get("accessibleCapacity"),
                    alliance_slots=lg.get("allianceSlots", 0),
                    alliance_cost_adjustment=lg.get("allianceCostAdjustment", 0.0),
                )
                self.db.add(leg)
                self.db.commit()
                self.legs[lg["id"]] = leg

        # Seed Leases
        leases_data = load_reference_leases()
        for lz in leases_data:
            lessor_c = self.companies.get(lz["lessorCompanyId"], lessor)
            pickup_l = self.locations.get(lz["pickupUnlocode"])
            return_l = self.locations.get(lz["returnUnlocode"])
            start_dt = datetime.fromisoformat(lz["startDate"].replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(lz["endDate"].replace("Z", "+00:00")) if lz.get("endDate") else None
            if pickup_l:
                lease_obj = models.Lease(
                    lessor_company_id=lessor_c.id,
                    lessee_company_id=carrier.id,
                    container_type=enums.ContainerType(lz["containerType"]),
                    quantity=lz["quantity"],
                    start_date=start_dt,
                    end_date=end_dt,
                    pickup_location_id=pickup_l.id,
                    return_location_id=return_l.id if return_l else None,
                    cost_per_unit=lz["costPerUnit"],
                    minimum_duration_days=lz.get("minimumDurationDays", 30),
                    early_return_allowed=lz.get("earlyReturnAllowed", True),
                    early_return_fee=lz.get("earlyReturnFee", 0.0),
                )
                self.db.add(lease_obj)
        self.db.commit()

        # Seed Procurement Orders
        po_data = load_reference_procurement_orders()
        for po in po_data:
            deliv_l = self.locations.get(po["deliveryUnlocode"])
            if deliv_l:
                po_obj = models.ProcurementOrder(
                    po_number=po["poNumber"],
                    supplier_name=po["supplierName"],
                    container_type=enums.ContainerType(po["containerType"]),
                    quantity=po["quantity"],
                    order_date=date.fromisoformat(po["orderDate"]),
                    expected_delivery=date.fromisoformat(po["expectedDelivery"]),
                    delivery_location_id=deliv_l.id,
                    unit_price=po["unitPrice"],
                    status=po.get("status", "IN_PRODUCTION"),
                )
                self.db.add(po_obj)
        self.db.commit()

        # Seed Procurement Recommendations
        rec_data = load_reference_procurement_recommendations()
        for pr in rec_data:
            rec_l = self.locations.get(pr["recommendedUnlocode"])
            if rec_l:
                pr_obj = models.ProcurementRecommendation(
                    recommendation_code=pr["recommendationCode"],
                    container_type=enums.ContainerType(pr["containerType"]),
                    quantity=pr["quantity"],
                    recommended_location_id=rec_l.id,
                    required_by_week=pr["requiredByWeek"],
                    recommended_order_by_date=pr["recommendedOrderByDate"],
                    reason=pr.get("reason"),
                )
                self.db.add(pr_obj)
        self.db.commit()

        now = datetime.utcnow()

        # 5. Seed Specific Test Containers (CONT_001 to CONT_024)
        containers_data = load_reference_containers()
        for c in containers_data:
            owner_id = carrier.id if c["controlledByCarrier"] else other_carrier.id
            loc = self.locations.get(c["unlocode"])
            avail_dt = datetime.fromisoformat(c["availableFrom"].replace("Z", "+00:00")) if c.get("availableFrom") else None
            cnt = models.Container(
                container_number=c["containerNumber"],
                container_type=enums.ContainerType(c["containerType"]),
                owner_company_id=owner_id,
                current_location_id=loc.id if loc else None,
                status=enums.ContainerStatus(c["status"]),
                condition=enums.ContainerCondition(c["condition"]),
                controlled_by_carrier=c["controlledByCarrier"],
                customs_hold=c["customsHold"],
                is_emergency_reserve=c.get("isEmergencyReserve", False),
                available_from=avail_dt,
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

        # Seed Container Voyage Assignments (CVA_001, CVA_002)
        assignments_data = load_reference_container_assignments()
        for cva in assignments_data:
            cnt_obj = self.containers.get(cva["containerId"])
            vy_obj = self.voyages.get(cva["voyageId"])
            if cnt_obj and vy_obj:
                cva_obj = models.ContainerVoyageAssignment(
                    container_id=cnt_obj.id,
                    voyage_id=vy_obj.id,
                    status=cva.get("status", "COMMITTED"),
                )
                self.db.add(cva_obj)
        self.db.commit()

        # Seed Expected Container Movements (ECM_001 to ECM_004)
        expected_movements_data = load_reference_expected_container_movements()
        for ecm in expected_movements_data:
            cnt_obj = self.containers.get(ecm["containerId"])
            from_loc = self.locations.get(ecm.get("fromUnlocode"))
            to_loc = self.locations.get(ecm.get("toUnlocode"))
            vy_obj = self.voyages.get(ecm.get("voyageId"))
            if cnt_obj:
                ecm_obj = models.ExpectedContainerMovement(
                    container_id=cnt_obj.id,
                    from_location_id=from_loc.id if from_loc else None,
                    to_location_id=to_loc.id if to_loc else None,
                    voyage_id=vy_obj.id if vy_obj else None,
                    planned_date=datetime.fromisoformat(ecm["plannedDate"].replace("Z", "+00:00")),
                    expected_date=datetime.fromisoformat(ecm["expectedDate"].replace("Z", "+00:00")),
                    status=ecm.get("status", "EXPECTED"),
                )
                self.db.add(ecm_obj)
        self.db.commit()

        # Seed additional containers up to 25+ for total fleet size compatibility
        for i in range(25, 31):
            loc_key = "CNSHA" if i <= 27 else "AEDXB"
            cnt = models.Container(
                container_number=f"MSCU9900{i:03d}",
                container_type=enums.ContainerType.DRY_40FT,
                owner_company_id=carrier.id,
                current_location_id=self.locations[loc_key].id,
                status=enums.ContainerStatus.AVAILABLE,
                condition=enums.ContainerCondition.CARGO_WORTHY,
                controlled_by_carrier=True,
                customs_hold=False,
                is_emergency_reserve=False,
                available_from=now,
            )
            self.db.add(cnt)
        self.db.commit()

    def build_scenario_capacity_shortage(self):
        """Scenario 2: High booked capacity leaves minimal space for empty repositioning."""
        self.setup_base_world()
        if "LEG_001" in self.legs:
            leg1 = self.legs["LEG_001"]
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
