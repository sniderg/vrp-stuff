from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .model import Instance, Shift, Solution


@dataclass(frozen=True)
class ShiftSummary:
    index: int
    driver: int
    trailer: int
    start: int
    first_arrival: int | None
    end_time: int
    operations: int
    distance: float
    travel_time: int
    service_time: int
    delivered_quantity: float
    loaded_quantity: float
    distance_cost: float
    time_cost: float
    estimated_cost: float
    min_load: float
    max_load: float
    final_load: float
    load_violations: int


@dataclass(frozen=True)
class CustomerInventorySummary:
    point: int
    deliveries: int
    delivered_quantity: float
    min_inventory: float
    max_inventory: float
    min_margin_to_safety: float
    first_dry_step: int | None
    first_overfill_step: int | None
    first_safety_breach_step: int | None
    final_inventory: float


def summarize_shift(
    instance: Instance,
    shift: Shift,
    initial_load: float | None = None,
) -> ShiftSummary:
    trailer = instance.trailers[shift.trailer]
    driver = instance.drivers[shift.driver]
    previous_point = instance.base_index
    previous_departure = shift.start
    distance = 0.0
    travel_time = 0
    service_time = 0
    delivered_quantity = 0.0
    loaded_quantity = 0.0
    load = trailer.initial_quantity if initial_load is None else initial_load
    min_load = load
    max_load = load
    load_violations = 0

    for operation in shift.operations:
        leg_time = instance.time_matrix[previous_point][operation.point]
        leg_distance = instance.distance_matrix[previous_point][operation.point]
        travel_time += leg_time
        distance += leg_distance
        setup_time = instance.setup_time_for_point(operation.point)
        service_time += setup_time

        load -= operation.quantity
        if operation.quantity > 0:
            delivered_quantity += operation.quantity
        elif operation.quantity < 0:
            loaded_quantity += -operation.quantity

        min_load = min(min_load, load)
        max_load = max(max_load, load)
        if load < -1e-6 or load - trailer.capacity > 1e-6:
            load_violations += 1

        previous_point = operation.point
        previous_departure = operation.arrival + setup_time

    if previous_point != instance.base_index:
        distance += instance.distance_matrix[previous_point][instance.base_index]
        travel_time += instance.time_matrix[previous_point][instance.base_index]
        end_time = previous_departure + instance.time_matrix[previous_point][instance.base_index]
    else:
        end_time = previous_departure

    distance_cost = distance * trailer.distance_cost
    time_cost = (end_time - shift.start) * driver.time_cost / 60.0

    return ShiftSummary(
        index=shift.index,
        driver=shift.driver,
        trailer=shift.trailer,
        start=shift.start,
        first_arrival=shift.operations[0].arrival if shift.operations else None,
        end_time=end_time,
        operations=len(shift.operations),
        distance=distance,
        travel_time=travel_time,
        service_time=service_time,
        delivered_quantity=delivered_quantity,
        loaded_quantity=loaded_quantity,
        distance_cost=distance_cost,
        time_cost=time_cost,
        estimated_cost=distance_cost + time_cost,
        min_load=min_load,
        max_load=max_load,
        final_load=load,
        load_violations=load_violations,
    )


def summarize_solution(instance: Instance, solution: Solution) -> list[ShiftSummary]:
    trailer_loads = {
        trailer.index: trailer.initial_quantity
        for trailer in instance.trailers
    }
    summaries_by_index: dict[int, ShiftSummary] = {}

    for shift in sorted(solution.shifts, key=lambda item: (item.start, item.index)):
        summary = summarize_shift(instance, shift, trailer_loads.get(shift.trailer, 0.0))
        trailer_loads[shift.trailer] = summary.final_load
        summaries_by_index[shift.index] = summary

    return [summaries_by_index[shift.index] for shift in solution.shifts]


def delivery_events(solution: Solution) -> dict[int, list[tuple[int, float]]]:
    events: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for shift in solution.shifts:
        for operation in shift.operations:
            if operation.quantity > 0:
                events[operation.point].append((operation.arrival, operation.quantity))

    for point_events in events.values():
        point_events.sort()
    return dict(events)


def customer_inventory_summary(
    instance: Instance,
    solution: Solution | None = None,
) -> list[CustomerInventorySummary]:
    events = delivery_events(solution) if solution is not None else {}
    summaries: list[CustomerInventorySummary] = []

    for customer in instance.customers:
        inventory = customer.initial_tank_quantity
        min_inventory = inventory
        max_inventory = inventory
        first_dry_step: int | None = None
        first_overfill_step: int | None = None
        first_safety_breach_step: int | None = None
        delivered_quantity = 0.0
        deliveries = 0
        events_by_step: dict[int, float] = defaultdict(float)

        for arrival, quantity in events.get(customer.index, []):
            step = min(max(arrival // instance.unit, 0), instance.horizon - 1)
            events_by_step[step] += quantity

        for step in range(instance.horizon):
            if step in events_by_step:
                inventory += events_by_step[step]
                delivered_quantity += events_by_step[step]
                deliveries += 1
                max_inventory = max(max_inventory, inventory)
                if (
                    first_overfill_step is None
                    and inventory > customer.capacity + 1e-6
                    and not customer.call_in
                ):
                    first_overfill_step = step
            if customer.forecast:
                inventory -= customer.forecast[step]
            min_inventory = min(min_inventory, inventory)
            max_inventory = max(max_inventory, inventory)
            if first_dry_step is None and inventory < -1e-6:
                first_dry_step = step
            if (
                first_safety_breach_step is None
                and inventory < customer.safety_level - 1e-6
                and not customer.call_in
            ):
                first_safety_breach_step = step

        summaries.append(
            CustomerInventorySummary(
                point=customer.index,
                deliveries=deliveries,
                delivered_quantity=delivered_quantity,
                min_inventory=min_inventory,
                max_inventory=max_inventory,
                min_margin_to_safety=min_inventory - customer.safety_level,
                first_dry_step=first_dry_step,
                first_overfill_step=first_overfill_step,
                first_safety_breach_step=first_safety_breach_step,
                final_inventory=inventory,
            )
        )

    return summaries


def point_visit_counts(solution: Solution) -> Counter[int]:
    counter: Counter[int] = Counter()
    for shift in solution.shifts:
        for operation in shift.operations:
            counter[operation.point] += 1
    return counter
