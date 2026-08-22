import uuid
from typing import List, Optional
from sqlalchemy.orm import Session

from app.db import models, enums
from app.optimization.models import OptimizationInput, ForecastItem, LegCapacityItem


class OptimizationInputBuilder:
    """Gathers facts from database tables into mathematical solver inputs."""

    def __init__(self, db: Session):
        self.db = db

    def get_usable_containers(
        self,
        location_id: Optional[uuid.UUID] = None,
        container_type: Optional[enums.ContainerType] = None,
    ) -> List[models.Container]:
        """Returns physical containers that are genuinely free & usable for allocation.
        Filters out:
        - Non-AVAILABLE status (e.g. IN_TRANSIT, UNDER_REPAIR, ASSIGNED)
        - Equipment controlled by another carrier (controlled_by_carrier = False)
        - Containers under customs hold (customs_hold = True)
        - Emergency reserve equipment (is_emergency_reserve = True)
        - Containers with active operational commitments (container_commitments)
        """
        query = self.db.query(models.Container).filter(
            models.Container.status == enums.ContainerStatus.AVAILABLE,
            models.Container.controlled_by_carrier == True,
            models.Container.customs_hold == False,
            models.Container.is_emergency_reserve == False,
        )

        if location_id:
            query = query.filter(models.Container.current_location_id == location_id)
        if container_type:
            query = query.filter(models.Container.container_type == container_type)

        containers = query.all()

        # Filter out containers with active commitments
        usable = []
        for c in containers:
            has_active_commitment = any(
                comm.status == enums.CommitmentStatus.ACTIVE for comm in c.commitments
            )
            if not has_active_commitment:
                usable.append(c)

        return usable

    def build_input(
        self,
        company_id: uuid.UUID,
        start_week: str,
        horizon_weeks: int,
        container_types: Optional[List[enums.ContainerType]] = None,
        location_ids: Optional[List[uuid.UUID]] = None,
    ) -> OptimizationInput:
        if not container_types:
            container_types = list(enums.ContainerType)

        if not location_ids:
            locations = self.db.query(models.Location.id).all()
            location_ids = [loc.id for loc in locations]

        # Gather forecasts
        forecast_records = self.db.query(models.DemandForecast).filter(
            models.DemandForecast.location_id.in_(location_ids),
            models.DemandForecast.container_type.in_(container_types),
        ).all()

        forecasts = [
            ForecastItem(
                location_id=f.location_id,
                container_type=f.container_type,
                week=f.week if isinstance(f.week, str) else f.week.isoformat(),
                quantity=f.quantity,
            )
            for f in forecast_records
        ]

        # Gather active legs
        legs = self.db.query(models.VoyageLeg).all()
        leg_capacities = [
            LegCapacityItem(
                leg_id=leg.id,
                voyage_id=leg.voyage_id,
                from_port_id=leg.from_port_call.port_id if leg.from_port_call else uuid.uuid4(),
                to_port_id=leg.to_port_call.port_id if leg.to_port_call else uuid.uuid4(),
                available_capacity=leg.available_capacity,
            )
            for leg in legs
        ]

        return OptimizationInput(
            company_id=company_id,
            start_week=start_week,
            horizon_weeks=horizon_weeks,
            container_types=container_types,
            location_ids=location_ids,
            forecasts=forecasts,
            leg_capacities=leg_capacities,
        )
