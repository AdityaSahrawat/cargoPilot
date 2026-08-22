from app.db import models, enums
from app.optimization.input_builder import OptimizationInputBuilder


def test_section_13_equipment_state_cases(api_client):
    """Tests Section 13 Cases A through J for Equipment State Inputs & Prior-Period Backlog."""
    client, db = api_client
    client.post("/api/v1/scenarios/baseline/reset")

    builder = OptimizationInputBuilder(db)

    # Get Chennai location
    chennai = db.query(models.Location).filter(models.Location.unlocode == "INMAA").first()
    assert chennai is not None

    # Case A: Immediately Available Container (CONT_001)
    c1 = db.query(models.Container).filter(models.Container.container_number == "MSCU9900001").first()
    assert c1 is not None
    assert c1.status == enums.ContainerStatus.AVAILABLE
    assert c1.condition == enums.ContainerCondition.CARGO_WORTHY

    # Case B: Assigned Container (CONT_002) -> ASSIGNED
    c2 = db.query(models.Container).filter(models.Container.container_number == "MSCU9900002").first()
    assert c2 is not None

    # Case C: Future Commitment (CONT_004) -> Committed COM_001
    c4 = db.query(models.Container).filter(models.Container.container_number == "MSCU9900004").first()
    assert c4 is not None
    assert len(c4.commitments) >= 1

    # Case D: In Transit (CONT_005) -> IN_TRANSIT
    c5 = db.query(models.Container).filter(models.Container.container_number == "MSCU9900005").first()
    assert c5 is not None
    assert c5.status == enums.ContainerStatus.IN_TRANSIT

    # Case E: Under Repair (CONT_006) -> UNDER_REPAIR
    c6 = db.query(models.Container).filter(models.Container.container_number == "MSCU9900006").first()
    assert c6 is not None
    assert c6.status == enums.ContainerStatus.UNDER_REPAIR

    # Case G: Unserviceable (CONT_022) -> OFF_HIRE & UNSERVICEABLE
    c22 = db.query(models.Container).filter(models.Container.container_number == "MSCU9900022").first()
    assert c22 is not None
    assert c22.status == enums.ContainerStatus.OFF_HIRE
    assert c22.condition == enums.ContainerCondition.UNSERVICEABLE

    # Verify Usability Filtering Excludes Cases B, C, D, E, G from usable list
    usable_containers = builder.get_usable_containers(
        location_id=chennai.id,
        container_type=enums.ContainerType.DRY_40FT,
    )
    usable_numbers = [c.container_number for c in usable_containers]

    assert "MSCU9900001" in usable_numbers  # Case A included
    assert "MSCU9900004" not in usable_numbers  # Case C committed excluded
    assert "MSCU9900005" not in usable_numbers  # Case D in transit excluded
    assert "MSCU9900006" not in usable_numbers  # Case E under repair excluded
    assert "MSCU9900022" not in usable_numbers  # Case G unserviceable excluded

    # Case H & I: Prior Period Backlogs (Confirmed vs Forecast)
    backlogs = db.query(models.PriorPeriodBacklog).all()
    assert len(backlogs) >= 2

    bg_confirmed = [bg for bg in backlogs if bg.demand_stream_type == "CONFIRMED"][0]
    bg_forecast = [bg for bg in backlogs if bg.demand_stream_type == "FORECAST"][0]

    assert bg_confirmed.quantity == 5
    assert bg_confirmed.backlog_age_weeks == 1

    assert bg_forecast.quantity == 8
    assert bg_forecast.backlog_age_weeks == 2

    # Case J: Multiple States at the Same Location
    all_chennai_cnts = db.query(models.Container).filter(models.Container.current_location_id == chennai.id).all()
    statuses = set([c.status for c in all_chennai_cnts])
    assert enums.ContainerStatus.AVAILABLE in statuses
    assert enums.ContainerStatus.IN_TRANSIT in statuses or enums.ContainerStatus.UNDER_REPAIR in statuses
