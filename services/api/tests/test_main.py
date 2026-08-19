import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app


def test_root():
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
