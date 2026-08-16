Input Data/ Entities

Purpose of the document
Explain that this document defines all real-world entities CargoPilot needs to understand the container equipment planning problem, their properties, and how those entities are used in the system's decisions.

# Input data / Entities

## Purpose

This document defines the real‑world entities CargoPilot needs to understand the container equipment planning problem: their key properties and how the system will use them for forecasting and optimization.

## Core entities (overview)

- Company / Carrier — the CargoPilot customer that owns or controls equipment to be optimized
- Container — an individual physical container
- Port — physical port/location where containers may be located or moved through
- Depot — storage/repair facilities for containers
- Vessel — a physical ship
- Voyage / Service — a scheduled movement of a vessel (distinct from the vessel itself)
- Booking — a customer request that creates container demand

---

## 1. Company / Carrier

Represents the shipping company that uses CargoPilot and whose equipment/network is being planned.

Possible properties:

- `company_id`
- `name`
- `company_type` — e.g., `carrier`, `shipping_line`
- `country`
- `contact_information`
- `operating_regions`
- `fleet_size` — likely derived, not stored
- `status` — `active` / `inactive`

Note: `fleet_size` can be computed from container records and may not need persistent storage.

## 2. Container

Represents a single physical container.

Possible properties:

- `container_id` (container number)
- `container_type` — e.g., `20ft`, `40ft`, `reefer`
- `owner_company_id`
- `current_location` (ref: `port_id` / `depot_id` / `vessel_id`)
- `location_type` — `port`, `depot`, `vessel`
- `status` — `available`, `loaded`, `in_transit`, `under_repair`, etc.
- `availability_time`
- `condition`
- `last_movement_time`

Note: Distinguish `owner` from `current_controller` later to model leased containers.

## 3. Port

Represents a physical port or terminal in the carrier's network.

Possible properties:

- `port_id`
- `name`
- `UNLOCODE`
- `country`
- `region`
- `latitude`
- `longitude`
- `operational_status`
- `container_handling_capacity`

Relationship note: whether a carrier operates at a port is best modeled as a relationship (e.g., `carrier_port` table) rather than a simple property.

## 4. Depot

Represents a container depot used for storage and repair.

Possible properties:

- `depot_id`
- `name`
- `location` (address / coordinates)
- `country`
- `latitude`
- `longitude`
- `capacity`
- `repair_capability` (boolean / details)
- `storage_capacity`
- `operational_status`

Relationship note: access/ownership by a company should be modeled as a separate relationship.

## 5. Vessel

Represents the physical ship.

Possible properties:

- `vessel_id`
- `IMO_number`
- `name`
- `operator_company_id`
- `owner_company_id`
- `vessel_type`
- `container_capacity`
- `status`
- `current_location` (lat/long or reference)

Note: ownership and operation can be modeled separately if required.

## 6. Voyage / Service

Represents a specific scheduled movement or service of a vessel (planning construct).

Possible properties:

- `voyage_id`
- `vessel_id`
- `service_id`
- `origin` (port_id)
- `destination` (port_id)
- `port_sequence` (ordered list of port_ids with ETAs)
- `departure_time`
- `arrival_time`
- `status`
- `available_capacity`
- `container_type_constraints`

This entity will contain much of the planning and capacity information used by the optimizer.

## 7. Booking

Represents a customer request/commitment that creates container demand for the carrier.

Possible properties:

- `booking_id`
- `company_id` — carrier handling the booking
- `customer_id`
- `origin_port`
- `destination_port`
- `container_type`
- `quantity`
- `requested_pickup_date`
- `required_delivery_date`
- `voyage_id` — if already assigned
- `priority`
- `status`

---

## Implementation notes / next steps

- Consider drafting JSON Schema or database schemas for each entity.
- Model many‑to‑many relationships (e.g., carrier ↔ port) explicitly.
- Decide how to represent time‑series / event streams (container movements, bookings) and link them to these entities.

