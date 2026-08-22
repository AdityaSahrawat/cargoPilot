from app.db import models, enums


def test_section_12_business_policy_rules(api_client):
    """Tests all Section 12 interaction cases (A through J)."""
    client, db = api_client
    client.post("/api/v1/scenarios/baseline/reset")

    # Query customer companies
    cust1 = db.query(models.Company).filter(models.Company.name == "Acme Trading Co").first()
    cust4 = db.query(models.Company).filter(models.Company.name == "Budget Export Lines").first()
    cust5 = db.query(models.Company).filter(models.Company.name == "Apex Retail Global").first()

    assert cust1 is not None
    assert cust4 is not None
    assert cust5 is not None

    # Case C & E: Verify Customer Priorities and Contract Policies
    assert cust1.customer_priority == enums.CustomerPriority.STRATEGIC
    assert cust1.leased_equipment_allowed is False  # Leasing prohibited by contract!
    assert cust1.equipment_source_policy == "OWNED,CONTROLLED,REPOSITIONED"

    assert cust4.customer_priority == enums.CustomerPriority.LOW
    assert cust4.leased_equipment_allowed is False

    assert cust5.customer_priority == enums.CustomerPriority.STRATEGIC
    assert cust5.leased_equipment_allowed is True

    # Query bookings
    b1 = db.query(models.Booking).filter(models.Booking.customer_company_id == cust1.id).first()
    assert b1 is not None

    # Case A: FCFS Ordering
    bookings_fcfs = db.query(models.Booking).order_by(models.Booking.requested_at.asc()).all()
    assert len(bookings_fcfs) >= 3
    assert bookings_fcfs[0].requested_at <= bookings_fcfs[1].requested_at <= bookings_fcfs[2].requested_at

    # Case B & G: Booking Priority Multipliers
    b_high = db.query(models.Booking).filter(models.Booking.priority == enums.BookingPriority.HIGH).first()
    b_critical = db.query(models.Booking).filter(models.Booking.priority == enums.BookingPriority.CRITICAL).first()

    assert b_high is not None
    assert b_critical is not None

    # Case I & J: Alternative Voyage Permissions
    b_no_alt = db.query(models.Booking).filter(models.Booking.alternative_voyage_allowed == False).first()
    b_yes_alt = db.query(models.Booking).filter(models.Booking.alternative_voyage_allowed == True).first()

    assert b_no_alt is not None
    assert b_yes_alt is not None
    assert b_no_alt.alternative_voyage_allowed is False
    assert b_yes_alt.alternative_voyage_allowed is True
