from __future__ import annotations

import csv
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from roadef_tools.inventory import tank_events
from roadef_tools.rules import derive_solution
from roadef_tools.model import Operation, Shift, Solution
from roadef_tools.xml_io import load_instance, load_solution, save_solution


ROOT = Path(__file__).resolve().parent
INSTANCE_XML = ROOT / "roadef_2016_data/set_B/Instances_B_V25-11042016/V2.12.xml"
BASE_SOLUTION_XML = (
    ROOT / "roadef_2016_data/hust_smart_results/ROADEF2016-IRP-Results-master/2.12_0.xml"
)
OUT_DIR = ROOT / "roadef_2016_data/edge_case_probes"
CHECKER_EXE = (
    ROOT
    / "roadef_2016_data/checker_v2/Challenge_Roadef_EURO_Checker_V2/bin/Release/IRP_Roadef_Challenge_Checker.exe"
)
VALID_RE = re.compile(r"THIS OUTPUT IS VALID")
FAIL_RE = re.compile(r"CHECKING FAILED")
RATIO_RE = re.compile(r"Logistic Ratio\s*=\s*([0-9]+(?:[.,][0-9]+)?)")


def with_operation(
    solution: Solution,
    shift_index: int,
    operation_index: int,
    operation: Operation,
) -> Solution:
    shifts = []
    for shift in solution.shifts:
        if shift.index != shift_index:
            shifts.append(shift)
            continue
        operations = list(shift.operations)
        operations[operation_index] = operation
        shifts.append(replace(shift, operations=tuple(operations)))
    return Solution(shifts=tuple(shifts))


def with_operations(
    solution: Solution,
    shift_index: int,
    replacements: dict[int, Operation],
) -> Solution:
    shifts = []
    for shift in solution.shifts:
        if shift.index != shift_index:
            shifts.append(shift)
            continue
        operations = list(shift.operations)
        for operation_index, operation in replacements.items():
            operations[operation_index] = operation
        shifts.append(replace(shift, operations=tuple(operations)))
    return Solution(shifts=tuple(shifts))


def run_checker(solution_xml: Path) -> tuple[bool, str, str]:
    mono = shutil.which("mono")
    if mono is None:
        raise SystemExit("mono is required")
    process = subprocess.run(
        [mono, str(CHECKER_EXE), str(INSTANCE_XML), str(solution_xml)],
        input="\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = process.stdout
    is_valid = bool(VALID_RE.search(output)) and not bool(FAIL_RE.search(output))
    ratio_match = RATIO_RE.search(output)
    ratio = ratio_match.group(1) if ratio_match else ""
    first_rule = ""
    for line in output.splitlines():
        if line.strip().startswith("["):
            first_rule = line.strip()
            break
    return is_valid, ratio, first_rule


def checker_first_rule(solution: Solution, name: str) -> tuple[bool, str, str]:
    output_xml = OUT_DIR / f"candidate_{name}.xml"
    save_solution(solution, output_xml)
    return run_checker(output_xml)


def find_window_candidate(instance, solution):
    best = None
    best_last = None
    for shift in solution.shifts:
        for op_index, operation in enumerate(shift.operations):
            customer = instance.customer_by_point.get(operation.point)
            if customer is None or not customer.time_windows:
                continue
            setup = instance.setup_time_for_point(operation.point)
            for window in customer.time_windows:
                latest_valid_arrival = window.end - setup
                if latest_valid_arrival < window.start:
                    continue
                if not (window.start <= operation.arrival and operation.arrival + setup <= window.end):
                    continue
                slack = latest_valid_arrival - operation.arrival
                if slack >= 1 and (best is None or slack < best[0]):
                    best = (slack, shift, op_index, operation, latest_valid_arrival)
                if (
                    slack >= 1
                    and op_index == len(shift.operations) - 1
                    and (best_last is None or slack < best_last[0])
                ):
                    best_last = (slack, shift, op_index, operation, latest_valid_arrival)
    if best_last is not None:
        return best_last[1:]
    if best is not None:
        return best[1:]
    raise SystemExit("no customer time-window candidate found")


def find_travel_candidate(instance, solution):
    for shift in solution.shifts:
        previous_point = instance.base_index
        previous_departure = shift.start
        for op_index, operation in enumerate(shift.operations):
            required = previous_departure + instance.time_matrix[previous_point][operation.point]
            customer = instance.customer_by_point.get(operation.point)
            setup = instance.setup_time_for_point(operation.point)
            if customer is not None and operation.arrival >= required:
                exact_departure = required + setup
                if any(w.start <= required and exact_departure <= w.end for w in customer.time_windows):
                    return shift, op_index, operation, required
            previous_point = operation.point
            previous_departure = operation.arrival + setup
    raise SystemExit("no travel lower-bound candidate found")


def find_safety_candidate(instance, solution):
    events = tank_events(instance, solution)
    min_by_point = {}
    for event in events:
        customer = instance.customer_by_point[event.point]
        if customer.call_in:
            continue
        current = min_by_point.get(event.point)
        margin = event.ending_inventory - event.safety_level
        if current is None or margin < current[0]:
            min_by_point[event.point] = (margin, event.step)

    for margin, point in sorted((value[0], point) for point, value in min_by_point.items()):
        if margin <= 1.0:
            continue
        target_step = min_by_point[point][1]
        customer = instance.customer_by_point[point]
        for shift in solution.shifts:
            for op_index, operation in enumerate(shift.operations):
                if operation.point != point or operation.quantity <= 0:
                    continue
                op_step = operation.arrival // instance.unit
                prior_sources = [
                    (source_index, source_op)
                    for source_index, source_op in enumerate(shift.operations[:op_index])
                    if instance.point_kind(source_op.point) == "source"
                ]
                if (
                    op_step <= target_step
                    and prior_sources
                    and operation.quantity - customer.min_operation_quantity > margin + 0.1
                ):
                    source_index, source_op = prior_sources[-1]
                    reduction = margin + 0.1
                    candidate = with_operations(
                        solution,
                        shift.index,
                        {
                            source_index: replace(source_op, quantity=source_op.quantity + reduction),
                            op_index: replace(operation, quantity=operation.quantity - reduction),
                        },
                    )
                    valid, _, first_rule = checker_first_rule(candidate, "safety_search")
                    if not valid and "Total runout" in first_rule:
                        return shift, op_index, operation, reduction, source_index, source_op
    raise SystemExit("no safety perturbation candidate found")


def find_overfill_candidate(instance, solution):
    events = tank_events(instance, solution)
    event_by_point_step = {(event.point, event.step): event for event in events}
    derived_by_shift = {derived.shift.index: derived for derived in derive_solution(instance, solution)}
    for shift in solution.shifts:
        for op_index, operation in enumerate(shift.operations):
            customer = instance.customer_by_point.get(operation.point)
            if customer is None or customer.call_in or operation.quantity <= 0:
                continue
            step = operation.arrival // instance.unit
            event = event_by_point_step[(operation.point, step)]
            slack = customer.capacity - event.ending_inventory
            trailer_after_op = derived_by_shift[shift.index].operations[op_index].trailer_quantity
            increase = max(0.0, slack) + 0.1
            if slack > -1e-6 and trailer_after_op > increase:
                candidate = with_operation(
                    solution,
                    shift.index,
                    op_index,
                    replace(operation, quantity=operation.quantity + increase),
                )
                valid, _, first_rule = checker_first_rule(candidate, "overfill_search")
                if not valid and "tankQuantity" in first_rule and ">" in first_rule:
                    return shift, op_index, operation, increase
    raise SystemExit("no overfill perturbation candidate found")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    instance = load_instance(INSTANCE_XML)
    solution = load_solution(BASE_SOLUTION_XML)

    probes = []

    shift, op_index, operation, latest_valid = find_window_candidate(instance, solution)
    probes.append(
        (
            "customer_window_exact_latest_arrival",
            "Set customer arrival to latest minute where arrival+setup still fits the window.",
            with_operation(solution, shift.index, op_index, replace(operation, arrival=latest_valid)),
        )
    )
    probes.append(
        (
            "customer_window_1_min_late",
            "Set customer arrival one minute past the latest window-feasible arrival.",
            with_operation(solution, shift.index, op_index, replace(operation, arrival=latest_valid + 1)),
        )
    )

    shift, op_index, operation, required_arrival = find_travel_candidate(instance, solution)
    probes.append(
        (
            "travel_exact_earliest_arrival",
            "Set operation arrival exactly to previous departure plus travel time.",
            with_operation(solution, shift.index, op_index, replace(operation, arrival=required_arrival)),
        )
    )
    probes.append(
        (
            "travel_1_min_too_early",
            "Set operation arrival one minute before previous departure plus travel time.",
            with_operation(solution, shift.index, op_index, replace(operation, arrival=required_arrival - 1)),
        )
    )

    shift, op_index, operation, reduction, source_index, source_op = find_safety_candidate(instance, solution)
    probes.append(
        (
            "safety_exact_threshold",
            "Reduce a VMI delivery so the customer's minimum tank level lands at the safety threshold.",
            with_operations(
                solution,
                shift.index,
                {
                    source_index: replace(source_op, quantity=source_op.quantity + reduction - 0.1),
                    op_index: replace(operation, quantity=operation.quantity - reduction + 0.1),
                },
            ),
        )
    )
    probes.append(
        (
            "safety_0_1_kg_under",
            "Reduce a VMI delivery so the customer's minimum tank level is about 0.1 kg below safety.",
            with_operations(
                solution,
                shift.index,
                {
                    source_index: replace(source_op, quantity=source_op.quantity + reduction),
                    op_index: replace(operation, quantity=operation.quantity - reduction),
                },
            ),
        )
    )

    shift, op_index, operation, increase = find_overfill_candidate(instance, solution)
    probes.append(
        (
            "capacity_exact_threshold",
            "Increase a VMI delivery so the customer's post-step tank level lands at capacity.",
            with_operation(
                solution,
                shift.index,
                op_index,
                replace(operation, quantity=operation.quantity + increase - 0.1),
            ),
        )
    )
    probes.append(
        (
            "capacity_0_1_kg_over",
            "Increase a VMI delivery so the customer's post-step tank level is about 0.1 kg over capacity.",
            with_operation(
                solution,
                shift.index,
                op_index,
                replace(operation, quantity=operation.quantity + increase),
            ),
        )
    )

    rows = []
    for name, description, mutated in probes:
        output_xml = OUT_DIR / f"{name}.xml"
        save_solution(mutated, output_xml)
        is_valid, ratio, first_rule = run_checker(output_xml)
        rows.append(
            {
                "probe": name,
                "valid": is_valid,
                "ratio": ratio,
                "first_rule_message": first_rule,
                "solution_xml": str(output_xml.relative_to(ROOT)),
                "description": description,
            }
        )
        print(f"{name}: valid={is_valid} ratio={ratio} first_rule={first_rule}")

    output_csv = OUT_DIR / "edge_case_probe_results.csv"
    with output_csv.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {output_csv.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
