import pytest
from fastapi.testclient import TestClient


def test_simulation_world_1_summary(api_client):
    client, db = api_client
    response = client.get("/api/v1/simulation/world-1/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["world_id"] == "WORLD-01"
    assert len(data["ports"]) == 4
    assert len(data["vessels"]) == 2
    assert len(data["voyage_legs"]) == 18
    assert len(data["bookings"]) == 33


def test_simulation_world_1_solve_milp(api_client):
    client, db = api_client
    response = client.post("/api/v1/simulation/world-1/solve-milp")
    assert response.status_code == 200
    data = response.json()
    assert data["solver_status"] == "Optimal"
    assert data["optimality_gap"] == 0.0
    assert data["objective_value"] > 0
    assert len(data["booking_decisions"]) >= 33


def test_simulation_world_1_run_and_day_lookup(api_client):
    client, db = api_client
    response = client.post("/api/v1/simulation/world-1/run")
    assert response.status_code == 200
    data = response.json()
    assert data["total_days"] == 41  # Day 0 through Day 40
    assert len(data["snapshots"]) == 41

    # Check day 0 snapshot
    snap0 = data["snapshots"][0]
    assert snap0["day"] == 0
    assert "CNSHA" in snap0["port_inventories"]
    assert snap0["port_inventories"]["CNSHA"]["20FT_DRY"] == 700.0

    # Check day 2 snapshot lookup
    response_day2 = client.get("/api/v1/simulation/world-1/day/2")
    assert response_day2.status_code == 200
    d2 = response_day2.json()
    assert d2["day"] == 2
