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
class _ResourceState:
    driver: int
    trailer: int
    next_window_index: int = 0
    available_time: int = 0
    trailer_quantity: float = 0.0

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
) -> tuple[Solution, ConstructionReport]:
    resources = _initial_resources(instance)
    scheduled: dict[int, dict[int, float]] = {customer.index: {} for customer in instance.customers}
    ignore_before_step: dict[int, int] = {customer.index: 0 for customer in instance.customers}
    shifts: list[Shift] = []
    exhausted_resources = False

    neighborhoods = _compute_neighborhoods(instance, k=neighborhood_size)

    while True:
        if max_shifts is not None and len(shifts) >= max_shifts:
            exhausted_resources = len(_all_needs(instance, scheduled, ignore_before_step)) > 0
            break
        
        all_needs = _all_needs(instance, scheduled, ignore_before_step)
        if not all_needs:
            break
        all_needs.sort(key=lambda x: x[1])

        next_window_info = _next_resource_window(instance, resources)
        if next_window_info is None:
            exhausted_resources = True
            break
        
        start_time, resource_index, window_index, window = next_window_info
        resource = resources[resource_index]

        shift = None
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
            )
            if shift:
                break
        
        if shift is None:
            resource.next_window_index = window_index + 1
            continue

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

def _all_needs(instance: Instance, scheduled, ignore_before_step):
    needs = []
    for customer in instance.customers:
        if customer.call_in: continue
        breach = _first_breach_step(instance, customer, scheduled[customer.index], ignore_before_step[customer.index])
        if breach is not None:
            needs.append((customer, breach))
    return needs

def _compute_neighborhoods(instance: Instance, k: int):
    rows = nearest_neighbors(instance, k=len(instance.time_matrix), metric="distance")
    nb_dict = {}
    for row in rows:
        o = row["origin"]
        if o not in nb_dict: nb_dict[o] = []
        if row["destination_kind"] == "customer" and len(nb_dict[o]) < k:
            nb_dict[o].append(row["destination"])
    return nb_dict

def _build_cluster_shift(instance, resource, window, shift_idx, target, neighbors, scheduled, ignore, buffer):
    driver = instance.drivers[resource.driver]
    start = max(window.start, resource.available_time)
    
    operations = []
    current_pt = instance.base_index
    current_time = start
    driving = 0
    end_after_return = start

    needy_ids = {c.index for c, _ in _all_needs(instance, scheduled, ignore)}
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
            c = _candidate_for_customer(instance, resource, window, current_pt, current_time, driving, customer, scheduled[customer.index], buffer)
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

def _candidate_for_customer(instance, resource, window, current_pt, current_time, driving, customer, deliveries, buffer):
    if not is_trailer_allowed(instance, customer.index, resource.trailer): return None
    source = next((s for s in instance.sources if resource.trailer in s.allowed_trailers), None)
    if source is None: return None
    trailer = instance.trailers[resource.trailer]
    load_qty, source_arr, time, pt, travel, trailer_qty = 0.0, None, current_time, current_pt, 0, resource.trailer_quantity

    # Potential reload
    if trailer_qty < customer.min_operation_quantity - EPSILON:
        source_arr = time + instance.time_matrix[pt][source.index]
        time = source_arr + source.setup_time
        travel += instance.time_matrix[pt][source.index]
        pt = source.index
        load_qty = trailer.capacity - trailer_qty
        trailer_qty = trailer.capacity

    arrival = time + instance.time_matrix[pt][customer.index]
    departure = arrival + customer.setup_time
    total_travel = travel + instance.time_matrix[pt][customer.index]
    ret_travel = instance.time_matrix[customer.index][instance.base_index]
    
    if departure + ret_travel > window.end: return None
    if not is_driving_duration_valid(instance.drivers[resource.driver], driving + total_travel + ret_travel): return None
    if not is_time_window_valid(arrival, departure, customer.time_windows): return None

    arrival_step = min(max(arrival // instance.unit, 0), instance.horizon - 1)
    events = project_customer_inventory(instance, customer, deliveries)
    inv_at_arr = events[arrival_step].after_consumption
    
    max_room = customer.capacity - inv_at_arr
    if max_room < customer.min_operation_quantity - EPSILON: return None
    
    target = _target_inventory(instance, customer, buffer)
    qty = min(trailer_qty, max_room, target - inv_at_arr)
    
    if qty < customer.min_operation_quantity - EPSILON:
        if max_room >= customer.min_operation_quantity - EPSILON and trailer_qty >= customer.min_operation_quantity - EPSILON:
             qty = customer.min_operation_quantity
        else: return None

    return _Candidate(customer=customer, arrival=arrival, departure=departure, quantity=qty, travel_time=total_travel, source_arrival=source_arr, load_quantity=load_qty, source_index=source.index)

def _target_inventory(instance, customer, buffer):
    demand = sum(customer.forecast) / max(instance.horizon / 24.0, 1.0)
    return min(customer.capacity, customer.capacity - buffer * demand)

def _initial_resources(instance):
    res = []
    used_t = set()
    for d in instance.drivers:
        t_id = next((tid for tid in d.trailer_ids if tid not in used_t), None)
        if t_id is not None:
            used_t.add(t_id)
            res.append(_ResourceState(driver=d.index, trailer=t_id, trailer_quantity=instance.trailers[t_id].initial_quantity))
    return res

def _first_breach_step(instance, customer, deliveries, min_step = 0):
    for e in project_customer_inventory(instance, customer, deliveries):
        if e.step >= min_step and e.safety_breach: return e.step
    return None

def _next_resource_window(instance, resources):
    cands = []
    for ri, r in enumerate(resources):
        d = instance.drivers[r.driver]
        for wi in range(r.next_window_index, len(d.time_windows)):
            w = d.time_windows[wi]
            s = max(w.start, r.available_time)
            if s <= w.end:
                cands.append((s, ri, wi, w))
                break
    return min(cands, key=lambda i: (i[0], i[1])) if cands else None
