from __future__ import annotations

from dataclasses import dataclass, replace

from .analysis import summarize_solution
from .contest import score_prefix_with_feasibility_tail
from .model import Instance, Solution


@dataclass(frozen=True)
class PruneReport:
    initial_shifts: int
    final_shifts: int
    removed_shifts: tuple[int, ...]
    initial_cost: float
    final_cost: float
    feasible: bool

    def flat(self) -> dict[str, object]:
        row = self.__dict__.copy()
        row["removed_shifts"] = " ".join(str(index) for index in self.removed_shifts)
        return row


def prune_redundant_shifts(
    instance: Instance,
    solution: Solution,
    *,
    score_days: int,
    feasibility_days: int | None = None,
    ignore_tail_call_ins: bool = False,
    max_passes: int = 3,
) -> tuple[Solution, PruneReport]:
    """Remove whole shifts when contest feasibility survives.

    This is intentionally conservative. It does not reinsert operations or alter
    timing; it only deletes shifts that are redundant under the contest metric.
    """

    current = solution
    initial = score_prefix_with_feasibility_tail(
        instance,
        current,
        score_days=score_days,
        feasibility_days=feasibility_days,
        ignore_tail_call_ins=ignore_tail_call_ins,
    )
    removed: list[int] = []

    for _ in range(max_passes):
        changed = False
        for shift_index in _removal_order(instance, current):
            candidate = Solution(
                shifts=tuple(
                    shift
                    for shift in current.shifts
                    if shift.index != shift_index
                )
            )
            score = score_prefix_with_feasibility_tail(
                instance,
                candidate,
                score_days=score_days,
                feasibility_days=feasibility_days,
                ignore_tail_call_ins=ignore_tail_call_ins,
            )
            if not score.feasible:
                continue
            current = candidate
            removed.append(shift_index)
            changed = True
            break
        if not changed:
            break

    final = score_prefix_with_feasibility_tail(
        instance,
        current,
        score_days=score_days,
        feasibility_days=feasibility_days,
        ignore_tail_call_ins=ignore_tail_call_ins,
    )
    return current, PruneReport(
        initial_shifts=initial.scored_shifts,
        final_shifts=final.scored_shifts,
        removed_shifts=tuple(removed),
        initial_cost=initial.scored_estimated_cost,
        final_cost=final.scored_estimated_cost,
        feasible=final.feasible,
    )


def trim_redundant_deliveries(
    instance: Instance,
    solution: Solution,
    *,
    score_days: int,
    feasibility_days: int | None = None,
    ignore_tail_call_ins: bool = False,
    step_fraction: float = 0.25,
    max_rounds: int = 5,
) -> Solution:
    """Conservatively reduce delivery quantities while preserving feasibility."""

    current = solution
    for _ in range(max_rounds):
        changed = False
        for shift in sorted(current.shifts, key=lambda item: item.index, reverse=True):
            for operation_index in range(len(shift.operations) - 1, -1, -1):
                operation = shift.operations[operation_index]
                customer = instance.customer_by_point.get(operation.point)
                if customer is None or customer.call_in or operation.quantity <= 0:
                    continue
                reduction = max(customer.min_operation_quantity, operation.quantity * step_fraction)
                if operation.quantity - reduction <= 0:
                    continue
                candidate = _replace_operation_quantity(
                    current,
                    shift.index,
                    operation_index,
                    operation.quantity - reduction,
                )
                score = score_prefix_with_feasibility_tail(
                    instance,
                    candidate,
                    score_days=score_days,
                    feasibility_days=feasibility_days,
                    ignore_tail_call_ins=ignore_tail_call_ins,
                )
                if not score.feasible:
                    continue
                current = candidate
                changed = True
                break
            if changed:
                break
        if not changed:
            break
    return current


def remove_redundant_source_visits(
    instance: Instance,
    solution: Solution,
    *,
    score_days: int,
    feasibility_days: int | None = None,
    ignore_tail_call_ins: bool = False,
    max_rounds: int = 10,
) -> Solution:
    """Remove source loading operations when feasibility survives."""

    current = solution
    for _ in range(max_rounds):
        changed = False
        for shift in sorted(current.shifts, key=lambda item: item.index, reverse=True):
            for operation_index in range(len(shift.operations) - 1, -1, -1):
                operation = shift.operations[operation_index]
                if operation.point not in instance.source_by_point or operation.quantity >= 0:
                    continue
                candidate = _remove_operation(current, shift.index, operation_index)
                score = score_prefix_with_feasibility_tail(
                    instance,
                    candidate,
                    score_days=score_days,
                    feasibility_days=feasibility_days,
                    ignore_tail_call_ins=ignore_tail_call_ins,
                )
                if not score.feasible:
                    continue
                current = candidate
                changed = True
                break
            if changed:
                break
        if not changed:
            break
    return current


def _replace_operation_quantity(
    solution: Solution,
    shift_index: int,
    operation_index: int,
    quantity: float,
) -> Solution:
    shifts = []
    for shift in solution.shifts:
        if shift.index != shift_index:
            shifts.append(shift)
            continue
        operations = list(shift.operations)
        operations[operation_index] = replace(operations[operation_index], quantity=quantity)
        shifts.append(replace(shift, operations=tuple(operations)))
    return Solution(shifts=tuple(shifts))


def _remove_operation(
    solution: Solution,
    shift_index: int,
    operation_index: int,
) -> Solution:
    shifts = []
    for shift in solution.shifts:
        if shift.index != shift_index:
            shifts.append(shift)
            continue
        operations = list(shift.operations)
        operations.pop(operation_index)
        shifts.append(replace(shift, operations=tuple(operations)))
    return Solution(shifts=tuple(shifts))


def _removal_order(instance: Instance, solution: Solution) -> list[int]:
    summaries = summarize_solution(instance, solution)
    return [
        summary.index
        for summary in sorted(
            summaries,
            key=lambda item: (
                item.delivered_quantity,
                -item.estimated_cost,
                item.operations,
            ),
        )
    ]
