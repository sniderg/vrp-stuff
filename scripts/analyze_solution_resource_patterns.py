from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

from roadef_tools.rules import derive_solution
from roadef_tools.xml_io import load_instance, load_solution


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("instance_xml", type=Path)
    parser.add_argument("solution_xml", type=Path)
    parser.add_argument("--examples", type=int, default=8)
    parser.add_argument("--output-csv", type=Path)
    args = parser.parse_args()

    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    derived = sorted(derive_solution(instance, solution), key=lambda item: (item.shift.start, item.shift.index))
    source_points = set(instance.source_by_point)
    customer_points = set(instance.customer_by_point)

    rows = []
    counters = Counter()
    trailer_drivers: dict[int, set[int]] = defaultdict(set)
    driver_trailers: dict[int, set[int]] = defaultdict(set)
    previous_by_trailer = {}

    for item in derived:
        shift = item.shift
        trailer_drivers[shift.trailer].add(shift.driver)
        driver_trailers[shift.driver].add(shift.trailer)
        sources = [
            index
            for index, operation in enumerate(shift.operations)
            if operation.point in source_points
        ]
        customers = [
            operation.point
            for operation in shift.operations
            if operation.quantity > 0 and operation.point in customer_points
        ]
        first_source_index = sources[0] if sources else None
        first_customer_index = next(
            (
                index
                for index, operation in enumerate(shift.operations)
                if operation.quantity > 0 and operation.point in customer_points
            ),
            None,
        )
        starts_without_source = first_customer_index is not None and (
            first_source_index is None or first_customer_index < first_source_index
        )
        starts_with_loaded_trailer = starts_without_source and item.start_trailer_quantity > 1e-6
        multi_reload = len(sources) >= 2
        source_after_customer = any(
            source_index > 0
            and any(
                operation.quantity > 0 and operation.point in customer_points
                for operation in shift.operations[:source_index]
            )
            for source_index in sources
        )
        partial_source_loads = [
            -operation.quantity
            for operation in shift.operations
            if operation.point in source_points and operation.quantity < -1e-6
        ]
        partial_load = any(
            1e-6 < quantity < instance.trailers[shift.trailer].capacity - 1e-6
            for quantity in partial_source_loads
        )
        delayed_start = False
        window_slack = None
        for window in instance.drivers[shift.driver].time_windows:
            if window.start <= shift.start <= window.end:
                window_slack = shift.start - window.start
                delayed_start = window_slack > 0
                break

        previous = previous_by_trailer.get(shift.trailer)
        handoff = previous is not None and previous.shift.driver != shift.driver
        if previous is not None:
            if item.start_trailer_quantity > 1e-6:
                counters["carryover_positive_shift"] += 1
            if handoff and item.start_trailer_quantity > 1e-6:
                counters["positive_handoff_shift"] += 1
        previous_by_trailer[shift.trailer] = item

        if starts_without_source:
            counters["starts_without_source"] += 1
        if starts_with_loaded_trailer:
            counters["starts_with_loaded_trailer"] += 1
        if multi_reload:
            counters["multi_reload_shifts"] += 1
        if source_after_customer:
            counters["source_after_customer_shifts"] += 1
        if partial_load:
            counters["partial_source_load_shifts"] += 1
        if item.layovers:
            counters["layover_shifts"] += 1
        if handoff:
            counters["driver_handoff_shifts"] += 1
        if delayed_start:
            counters["delayed_start_shifts"] += 1

        rows.append(
            {
                "shift": shift.index,
                "start": shift.start,
                "driver": shift.driver,
                "trailer": shift.trailer,
                "start_load": item.start_trailer_quantity,
                "end_load": item.end_trailer_quantity,
                "ops": len(shift.operations),
                "customers": " ".join(map(str, customers)),
                "sources": len(sources),
                "layovers": item.layovers,
                "window_slack": window_slack,
                "starts_without_source": starts_without_source,
                "starts_with_loaded_trailer": starts_with_loaded_trailer,
                "multi_reload": multi_reload,
                "source_after_customer": source_after_customer,
                "partial_source_load": partial_load,
                "handoff_from_previous_driver": handoff,
            }
        )

    summary = {
        "instance": instance.name,
        "solution": args.solution_xml.name,
        "shifts": len(derived),
        "drivers_used": len(driver_trailers),
        "trailers_used": len(trailer_drivers),
        "trailers_with_multiple_drivers": sum(1 for drivers in trailer_drivers.values() if len(drivers) > 1),
        "drivers_with_multiple_trailers": sum(1 for trailers in driver_trailers.values() if len(trailers) > 1),
        **counters,
    }
    for key, value in summary.items():
        print(f"{key},{value}")

    interesting_keys = [
        "starts_without_source",
        "multi_reload",
        "source_after_customer",
        "partial_source_load",
        "handoff_from_previous_driver",
        "layovers",
    ]
    for key in interesting_keys:
        examples = [row for row in rows if row[key]]
        if examples:
            print(f"examples_{key}")
            for row in examples[: args.examples]:
                print(
                    f"shift={row['shift']} start={row['start']} d={row['driver']} "
                    f"t={row['trailer']} start_load={row['start_load']:.3f} "
                    f"end_load={row['end_load']:.3f} sources={row['sources']} "
                    f"layovers={row['layovers']} customers={row['customers']}"
                )

    if args.output_csv:
        with args.output_csv.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
