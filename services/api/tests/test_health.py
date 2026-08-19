import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app

client = TestClient(app)


def test_health_aggregate_no_env():
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
