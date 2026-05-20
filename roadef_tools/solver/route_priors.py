from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

from ..model import Instance, Operation, Shift, Solution
from ..xml_io import load_solution

MINUTES_PER_DAY = 1440


@dataclass(frozen=True)
class PriorRouteCandidate:
    shift: Shift
    source: str = "historical_prior"


def load_route_prior_candidates(
    instance: Instance,
    path: str | Path,
    *,
    start_day: int = 0,
    end_day: int | None = None,
) -> tuple[PriorRouteCandidate, ...]:
    path = Path(path)
    if path.suffix.lower() == ".xml":
        return route_priors_from_solution(
            instance,
            load_solution(path),
            start_day=start_day,
            end_day=end_day,
        )
    if path.suffix.lower() == ".csv":
        return route_priors_from_csv(instance, path, start_day=start_day, end_day=end_day)
    raise ValueError(f"Unsupported route prior format: {path.suffix}")


def route_priors_from_solution(
    instance: Instance,
    solution: Solution,
    *,
    start_day: int = 0,
    end_day: int | None = None,
) -> tuple[PriorRouteCandidate, ...]:
    start = start_day * MINUTES_PER_DAY
    end = (end_day * MINUTES_PER_DAY) if end_day is not None else None
    candidates = []
    for shift in solution.shifts:
        if shift.start < start or (end is not None and shift.start >= end):
            continue
        if _candidate_is_structurally_valid(instance, shift):
            candidates.append(PriorRouteCandidate(replace(shift, index=len(candidates))))
    return tuple(candidates)


def route_priors_from_csv(
    instance: Instance,
    path: str | Path,
    *,
    start_day: int = 0,
    end_day: int | None = None,
) -> tuple[PriorRouteCandidate, ...]:
    grouped: dict[str, list[dict[str, str]]] = {}
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            grouped.setdefault(row.get("route_id") or row.get("shift_id") or str(len(grouped)), []).append(row)
    shifts = []
    for rows in grouped.values():
        rows.sort(key=lambda row: int(float(row.get("sequence") or row.get("op_index") or 0)))
        first = rows[0]
        start = int(float(first.get("start") or first.get("start_minute") or 0))
        if start < start_day * MINUTES_PER_DAY:
            continue
        if end_day is not None and start >= end_day * MINUTES_PER_DAY:
            continue
        shift = Shift(
            index=len(shifts),
            driver=int(float(first.get("driver") or 0)),
            trailer=int(float(first.get("trailer") or 0)),
            start=start,
            operations=tuple(
                Operation(
                    point=int(float(row.get("point") or row.get("customer_id") or row.get("source_id") or 0)),
                    arrival=int(float(row.get("arrival") or row.get("arrival_minute") or start)),
                    quantity=float(row.get("quantity") or row.get("delivered_quantity") or 0.0),
                )
                for row in rows
            ),
        )
        if _candidate_is_structurally_valid(instance, shift):
            shifts.append(shift)
    return tuple(PriorRouteCandidate(shift=shift) for shift in shifts)


def prior_shifts(priors: tuple[PriorRouteCandidate, ...] | None) -> tuple[Shift, ...]:
    if not priors:
        return ()
    return tuple(prior.shift for prior in priors)


def _candidate_is_structurally_valid(instance: Instance, shift: Shift) -> bool:
    if shift.driver < 0 or shift.driver >= len(instance.drivers):
        return False
    if shift.trailer < 0 or shift.trailer >= len(instance.trailers):
        return False
    driver = instance.drivers[shift.driver]
    if shift.trailer not in driver.trailer_ids:
        return False
    known_points = {instance.base_index}
    known_points.update(source.index for source in instance.sources)
    known_points.update(customer.index for customer in instance.customers)
    return all(operation.point in known_points and operation.quantity >= 0.0 for operation in shift.operations)
