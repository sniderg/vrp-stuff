from __future__ import annotations

from dataclasses import dataclass, replace

from ..inventory import tank_events
from ..model import Instance, Operation, Shift, Solution
from ..rules import derive_solution, is_time_window_valid, is_trailer_allowed
from ..highs_repair import repair_quantities_with_highs
from .highs_selector import select_shifts_with_highs


MINUTES_PER_DAY = 1440
EPSILON = 1e-6


@dataclass(frozen=True)
class RescueConfig:
    start_day: int = 0
    end_day: int = 14
    replace_from_day: int = 7
    max_customers: int = 12
    samples_per_customer: int = 6
    target_fill_ratio: float = 0.95
    max_pre_service_fill_ratio: float = 0.95
    sample_lookback_days: int = 5
    max_chain_length: int = 3
    nearest_chain_neighbors: int = 4
    repair_quantities: bool = True
    variable_quantity_columns: bool = False
    pressure_pricing: bool = True


@dataclass(frozen=True)
class RescueReport:
    failing_customers: tuple[int, ...]
    generated_candidates: int
    selected_extra_shifts: int
    quantity_repair_status: str | None = None
    quantity_repair_constraints: int | None = None


def targeted_rescue(
    instance: Instance,
    baseline: Solution,
    *,
    config: RescueConfig = RescueConfig(),
) -> tuple[Solution, RescueReport]:
    failing = _failing_customers(instance, baseline, config)
    fixed_prefix = _keep_shifts_started_before(
        baseline,
        config.replace_from_day * MINUTES_PER_DAY,
    )
    candidates = _baseline_window_shifts(baseline, config)
    candidates.extend(generate_rescue_candidates(instance, fixed_prefix, failing, config=config))
    candidates.extend(generate_chain_rescue_candidates(instance, fixed_prefix, failing, config=config))
    candidates = _dedupe_reindex(candidates)
    if not candidates:
        return baseline, RescueReport(tuple(failing), 0, 0)

    rescued = select_shifts_with_highs(
        instance,
        fixed_prefix,
        candidates,
        start_day=config.replace_from_day,
        end_day=config.end_day,
        variable_quantities=config.variable_quantity_columns,
        pressure_pricing=config.pressure_pricing,
    )
    rescued = normalize_source_loads(instance, rescued)
    selected_extra = max(0, len(rescued.shifts) - len(fixed_prefix.shifts))
    repair_status = None
    repair_constraints = None
    if config.repair_quantities:
        rescued, repair_report = repair_quantities_with_highs(
            instance,
            rescued,
            score_days=config.end_day,
            feasibility_days=config.end_day,
        )
        rescued = normalize_source_loads(instance, rescued)
        repair_status = repair_report.status
        repair_constraints = repair_report.constraints
    rescued = Solution(
        shifts=tuple(replace(shift, index=i) for i, shift in enumerate(rescued.shifts))
    )
    return rescued, RescueReport(
        tuple(failing),
        len(candidates),
        selected_extra,
        repair_status,
        repair_constraints,
    )


def normalize_source_loads(instance: Instance, solution: Solution) -> Solution:
    """Make source load quantities consistent with selected trailer histories.

    Candidate generation estimates source quantities against a fixed baseline.
    Once several candidates are selected together, the real trailer state may be
    different. This pass keeps the selected route/timing and delivery quantities,
    then turns each source operation into a fill-to-capacity operation under the
    actual selected trailer history.
    """
    trailer_quantities = {
        trailer.index: trailer.initial_quantity
        for trailer in instance.trailers
    }
    trailer_capacities = {
        trailer.index: trailer.capacity
        for trailer in instance.trailers
    }
    normalized_by_index: dict[int, Shift] = {}

    for shift in sorted(solution.shifts, key=lambda item: (item.start, item.index)):
        trailer_quantity = trailer_quantities[shift.trailer]
        trailer_capacity = trailer_capacities[shift.trailer]
        operations: list[Operation] = []

        for operation in shift.operations:
            if operation.point in instance.source_by_point:
                load = max(0.0, trailer_capacity - trailer_quantity)
                operations.append(replace(operation, quantity=-load))
                trailer_quantity += load
                continue

            operations.append(operation)
            trailer_quantity -= operation.quantity

        trailer_quantities[shift.trailer] = trailer_quantity
        normalized_by_index[shift.index] = replace(shift, operations=tuple(operations))

    return Solution(
        shifts=tuple(normalized_by_index[shift.index] for shift in solution.shifts)
    )


def _keep_shifts_started_before(solution: Solution, cutoff_minute: int) -> Solution:
    return Solution(
        shifts=tuple(shift for shift in solution.shifts if shift.start < cutoff_minute)
    )


def _baseline_window_shifts(solution: Solution, config: RescueConfig) -> list[Shift]:
    start = config.replace_from_day * MINUTES_PER_DAY
    end = config.end_day * MINUTES_PER_DAY
    return [shift for shift in solution.shifts if start <= shift.start < end]


def _dedupe_reindex(shifts: list[Shift]) -> list[Shift]:
    seen: set[tuple[object, ...]] = set()
    unique: list[Shift] = []
    for shift in shifts:
        key = _shift_key(shift)
        if key in seen:
            continue
        seen.add(key)
        unique.append(replace(shift, index=len(unique)))
    return unique


def generate_rescue_candidates(
    instance: Instance,
    baseline: Solution,
    failing_customers: list[int],
    *,
    config: RescueConfig,
) -> list[Shift]:
    start_minute = max(config.start_day, config.replace_from_day) * MINUTES_PER_DAY
    end_minute = config.end_day * MINUTES_PER_DAY
    candidates: list[Shift] = []
    seen: set[tuple[object, ...]] = set()
    event_cache = _events_by_customer(instance, baseline)
    trailer_cache = _trailer_load_cache(instance, baseline)

    for customer_id in failing_customers:
        customer = instance.customer_by_point[customer_id]
        if customer.call_in:
            continue
        breach_minute = _first_breach_minute(instance, baseline, customer_id, event_cache)
        if breach_minute is None:
            continue
        latest_customer_arrival = min(breach_minute - instance.unit, end_minute - 1)
        if latest_customer_arrival < start_minute:
            continue

        for driver in instance.drivers:
            for trailer in instance.trailers:
                if trailer.index not in driver.trailer_ids:
                    continue
                if not is_trailer_allowed(instance, customer.index, trailer.index):
                    continue
                source = next(
                    (
                        src
                        for src in instance.sources
                        if trailer.index in src.allowed_trailers
                    ),
                    None,
                )
                if source is None:
                    continue

                route_to_customer = (
                    instance.time_matrix[instance.base_index][source.index]
                    + source.setup_time
                    + instance.time_matrix[source.index][customer.index]
                )
                return_time = instance.time_matrix[customer.index][instance.base_index]

                for target_arrival in _arrival_samples(
                    start_minute,
                    latest_customer_arrival,
                    config.samples_per_customer,
                    config.sample_lookback_days,
                ):
                    shift_start = target_arrival - route_to_customer
                    if shift_start < start_minute:
                        continue
                    source_arrival = (
                        shift_start + instance.time_matrix[instance.base_index][source.index]
                    )
                    arrival = source_arrival + source.setup_time + instance.time_matrix[source.index][customer.index]
                    departure = arrival + customer.setup_time
                    total_driving = (
                        instance.time_matrix[instance.base_index][source.index]
                        + instance.time_matrix[source.index][customer.index]
                        + return_time
                    )
                    needs_return_layover = (
                        customer.layover_customer
                        and total_driving > driver.max_driving_duration
                    )
                    end = departure + return_time + (
                        driver.layover_duration if needs_return_layover else 0
                    )
                    if end > end_minute:
                        continue
                    if not is_time_window_valid(shift_start, end, driver.time_windows):
                        continue
                    if not is_time_window_valid(arrival, departure, customer.time_windows):
                        continue
                    if (
                        total_driving > driver.max_driving_duration
                        and not customer.layover_customer
                    ):
                        continue

                    inventory_at_arrival = _inventory_at_arrival(
                        instance, baseline, customer_id, arrival, event_cache
                    )
                    if (
                        inventory_at_arrival
                        > customer.capacity * config.max_pre_service_fill_ratio + EPSILON
                    ):
                        continue
                    room = max(0.0, customer.capacity - inventory_at_arrival)
                    target_room = max(
                        0.0,
                        customer.capacity * config.target_fill_ratio
                        - inventory_at_arrival,
                    )
                    trailer_load = _trailer_load_at(instance, trailer_cache, trailer.index, shift_start)
                    load_quantity = max(0.0, trailer.capacity - trailer_load)
                    available_quantity = trailer_load + load_quantity
                    quantity = min(available_quantity, room, target_room)
                    if quantity < customer.min_operation_quantity - EPSILON:
                        continue

                    operations = []
                    if load_quantity > EPSILON:
                        operations.append(Operation(source.index, source_arrival, -load_quantity))
                    operations.append(Operation(customer.index, arrival, quantity))
                    shift = Shift(
                        index=len(candidates),
                        driver=driver.index,
                        trailer=trailer.index,
                        start=shift_start,
                        operations=tuple(operations),
                    )
                    if not _is_shift_route_valid(instance, shift):
                        continue
                    key = _shift_key(shift)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(shift)

    return candidates


def generate_chain_rescue_candidates(
    instance: Instance,
    baseline: Solution,
    failing_customers: list[int],
    *,
    config: RescueConfig,
) -> list[Shift]:
    start_minute = max(config.start_day, config.replace_from_day) * MINUTES_PER_DAY
    end_minute = config.end_day * MINUTES_PER_DAY
    event_cache = _events_by_customer(instance, baseline)
    trailer_cache = _trailer_load_cache(instance, baseline)
    sequences = _chain_sequences(instance, baseline, failing_customers, config, event_cache)
    candidates: list[Shift] = []
    seen: set[tuple[object, ...]] = set()

    for sequence in sequences:
        anchor = instance.customer_by_point[sequence[0]]
        anchor_breach = _first_breach_minute(instance, baseline, anchor.index, event_cache)
        if anchor_breach is None:
            continue
        latest_anchor_arrival = min(anchor_breach - instance.unit, end_minute - 1)
        if latest_anchor_arrival < start_minute:
            continue

        for driver in instance.drivers:
            for trailer in instance.trailers:
                if trailer.index not in driver.trailer_ids:
                    continue
                if any(
                    not is_trailer_allowed(instance, customer_id, trailer.index)
                    for customer_id in sequence
                ):
                    continue
                source = next(
                    (
                        src
                        for src in instance.sources
                        if trailer.index in src.allowed_trailers
                    ),
                    None,
                )
                if source is None:
                    continue

                lead_to_anchor = (
                    instance.time_matrix[instance.base_index][source.index]
                    + source.setup_time
                    + instance.time_matrix[source.index][anchor.index]
                )

                for anchor_arrival in _arrival_samples(
                    start_minute,
                    latest_anchor_arrival,
                    config.samples_per_customer,
                    config.sample_lookback_days,
                ):
                    shift_start = anchor_arrival - lead_to_anchor
                    if shift_start < start_minute:
                        continue
                    shift = _build_chain_shift(
                        instance,
                        baseline,
                        event_cache,
                        trailer_cache,
                        sequence,
                        driver.index,
                        trailer.index,
                        source.index,
                        shift_start,
                        end_minute,
                        config,
                    )
                    if shift is None:
                        continue
                    key = _shift_key(shift)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(replace(shift, index=len(candidates)))

    return candidates


def _chain_sequences(
    instance: Instance,
    baseline: Solution,
    failing_customers: list[int],
    config: RescueConfig,
    event_cache: dict[int, list],
) -> list[tuple[int, ...]]:
    failing = [
        customer_id
        for customer_id in failing_customers
        if not instance.customer_by_point[customer_id].call_in
    ]
    breach_order = {
        customer_id: _first_breach_minute(instance, baseline, customer_id, event_cache) or 10**12
        for customer_id in failing
    }
    sequences: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()

    for anchor in failing:
        neighbors = sorted(
            (customer_id for customer_id in failing if customer_id != anchor),
            key=lambda customer_id: (
                instance.time_matrix[anchor][customer_id],
                breach_order[customer_id],
                customer_id,
            ),
        )[: config.nearest_chain_neighbors]
        for neighbor in neighbors:
            pair = (anchor, neighbor)
            if pair not in seen:
                seen.add(pair)
                sequences.append(pair)
            if config.max_chain_length < 3:
                continue
            third_candidates = sorted(
                (
                    customer_id
                    for customer_id in failing
                    if customer_id not in pair
                ),
                key=lambda customer_id: (
                    instance.time_matrix[neighbor][customer_id],
                    breach_order[customer_id],
                    customer_id,
                ),
            )
            if third_candidates:
                triple = (anchor, neighbor, third_candidates[0])
                if triple not in seen:
                    seen.add(triple)
                    sequences.append(triple)

    return sequences


def _build_chain_shift(
    instance: Instance,
    baseline: Solution,
    event_cache: dict[int, list],
    trailer_cache: dict[int, list[tuple[int, float]]],
    sequence: tuple[int, ...],
    driver_id: int,
    trailer_id: int,
    source_id: int,
    shift_start: int,
    end_minute: int,
    config: RescueConfig,
) -> Shift | None:
    driver = instance.drivers[driver_id]
    trailer = instance.trailers[trailer_id]
    source = instance.source_by_point[source_id]
    source_arrival = shift_start + instance.time_matrix[instance.base_index][source_id]
    current_time = source_arrival + source.setup_time
    current_point = source_id
    trailer_load = _trailer_load_at(instance, trailer_cache, trailer_id, shift_start)
    load_quantity = max(0.0, trailer.capacity - trailer_load)
    trailer_load += load_quantity
    operations: list[Operation] = []
    if load_quantity > EPSILON:
        operations.append(Operation(source_id, source_arrival, -load_quantity))

    total_driving = instance.time_matrix[instance.base_index][source_id]
    delivered_count = 0
    for customer_id in sequence:
        customer = instance.customer_by_point[customer_id]
        arrival = current_time + instance.time_matrix[current_point][customer_id]
        departure = arrival + customer.setup_time
        breach_minute = _first_breach_minute(instance, baseline, customer_id, event_cache)
        if breach_minute is not None and arrival >= breach_minute:
            continue
        if departure >= end_minute:
            continue
        if not is_time_window_valid(arrival, departure, customer.time_windows):
            continue
        inventory_at_arrival = _inventory_at_arrival(
            instance, baseline, customer_id, arrival, event_cache
        )
        if inventory_at_arrival > customer.capacity * config.max_pre_service_fill_ratio + EPSILON:
            continue
        room = max(0.0, customer.capacity - inventory_at_arrival)
        target_room = max(
            0.0,
            customer.capacity * config.target_fill_ratio
            - inventory_at_arrival,
        )
        quantity = min(trailer_load, room, target_room)
        if quantity < customer.min_operation_quantity - EPSILON:
            continue
        operations.append(Operation(customer_id, arrival, quantity))
        delivered_count += 1
        trailer_load -= quantity
        total_driving += instance.time_matrix[current_point][customer_id]
        current_time = departure
        current_point = customer_id

    if delivered_count < 2:
        return None
    total_driving += instance.time_matrix[current_point][instance.base_index]
    has_layover_customer = any(
        instance.customer_by_point[customer_id].layover_customer
        for customer_id in sequence
    )
    needs_return_layover = (
        has_layover_customer
        and total_driving > driver.max_driving_duration
    )
    end = (
        current_time
        + instance.time_matrix[current_point][instance.base_index]
        + (driver.layover_duration if needs_return_layover else 0)
    )
    if end > end_minute:
        return None
    if total_driving > driver.max_driving_duration and not has_layover_customer:
        return None
    if not is_time_window_valid(shift_start, end, driver.time_windows):
        return None

    shift = Shift(
        index=0,
        driver=driver_id,
        trailer=trailer_id,
        start=shift_start,
        operations=tuple(operations),
    )
    if not _is_shift_route_valid(instance, shift):
        return None
    return shift


def _failing_customers(
    instance: Instance,
    solution: Solution,
    config: RescueConfig,
) -> list[int]:
    cutoff_step = min(instance.horizon, config.end_day * MINUTES_PER_DAY // instance.unit)
    first_by_customer: dict[int, int] = {}
    for event in tank_events(instance, solution):
        if event.step >= cutoff_step:
            continue
        if event.safety_breach:
            first_by_customer.setdefault(event.point, event.step)
    return [
        customer_id
        for customer_id, _step in sorted(first_by_customer.items(), key=lambda item: item[1])
    ][: config.max_customers]


def _first_breach_minute(
    instance: Instance,
    solution: Solution,
    customer_id: int,
    event_cache: dict[int, list] | None = None,
) -> int | None:
    events = event_cache.get(customer_id, ()) if event_cache is not None else tank_events(instance, solution)
    for event in events:
        if event.point == customer_id and event.safety_breach:
            return event.time_start
    return None


def _inventory_at_arrival(
    instance: Instance,
    solution: Solution,
    customer_id: int,
    arrival: int,
    event_cache: dict[int, list] | None = None,
) -> float:
    step = min(max(arrival // instance.unit, 0), instance.horizon - 1)
    events = event_cache.get(customer_id, ()) if event_cache is not None else tank_events(instance, solution)
    for event in events:
        if event.point == customer_id and event.step == step:
            return event.after_consumption
    return 0.0


def _room_at_arrival(
    instance: Instance,
    solution: Solution,
    customer_id: int,
    arrival: int,
    event_cache: dict[int, list] | None = None,
) -> float:
    customer = instance.customer_by_point[customer_id]
    inventory = _inventory_at_arrival(instance, solution, customer_id, arrival, event_cache)
    return max(0.0, customer.capacity - inventory)


def _arrival_samples(
    start_minute: int,
    latest_arrival: int,
    count: int,
    lookback_days: int,
) -> list[int]:
    if count <= 1:
        return [latest_arrival]
    earliest = max(start_minute, latest_arrival - lookback_days * MINUTES_PER_DAY)
    span = latest_arrival - earliest
    if span <= 0:
        return [latest_arrival]
    return sorted(
        {
            earliest + round(span * i / (count - 1))
            for i in range(count)
        },
        reverse=True,
    )


def _trailer_load_at(
    instance: Instance,
    trailer_cache: dict[int, list[tuple[int, float]]],
    trailer_id: int,
    minute: int,
) -> float:
    load = instance.trailers[trailer_id].initial_quantity
    for shift_start, end_quantity in trailer_cache.get(trailer_id, ()):
        if shift_start >= minute:
            break
        load = end_quantity
    return load


def _events_by_customer(instance: Instance, solution: Solution) -> dict[int, list]:
    events: dict[int, list] = {}
    for event in tank_events(instance, solution):
        events.setdefault(event.point, []).append(event)
    return events


def _trailer_load_cache(instance: Instance, solution: Solution) -> dict[int, list[tuple[int, float]]]:
    cache: dict[int, list[tuple[int, float]]] = {}
    for derived in sorted(derive_solution(instance, solution), key=lambda item: item.shift.start):
        cache.setdefault(derived.shift.trailer, []).append(
            (derived.shift.start, derived.end_trailer_quantity)
        )
    return cache


def _is_shift_route_valid(instance: Instance, shift: Shift) -> bool:
    derived = derive_solution(instance, Solution(shifts=(shift,)))[0]
    driver = instance.drivers[shift.driver]
    has_layover_customer = any(
        operation.point in instance.customer_by_point
        and instance.customer_by_point[operation.point].layover_customer
        for operation in shift.operations
    )
    if derived.layovers > 1:
        return False
    if derived.layovers > 0 and not has_layover_customer:
        return False
    if not is_time_window_valid(shift.start, derived.end, driver.time_windows):
        return False

    previous_driving = 0
    for operation, derived_operation in zip(shift.operations, derived.operations):
        if operation.point in instance.customer_by_point:
            customer = instance.customer_by_point[operation.point]
            if not is_time_window_valid(
                derived_operation.arrival,
                derived_operation.departure,
                customer.time_windows,
            ):
                return False
        if derived_operation.layover_before:
            driving = previous_driving + derived_operation.driving_before_layover
        else:
            driving = derived_operation.driving_since_layover
        if driving > driver.max_driving_duration + EPSILON:
            return False
        previous_driving = derived_operation.driving_since_layover
    return True


def _shift_key(shift: Shift) -> tuple[object, ...]:
    return (
        shift.driver,
        shift.trailer,
        shift.start,
        tuple((op.point, op.arrival, round(op.quantity, 9)) for op in shift.operations),
    )
