from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from roadef_tools.alns_state import (
    IRPState,
    PerturbationScope,
    highs_repair_operator,
    jitter_targeted_arrivals,
    remove_targeted_operations,
    restore_removed_operations,
    save_state_solution,
)
from roadef_tools.geo import GeoPoint, mds_coordinates
from roadef_tools.xml_io import load_instance, load_solution


def load_geo(path: Path, instance, clusters: int) -> dict[int, GeoPoint]:
    if not path.exists():
        return {point.point: point for point in mds_coordinates(instance, clusters=clusters)}

    import csv

    with path.open(newline="") as file:
        return {
            int(row["point"]): GeoPoint(
                point=int(row["point"]),
                kind=row["kind"],
                x=float(row["x"]),
                y=float(row["y"]),
                cluster=int(row["cluster"]),
            )
            for row in csv.DictReader(file)
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Targeted ROADEF ALNS smoke probe")
    parser.add_argument("instance_xml", type=Path)
    parser.add_argument("solution_xml", type=Path)
    parser.add_argument("--geo-csv", type=Path, required=True)
    parser.add_argument("--clusters", type=int, default=12)
    parser.add_argument("--target-cluster", type=int, required=True)
    parser.add_argument("--start-minute", type=int, required=True)
    parser.add_argument("--end-minute", type=int, required=True)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--output-xml", type=Path, required=True)
    args = parser.parse_args()

    instance = load_instance(args.instance_xml)
    solution = load_solution(args.solution_xml)
    geo = load_geo(args.geo_csv, instance, args.clusters)
    initial = IRPState(
        instance=instance,
        solution=solution,
        geo_points=geo,
        scope=PerturbationScope(
            clusters=(args.target_cluster,),
            start_minute=args.start_minute,
            end_minute=args.end_minute,
        ),
    )

    try:
        from alns import ALNS
        from alns.accept import HillClimbing
        from alns.select import RandomSelect
        from alns.stop import MaxIterations
    except ModuleNotFoundError:
        rng = np.random.default_rng(42)
        candidate = jitter_targeted_arrivals(initial, rng)
        candidate = restore_removed_operations(remove_targeted_operations(candidate, rng), rng)
        save_state_solution(candidate, args.output_xml)
        print("alns_installed,False")
        print(f"initial_objective,{initial.objective()}")
        print(f"candidate_objective,{candidate.objective()}")
        print(f"wrote,{args.output_xml}")
        return

    alns = ALNS(np.random.default_rng(42))
    alns.add_destroy_operator(remove_targeted_operations, name="remove_targeted_operations")
    alns.add_destroy_operator(jitter_targeted_arrivals, name="jitter_targeted_arrivals")
    alns.add_repair_operator(restore_removed_operations, name="restore_removed_operations")
    alns.add_repair_operator(highs_repair_operator, name="highs_repair_operator")

    select = RandomSelect(num_destroy=2, num_repair=2)
    accept = HillClimbing()
    stop = MaxIterations(args.iterations)
    result = alns.iterate(initial, select, accept, stop)
    best = result.best_state
    save_state_solution(best, args.output_xml)

    print("alns_installed,True")
    print(f"initial_objective,{initial.objective()}")
    print(f"best_objective,{best.objective()}")
    print(f"wrote,{args.output_xml}")


if __name__ == "__main__":
    main()
