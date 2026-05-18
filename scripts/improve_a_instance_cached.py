from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import highspy
import numpy as np

from roadef_tools.analysis import summarize_solution
from roadef_tools.contest import score_prefix_with_feasibility_tail
from roadef_tools.highs_repair import (
    _DeliveryVariable,
    _add_trailer_load_constraints,
    _apply_quantities,
)
from roadef_tools.model import Instance, Operation, Shift, Solution
from roadef_tools.route_cache import RouteCache
from roadef_tools.rules import derive_solution, is_time_window_valid
from roadef_tools.xml_io import load_instance, load_solution, save_solution


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("instance_xml", type=Path)
    parser.add_argument("solution_xml", type=Path)
    parser.add_argument("output_xml", type=Path)
    parser.add_argument("--passes", type=int, default=4)
    parser.add_argument("--max-tries", type=int, default=900)
    parser.add_argument("--max-extra-customers", type=int, default=4)
    parser.add_argument("--max-route-customers", type=int, default=6)
    parser.add_argument("--merge-rounds", type=int, default=2)
    args = parser.parse_args()

    instance = load_instance(args.instance_xml)
    best = load_solution(args.solution_xml)
    best = _maxfill(instance, best) or best
    best_score, best_ratio = _score(instance, best)
    cache = RouteCache(instance)
    print(
        "initial",
        best_score.feasible,
        best_score.scored_estimated_cost,
        best_score.scored_delivered_quantity,
        best_ratio,
        flush=True,
    )

    best, best_score, best_ratio = _expand_routes(
        instance,
        cache,
        best,
        best_score,
        best_ratio,
        passes=args.passes,
        max_tries=args.max_tries,
        max_extra_customers=args.max_extra_customers,
        max_route_customers=args.max_route_customers,
        output_xml=args.output_xml,
    )
    best, best_score, best_ratio = _merge_routes(
        instance,
        cache,
        best,
        best_score,
        best_ratio,
        rounds=args.merge_rounds,
        max_tries=args.max_tries,
        max_route_customers=args.max_route_customers,
        output_xml=args.output_xml,
    )

    save_solution(best, args.output_xml)
    print(
        "final",
        best_score.feasible,
        best_score.scored_estimated_cost,
        best_score.scored_delivered_quantity,
        best_ratio,
        len(best.shifts),
        flush=True,
    )
    return 0


def _customer_pool(instance: Instance) -> list[int]:
    ranked = sorted(
        instance.customers,
        key=lambda customer: (
            -sum(customer.forecast),
            instance.distance_matrix[instance.sources[0].index][customer.index],
            customer.index,
        ),
    )
    return [customer.index for customer in ranked]


def _source_id(instance: Instance) -> int:
    return instance.sources[0].index


def _rebuild_shift(instance: Instance, shift: Shift, sequence: tuple[int, ...]) -> Shift:
    source_id = _source_id(instance)
    start = shift.start
    operations = [Operation(source_id, start, -instance.trailers[shift.trailer].capacity)]
    current_time = start + instance.setup_time_for_point(source_id)
    current_point = source_id
    for point in sequence:
        arrival = current_time + instance.time_matrix[current_point][point]
        operations.append(Operation(point, arrival, 0.0))
        current_time = arrival + instance.setup_time_for_point(point)
        current_point = point
    return Shift(shift.index, shift.driver, shift.trailer, start, tuple(operations))


def _route_ok(instance: Instance, shift: Shift) -> bool:
    derived = derive_solution(instance, Solution((shift,)))[0]
    driver = instance.drivers[shift.driver]
    if derived.layovers:
        return False
    if not is_time_window_valid(shift.start, derived.end, driver.time_windows):
        return False
    return all(
        operation.driving_since_layover <= driver.max_driving_duration
        for operation in derived.operations
    )


def _served(instance: Instance, shift: Shift) -> tuple[int, ...]:
    return tuple(
        dict.fromkeys(
            operation.point
            for operation in shift.operations
            if operation.quantity > 1e-6 and operation.point in instance.customer_by_point
        )
    )


def _score(instance: Instance, solution: Solution):
    score = score_prefix_with_feasibility_tail(
        instance,
        solution,
        score_days=max(1, instance.horizon * instance.unit // 1440),
        feasibility_days=max(1, instance.horizon * instance.unit // 1440),
    )
    ratio = (
        score.scored_estimated_cost / score.scored_delivered_quantity
        if score.scored_delivered_quantity
        else 10**9
    )
    return score, ratio


def _maxfill(instance: Instance, solution: Solution) -> Solution | None:
    variables: list[_DeliveryVariable] = []
    for shift in solution.shifts:
        for operation_index, operation in enumerate(shift.operations):
            customer = instance.customer_by_point.get(operation.point)
            if customer and not customer.call_in:
                variables.append(
                    _DeliveryVariable(
                        shift.index,
                        operation_index,
                        operation.point,
                        operation.arrival,
                        min(max(operation.arrival // instance.unit, 0), instance.horizon - 1),
                        operation.quantity,
                        customer.min_operation_quantity,
                        customer.capacity,
                    )
                )

    highs = highspy.Highs()
    highs.setOptionValue("output_flag", False)
    q_indices = []
    for variable in variables:
        q_indices.append(highs.getNumCol())
        highs.addCol(
            -1.0,
            variable.min_quantity,
            variable.max_quantity,
            0,
            np.array([], dtype=np.int32),
            np.array([], dtype=np.float64),
        )

    by_point: dict[int, list[tuple[int, _DeliveryVariable]]] = {}
    for index, variable in enumerate(variables):
        by_point.setdefault(variable.point, []).append((index, variable))

    for customer in instance.customers:
        if customer.call_in:
            continue
        entries = by_point.get(customer.index, [])
        cumulative = 0.0
        for step in range(instance.horizon):
            if step < len(customer.forecast):
                cumulative += customer.forecast[step]
            cols = [
                q_indices[index]
                for index, variable in entries
                if variable.arrival_step <= step
            ]
            if not cols:
                continue
            highs.addRow(
                customer.safety_level - customer.initial_tank_quantity + cumulative,
                customer.capacity - customer.initial_tank_quantity + cumulative,
                len(cols),
                np.array(cols, dtype=np.int32),
                np.ones(len(cols), dtype=np.float64),
            )

    _add_trailer_load_constraints(instance, solution, variables, q_indices, highs)
    highs.run()
    status = highs.modelStatusToString(highs.getModelStatus())
    if "Optimal" not in status and "Feasible" not in status:
        return None
    return _apply_quantities(solution, variables, highs.getSolution().col_value)


def _expand_routes(
    instance: Instance,
    cache: RouteCache,
    best: Solution,
    best_score,
    best_ratio: float,
    *,
    passes: int,
    max_tries: int,
    max_extra_customers: int,
    max_route_customers: int,
    output_xml: Path,
):
    pool = _customer_pool(instance)
    tries = 0
    for pass_index in range(passes):
        summaries = {summary.index: summary for summary in summarize_solution(instance, best)}
        expansions = []
        for shift_index, shift in enumerate(best.shifts):
            served = _served(instance, shift)
            if not served:
                continue
            summary = summaries[shift.index]
            base = set(served)
            candidates = [point for point in pool[: min(len(pool), 18)] if point not in base]
            for add_count in range(1, min(max_extra_customers, len(candidates)) + 1):
                for add in combinations(candidates, add_count):
                    subset = tuple(sorted(base | set(add)))
                    if len(subset) > max_route_customers:
                        continue
                    stats = cache.best_order(
                        subset,
                        start_point=_source_id(instance),
                        end_point=instance.base_index,
                        max_bruteforce=7,
                    )
                    if stats.duration + instance.setup_time_for_point(_source_id(instance)) > 900:
                        continue
                    allowance = 260 if any(point in add for point in pool[:4]) else 120
                    if stats.distance > summary.estimated_cost + allowance:
                        continue
                    candidate_shift = _rebuild_shift(instance, shift, stats.sequence)
                    if _route_ok(instance, candidate_shift):
                        expansions.append(
                            (
                                stats.distance - summary.estimated_cost,
                                -len(stats.sequence),
                                shift_index,
                                stats.sequence,
                                stats.distance,
                            )
                        )
        print("expand_pass", pass_index, "candidates", len(expansions), "tries", tries, flush=True)
        accepted = False
        for _delta, _length, shift_index, sequence, _distance in sorted(expansions):
            candidate_shifts = list(best.shifts)
            candidate_shifts[shift_index] = _rebuild_shift(
                instance,
                candidate_shifts[shift_index],
                sequence,
            )
            tries += 1
            filled = _maxfill(instance, Solution(tuple(candidate_shifts)))
            if filled is None:
                continue
            candidate_score, candidate_ratio = _score(instance, filled)
            if candidate_score.feasible and candidate_ratio < best_ratio - 1e-9:
                best, best_score, best_ratio = filled, candidate_score, candidate_ratio
                save_solution(best, output_xml)
                print(
                    "accept_expand",
                    pass_index,
                    candidate_score.scored_estimated_cost,
                    candidate_score.scored_delivered_quantity,
                    candidate_ratio,
                    flush=True,
                )
                accepted = True
                break
            if tries >= max_tries:
                break
        if not accepted or tries >= max_tries:
            break
    return best, best_score, best_ratio


def _merge_routes(
    instance: Instance,
    cache: RouteCache,
    best: Solution,
    best_score,
    best_ratio: float,
    *,
    rounds: int,
    max_tries: int,
    max_route_customers: int,
    output_xml: Path,
):
    tries = 0
    for round_index in range(rounds):
        summaries = {summary.index: summary for summary in summarize_solution(instance, best)}
        worst = sorted(
            best.shifts,
            key=lambda shift: summaries[shift.index].estimated_cost
            / max(summaries[shift.index].delivered_quantity, 1.0),
            reverse=True,
        )[:12]
        accepted = False
        for removed in worst:
            removed_served = _served(instance, removed)
            if not removed_served:
                continue
            for target_index, target in enumerate(best.shifts):
                if target.index == removed.index:
                    continue
                target_served = _served(instance, target)
                if not target_served:
                    continue
                subset = tuple(sorted(set(removed_served) | set(target_served)))
                if len(subset) > max_route_customers:
                    continue
                stats = cache.best_order(
                    subset,
                    start_point=_source_id(instance),
                    end_point=instance.base_index,
                    max_bruteforce=7,
                )
                if stats.duration + instance.setup_time_for_point(_source_id(instance)) > 900:
                    continue
                old_cost = summaries[removed.index].estimated_cost + summaries[target.index].estimated_cost
                if stats.distance > old_cost - 80:
                    continue
                merged = _rebuild_shift(instance, target, stats.sequence)
                if not _route_ok(instance, merged):
                    continue
                candidate_shifts = []
                for shift in best.shifts:
                    if shift.index == removed.index:
                        continue
                    candidate_shifts.append(merged if shift.index == target.index else shift)
                tries += 1
                filled = _maxfill(instance, Solution(tuple(candidate_shifts)))
                if filled is None:
                    continue
                candidate_score, candidate_ratio = _score(instance, filled)
                if candidate_score.feasible and candidate_ratio < best_ratio - 1e-9:
                    best, best_score, best_ratio = filled, candidate_score, candidate_ratio
                    save_solution(best, output_xml)
                    print(
                        "accept_merge",
                        round_index,
                        candidate_score.scored_estimated_cost,
                        candidate_score.scored_delivered_quantity,
                        candidate_ratio,
                        flush=True,
                    )
                    accepted = True
                    break
                if tries >= max_tries:
                    break
            if accepted or tries >= max_tries:
                break
        if not accepted or tries >= max_tries:
            break
    return best, best_score, best_ratio


if __name__ == "__main__":
    raise SystemExit(main())
