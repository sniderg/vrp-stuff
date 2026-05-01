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


def repair_quantities_with_highs(
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
    variables = _delivery_variables(instance, working)

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    inf = highspy.kHighsInf

    for variable in variables:
        customer = instance.customer_by_point[variable.point]
        lower = 0.0 if customer.call_in else min(
            variable.original_quantity,
            customer.min_operation_quantity,
        )
        highs.addCol(
            1.0,
            lower,
            variable.original_quantity,
            0,
            np.array([], dtype=np.int32),
            np.array([], dtype=np.float64),
        )

    constraints = 0
    by_point = _variables_by_point(variables)
    horizon = _repair_horizon(instance, feasibility_days)
    for customer in instance.customers:
        customer_variables = by_point.get(customer.index, [])
        if customer.call_in:
            for order in customer.orders:
                if ignore_tail_call_ins and order.earliest_time >= cutoff:
                    continue
                if order.latest_time >= horizon * instance.unit:
                    continue
                indices = [
                    index
                    for index, variable in customer_variables
                    if order.earliest_time <= variable.arrival <= order.latest_time
                ]
                highs.addRow(
                    order.min_quantity_to_satisfy,
                    inf,
                    len(indices),
                    np.array(indices, dtype=np.int32),
                    np.ones(len(indices), dtype=np.float64),
                )
                constraints += 1
            continue

        cumulative_demand = 0.0
        customer_indices = [
            (index, variable.arrival_step)
            for index, variable in customer_variables
        ]
        for step in range(horizon):
            if step < len(customer.forecast):
                cumulative_demand += customer.forecast[step]
            indices = [
                index
                for index, arrival_step in customer_indices
                if arrival_step <= step
            ]
            lower = customer.safety_level - customer.initial_tank_quantity + cumulative_demand
            upper = customer.capacity - customer.initial_tank_quantity + cumulative_demand
            highs.addRow(
                lower,
                upper,
                len(indices),
                np.array(indices, dtype=np.int32),
                np.ones(len(indices), dtype=np.float64),
            )
            constraints += 1

    highs.run()
    status = highs.modelStatusToString(highs.getModelStatus())
    repaired = working
    if "Optimal" in status:
        solution_values = highs.getSolution().col_value
        repaired = _apply_quantities(working, variables, solution_values)
        repaired = _cap_loads(instance, repaired)

    after = score_prefix_with_feasibility_tail(
        instance,
        repaired,
        score_days=score_days,
        feasibility_days=feasibility_days,
        ignore_tail_call_ins=ignore_tail_call_ins,
    )
    return repaired, HighsRepairReport(
        status=status,
        variables=len(variables),
        constraints=constraints,
        before_feasible=before.feasible,
        after_feasible=after.feasible,
        before_delivered=before.scored_delivered_quantity,
        after_delivered=after.scored_delivered_quantity,
        before_cost=before.scored_estimated_cost,
        after_cost=after.scored_estimated_cost,
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
