"""
Integration tests for Simulation REST API.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "cargopilot-simulation"


@pytest.mark.asyncio
async def test_api_full_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Start simulation
        start_resp = await client.post(
            "/api/v1/simulation/start",
            json={"scenario_id": "NORMAL", "seed": 42},
        )
        assert start_resp.status_code == 200
        start_data = start_resp.json()
        assert "run_id" in start_data
        assert start_data["ports_count"] == 55
        assert start_data["vessels_count"] == 18

        # 2. Check status
        status_resp = await client.get("/api/v1/simulation/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "RUNNING"

        # 3. Advance 24 hours
        adv_resp = await client.post(
            "/api/v1/simulation/advance",
            json={"delta_hours": 24.0},
        )
        assert adv_resp.status_code == 200
        adv_data = adv_resp.json()
        assert "simulation_time" in adv_data

        # 4. Check state
        state_resp = await client.get("/api/v1/simulation/state")
        assert state_resp.status_code == 200
        state_data = state_resp.json()
        assert state_data["vessels_count"] == 18
        assert state_data["ports_count"] == 55

        # 5. Check ports endpoint
        ports_resp = await client.get("/api/v1/simulation/state/ports")
        assert ports_resp.status_code == 200
        ports = ports_resp.json()
        assert len(ports) == 55

        # 6. Check vessels endpoint
        vessels_resp = await client.get("/api/v1/simulation/state/vessels")
        assert vessels_resp.status_code == 200
        vessels = vessels_resp.json()
        assert len(vessels) == 18

        # 6b. Check voyages, demand, leases, equipment endpoints
        voyages_resp = await client.get("/api/v1/simulation/state/voyages")
        assert voyages_resp.status_code == 200

        demand_resp = await client.get("/api/v1/simulation/state/demand")
        assert demand_resp.status_code == 200
        assert "current_demand" in demand_resp.json()

        leases_resp = await client.get("/api/v1/simulation/state/leases")
        assert leases_resp.status_code == 200

        equipment_resp = await client.get("/api/v1/simulation/state/equipment")
        assert equipment_resp.status_code == 200
        assert len(equipment_resp.json()) > 0

        # 7. Inject disruption
        dis_resp = await client.post(
            "/api/v1/simulation/inject-disruption",
            json={
                "disruption_type": "STORM",
                "severity": 0.5,
                "duration_hours": 24.0,
                "affected_entity_ids": ["V001"],
            },
        )
        assert dis_resp.status_code == 202
        assert "disruption_id" in dis_resp.json()

        # 8. Check config endpoints
        params_resp = await client.get("/api/v1/simulation/config/parameters")
        assert params_resp.status_code == 200
        assert len(params_resp.json()) > 20

        scenarios_resp = await client.get("/api/v1/simulation/config/scenarios")
        assert scenarios_resp.status_code == 200
        assert len(scenarios_resp.json()) == 7

        dt_resp = await client.get("/api/v1/simulation/config/disruption-types")
        assert dt_resp.status_code == 200
        assert len(dt_resp.json()) == 6

        # 9. Pause, resume, reset
        pause_resp = await client.post("/api/v1/simulation/pause")
        assert pause_resp.status_code == 200

        resume_resp = await client.post("/api/v1/simulation/resume")
        assert resume_resp.status_code == 200

        reset_resp = await client.post("/api/v1/simulation/reset")
        assert reset_resp.status_code == 200
