import pytest
from fastapi.testclient import TestClient
from main import app
from app.db.database import TestSessionLocal, Base, test_engine
from app.test_worlds.world_1.db_seeder import reseed_world_1_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestSessionLocal()
    reseed_world_1_db(db)
    db.close()
    yield


def test_test_admin_db_status_and_reset():
    # 1. Check DB status
    res = client.get("/api/v1/test-admin/db-status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ACTIVE"
    assert data["counts"]["ports"] == 4
    assert data["counts"]["vessels"] == 2
    assert data["counts"]["bookings"] == 33

    # 2. Reset DB
    res_reset = client.post("/api/v1/test-admin/reset-db")
    assert res_reset.status_code == 200
    assert res_reset.json()["status"] == "success"
    assert res_reset.json()["records_seeded"]["bookings"] == 33


def test_test_admin_bookings_crud():
    # 1. List bookings
    res = client.get("/api/v1/test-admin/bookings")
    assert res.status_code == 200
    bookings = res.json()["bookings"]
    assert len(bookings) == 33

    # 2. Create a new booking
    new_b_payload = {
        "origin_unlocode": "CNSHA",
        "destination_unlocode": "AEDXB",
        "container_type": "40FT_DRY",
        "quantity": 30,
        "cargo_weight_mt": 16.0,
        "cargo_ready_day": 2,
        "cutoff_day": 3,
        "delivery_deadline_day": 24,
        "priority": "HIGH",
    }
    create_res = client.post("/api/v1/test-admin/bookings", json=new_b_payload)
    assert create_res.status_code == 200
    booking_id = create_res.json()["booking_id"]
    assert booking_id is not None

    # Check that count increased to 34
    res2 = client.get("/api/v1/test-admin/bookings")
    assert len(res2.json()["bookings"]) == 34

    # 3. Update the booking
    update_res = client.put(f"/api/v1/test-admin/bookings/{booking_id}", json={"quantity": 35, "priority": "CRITICAL"})
    assert update_res.status_code == 200

    # 4. Delete the booking
    del_res = client.delete(f"/api/v1/test-admin/bookings/{booking_id}")
    assert del_res.status_code == 200

    # Count back to 33
    res3 = client.get("/api/v1/test-admin/bookings")
    assert len(res3.json()["bookings"]) == 33


def test_test_admin_voyages_and_inventory():
    # 1. List voyages
    res = client.get("/api/v1/test-admin/voyages")
    assert res.status_code == 200
    voyages = res.json()["voyages"]
    assert len(voyages) == 6

    # 2. Adjust inventory
    inv_res = client.post(
        "/api/v1/test-admin/inventory/adjust",
        json={
            "port_unlocode": "CNSHA",
            "container_type": "20FT_DRY",
            "quantity_change": 15,
        },
    )
    assert inv_res.status_code == 200
    assert inv_res.json()["status"] == "success"

    # 3. Check inventory
    inv_list = client.get("/api/v1/test-admin/inventory")
    assert inv_list.status_code == 200
    assert len(inv_list.json()["inventory"]) > 0
