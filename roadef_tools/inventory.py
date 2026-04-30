from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .model import Customer, Instance, Solution


EPSILON = 1e-6


@dataclass(frozen=True)
class TankEvent:
    point: int
    step: int
    time_start: int
    initial_inventory: float
    delivered: float
    consumed: float
    after_consumption: float
    after_delivery: float
    ending_inventory: float
    capacity: float
    safety_level: float
    overfilled_after_delivery: bool
    overfilled_ending: bool
    negative: bool
    safety_breach: bool


@dataclass(frozen=True)
class TankViolation:
    code: str
    point: int
    step: int
    time_start: int
    inventory: float
    limit: float
    message: str


def delivery_by_customer_step(solution: Solution) -> dict[int, dict[int, float]]:
    deliveries: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for shift in solution.shifts:
        for operation in shift.operations:
            if operation.quantity <= 0:
                continue
            deliveries[operation.point][operation.arrival] += operation.quantity
    return {
        point: dict(events)
        for point, events in deliveries.items()
    }


def tank_events(instance: Instance, solution: Solution) -> list[TankEvent]:
    deliveries_by_arrival = delivery_by_customer_step(solution)
    events: list[TankEvent] = []

    for customer in instance.customers:
        events.extend(_customer_tank_events(instance, customer, deliveries_by_arrival))

    return events


def _customer_tank_events(
    instance: Instance,
    customer: Customer,
    deliveries_by_arrival: dict[int, dict[int, float]],
) -> list[TankEvent]:
    inventory = customer.initial_tank_quantity
    arrival_deliveries = deliveries_by_arrival.get(customer.index, {})
    deliveries_by_step: dict[int, float] = defaultdict(float)

    for arrival, quantity in arrival_deliveries.items():
        step = min(max(arrival // instance.unit, 0), instance.horizon - 1)
        deliveries_by_step[step] += quantity

    events: list[TankEvent] = []
    for step in range(instance.horizon):
        initial = inventory
        delivered = deliveries_by_step.get(step, 0.0)
        consumed = customer.forecast[step] if customer.forecast else 0.0
        after_consumption = initial - consumed
        ending = after_consumption + delivered
        events.append(
            TankEvent(
                point=customer.index,
                step=step,
                time_start=step * instance.unit,
                initial_inventory=initial,
                delivered=delivered,
                consumed=consumed,
                after_consumption=after_consumption,
                after_delivery=ending,
                ending_inventory=ending,
                capacity=customer.capacity,
                safety_level=customer.safety_level,
                overfilled_after_delivery=(
                    not customer.call_in
                    and ending > customer.capacity + EPSILON
                ),
                overfilled_ending=(
                    not customer.call_in
                    and ending > customer.capacity + EPSILON
                ),
                negative=(not customer.call_in and ending < -EPSILON),
                safety_breach=(
                    not customer.call_in
                    and ending < customer.safety_level - EPSILON
                ),
            )
        )
        inventory = ending

    return events


def tank_violations(instance: Instance, solution: Solution) -> list[TankViolation]:
    violations: list[TankViolation] = []

    for event in tank_events(instance, solution):
        if event.overfilled_after_delivery:
            violations.append(
                TankViolation(
                    code="TANK_OVERFILL",
                    point=event.point,
                    step=event.step,
                    time_start=event.time_start,
                    inventory=event.ending_inventory,
                    limit=event.capacity,
                    message=(
                        f"ending inventory {event.ending_inventory:.6f} "
                        f"exceeds capacity {event.capacity:.6f}"
                    ),
                )
            )
        if event.negative:
            violations.append(
                TankViolation(
                    code="TANK_NEGATIVE",
                    point=event.point,
                    step=event.step,
                    time_start=event.time_start,
                    inventory=event.ending_inventory,
                    limit=0.0,
                    message=(
                        f"ending inventory {event.ending_inventory:.6f} "
                        "is below zero after consumption"
                    ),
                )
            )
        if event.safety_breach:
            violations.append(
                TankViolation(
                    code="TANK_SAFETY_BREACH",
                    point=event.point,
                    step=event.step,
                    time_start=event.time_start,
                    inventory=event.ending_inventory,
                    limit=event.safety_level,
                    message=(
                        f"ending inventory {event.ending_inventory:.6f} "
                        f"is below safety level {event.safety_level:.6f}"
                    ),
                )
            )

    return violations
