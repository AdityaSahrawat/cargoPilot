"""Initial CargoPilot V1 Database Schema

Revision ID: 0001_initial_v1_schema
Revises: 
Create Date: 2026-08-17 21:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial_v1_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Companies
    op.create_table(
        'companies',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('company_type', sa.String(length=50), nullable=False),
        sa.Column('is_self', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('hq_country', sa.String(length=100), nullable=True),
        sa.Column('alliance', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_companies_id'), 'companies', ['id'], unique=False)
    op.create_index(op.f('ix_companies_name'), 'companies', ['name'], unique=False)

    # 2. Locations
    op.create_table(
        'locations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('location_type', sa.String(length=50), nullable=False),
        sa.Column('unlocode', sa.String(length=10), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=False),
        sa.Column('region', sa.String(length=100), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('storage_capacity', sa.Integer(), nullable=True),
        sa.Column('repair_capability', sa.Boolean(), nullable=True),
        sa.Column('operational_status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_locations_id'), 'locations', ['id'], unique=False)
    op.create_index(op.f('ix_locations_name'), 'locations', ['name'], unique=False)
    op.create_index(op.f('ix_locations_country'), 'locations', ['country'], unique=False)
    op.create_index(op.f('ix_locations_unlocode'), 'locations', ['unlocode'], unique=False)

    # CompanyLocations Association Table
    op.create_table(
        'company_locations',
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('location_id', sa.UUID(), nullable=False),
        sa.Column('is_home_port', sa.Boolean(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('company_id', 'location_id')
    )

    # 3. Vessels
    op.create_table(
        'vessels',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('imo_number', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('owner_company_id', sa.UUID(), nullable=False),
        sa.Column('operator_company_id', sa.UUID(), nullable=False),
        sa.Column('vessel_type', sa.String(length=50), nullable=False),
        sa.Column('container_capacity', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['owner_company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['operator_company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('imo_number')
    )
    op.create_index(op.f('ix_vessels_id'), 'vessels', ['id'], unique=False)
    op.create_index(op.f('ix_vessels_imo_number'), 'vessels', ['imo_number'], unique=True)

    # 4. Services
    op.create_table(
        'services',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('operator_company_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['operator_company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_services_id'), 'services', ['id'], unique=False)
    op.create_index(op.f('ix_services_name'), 'services', ['name'], unique=False)

    # 5. Voyages
    op.create_table(
        'voyages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('service_id', sa.UUID(), nullable=False),
        sa.Column('vessel_id', sa.UUID(), nullable=False),
        sa.Column('voyage_number', sa.String(length=100), nullable=False),
        sa.Column('departure_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('arrival_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['vessel_id'], ['vessels.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voyages_id'), 'voyages', ['id'], unique=False)
    op.create_index(op.f('ix_voyages_voyage_number'), 'voyages', ['voyage_number'], unique=False)

    # 6. VoyagePortCalls
    op.create_table(
        'voyage_port_calls',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('voyage_id', sa.UUID(), nullable=False),
        sa.Column('port_id', sa.UUID(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('arrival_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('departure_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['port_id'], ['locations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['voyage_id'], ['voyages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voyage_port_calls_id'), 'voyage_port_calls', ['id'], unique=False)

    # 7. VoyageLegs
    op.create_table(
        'voyage_legs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('voyage_id', sa.UUID(), nullable=False),
        sa.Column('from_port_call_id', sa.UUID(), nullable=False),
        sa.Column('to_port_call_id', sa.UUID(), nullable=False),
        sa.Column('total_capacity', sa.Integer(), nullable=False),
        sa.Column('booked_capacity', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['from_port_call_id'], ['voyage_port_calls.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['to_port_call_id'], ['voyage_port_calls.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['voyage_id'], ['voyages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voyage_legs_id'), 'voyage_legs', ['id'], unique=False)

    # 8. Containers
    op.create_table(
        'containers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('container_number', sa.String(length=50), nullable=False),
        sa.Column('container_type', sa.String(length=50), nullable=False),
        sa.Column('owner_company_id', sa.UUID(), nullable=False),
        sa.Column('current_location_id', sa.UUID(), nullable=True),
        sa.Column('current_voyage_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('condition', sa.String(length=50), nullable=False),
        sa.Column('available_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_movement_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['current_location_id'], ['locations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['current_voyage_id'], ['voyages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['owner_company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('container_number')
    )
    op.create_index(op.f('ix_containers_container_number'), 'containers', ['container_number'], unique=True)
    op.create_index(op.f('ix_containers_id'), 'containers', ['id'], unique=False)

    # 9. Bookings
    op.create_table(
        'bookings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('customer_company_id', sa.UUID(), nullable=False),
        sa.Column('carrier_company_id', sa.UUID(), nullable=False),
        sa.Column('origin_location_id', sa.UUID(), nullable=False),
        sa.Column('destination_location_id', sa.UUID(), nullable=False),
        sa.Column('container_type', sa.String(length=50), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('requested_pickup_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('required_delivery_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('voyage_id', sa.UUID(), nullable=True),
        sa.Column('priority', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['carrier_company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['customer_company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['destination_location_id'], ['locations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['origin_location_id'], ['locations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['voyage_id'], ['voyages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bookings_id'), 'bookings', ['id'], unique=False)

    # 10. EquipmentAssignments
    op.create_table(
        'equipment_assignments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('container_id', sa.UUID(), nullable=False),
        sa.Column('booking_id', sa.UUID(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['container_id'], ['containers.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_equipment_assignments_id'), 'equipment_assignments', ['id'], unique=False)

    # 11. Leases
    op.create_table(
        'leases',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('lessor_company_id', sa.UUID(), nullable=False),
        sa.Column('lessee_company_id', sa.UUID(), nullable=False),
        sa.Column('container_type', sa.String(length=50), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pickup_location_id', sa.UUID(), nullable=False),
        sa.Column('return_location_id', sa.UUID(), nullable=True),
        sa.Column('cost_per_unit', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['lessee_company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['lessor_company_id'], ['companies.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['pickup_location_id'], ['locations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['return_location_id'], ['locations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_leases_id'), 'leases', ['id'], unique=False)

    # 12. DemandForecasts
    op.create_table(
        'demand_forecasts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('location_id', sa.UUID(), nullable=False),
        sa.Column('container_type', sa.String(length=50), nullable=False),
        sa.Column('week', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_demand_forecasts_id'), 'demand_forecasts', ['id'], unique=False)
    op.create_index(op.f('ix_demand_forecasts_week'), 'demand_forecasts', ['week'], unique=False)

    # 13. ContainerEvents
    op.create_table(
        'container_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('container_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('location_id', sa.UUID(), nullable=True),
        sa.Column('voyage_id', sa.UUID(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['container_id'], ['containers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['voyage_id'], ['voyages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_container_events_id'), 'container_events', ['id'], unique=False)

    # 14. OptimizationRuns
    op.create_table(
        'optimization_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('start_week', sa.Date(), nullable=False),
        sa.Column('horizon_weeks', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('objective_value', sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_optimization_runs_id'), 'optimization_runs', ['id'], unique=False)

    # 15. OptimizationReposition
    op.create_table(
        'optimization_repositions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('voyage_leg_id', sa.UUID(), nullable=False),
        sa.Column('container_type', sa.String(length=50), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('departure_week', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['optimization_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['voyage_leg_id'], ['voyage_legs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_optimization_repositions_id'), 'optimization_repositions', ['id'], unique=False)

    # 16. OptimizationLease
    op.create_table(
        'optimization_leases',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('lease_id', sa.UUID(), nullable=True),
        sa.Column('location_id', sa.UUID(), nullable=False),
        sa.Column('container_type', sa.String(length=50), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('week', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['lease_id'], ['leases.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['optimization_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_optimization_leases_id'), 'optimization_leases', ['id'], unique=False)

    # 17. OptimizationInventory
    op.create_table(
        'optimization_inventories',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('location_id', sa.UUID(), nullable=False),
        sa.Column('container_type', sa.String(length=50), nullable=False),
        sa.Column('week', sa.Date(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['optimization_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_optimization_inventories_id'), 'optimization_inventories', ['id'], unique=False)

    # 18. OptimizationDemand
    op.create_table(
        'optimization_demands',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('location_id', sa.UUID(), nullable=False),
        sa.Column('container_type', sa.String(length=50), nullable=False),
        sa.Column('week', sa.Date(), nullable=False),
        sa.Column('confirmed_served', sa.Integer(), server_default='0', nullable=False),
        sa.Column('forecast_served', sa.Integer(), server_default='0', nullable=False),
        sa.Column('forecast_backlog', sa.Integer(), server_default='0', nullable=False),
        sa.Column('confirmed_shortage', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['optimization_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_optimization_demands_id'), 'optimization_demands', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('optimization_demands')
    op.drop_table('optimization_inventories')
    op.drop_table('optimization_leases')
    op.drop_table('optimization_repositions')
    op.drop_table('optimization_runs')
    op.drop_table('container_events')
    op.drop_table('demand_forecasts')
    op.drop_table('leases')
    op.drop_table('equipment_assignments')
    op.drop_table('bookings')
    op.drop_table('containers')
    op.drop_table('voyage_legs')
    op.drop_table('voyage_port_calls')
    op.drop_table('voyages')
    op.drop_table('services')
    op.drop_table('vessels')
    op.drop_table('company_locations')
    op.drop_table('locations')
    op.drop_table('companies')
