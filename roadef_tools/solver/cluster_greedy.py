from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Set, Tuple

from ..inventory import project_customer_inventory, tank_events
from ..model import Customer, Instance, Operation, Shift, Solution, TimeWindow
from ..rules import is_driving_duration_valid, is_time_window_valid, is_trailer_allowed
from ..movement import nearest_neighbors


EPSILON = 1e-6

@dataclass(frozen=True)
class ConstructionReport:
    shifts: int
    operations: int
    delivered_quantity: float
    unscheduled_customers: tuple[int, ...]
    exhausted_resources: bool

@dataclass
class _DriverState:
    driver: int
    next_window_index: int = 0
    available_time: int = 0

@dataclass
class _TrailerState:
    trailer: int
    available_time: int = 0
    trailer_quantity: float = 0.0

@dataclass
class _ResourceState:
    driver: int
    trailer: int
    trailer_quantity: float = 0.0
    available_time: int = 0
    trailer_available_time: int = 0

@dataclass(frozen=True)
class _Candidate:
    customer: Customer
    arrival: int
    departure: int
    quantity: float
    travel_time: int
    source_arrival: int | None
    load_quantity: float
    source_index: int | None = None

def construct_cluster_solution(
    instance: Instance,
    *,
    safety_buffer: float = 0.20,
    neighborhood_size: int = 5,
    max_shifts: int | None = None,
    score_cutoff_minute: int | None = None,
    terminal_buffer_days: float = 0.0,
) -> tuple[Solution, ConstructionReport]:
    drivers, trailers = _initial_resources(instance)
    scheduled: dict[int, dict[int, float]] = {customer.index: {} for customer in instance.customers}
    ignore_before_step: dict[int, int] = {customer.index: 0 for customer in instance.customers}
    shifts: list[Shift] = []
    exhausted_resources = False

    neighborhoods = _compute_neighborhoods(instance, k=neighborhood_size)

    while True:
        if max_shifts is not None and len(shifts) >= max_shifts:
            exhausted_resources = len(_all_needs(instance, scheduled, ignore_before_step, score_cutoff_minute)) > 0
            break
        
        all_needs = _all_needs(instance, scheduled, ignore_before_step, score_cutoff_minute)
        if not all_needs:
            break
        all_needs.sort(key=lambda x: x[1])

        next_window_infos = _resource_window_candidates(instance, drivers, trailers, score_cutoff_minute)
        if not next_window_infos:
            exhausted_resources = True
            break

        shift = None
        selected_driver_state_index = None
        selected_trailer_state_index = None
        selected_resource = None
        for start_time, driver_state_index, trailer_state_index, window_index, window, resource in next_window_infos:
            for target_customer, breach_step in all_needs:
                if (breach_step + 1) * instance.unit < start_time:
                    continue

                shift = _build_cluster_shift(
                    instance,
                    resource,
                    window,
                    len(shifts),
                    target_customer,
                    neighborhoods[target_customer.index],
                    scheduled,
                    ignore_before_step,
                    safety_buffer,
                    score_cutoff_minute,
                    terminal_buffer_days,
                )
                if shift:
                    selected_driver_state_index = driver_state_index
                    selected_trailer_state_index = trailer_state_index
                    selected_resource = resource
                    break
            if shift:
                break
        
        if shift is None:
            earliest_start = next_window_infos[0][0]
            for start_time, driver_state_index, _, window_index, _, _ in next_window_infos:
                if start_time != earliest_start:
                    break
                drivers[driver_state_index].next_window_index = max(
                    drivers[driver_state_index].next_window_index,
                    window_index + 1,
                )
            continue

        drivers[selected_driver_state_index].available_time = selected_resource.available_time
        trailers[selected_trailer_state_index].available_time = selected_resource.trailer_available_time
        trailers[selected_trailer_state_index].trailer_quantity = selected_resource.trailer_quantity
        shifts.append(shift)

    unscheduled = tuple(
        customer.index
        for customer in instance.customers
        if _first_breach_step(instance, customer, scheduled[customer.index], 0)
        is not None
    )
    
    solution = Solution(shifts=tuple(shifts))
    return solution, ConstructionReport(
        shifts=len(solution.shifts),
        operations=sum(len(shift.operations) for shift in solution.shifts),
        delivered_quantity=sum(op.quantity for s in solution.shifts for op in s.operations if op.quantity > 0),
        unscheduled_customers=unscheduled,
        exhausted_resources=exhausted_resources,
    )

def _all_needs(instance: Instance, scheduled, ignore_before_step, score_cutoff_minute=None):
    needs = []
    for customer in instance.customers:
        if customer.call_in:
            order = _next_unsatisfied_order(customer, scheduled[customer.index], score_cutoff_minute)
            if order is not None:
                order_index, order_due = order
                needs.append((customer, max(0, order_due.latest_time // instance.unit - 1)))
            continue
        breach = _first_breach_step(
            instance,
            customer,
            scheduled[customer.index],
            ignore_before_step[customer.index],
        )
        if breach is not None:
            needs.append((customer, breach))
    return needs

def _next_unsatisfied_order(customer, deliveries, score_cutoff_minute=None):
    for order_index, order in enumerate(customer.orders):
        if score_cutoff_minute is not None and order.earliest_time >= score_cutoff_minute:
            continue
        delivered = sum(
            quantity
            for arrival, quantity in deliveries.items()
            if order.earliest_time <= arrival <= order.latest_time
        )
        if delivered + EPSILON < order.min_quantity_to_satisfy:
            return order_index, order
    return None

def _compute_neighborhoods(instance: Instance, k: int):
    rows = nearest_neighbors(instance, k=len(instance.time_matrix), metric="distance")
    nb_dict = {}
    for row in rows:
        o = row["origin"]
        if o not in nb_dict: nb_dict[o] = []
        if row["destination_kind"] == "customer" and len(nb_dict[o]) < k:
            nb_dict[o].append(row["destination"])
    return nb_dict

def _build_cluster_shift(
    instance,
    resource,
    window,
    shift_idx,
    target,
    neighbors,
    scheduled,
    ignore,
    buffer,
    score_cutoff_minute,
    terminal_buffer_days,
):
    driver = instance.drivers[resource.driver]
    start = max(window.start, resource.available_time)
    
    operations = []
    current_pt = instance.base_index
    current_time = start
    driving = 0
    end_after_return = start

    needy_ids = {c.index for c, _ in _all_needs(instance, scheduled, ignore, score_cutoff_minute)}
    cand_ids = [target.index] + [n for n in neighbors if n in needy_ids and n != target.index]
    if len(cand_ids) < 5:
        for c_id in needy_ids:
            if c_id not in cand_ids:
                cand_ids.append(c_id)
    
    candidates_to_try = [instance.customer_by_point[cid] for cid in cand_ids]
    served_this_shift = set()

    while True:
        best_cand = None
        for customer in candidates_to_try:
            if customer.index in served_this_shift: continue
            c = _candidate_for_customer(
                instance,
                resource,
                window,
                current_pt,
                current_time,
                driving,
                customer,
                scheduled[customer.index],
                buffer,
                score_cutoff_minute,
                terminal_buffer_days,
            )
            if c:
                best_cand = c
                break
        
        if best_cand is None: break
            
        _apply_cand(operations, resource, scheduled, ignore, best_cand, instance)
        served_this_shift.add(best_cand.customer.index)
        current_pt = best_cand.customer.index
        current_time = best_cand.departure
        driving += best_cand.travel_time
        end_after_return = current_time + instance.time_matrix[current_pt][instance.base_index]

    if not operations: return None
    resource.available_time = end_after_return + driver.min_inter_shift_duration
    resource.trailer_available_time = end_after_return
    return Shift(index=shift_idx, driver=resource.driver, trailer=resource.trailer, start=start, operations=tuple(operations))

def _apply_cand(ops, resource, scheduled, ignore, cand, instance):
    if cand.source_arrival is not None and cand.load_quantity > EPSILON:
        ops.append(Operation(point=cand.source_index, arrival=cand.source_arrival, quantity=-cand.load_quantity))
        resource.trailer_quantity += cand.load_quantity
    ops.append(Operation(point=cand.customer.index, arrival=cand.arrival, quantity=cand.quantity))
    resource.trailer_quantity -= cand.quantity
    scheduled[cand.customer.index][cand.arrival] = scheduled[cand.customer.index].get(cand.arrival, 0.0) + cand.quantity
    arrival_step = min(max(cand.arrival // instance.unit, 0), instance.horizon - 1)
    ignore[cand.customer.index] = max(ignore[cand.customer.index], arrival_step + 1)

def _candidate_for_customer(
    instance,
    resource,
    window,
    current_pt,
    current_time,
    driving,
    customer,
    deliveries,
    buffer,
    score_cutoff_minute=None,
    terminal_buffer_days=0.0,
):
    if not is_trailer_allowed(instance, customer.index, resource.trailer): return None
    if customer.call_in:
        return _candidate_for_call_in(
            instance,
            resource,
            window,
            current_pt,
            current_time,
            driving,
            customer,
            deliveries,
            score_cutoff_minute,
        )
    source = next((s for s in instance.sources if resource.trailer in s.allowed_trailers), None)
    if source is None: return None
    trailer = instance.trailers[resource.trailer]
    load_qty, source_arr, time, pt, travel, trailer_qty = 0.0, None, current_time, current_pt, 0, resource.trailer_quantity

    # Potential reload
    if trailer_qty < customer.min_operation_quantity - EPSILON:
        source_arr = time + instance.time_matrix[pt][source.index]
        if score_cutoff_minute is not None and source_arr >= score_cutoff_minute:
            return None
        time = source_arr + source.setup_time
        travel += instance.time_matrix[pt][source.index]
        pt = source.index
        load_qty = trailer.capacity - trailer_qty
        trailer_qty = trailer.capacity

    arrival = time + instance.time_matrix[pt][customer.index]
    if score_cutoff_minute is not None and arrival >= score_cutoff_minute:
        return None
    departure = arrival + customer.setup_time
    total_travel = travel + instance.time_matrix[pt][customer.index]
    ret_travel = instance.time_matrix[customer.index][instance.base_index]
    
    if departure + ret_travel > window.end: return None
    if not is_driving_duration_valid(instance.drivers[resource.driver], driving + total_travel + ret_travel): return None
    if not is_time_window_valid(arrival, departure, customer.time_windows): return None

    arrival_step = min(max(arrival // instance.unit, 0), instance.horizon - 1)
    events = project_customer_inventory(instance, customer, deliveries)
    inv_at_arr = events[arrival_step].after_consumption
    already_delivered = sum(
        quantity
        for delivery_arrival, quantity in deliveries.items()
        if min(max(delivery_arrival // instance.unit, 0), instance.horizon - 1) == arrival_step
    )
    
    max_room = customer.capacity - inv_at_arr - already_delivered
    if max_room < customer.min_operation_quantity - EPSILON: return None
    
    target = _target_inventory(
        instance,
        customer,
        buffer,
        arrival_step=arrival_step,
        terminal_buffer_days=terminal_buffer_days,
    )
    qty = min(trailer_qty, max_room, target - inv_at_arr - already_delivered)
    
    if qty < customer.min_operation_quantity - EPSILON:
        if max_room >= customer.min_operation_quantity - EPSILON and trailer_qty >= customer.min_operation_quantity - EPSILON:
             qty = customer.min_operation_quantity
        else: return None

    qty = _cap_quantity_without_future_overfill(instance, customer, deliveries, arrival, qty)
    if qty < customer.min_operation_quantity - EPSILON:
        return None

    return _Candidate(customer=customer, arrival=arrival, departure=departure, quantity=qty, travel_time=total_travel, source_arrival=source_arr, load_quantity=load_qty, source_index=source.index)

def _candidate_for_call_in(
    instance,
    resource,
    window,
    current_pt,
    current_time,
    driving,
    customer,
    deliveries,
    score_cutoff_minute=None,
):
    order_info = _next_unsatisfied_order(customer, deliveries, score_cutoff_minute)
    if order_info is None:
        return None
    _, order = order_info
    source = next((s for s in instance.sources if resource.trailer in s.allowed_trailers), None)
    if source is None:
        return None

    delivered = sum(
        quantity
        for arrival, quantity in deliveries.items()
        if order.earliest_time <= arrival <= order.latest_time
    )
    remaining = order.min_quantity_to_satisfy - delivered
    if remaining <= EPSILON:
        return None

    trailer = instance.trailers[resource.trailer]
    trailer_qty = resource.trailer_quantity
    load_qty = 0.0
    source_arr = None
    time = current_time
    point = current_pt
    travel = 0
    if trailer_qty < min(remaining, trailer.capacity) - EPSILON:
        source_arr = time + instance.time_matrix[point][source.index]
        if score_cutoff_minute is not None and source_arr >= score_cutoff_minute:
            return None
        time = source_arr + source.setup_time
        travel += instance.time_matrix[point][source.index]
        point = source.index
        load_qty = trailer.capacity - trailer_qty
        trailer_qty = trailer.capacity

    raw_arrival = time + instance.time_matrix[point][customer.index]
    arrival = max(raw_arrival, order.earliest_time)
    if arrival - time >= instance.drivers[resource.driver].layover_duration + instance.time_matrix[point][customer.index]:
        return None
    if score_cutoff_minute is not None and arrival >= score_cutoff_minute:
        return None
    if arrival > order.latest_time:
        return None
    departure = arrival + customer.setup_time
    total_travel = travel + instance.time_matrix[point][customer.index]
    ret_travel = instance.time_matrix[customer.index][instance.base_index]

    if departure + ret_travel > window.end:
        return None
    if not is_driving_duration_valid(instance.drivers[resource.driver], driving + total_travel + ret_travel):
        return None
    if not is_time_window_valid(arrival, departure, customer.time_windows):
        return None

    qty = min(trailer_qty, remaining)
    if qty <= EPSILON:
        return None
    return _Candidate(
        customer=customer,
        arrival=arrival,
        departure=departure,
        quantity=qty,
        travel_time=total_travel,
        source_arrival=source_arr,
        load_quantity=load_qty,
        source_index=source.index,
    )

def _cap_quantity_without_future_overfill(instance, customer, deliveries, arrival, quantity):
    capped = quantity
    for _ in range(10):
        proposed = dict(deliveries)
        proposed[arrival] = proposed.get(arrival, 0.0) + capped
        overflow = max(
            (
                event.ending_inventory - customer.capacity
                for event in project_customer_inventory(instance, customer, proposed)
            ),
            default=0.0,
        )
        if overflow <= EPSILON:
            return capped
        capped -= overflow
        if capped <= EPSILON:
            return 0.0
    return max(0.0, capped)

def _target_inventory(
    instance,
    customer,
    buffer,
    *,
    arrival_step: int | None = None,
    terminal_buffer_days: float = 0.0,
):
    if arrival_step is not None:
        remaining_forecast = sum(customer.forecast[arrival_step:])
        steps_per_day = max(1, 1440 // instance.unit)
        buffer_steps = max(0, int(round(terminal_buffer_days * steps_per_day)))
        if buffer_steps:
            tail = list(customer.forecast[-steps_per_day:]) or [0.0]
            remaining_forecast += sum(tail[i % len(tail)] for i in range(buffer_steps))
        return min(customer.capacity, customer.safety_level + remaining_forecast)
    demand = sum(customer.forecast) / max(instance.horizon / 24.0, 1.0)
    return min(customer.capacity, customer.capacity - buffer * demand)

def _initial_resources(instance):
    drivers = [_DriverState(driver=driver.index) for driver in instance.drivers]
    trailers = [
        _TrailerState(
            trailer=trailer.index,
            trailer_quantity=trailer.initial_quantity,
        )
        for trailer in instance.trailers
    ]
    return drivers, trailers

def _first_breach_step(instance, customer, deliveries, min_step = 0):
    for e in project_customer_inventory(instance, customer, deliveries):
        if e.step >= min_step and e.safety_breach: return e.step
    return None

def _resource_window_candidates(instance, drivers, trailers, score_cutoff_minute=None):
    cands = []
    for di, driver_state in enumerate(drivers):
        d = instance.drivers[driver_state.driver]
        for wi in range(driver_state.next_window_index, len(d.time_windows)):
            w = d.time_windows[wi]
            has_candidate_for_window = False
            for ti, trailer_state in enumerate(trailers):
                if trailer_state.trailer not in d.trailer_ids:
                    continue
                s = max(w.start, driver_state.available_time, trailer_state.available_time)
                if score_cutoff_minute is not None and s >= score_cutoff_minute:
                    continue
                if s <= w.end:
                    resource = _ResourceState(
                        driver=driver_state.driver,
                        trailer=trailer_state.trailer,
                        trailer_quantity=trailer_state.trailer_quantity,
                        available_time=s,
                        trailer_available_time=s,
                    )
                    cands.append((s, di, ti, wi, w, resource))
                    has_candidate_for_window = True
            if has_candidate_for_window:
                break
    return sorted(cands, key=lambda i: (i[0], i[1], i[2]))
