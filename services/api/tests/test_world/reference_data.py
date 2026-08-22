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


def load_reference_services() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "services.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_voyages() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "voyages.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_voyage_legs() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "voyage_legs.json")
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


def load_reference_container_assignments() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "container_voyage_assignments.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_expected_container_movements() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "expected_container_movements.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_leases() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "leases.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_procurement_orders() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "procurement_orders.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_procurement_recommendations() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "procurement_recommendations.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_repositioning_options() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "repositioning_options.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_repositioning_commitments() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "repositioning_commitments.json")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_reference_surplus_shortage_profiles() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "weekly_surplus_shortage_profiles.json")
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


def load_reference_consolidated_supply_streams() -> List[Dict[str, Any]]:
    file_path = os.path.join(DATA_DIR, "consolidated_supply_streams.json")
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
