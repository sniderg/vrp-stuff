from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .analysis import customer_inventory_summary, summarize_solution
from .contest import score_prefix_with_feasibility_tail
from .solver.greedy import construct_solution
from .solver.cluster_greedy import construct_cluster_solution
from .evaluate import evaluate_solution
from .improve import (
    move_single_customer_shifts,
    prune_redundant_shifts,
    remove_redundant_source_visits,
    trim_redundant_deliveries,
)
from .highs_repair import repair_quantities_with_highs
from .inventory import tank_events, tank_violations
from .geo import mds_coordinates, plot_geo, write_geo_csv
from .movement import (
    asymmetry_outliers,
    collocation_groups,
    distance_time_outliers,
    movement_edges,
    nearest_neighbors,
    summarize_matrices,
)
from .penalties import PenaltyWeights, penalty_breakdown
from .replay import (
    build_segments,
    customer_states_at,
    replay_grid,
    resource_states_at,
    status_overview,
)
from .rules import validate_solution
from .rolling import rolling_days, rolling_summary
from .smoothness import period_buckets, smoothness_summary
from .xml_io import load_instance, load_solution, save_solution


CHECKER_EXE = (
    Path(__file__).resolve().parent.parent
    / "roadef_2016_data"
    / "checker_v2"
    / "Challenge_Roadef_EURO_Checker_V2"
    / "bin"
    / "Release"
    / "IRP_Roadef_Challenge_Checker.exe"
)
RATIO_RE = re.compile(r"Logistic Ratio\s*=\s*([0-9]+(?:[.,][0-9]+)?)")
RULES_INDEX = Path(__file__).resolve().parent.parent / "roadef_2016_data" / "rules_index.md"


def cmd_instance_summary(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    customers_by_kind = {
        "vmi": sum(1 for customer in instance.customers if not customer.call_in),
        "call_in": sum(1 for customer in instance.customers if customer.call_in),
    }
    avg_forecast = [
        sum(customer.forecast) / len(customer.forecast)
        for customer in instance.customers
        if customer.forecast
    ]

    print(f"name,{instance.name}")
    print(f"unit_minutes,{instance.unit}")
    print(f"horizon_steps,{instance.horizon}")
    print(f"horizon_hours,{instance.horizon * instance.unit / 60:.2f}")
    print(f"points,{len(instance.time_matrix)}")
    print(f"drivers,{len(instance.drivers)}")
    print(f"trailers,{len(instance.trailers)}")
    print(f"sources,{len(instance.sources)}")
    print(f"customers,{len(instance.customers)}")
    print(f"vmi_customers,{customers_by_kind['vmi']}")
    print(f"call_in_customers,{customers_by_kind['call_in']}")
    print(f"avg_customer_forecast_per_step,{sum(avg_forecast) / len(avg_forecast):.6f}")
    print(f"total_initial_customer_inventory,{sum(c.initial_tank_quantity for c in instance.customers):.3f}")
    print(f"total_customer_safety_level,{sum(c.safety_level for c in instance.customers):.3f}")
    return 0


def cmd_solution_summary(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    shifts = summarize_solution(instance, solution)
    inventories = customer_inventory_summary(instance, solution)
    total_delivered = sum(summary.delivered_quantity for summary in shifts)
    total_estimated_cost = sum(summary.estimated_cost for summary in shifts)
    breached = [summary for summary in inventories if summary.first_safety_breach_step is not None]

    print(f"shifts,{len(solution.shifts)}")
    print(f"operations,{sum(summary.operations for summary in shifts)}")
    print(f"delivered_quantity,{total_delivered:.6f}")
    print(f"estimated_distance_cost_plus_time_cost,{total_estimated_cost:.6f}")
    print(f"load_violations,{sum(summary.load_violations for summary in shifts)}")
    print(f"customers_with_safety_breach_by_simple_projection,{len(breached)}")
    print(
        "worst_margin_to_safety,"
        f"{min(summary.min_margin_to_safety for summary in inventories):.6f}"
    )

    if args.shifts_csv:
        with Path(args.shifts_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(shifts[0].__dict__))
            writer.writeheader()
            writer.writerows(summary.__dict__ for summary in shifts)

    if args.inventory_csv:
        with Path(args.inventory_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(inventories[0].__dict__))
            writer.writeheader()
            writer.writerows(summary.__dict__ for summary in inventories)

    return 0


def cmd_customer_targets(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    inventories = customer_inventory_summary(instance, solution)
    customers = instance.customer_by_point

    rows = []
    for summary in inventories:
        customer = customers[summary.point]
        total_forecast = sum(customer.forecast)
        excess_delivery = summary.delivered_quantity - max(
            0.0,
            total_forecast + customer.safety_level - customer.initial_tank_quantity,
        )
        rows.append(
            {
                "point": summary.point,
                "deliveries": summary.deliveries,
                "delivered_quantity": f"{summary.delivered_quantity:.6f}",
                "total_forecast": f"{total_forecast:.6f}",
                "initial_inventory": f"{customer.initial_tank_quantity:.6f}",
                "safety_level": f"{customer.safety_level:.6f}",
                "min_margin_to_safety": f"{summary.min_margin_to_safety:.6f}",
                "final_inventory": f"{summary.final_inventory:.6f}",
                "excess_delivery_estimate": f"{excess_delivery:.6f}",
                "first_safety_breach_step": (
                    "" if summary.first_safety_breach_step is None
                    else summary.first_safety_breach_step
                ),
            }
        )

    rows.sort(
        key=lambda row: (
            -float(row["excess_delivery_estimate"]),
            -int(row["deliveries"]),
            float(row["min_margin_to_safety"]),
        )
    )

    if args.output_csv:
        with Path(args.output_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    for row in rows[: args.limit]:
        print(
            f"point={row['point']} deliveries={row['deliveries']} "
            f"excess={row['excess_delivery_estimate']} "
            f"min_margin={row['min_margin_to_safety']} "
            f"final_inventory={row['final_inventory']}"
        )
    return 0


def cmd_rule_check(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    violations = validate_solution(instance, solution)

    counts: dict[str, int] = {}
    for violation in violations:
        counts[violation.code] = counts.get(violation.code, 0) + 1

    print(f"violations,{len(violations)}")
    for code, count in sorted(counts.items()):
        print(f"{code},{count}")
    error_count = sum(1 for violation in violations if violation.severity == "error")
    warning_count = sum(1 for violation in violations if violation.severity == "warning")
    print(f"errors,{error_count}")
    print(f"warnings,{warning_count}")

    if args.output_csv:
        with Path(args.output_csv).open("w", newline="") as file:
            fieldnames = ["code", "severity", "shift", "operation", "point", "message"]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(violation.__dict__ for violation in violations)

    if args.limit:
        for violation in violations[: args.limit]:
            print(
                f"{violation.code}: shift={violation.shift} op={violation.operation} "
                f"point={violation.point} {violation.message}"
            )

    return 1 if error_count and args.fail_on_violation else 0


def cmd_rules_index(args: argparse.Namespace) -> int:
    print(RULES_INDEX.read_text())
    return 0


def cmd_construct_solution(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution, report = construct_solution(
        instance,
        safety_buffer=args.safety_buffer,
        max_shifts=args.max_shifts,
    )
    save_solution(solution, args.output_xml)
    print(f"wrote,{args.output_xml}")
    print(f"shifts,{report.shifts}")
    print(f"operations,{report.operations}")
    print(f"delivered_quantity,{report.delivered_quantity:.6f}")
    print(f"exhausted_resources,{report.exhausted_resources}")
    print(f"unscheduled_customers,{len(report.unscheduled_customers)}")
    if report.unscheduled_customers:
        print(
            "unscheduled_customer_ids,"
            + " ".join(str(point) for point in report.unscheduled_customers[: args.limit])
        )
    return 0


def cmd_cluster_construct_solution(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    score_cutoff_minute = (
        None
        if args.score_days is None
        else args.score_days * 1440
    )
    solution, report = construct_cluster_solution(
        instance,
        safety_buffer=args.safety_buffer,
        neighborhood_size=args.neighborhood_size,
        max_shifts=args.max_shifts,
        score_cutoff_minute=score_cutoff_minute,
        terminal_buffer_days=args.terminal_buffer_days,
    )
    save_solution(solution, args.output_xml)
    print(f"wrote,{args.output_xml}")
    print(f"shifts,{report.shifts}")
    print(f"operations,{report.operations}")
    print(f"delivered_quantity,{report.delivered_quantity:.6f}")
    print(f"exhausted_resources,{report.exhausted_resources}")
    print(f"unscheduled_customers,{len(report.unscheduled_customers)}")
    if report.unscheduled_customers:
        print(
            "unscheduled_customer_ids,"
            + " ".join(str(point) for point in report.unscheduled_customers[: args.limit])
        )
    return 0


def cmd_matrix_summary(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    summary = summarize_matrices(instance)
    for key, value in summary.__dict__.items():
        print(f"{key},{value}")
    groups = collocation_groups(instance)
    print(f"collocation_groups,{len(groups)}")
    print(f"collocated_points,{sum(len(group) for group in groups)}")
    return 0


def cmd_export_edges(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    edges = movement_edges(instance)
    with Path(args.output_csv).open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(edges[0].__dict__))
        writer.writeheader()
        writer.writerows(edge.__dict__ for edge in edges)
    print(f"wrote,{args.output_csv}")
    print(f"edges,{len(edges)}")
    return 0


def cmd_nearest(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    rows = nearest_neighbors(instance, k=args.k, metric=args.metric)
    with Path(args.output_csv).open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote,{args.output_csv}")
    print(f"rows,{len(rows)}")
    return 0


def cmd_collocations(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    groups = collocation_groups(instance)
    rows = [
        {
            "group_id": group_id,
            "size": len(group),
            "points": " ".join(str(point) for point in group),
            "kinds": " ".join(instance.point_kind(point) for point in group),
        }
        for group_id, group in enumerate(groups)
    ]
    if args.output_csv:
        with Path(args.output_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["group_id", "size", "points", "kinds"])
            writer.writeheader()
            writer.writerows(rows)
    print(f"groups,{len(groups)}")
    print(f"points,{sum(len(group) for group in groups)}")
    for row in rows[: args.limit]:
        print(f"group={row['group_id']} size={row['size']} points={row['points']}")
    return 0


def cmd_speed_outliers(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    edges = distance_time_outliers(instance, limit=args.limit)
    if args.output_csv:
        with Path(args.output_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(edges[0].__dict__))
            writer.writeheader()
            writer.writerows(edge.__dict__ for edge in edges)
    for edge in edges:
        print(
            f"{edge.origin}->{edge.destination} "
            f"distance={edge.distance} time={edge.time} "
            f"speed={edge.speed_distance_per_hour:.3f}"
        )
    return 0


def cmd_asymmetry_outliers(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    edges = asymmetry_outliers(instance, metric=args.metric, limit=args.limit)
    if args.output_csv:
        with Path(args.output_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(edges[0].__dict__))
            writer.writeheader()
            writer.writerows(edge.__dict__ for edge in edges)
    for edge in edges:
        print(
            f"{edge.origin}->{edge.destination} "
            f"distance={edge.distance} reverse_distance={edge.reverse_distance} "
            f"time={edge.time} reverse_time={edge.reverse_time} "
            f"distance_delta={edge.distance_delta} time_delta={edge.time_delta}"
        )
    return 0


def cmd_tank_check(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    violations = tank_violations(instance, solution)
    counts: dict[str, int] = {}
    for violation in violations:
        counts[violation.code] = counts.get(violation.code, 0) + 1

    print(f"tank_violations,{len(violations)}")
    for code, count in sorted(counts.items()):
        print(f"{code},{count}")

    if args.violations_csv:
        with Path(args.violations_csv).open("w", newline="") as file:
            fieldnames = ["code", "point", "step", "time_start", "inventory", "limit", "message"]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(violation.__dict__ for violation in violations)

    if args.events_csv:
        events = tank_events(instance, solution)
        with Path(args.events_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(events[0].__dict__))
            writer.writeheader()
            writer.writerows(event.__dict__ for event in events)

    for violation in violations[: args.limit]:
        print(
            f"{violation.code}: point={violation.point} step={violation.step} "
            f"time={violation.time_start} inventory={violation.inventory:.6f} "
            f"limit={violation.limit:.6f}"
        )
    return 1 if violations and args.fail_on_violation else 0


def cmd_segments(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    segments = build_segments(instance, solution)
    with Path(args.output_csv).open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(segments[0].__dict__))
        writer.writeheader()
        writer.writerows(segment.__dict__ for segment in segments)
    print(f"wrote,{args.output_csv}")
    print(f"segments,{len(segments)}")
    return 0


def cmd_replay_snapshot(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    resources = resource_states_at(instance, solution, args.time)
    customers = customer_states_at(instance, solution, args.time)

    if args.resources_csv:
        with Path(args.resources_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(resources[0].__dict__))
            writer.writeheader()
            writer.writerows(state.__dict__ for state in resources)
    if args.customers_csv:
        with Path(args.customers_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(customers[0].__dict__))
            writer.writeheader()
            writer.writerows(state.__dict__ for state in customers)

    active = [state for state in resources if state.kind not in {"off_shift", "idle_trailer"}]
    vmi_customers = [state for state in customers if not state.call_in]
    low_customers = sorted(vmi_customers, key=lambda state: state.margin_to_safety)[: args.limit]
    print(f"time,{args.time}")
    print(f"active_resource_states,{len(active)}")
    for state in active[: args.limit]:
        print(
            f"{state.kind}: shift={state.shift} driver={state.driver} trailer={state.trailer} "
            f"point={state.point} arc={state.origin}->{state.destination} {state.message}"
        )
    print("lowest_customer_margins")
    for state in low_customers:
        print(
            f"point={state.point} inventory={state.inventory:.6f} "
            f"safety_margin={state.margin_to_safety:.6f} "
            f"capacity_margin={state.margin_to_capacity:.6f}"
        )
    return 0


def cmd_replay_grid(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    resources, customers = replay_grid(
        instance,
        solution,
        start=args.start,
        end=args.end,
        step=args.step,
    )
    with Path(args.resources_csv).open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(resources[0].__dict__))
        writer.writeheader()
        writer.writerows(state.__dict__ for state in resources)
    with Path(args.customers_csv).open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(customers[0].__dict__))
        writer.writeheader()
        writer.writerows(state.__dict__ for state in customers)
    print(f"wrote_resources,{args.resources_csv}")
    print(f"wrote_customers,{args.customers_csv}")
    print(f"resource_rows,{len(resources)}")
    print(f"customer_rows,{len(customers)}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    status = status_overview(instance, solution, time=args.time, limit=args.limit)

    print(f"time,{status['time']}")
    print(f"forecast_step,{status['step']}")
    print(f"active_resources,{len(status['active_resources'])}")
    print()
    print("active_resources")
    for state in status["active_resources"]:
        print(
            f"shift={state.shift} driver={state.driver} trailer={state.trailer} "
            f"kind={state.kind} point={state.point} arc={state.origin}->{state.destination} "
            f"load={state.trailer_quantity:.3f} drive={state.driving_since_layover} "
            f"{state.message}"
        )
    print()
    print("lowest_vmi_inventory")
    for state in status["low_inventory_customers"]:
        print(
            f"point={state.point} inv={state.inventory:.3f} "
            f"safety_margin={state.margin_to_safety:.3f} "
            f"capacity_margin={state.margin_to_capacity:.3f}"
        )
    print()
    print("nearest_capacity")
    for state in status["near_capacity_customers"]:
        print(
            f"point={state.point} inv={state.inventory:.3f} "
            f"capacity_margin={state.margin_to_capacity:.3f} "
            f"safety_margin={state.margin_to_safety:.3f}"
        )
    print()
    print("deliveries_this_step")
    for state in status["delivered_this_step"][: args.limit]:
        print(
            f"point={state.point} delivered={state.delivered_this_step:.3f} "
            f"consumed={state.consumed_this_step:.3f} inv={state.inventory:.3f}"
        )
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    instance_path = Path(args.instance_xml)
    solution_path = Path(args.solution_xml)
    instance = load_instance(instance_path)
    solution = load_solution(solution_path)
    checker_exe = (
        Path(__file__).resolve().parent.parent
        / "roadef_2016_data"
        / "checker_v2"
        / "Challenge_Roadef_EURO_Checker_V2"
        / "bin"
        / "Release"
        / "IRP_Roadef_Challenge_Checker.exe"
    )
    evaluation = evaluate_solution(
        instance,
        solution,
        instance_xml=instance_path,
        solution_xml=solution_path,
        checker_exe=checker_exe,
        run_official_checker=args.official,
    )
    row = evaluation.flat()

    if args.output_csv:
        with Path(args.output_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)

    for key, value in row.items():
        print(f"{key},{value}")
    return 1 if args.fail_on_error and evaluation.local_errors else 0


def cmd_smoothness(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    buckets = period_buckets(instance, solution, period_minutes=args.period_minutes)
    summary = smoothness_summary(buckets)

    if args.buckets_csv:
        with Path(args.buckets_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(buckets[0].__dict__))
            writer.writeheader()
            writer.writerows(bucket.__dict__ for bucket in buckets)

    if args.summary_csv:
        with Path(args.summary_csv).open("w", newline="") as file:
            row = summary.flat()
            writer = csv.DictWriter(file, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)

    for key, value in summary.flat().items():
        print(f"{key},{value}")

    print("period_preview")
    for bucket in buckets[: args.limit]:
        print(
            f"period={bucket.period} minutes={bucket.start_minute}-{bucket.end_minute} "
            f"delivered={bucket.delivered_quantity:.3f} "
            f"shift_starts={bucket.shift_starts} "
            f"delivery_ops={bucket.delivery_operations}"
        )
    return 0


def cmd_rolling_monitor(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml) if args.solution_xml else None
    days = rolling_days(instance, solution, monitor_days=args.days)
    summary = rolling_summary(instance, solution, monitor_days=args.days)

    if args.days_csv:
        with Path(args.days_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(days[0].__dict__))
            writer.writeheader()
            writer.writerows(day.__dict__ for day in days)

    if args.summary_csv:
        row = summary.flat()
        with Path(args.summary_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)

    for key, value in summary.flat().items():
        print(f"{key},{value}")
    print("day_preview")
    for day in days[: args.limit]:
        print(
            f"day={day.day} consumption={day.vmi_consumption:.3f} "
            f"required_cum={day.cumulative_required_delivery:.3f} "
            f"planned={day.planned_delivered:.3f} "
            f"gap_required={day.cumulative_delivery_gap_to_required:.3f} "
            f"gap_smooth={day.cumulative_delivery_gap_to_smooth_target:.3f} "
            f"gap_planned_avg={day.cumulative_delivery_gap_to_planned_average:.3f} "
            f"starts={day.planned_shift_starts}"
        )
    return 0


def cmd_penalties(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    weights = PenaltyWeights(
        safety_kg_min=args.safety_kg_min,
        driver_window_min=args.driver_window_min,
        driver_rest_min=args.driver_rest_min,
        max_driving_min=args.max_driving_min,
        timing_min=args.timing_min,
        customer_window_min=args.customer_window_min,
        smoothness_cv=args.smoothness_cv,
        frontload_share=args.frontload_share,
        hard_violation=args.hard_violation,
    )
    penalties = penalty_breakdown(instance, solution, weights=weights)
    row = penalties.flat()

    if args.output_csv:
        with Path(args.output_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)

    for key, value in row.items():
        print(f"{key},{value}")
    return 1 if args.fail_on_hard and penalties.hard_violations else 0


def cmd_contest_score(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    score = score_prefix_with_feasibility_tail(
        instance,
        solution,
        score_days=args.score_days,
        feasibility_days=args.feasibility_days,
        ignore_tail_call_ins=args.ignore_tail_call_ins,
    )
    row = score.flat()

    if args.output_csv:
        with Path(args.output_csv).open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)

    for key, value in row.items():
        print(f"{key},{value}")
    return 1 if args.fail_on_infeasible and not score.feasible else 0


def cmd_contest_prune(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    if args.move_single_shifts:
        solution = move_single_customer_shifts(
            instance,
            solution,
            score_days=args.score_days,
            feasibility_days=args.feasibility_days,
            ignore_tail_call_ins=args.ignore_tail_call_ins,
            max_moves=args.move_rounds,
        )
    improved, report = prune_redundant_shifts(
        instance,
        solution,
        score_days=args.score_days,
        feasibility_days=args.feasibility_days,
        ignore_tail_call_ins=args.ignore_tail_call_ins,
        max_passes=args.max_passes,
    )
    if args.trim_deliveries:
        improved = trim_redundant_deliveries(
            instance,
            improved,
            score_days=args.score_days,
            feasibility_days=args.feasibility_days,
            ignore_tail_call_ins=args.ignore_tail_call_ins,
            max_rounds=args.trim_rounds,
        )
    if args.remove_sources:
        improved = remove_redundant_source_visits(
            instance,
            improved,
            score_days=args.score_days,
            feasibility_days=args.feasibility_days,
            ignore_tail_call_ins=args.ignore_tail_call_ins,
            max_rounds=args.source_rounds,
        )
    save_solution(improved, args.output_xml)
    row = report.flat()
    print(f"wrote,{args.output_xml}")
    for key, value in row.items():
        print(f"{key},{value}")
    return 0


def cmd_contest_highs_repair(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    repaired, report = repair_quantities_with_highs(
        instance,
        solution,
        score_days=args.score_days,
        feasibility_days=args.feasibility_days,
        ignore_tail_call_ins=args.ignore_tail_call_ins,
    )
    output_solution = repaired if report.after_feasible else solution
    save_solution(output_solution, args.output_xml)
    print(f"wrote,{args.output_xml}")
    print(f"applied,{str(report.after_feasible)}")
    for key, value in report.flat().items():
        print(f"{key},{value}")
    return 1 if args.fail_on_infeasible and not report.after_feasible else 0


def cmd_mds_map(args: argparse.Namespace) -> int:
    instance = load_instance(args.instance_xml)
    points = mds_coordinates(
        instance,
        clusters=args.clusters,
        random_state=args.seed,
        dissimilarity=args.dissimilarity,
    )
    write_geo_csv(points, args.output_csv)
    if args.output_png:
        plot_geo(points, args.output_png)

    counts: dict[int, int] = {}
    for point in points:
        counts[point.cluster] = counts.get(point.cluster, 0) + 1
    print(f"wrote_csv,{args.output_csv}")
    if args.output_png:
        print(f"wrote_png,{args.output_png}")
    print(f"points,{len(points)}")
    print(f"clusters,{args.clusters}")
    for cluster, count in sorted(counts.items()):
        print(f"cluster_{cluster},{count}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    mono = shutil.which("mono")
    if mono is None:
        raise SystemExit("`mono` is not installed or not on PATH.")

    process = subprocess.run(
        [mono, str(CHECKER_EXE), args.instance_xml, args.solution_xml],
        input="\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(process.stdout)
    if process.returncode != 0:
        return process.returncode

    match = RATIO_RE.search(process.stdout)
    if match:
        print(f"parsed_logistic_ratio,{float(match.group(1).replace(',', '.')):.12f}")
    return 0


def cmd_doi_report(args: argparse.Namespace) -> int:
    from .inventory import days_of_inventory, project_customer_inventory, delivery_by_customer_step
    from .model import Solution
    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml) if args.solution_xml else Solution(shifts=())
    deliveries_by_arrival = delivery_by_customer_step(solution)
    
    # Pre-calculate nearest source travel time for each customer
    source_travel = {}
    for customer in instance.customers:
        min_travel = min(instance.time_matrix[source.index][customer.index] for source in instance.sources)
        source_travel[customer.index] = min_travel

    step = args.minute // instance.unit
    print("point,kind,inventory,safety_level,lead_time_min,logistical_doi,status")
    for customer in instance.customers:
        events = project_customer_inventory(instance, customer, deliveries_by_arrival.get(customer.index, {}))
        current_event = events[min(step, len(events)-1)]
        lead_time = source_travel[customer.index]
        doi = days_of_inventory(instance, customer, current_event.ending_inventory, step + 1, lead_time_minutes=lead_time)
        
        status = "OK"
        if doi < 0: status = "INSOLVENT"
        elif doi < 0.5: status = "CRITICAL"
        elif doi < 1.0: status = "URGENT"
        
        print(f"{customer.index},{'call-in' if customer.call_in else 'vmi'},{current_event.ending_inventory:.1f},{customer.safety_level:.1f},{lead_time},{doi:.2f},{status}")
    return 0


def cmd_clone_solution(args: argparse.Namespace) -> int:
    solution = load_solution(args.solution_xml)
    save_solution(solution, args.output_xml)
    print(f"wrote,{args.output_xml}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ROADEF/EURO 2016 IRP helper tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    instance_summary = subparsers.add_parser("instance-summary")
    instance_summary.add_argument("instance_xml")
    instance_summary.set_defaults(func=cmd_instance_summary)

    solution_summary = subparsers.add_parser("solution-summary")
    solution_summary.add_argument("instance_xml")
    solution_summary.add_argument("solution_xml")
    solution_summary.add_argument("--shifts-csv")
    solution_summary.add_argument("--inventory-csv")
    solution_summary.set_defaults(func=cmd_solution_summary)

    customer_targets = subparsers.add_parser("customer-targets")
    customer_targets.add_argument("instance_xml")
    customer_targets.add_argument("solution_xml")
    customer_targets.add_argument("--output-csv")
    customer_targets.add_argument("--limit", type=int, default=20)
    customer_targets.set_defaults(func=cmd_customer_targets)

    rule_check = subparsers.add_parser("rule-check")
    rule_check.add_argument("instance_xml")
    rule_check.add_argument("solution_xml")
    rule_check.add_argument("--output-csv")
    rule_check.add_argument("--limit", type=int, default=20)
    rule_check.add_argument("--fail-on-violation", action="store_true")
    rule_check.set_defaults(func=cmd_rule_check)

    rules_index = subparsers.add_parser("rules-index")
    rules_index.set_defaults(func=cmd_rules_index)

    construct = subparsers.add_parser("construct-solution")
    construct.add_argument("instance_xml")
    construct.add_argument("output_xml")
    construct.add_argument("--safety-buffer", type=float, default=0.20)
    construct.add_argument("--max-shifts", type=int)
    construct.add_argument("--limit", type=int, default=25)
    construct.set_defaults(func=cmd_construct_solution)

    cluster_construct = subparsers.add_parser("cluster-construct-solution")
    cluster_construct.add_argument("instance_xml")
    cluster_construct.add_argument("output_xml")
    cluster_construct.add_argument("--safety-buffer", type=float, default=0.20)
    cluster_construct.add_argument("--neighborhood-size", type=int, default=5)
    cluster_construct.add_argument("--max-shifts", type=int)
    cluster_construct.add_argument("--score-days", type=int)
    cluster_construct.add_argument("--terminal-buffer-days", type=float, default=0.0)
    cluster_construct.add_argument("--limit", type=int, default=25)
    cluster_construct.set_defaults(func=cmd_cluster_construct_solution)

    matrix_summary = subparsers.add_parser("matrix-summary")
    matrix_summary.add_argument("instance_xml")
    matrix_summary.set_defaults(func=cmd_matrix_summary)

    export_edges = subparsers.add_parser("export-edges")
    export_edges.add_argument("instance_xml")
    export_edges.add_argument("output_csv")
    export_edges.set_defaults(func=cmd_export_edges)

    nearest = subparsers.add_parser("nearest")
    nearest.add_argument("instance_xml")
    nearest.add_argument("output_csv")
    nearest.add_argument("--metric", choices=["distance", "time"], default="distance")
    nearest.add_argument("-k", type=int, default=10)
    nearest.set_defaults(func=cmd_nearest)

    collocations = subparsers.add_parser("collocations")
    collocations.add_argument("instance_xml")
    collocations.add_argument("--output-csv")
    collocations.add_argument("--limit", type=int, default=20)
    collocations.set_defaults(func=cmd_collocations)

    speed_outliers = subparsers.add_parser("speed-outliers")
    speed_outliers.add_argument("instance_xml")
    speed_outliers.add_argument("--output-csv")
    speed_outliers.add_argument("--limit", type=int, default=25)
    speed_outliers.set_defaults(func=cmd_speed_outliers)

    asymmetry = subparsers.add_parser("asymmetry-outliers")
    asymmetry.add_argument("instance_xml")
    asymmetry.add_argument("--metric", choices=["distance", "time"], default="time")
    asymmetry.add_argument("--output-csv")
    asymmetry.add_argument("--limit", type=int, default=25)
    asymmetry.set_defaults(func=cmd_asymmetry_outliers)

    tank_check = subparsers.add_parser("tank-check")
    tank_check.add_argument("instance_xml")
    tank_check.add_argument("solution_xml")
    tank_check.add_argument("--violations-csv")
    tank_check.add_argument("--events-csv")
    tank_check.add_argument("--limit", type=int, default=25)
    tank_check.add_argument("--fail-on-violation", action="store_true")
    tank_check.set_defaults(func=cmd_tank_check)

    segments = subparsers.add_parser("segments")
    segments.add_argument("instance_xml")
    segments.add_argument("solution_xml")
    segments.add_argument("output_csv")
    segments.set_defaults(func=cmd_segments)

    replay_snapshot = subparsers.add_parser("replay-snapshot")
    replay_snapshot.add_argument("instance_xml")
    replay_snapshot.add_argument("solution_xml")
    replay_snapshot.add_argument("--time", type=int, required=True)
    replay_snapshot.add_argument("--resources-csv")
    replay_snapshot.add_argument("--customers-csv")
    replay_snapshot.add_argument("--limit", type=int, default=12)
    replay_snapshot.set_defaults(func=cmd_replay_snapshot)

    replay = subparsers.add_parser("replay-grid")
    replay.add_argument("instance_xml")
    replay.add_argument("solution_xml")
    replay.add_argument("--resources-csv", required=True)
    replay.add_argument("--customers-csv", required=True)
    replay.add_argument("--start", type=int, default=0)
    replay.add_argument("--end", type=int)
    replay.add_argument("--step", type=int, default=60)
    replay.set_defaults(func=cmd_replay_grid)

    status = subparsers.add_parser("status")
    status.add_argument("instance_xml")
    status.add_argument("solution_xml")
    status.add_argument("--time", type=int, required=True)
    status.add_argument("--limit", type=int, default=10)
    status.set_defaults(func=cmd_status)

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("instance_xml")
    evaluate.add_argument("solution_xml")
    evaluate.add_argument("--official", action="store_true")
    evaluate.add_argument("--output-csv")
    evaluate.add_argument("--fail-on-error", action="store_true")
    evaluate.set_defaults(func=cmd_evaluate)

    smoothness = subparsers.add_parser("smoothness")
    smoothness.add_argument("instance_xml")
    smoothness.add_argument("solution_xml")
    smoothness.add_argument("--period-minutes", type=int, default=1440)
    smoothness.add_argument("--buckets-csv")
    smoothness.add_argument("--summary-csv")
    smoothness.add_argument("--limit", type=int, default=10)
    smoothness.set_defaults(func=cmd_smoothness)

    rolling_monitor = subparsers.add_parser("rolling-monitor")
    rolling_monitor.add_argument("instance_xml")
    rolling_monitor.add_argument("solution_xml", nargs="?")
    rolling_monitor.add_argument("--days", type=int)
    rolling_monitor.add_argument("--days-csv")
    rolling_monitor.add_argument("--summary-csv")
    rolling_monitor.add_argument("--limit", type=int, default=10)
    rolling_monitor.set_defaults(func=cmd_rolling_monitor)

    penalties = subparsers.add_parser("penalties")
    penalties.add_argument("instance_xml")
    penalties.add_argument("solution_xml")
    penalties.add_argument("--output-csv")
    penalties.add_argument("--fail-on-hard", action="store_true")
    penalties.add_argument("--safety-kg-min", type=float, default=1.0)
    penalties.add_argument("--driver-window-min", type=float, default=100.0)
    penalties.add_argument("--driver-rest-min", type=float, default=100.0)
    penalties.add_argument("--max-driving-min", type=float, default=100.0)
    penalties.add_argument("--timing-min", type=float, default=100.0)
    penalties.add_argument("--customer-window-min", type=float, default=100.0)
    penalties.add_argument("--smoothness-cv", type=float, default=10_000.0)
    penalties.add_argument("--frontload-share", type=float, default=10_000.0)
    penalties.add_argument("--hard-violation", type=float, default=1_000_000_000.0)
    penalties.set_defaults(func=cmd_penalties)

    contest_score = subparsers.add_parser("contest-score")
    contest_score.add_argument("instance_xml")
    contest_score.add_argument("solution_xml")
    contest_score.add_argument("--score-days", type=int, required=True)
    contest_score.add_argument("--feasibility-days", type=int)
    contest_score.add_argument("--ignore-tail-call-ins", action="store_true")
    contest_score.add_argument("--output-csv")
    contest_score.add_argument("--fail-on-infeasible", action="store_true")
    contest_score.set_defaults(func=cmd_contest_score)

    contest_prune = subparsers.add_parser("contest-prune")
    contest_prune.add_argument("instance_xml")
    contest_prune.add_argument("solution_xml")
    contest_prune.add_argument("output_xml")
    contest_prune.add_argument("--score-days", type=int, required=True)
    contest_prune.add_argument("--feasibility-days", type=int)
    contest_prune.add_argument("--ignore-tail-call-ins", action="store_true")
    contest_prune.add_argument("--max-passes", type=int, default=3)
    contest_prune.add_argument("--trim-deliveries", action="store_true")
    contest_prune.add_argument("--trim-rounds", type=int, default=5)
    contest_prune.add_argument("--remove-sources", action="store_true")
    contest_prune.add_argument("--source-rounds", type=int, default=10)
    contest_prune.add_argument("--move-single-shifts", action="store_true")
    contest_prune.add_argument("--move-rounds", type=int, default=10)
    contest_prune.set_defaults(func=cmd_contest_prune)

    highs_repair = subparsers.add_parser("contest-highs-repair")
    highs_repair.add_argument("instance_xml")
    highs_repair.add_argument("solution_xml")
    highs_repair.add_argument("output_xml")
    highs_repair.add_argument("--score-days", type=int, required=True)
    highs_repair.add_argument("--feasibility-days", type=int)
    highs_repair.add_argument("--ignore-tail-call-ins", action="store_true")
    highs_repair.add_argument("--fail-on-infeasible", action="store_true")
    highs_repair.set_defaults(func=cmd_contest_highs_repair)

    mds_map = subparsers.add_parser("mds-map")
    mds_map.add_argument("instance_xml")
    mds_map.add_argument("output_csv")
    mds_map.add_argument("--output-png")
    mds_map.add_argument("--clusters", type=int, default=12)
    mds_map.add_argument("--seed", type=int, default=42)
    mds_map.add_argument("--dissimilarity", choices=["distance", "time"], default="distance")
    mds_map.set_defaults(func=cmd_mds_map)

    check = subparsers.add_parser("check")
    check.add_argument("instance_xml")
    check.add_argument("solution_xml")
    check.set_defaults(func=cmd_check)

    clone = subparsers.add_parser("clone-solution")
    clone.add_argument("solution_xml")
    clone.add_argument("output_xml")
    clone.set_defaults(func=cmd_clone_solution)

    doi_report = subparsers.add_parser("doi-report")
    doi_report.add_argument("instance_xml")
    doi_report.add_argument("solution_xml", nargs="?")
    doi_report.add_argument("--minute", type=int, default=0)
    doi_report.set_defaults(func=cmd_doi_report)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
