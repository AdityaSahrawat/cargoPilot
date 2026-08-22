import json
import os
from typing import List, Dict, Any

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))


def load_reference_ports() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "ports.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_vessels() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "vessels.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_containers() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "containers.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_container_commitments() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "container_commitments.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_bookings() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "bookings.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_demand_forecasts() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "demand_forecasts.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_import_returns() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "import_returns.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_location_closures() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "location_closure_windows.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_network_routes() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "network_routes.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
