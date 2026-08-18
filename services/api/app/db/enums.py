from enum import Enum


class CompanyType(str, Enum):
    CARRIER = "CARRIER"
    LESSOR = "LESSOR"
    CUSTOMER = "CUSTOMER"
    ALLIANCE_PARTNER = "ALLIANCE_PARTNER"


class LocationType(str, Enum):
    PORT = "PORT"
    DEPOT = "DEPOT"


class OperationalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"
    CLOSED = "CLOSED"


class ContainerType(str, Enum):
    DRY_20FT = "20FT_DRY"
    DRY_40FT = "40FT_DRY"
    REEFER_40FT = "40FT_REEFER"
    DRY_45FT = "45FT_DRY"
    HIGH_CUBE_40FT = "40FT_HIGH_CUBE"


class ContainerStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    LOADED = "LOADED"
    IN_TRANSIT = "IN_TRANSIT"
    UNDER_REPAIR = "UNDER_REPAIR"
    ON_HOLD = "ON_HOLD"
    OFF_HIRE = "OFF_HIRE"


class ContainerCondition(str, Enum):
    CARGO_WORTHY = "CARGO_WORTHY"
    DAMAGED = "DAMAGED"
    REPAIRABLE = "REPAIRABLE"
    UNSERVICEABLE = "UNSERVICEABLE"


class VesselType(str, Enum):
    CONTAINER_SHIP = "CONTAINER_SHIP"
    FEEDER = "FEEDER"
    ULCV = "ULCV"
    PANAMAX = "PANAMAX"
    POST_PANAMAX = "POST_PANAMAX"


class VesselStatus(str, Enum):
    ACTIVE = "ACTIVE"
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE"
    LAID_UP = "LAID_UP"
    CHARTERED_OUT = "CHARTERED_OUT"
    INACTIVE = "INACTIVE"


class ServiceStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    PLANNED = "PLANNED"


class VoyageStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    DELAYED = "DELAYED"


class BookingPriority(str, Enum):
    LOW = "LOW"
    STANDARD = "STANDARD"
    HIGH = "HIGH"
    URGENT = "URGENT"


class BookingStatus(str, Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class ContainerEventType(str, Enum):
    GATE_IN = "GATE_IN"
    GATE_OUT = "GATE_OUT"
    LOADED = "LOADED"
    DISCHARGED = "DISCHARGED"
    RETURNED = "RETURNED"
    REPAIRED = "REPAIRED"
    RELEASED = "RELEASED"
    DAMAGED = "DAMAGED"


class OptimizationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
