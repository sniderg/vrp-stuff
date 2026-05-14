from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from statistics import mean

import numpy as np

from roadef_tools.inventory import delivery_by_customer_step
from roadef_tools.model import Customer, Instance
from roadef_tools.solver.cluster_greedy import construct_cluster_solution
from roadef_tools.solver.greedy import construct_solution
from roadef_tools.xml_io import load_instance


def choose_group_seeds(instance: Instance, group_count: int) -> list[int]:
    customer_points = [customer.index for customer in instance.customers if not customer.call_in]
    if not customer_points:
        return []
    seeds = [customer_points[0]]
    while len(seeds) < min(group_count, len(customer_points)):
        next_seed = max(
            customer_points,
            key=lambda point: min(instance.time_matrix[point][seed] for seed in seeds),
        )
        if next_seed in seeds:
            break
        seeds.append(next_seed)
    return seeds


def assign_groups(instance: Instance, seeds: list[int]) -> dict[int, int]:
    if not seeds:
        return {}
    assignments: dict[int, int] = {}
    for customer in instance.customers:
        if customer.call_in:
            continue
        best_group = min(
            range(len(seeds)),
            key=lambda group: (instance.time_matrix[customer.index][seeds[group]], seeds[group]),
        )
        assignments[customer.index] = best_group
    return assignments


def sample_group_day_factors(
    rng: np.random.Generator,
    *,
    group_count: int,
    day_count: int,
    daily_noise: float,
    persistence: float,
    min_factor: float,
    max_factor: float,
) -> np.ndarray:
    factors = np.ones((group_count, day_count), dtype=float)
    for group in range(group_count):
        current = 1.0
        for day in range(day_count):
            shock = rng.normal(0.0, daily_noise)
            current = 1.0 + persistence * (current - 1.0) + shock
            current = float(np.clip(current, min_factor, max_factor))
            factors[group, day] = current
    return factors


def perturb_customer_forecast(
    rng: np.random.Generator,
    instance: Instance,
    customer: Customer,
    *,
    group_factor_by_day: np.ndarray,
    customer_noise: float,
) -> tuple[float, ...]:
    if customer.call_in:
        return customer.forecast

    steps_per_day = max(1, 1440 // instance.unit)
    day_count = (instance.horizon + steps_per_day - 1) // steps_per_day
    forecast = list(customer.forecast)
    max_daily_total = max(customer.capacity - customer.safety_level, 0.0)

    for day in range(day_count):
        start = day * steps_per_day
        end = min((day + 1) * steps_per_day, len(forecast))
        if start >= end:
            break
        base = forecast[start:end]
        if not any(base):
            continue

        factor = group_factor_by_day[day] * float(rng.normal(1.0, customer_noise))
        factor = max(0.0, factor)
        mutated = [value * factor for value in base]
        total = sum(mutated)
        if max_daily_total > 0.0 and total > max_daily_total:
            scale = max_daily_total / total
            mutated = [value * scale for value in mutated]
        forecast[start:end] = mutated

    return tuple(forecast)


def perturb_instance(
    rng: np.random.Generator,
    instance: Instance,
    *,
    group_count: int,
    daily_noise: float,
    customer_noise: float,
    persistence: float,
    min_factor: float,
    max_factor: float,
) -> Instance:
    steps_per_day = max(1, 1440 // instance.unit)
    day_count = (instance.horizon + steps_per_day - 1) // steps_per_day
    seeds = choose_group_seeds(instance, group_count)
    assignments = assign_groups(instance, seeds)
    factors = sample_group_day_factors(
        rng,
        group_count=max(1, len(seeds)),
        day_count=day_count,
        daily_noise=daily_noise,
        persistence=persistence,
        min_factor=min_factor,
        max_factor=max_factor,
    )

    customers = []
    for customer in instance.customers:
        if customer.call_in:
            customers.append(customer)
            continue
        group = assignments.get(customer.index, 0)
        customers.append(
            replace(
                customer,
                forecast=perturb_customer_forecast(
                    rng,
                    instance,
                    customer,
                    group_factor_by_day=factors[group],
                    customer_noise=customer_noise,
                ),
            )
        )
    return replace(instance, customers=tuple(customers))


def summarize_solution(
    instance: Instance,
    deliveries: dict[int, dict[int, float]],
    *,
    report_days: int,
) -> tuple[dict[int, int | None], dict[int, int], int, int, list[dict[str, object]]]:
    first_service_day: dict[int, int | None] = {}
    service_count: dict[int, int] = {}
    served_day1 = 0
    served_report = 0
    cutoff = report_days * 1440
    event_rows: list[dict[str, object]] = []

    for customer in instance.customers:
        arrivals = sorted(deliveries.get(customer.index, {}).keys())
        first = arrivals[0] if arrivals else None
        first_service_day[customer.index] = None if first is None else first // 1440 + 1
        count = sum(1 for arrival in arrivals if arrival < cutoff)
        service_count[customer.index] = count
        visit_index = 0
        for arrival in arrivals:
            if arrival >= cutoff:
                continue
            visit_index += 1
            event_rows.append(
                {
                    "point": customer.index,
                    "day": arrival // 1440 + 1,
                    "arrival_minute": arrival,
                    "visit_index": visit_index,
                }
            )
        if first is not None and first < 1440:
            served_day1 += 1
        if first is not None and first < cutoff:
            served_report += 1

    return first_service_day, service_count, served_day1, served_report, event_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Monte Carlo demand probe for short-horizon IRP patterns")
    parser.add_argument("instance_xml", type=Path)
    parser.add_argument("--solver", choices=["cluster", "greedy"], default="cluster")
    parser.add_argument("--scenarios", type=int, default=20)
    parser.add_argument("--solve-days", type=int, default=3)
    parser.add_argument("--report-days", type=int, default=3)
    parser.add_argument("--max-shifts", type=int, default=20)
    parser.add_argument("--neighborhood-size", type=int, default=3)
    parser.add_argument("--terminal-buffer-days", type=float, default=0.0)
    parser.add_argument("--group-count", type=int, default=6)
    parser.add_argument("--daily-noise", type=float, default=0.12)
    parser.add_argument("--customer-noise", type=float, default=0.04)
    parser.add_argument("--persistence", type=float, default=0.45)
    parser.add_argument("--min-factor", type=float, default=0.75)
    parser.add_argument("--max-factor", type=float, default=1.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--summary-csv", type=Path)
    parser.add_argument("--scenarios-csv", type=Path)
    parser.add_argument("--events-csv", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    base_instance = load_instance(args.instance_xml)
    rng = np.random.default_rng(args.seed)
    score_cutoff_minute = None if args.solve_days <= 0 else args.solve_days * 1440

    scenario_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    served_by_day_counts: dict[int, list[int]] = defaultdict(list)
    first_service_days: dict[int, list[int]] = defaultdict(list)
    service_counts: dict[int, list[int]] = defaultdict(list)

    for scenario in range(args.scenarios):
        instance = perturb_instance(
            rng,
            base_instance,
            group_count=args.group_count,
            daily_noise=args.daily_noise,
            customer_noise=args.customer_noise,
            persistence=args.persistence,
            min_factor=args.min_factor,
            max_factor=args.max_factor,
        )
        if args.solver == "greedy":
            solution, report = construct_solution(
                instance,
                max_shifts=args.max_shifts,
            )
        else:
            solution, report = construct_cluster_solution(
                instance,
                neighborhood_size=args.neighborhood_size,
                max_shifts=args.max_shifts,
                score_cutoff_minute=score_cutoff_minute,
                terminal_buffer_days=args.terminal_buffer_days,
            )
        deliveries = delivery_by_customer_step(solution)
        first_by_customer, counts_by_customer, served_day1, served_report, scenario_events = summarize_solution(
            instance,
            deliveries,
            report_days=args.report_days,
        )
        for event in scenario_events:
            event_rows.append(
                {
                    "scenario": scenario,
                    **event,
                }
            )

        scenario_rows.append(
            {
                "scenario": scenario,
                "shifts": report.shifts,
                "operations": report.operations,
                "delivered_quantity": report.delivered_quantity,
                "unscheduled_customers": len(report.unscheduled_customers),
                "served_by_day1": served_day1,
                "served_by_day{}".format(args.report_days): served_report,
            }
        )

        for customer in instance.customers:
            if customer.call_in:
                continue
            first_day = first_by_customer[customer.index]
            count = counts_by_customer[customer.index]
            if first_day is not None:
                first_service_days[customer.index].append(first_day)
                for day in range(1, args.report_days + 1):
                    served_by_day_counts[customer.index].append(1 if first_day <= day else 0)
            else:
                for day in range(1, args.report_days + 1):
                    served_by_day_counts[customer.index].append(0)
            service_counts[customer.index].append(count)

    summary_rows: list[dict[str, object]] = []
    for customer in base_instance.customers:
        if customer.call_in:
            continue
        first_days = first_service_days.get(customer.index, [])
        counts = service_counts.get(customer.index, [])
        row: dict[str, object] = {
            "point": customer.index,
            "mean_first_service_day": "" if not first_days else round(mean(first_days), 3),
            "served_in_any_scenario": len(first_days),
            "service_count_mean_by_day{}".format(args.report_days): round(mean(counts), 3) if counts else 0.0,
            "service_count_min_by_day{}".format(args.report_days): min(counts) if counts else 0,
            "service_count_max_by_day{}".format(args.report_days): max(counts) if counts else 0,
        }
        for day in range(1, args.report_days + 1):
            values = served_by_day_counts.get(customer.index, [])
            day_values = values[day - 1 :: args.report_days]
            row["served_by_day{}_freq".format(day)] = round(mean(day_values), 3) if day_values else 0.0
        summary_rows.append(row)

    summary_rows.sort(
        key=lambda row: (
            -float(row["served_by_day1_freq"]),
            float(row["mean_first_service_day"] or 9999),
            row["point"],
        )
    )

    scenario_served_key = "served_by_day{}".format(args.report_days)
    print("instance,{}".format(args.instance_xml))
    print("solver,{}".format(args.solver))
    print("scenarios,{}".format(args.scenarios))
    print("solve_days,{}".format(args.solve_days))
    print("report_days,{}".format(args.report_days))
    print("scenario_mean_shifts,{:.3f}".format(mean(row["shifts"] for row in scenario_rows)))
    print("scenario_mean_unscheduled,{:.3f}".format(mean(row["unscheduled_customers"] for row in scenario_rows)))
    print("scenario_mean_served_day1,{:.3f}".format(mean(row["served_by_day1"] for row in scenario_rows)))
    print(
        "scenario_mean_served_day{},{}".format(
            args.report_days,
            round(mean(row[scenario_served_key] for row in scenario_rows), 3),
        )
    )
    print("top_stable_customers")
    print("point,served_by_day1_freq,served_by_day{}_freq,mean_first_service_day,mean_service_count".format(args.report_days))
    service_mean_key = "service_count_mean_by_day{}".format(args.report_days)
    for row in summary_rows[: args.limit]:
        print(
            "{},{:.3f},{:.3f},{},{}".format(
                row["point"],
                row["served_by_day1_freq"],
                row["served_by_day{}_freq".format(args.report_days)],
                row["mean_first_service_day"],
                row[service_mean_key],
            )
        )

    if args.summary_csv:
        with args.summary_csv.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(summary_rows[0].keys()))
            writer.writeheader()
            writer.writerows(summary_rows)
    if args.scenarios_csv:
        with args.scenarios_csv.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(scenario_rows[0].keys()))
            writer.writeheader()
            writer.writerows(scenario_rows)
    if args.events_csv:
        with args.events_csv.open("w", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["scenario", "point", "day", "arrival_minute", "visit_index"],
            )
            writer.writeheader()
            writer.writerows(event_rows)


if __name__ == "__main__":
    main()
