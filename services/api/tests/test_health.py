from fastapi.testclient import TestClient
import os

from app.main import app


client = TestClient(app)


def test_health_aggregate_no_env():
    # Ensure env vars are not set for a predictable result
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("KAFKA_BOOTSTRAP_SERVERS", None)

    r = client.get("/health/")
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("degraded", "ok")
    assert isinstance(body.get("components"), list)


def test_readiness_when_db_missing():
    os.environ.pop("DATABASE_URL", None)
    r = client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ready") is False


def test_liveness():
    r = client.get("/health/live")
    assert r.status_code == 200
    assert r.json().get("live") is True
