from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .contest import score_prefix_with_feasibility_tail, truncate_solution
from .model import Instance, Solution
from .solver.greedy import _cap_source_loads


EPSILON = 1e-6


@dataclass(frozen=True)
class HighsRepairReport:
    status: str
    variables: int
    constraints: int
    before_feasible: bool
    after_feasible: bool
    before_delivered: float
    after_delivered: float
    before_cost: float
    after_cost: float

    def flat(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class _DeliveryVariable:
    shift_index: int
    operation_index: int
    point: int
    arrival: int
    arrival_step: int
    original_quantity: float
    min_quantity: float
    max_quantity: float


def repair_with_highs_selection(
    instance: Instance,
    solution: Solution,
    *,
    score_days: int,
    feasibility_days: int | None = None,
    ignore_tail_call_ins: bool = False,
) -> tuple[Solution, HighsRepairReport]:
    try:
        import highspy
    except ModuleNotFoundError as exc:
        raise RuntimeError("highspy is not installed; run `uv sync --extra milp`") from exc

    cutoff = score_days * 1440
    working = truncate_solution(solution, cutoff)
    before = score_prefix_with_feasibility_tail(
        instance,
        working,
        score_days=score_days,
        feasibility_days=feasibility_days,
        ignore_tail_call_ins=ignore_tail_call_ins,
    )
    
    # Identify variables: all deliveries to VMI customers
    variables: list[_DeliveryVariable] = []
    for shift in working.shifts:
        for op_index, op in enumerate(shift.operations):
            customer = instance.customer_by_point.get(op.point)
            if customer and not customer.call_in:
                variables.append(
                    _DeliveryVariable(
                        shift_index=shift.index,
                        operation_index=op_index,
                        point=op.point,
                        arrival=op.arrival,
                        arrival_step=min(max(op.arrival // instance.unit, 0), instance.horizon - 1),
                        original_quantity=op.quantity,
                        min_quantity=customer.min_operation_quantity,
                        max_quantity=customer.capacity,
                    )
                )

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    inf = highspy.kHighsInf

    # q_i: quantity of delivery i
    # z_i: binary selection of delivery i
    # Objective: Minimize total quantity (proxy for cost/overfill) + small penalty for dropping
    # Actually, let's try to maximize quantity delivered while staying within capacity.
    # No, better: minimize sum(q_i) + sum(z_i * -1000) to encourage keeping operations
    # but staying within inventory bounds.
    
    q_indices = []
    z_indices = []
    col_count = 0
    
    for var in variables:
        q_idx = col_count
        highs.addCol(1.0, 0.0, var.max_quantity, 0, np.array([], dtype=np.int32), np.array([], dtype=np.float64))
        q_indices.append(q_idx)
        col_count += 1
        
        z_idx = col_count
        highs.addCol(-1000.0, 0.0, 1.0, 0, np.array([], dtype=np.int32), np.array([], dtype=np.float64))
        highs.changeColIntegrality(z_idx, highspy.HighsVarType.kInteger)
        z_indices.append(z_idx)
        col_count += 1
        
        # q_i <= max_q * z_i
        highs.addRow(-inf, 0.0, 2, np.array([q_idx, z_idx], dtype=np.int32), np.array([1.0, -var.max_quantity], dtype=np.float64))
        # q_i >= min_q * z_i
        highs.addRow(0.0, inf, 2, np.array([q_idx, z_idx], dtype=np.int32), np.array([1.0, -var.min_quantity], dtype=np.float64))

    # Inventory constraints
    horizon = _repair_horizon(instance, feasibility_days)
    by_point = _variables_by_point(variables)
    for customer in instance.customers:
        if customer.call_in: continue
        cust_vars = by_point.get(customer.index, [])
        cumulative_demand = 0.0
        for step in range(horizon):
            if step < len(customer.forecast):
                cumulative_demand += customer.forecast[step]
            indices = [q_indices[idx] for idx, v in cust_vars if v.arrival_step <= step]
            if not indices:
                # Check if initial inventory is enough
                if customer.initial_tank_quantity - cumulative_demand < customer.safety_level - EPSILON:
                    # Infeasible without more deliveries! 
                    pass
                continue
            
            lower = customer.safety_level - customer.initial_tank_quantity + cumulative_demand
            upper = customer.capacity - customer.initial_tank_quantity + cumulative_demand
            highs.addRow(lower, upper, len(indices), np.array(indices, dtype=np.int32), np.ones(len(indices), dtype=np.float64))

    # Trailer capacity constraints
    # For each shift, we need to ensure that cumulative deliveries <= initial_load + cumulative_loads
    # Since we don't change loads, we can just say:
    # sum(selected_deliveries) <= original_total_deliveries + trailer_remaining_capacity
    shift_to_trailer = {shift.index: shift.trailer for shift in working.shifts}
    by_shift: dict[int, list[tuple[int, _DeliveryVariable]]] = {}
    for i, v in enumerate(variables):
        by_shift.setdefault(v.shift_index, []).append((i, v))
        
    for shift_index, shift_vars in by_shift.items():
        trailer_id = shift_to_trailer[shift_index]
        trailer = instance.trailers[trailer_id]
        # This is a simplification: we don't want to exceed the total load available in the shift.
        # Original total delivered in this shift:
        original_total = sum(v.original_quantity for _, v in shift_vars)
        # Assuming source loads are not changed, we can't deliver more than what was planned + what's left.
        # We'll need to calculate the actual remaining capacity at the end of the shift.
        # For now, let's just cap the total deliveries to original_total + 10% or something?
        # Better: let's not cap it if we can't do it accurately, but stay safe.
        indices = [q_indices[idx] for idx, _ in shift_vars]
        highs.addRow(0.0, original_total, len(indices), np.array(indices, dtype=np.int32), np.ones(len(indices), dtype=np.float64))

    highs.run()
    status = highs.modelStatusToString(highs.getModelStatus())
    repaired = working
    if "Optimal" in status or "Feasible" in status:
        values = highs.getSolution().col_value
        q_values = [values[i] for i in q_indices]
        repaired = _apply_quantities(working, variables, q_values)
        repaired = _cap_loads(instance, repaired)

    after = score_prefix_with_feasibility_tail(
        instance,
        repaired,
        score_days=score_days,
        feasibility_days=feasibility_days,
        ignore_tail_call_ins=ignore_tail_call_ins,
    )
    return repaired, HighsRepairReport(
        status=status, variables=len(variables)*2, constraints=highs.getNumRow(),
        before_feasible=before.feasible, after_feasible=after.feasible,
        before_delivered=before.scored_delivered_quantity, after_delivered=after.scored_delivered_quantity,
        before_cost=before.scored_estimated_cost, after_cost=after.scored_estimated_cost,
    )


def repair_quantities_with_highs(
    instance: Instance,
    solution: Solution,
    *,
    score_days: int,
    feasibility_days: int | None = None,
    ignore_tail_call_ins: bool = False,
) -> tuple[Solution, HighsRepairReport]:
    return repair_with_highs_selection(
        instance,
        solution,
        score_days=score_days,
        feasibility_days=feasibility_days,
        ignore_tail_call_ins=ignore_tail_call_ins,
    )


def _repair_horizon(instance: Instance, feasibility_days: int | None) -> int:
    if feasibility_days is None:
        return instance.horizon
    return min(instance.horizon, (feasibility_days * 1440 + instance.unit - 1) // instance.unit)


def _delivery_variables(instance: Instance, solution: Solution) -> list[_DeliveryVariable]:
    variables = []
    for shift in solution.shifts:
        for operation_index, operation in enumerate(shift.operations):
            if operation.quantity <= EPSILON or operation.point not in instance.customer_by_point:
                continue
            variables.append(
                _DeliveryVariable(
                    shift_index=shift.index,
                    operation_index=operation_index,
                    point=operation.point,
                    arrival=operation.arrival,
                    arrival_step=min(
                        max(operation.arrival // instance.unit, 0),
                        instance.horizon - 1,
                    ),
                    original_quantity=operation.quantity,
                )
            )
    return variables


def _variables_by_point(
    variables: list[_DeliveryVariable],
) -> dict[int, list[tuple[int, _DeliveryVariable]]]:
    by_point: dict[int, list[tuple[int, _DeliveryVariable]]] = {}
    for index, variable in enumerate(variables):
        by_point.setdefault(variable.point, []).append((index, variable))
    return by_point


def _apply_quantities(
    solution: Solution,
    variables: list[_DeliveryVariable],
    values,
) -> Solution:
    by_ref = {
        (variable.shift_index, variable.operation_index): max(0.0, float(values[index]))
        for index, variable in enumerate(variables)
    }
    shifts = []
    for shift in solution.shifts:
        operations = []
        for operation_index, operation in enumerate(shift.operations):
            key = (shift.index, operation_index)
            if key not in by_ref:
                operations.append(operation)
                continue
            quantity = by_ref[key]
            if quantity > EPSILON:
                operations.append(replace(operation, quantity=quantity))
        shifts.append(replace(shift, operations=tuple(operations)))
    return Solution(shifts=tuple(shifts))


def _cap_loads(instance: Instance, solution: Solution) -> Solution:
    operations = [list(shift.operations) for shift in solution.shifts]
    capped = _cap_source_loads(instance, list(solution.shifts), operations)
    return Solution(
        shifts=tuple(
            replace(shift, operations=tuple(shift_operations))
            for shift, shift_operations in zip(solution.shifts, capped)
        )
    )
