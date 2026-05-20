from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from ..contest import score_prefix_with_feasibility_tail
from ..inventory import tank_events
from ..model import Instance, Shift, Solution
from ..highs_repair import repair_quantities_with_highs
from ..highs_time_opt import optimize_solution_times
from ..route_cache import RouteCache
from .highs_selector import (
    SelectorConfig,
    _candidate_pressure_bonus,
    _inventory_pressure_by_customer,
    select_shifts_with_highs,
)
from .targeted_rescue import (
    MINUTES_PER_DAY,
    RescueConfig,
    _baseline_window_shifts,
    _dedupe_reindex,
    _failing_customers,
    _keep_shifts_started_before,
    generate_chain_rescue_candidates,
    generate_carryover_rescue_candidates,
    generate_multi_reload_candidates,
    generate_rescue_candidates,
    normalize_source_loads,
)


@dataclass(frozen=True)
class ColumnLoopConfig:
    start_day: int = 0
    end_day: int = 14
    replace_from_day: int = 3
    iterations: int = 3
    max_pressure_customers: int = 12
    neighbors_per_anchor: int = 8
    batch_workers: int = 4
    samples_per_customer: int = 8
    sample_lookback_days: int = 14
    max_chain_length: int = 4
    nearest_chain_neighbors: int = 4
    max_candidates_per_iteration: int = 1200
    target_fill_ratio: float = 0.95
    max_pre_service_fill_ratio: float = 0.95
    multi_reload_columns: bool = False
    max_multi_reload_per_batch: int = 20
    normalize_source_loads: bool = True
    quantity_objective: str = "min-delivered"
    commit_end_day: int = 7
    next_after_commit_day: int | None = None
    route_prior_candidates: tuple[Shift, ...] = ()
    selector_time_limit: float = 300.0
    selector_mip_gap: float | None = None
    selector_threads: int | None = None
    selector_mip_focus: int | None = None
    selector_node_limit: int | None = None


@dataclass(frozen=True)
class ColumnLoopStep:
    iteration: int
    generated_candidates: int
    pool_size: int
    selected_extra_shifts: int
    feasible: bool
    feasibility_errors: int
    hard_violations: int
    first_safety_breach_minute: int | None
    cost: float = 0.0
    logistic_ratio: float = 0.0
    min_commit_doi: float = 999.0
    vulnerable_commit_customers: list[tuple[int, float]] = None
    min_lookahead_doi: float = 999.0
    vulnerable_lookahead_customers: list[tuple[int, float]] = None
    next_after_commit_day: int | None = None
    min_next_after_commit_doi: float = 999.0
    vulnerable_next_after_commit_customers: list[tuple[int, float]] = None


def get_vulnerabilities(
    instance: Instance,
    solution: Solution,
    day: int,
) -> tuple[float, list[tuple[int, float]]]:
    """Calculate the remaining days of inventory (DOI) for each customer at the end of the given day."""
    from ..inventory import days_of_inventory
    # If the fast cython project_inventory is available, this call is extremely fast
    from ..inventory import tank_events
    events = list(tank_events(instance, solution))
    step_cutoff = min((day * 1440) // instance.unit, instance.horizon) - 1
    if step_cutoff < 0:
        step_cutoff = 0
    
    customer_inventories = {}
    for event in events:
        if event.step == step_cutoff:
            customer_inventories[event.point] = event.ending_inventory
            
    vulnerabilities = []
    for customer in instance.customers:
        if customer.call_in:
            continue
        current_inv = customer_inventories.get(customer.index, customer.initial_tank_quantity)
        doi = days_of_inventory(instance, customer, current_inv, start_step=step_cutoff + 1)
        vulnerabilities.append((customer.index, doi))
        
    vulnerabilities.sort(key=lambda x: x[1])
    min_doi = vulnerabilities[0][1] if vulnerabilities else 999.0
    return min_doi, vulnerabilities[:3]


def column_generation_rescue(
    instance: Instance,
    baseline: Solution,
    *,
    config: ColumnLoopConfig = ColumnLoopConfig(),
) -> tuple[Solution, tuple[ColumnLoopStep, ...]]:
    fixed_prefix = _keep_shifts_started_before(
        baseline,
        config.replace_from_day * MINUTES_PER_DAY,
    )
    pool = _dedupe_reindex(
        [
            *_baseline_window_shifts(baseline, _rescue_config(config)),
            *config.route_prior_candidates,
        ]
    )
    steps: list[ColumnLoopStep] = []
    best_solution = baseline
    best_score = score_prefix_with_feasibility_tail(
        instance,
        baseline,
        score_days=config.end_day,
        feasibility_days=config.end_day,
    )

    current = baseline
    for iteration in range(config.iterations):
        pressure_customers = _pressure_customers(instance, current, config)
        generated = _generate_priced_batches(
            instance,
            fixed_prefix,
            pressure_customers,
            config,
        )
        pressure = _inventory_pressure_by_customer(
            instance,
            fixed_prefix,
            config.replace_from_day,
            config.end_day,
        )
        generated = _top_diverse_columns(instance, generated, pressure, config)
        
        prev_pool_size = len(pool)
        pool = _dedupe_reindex([*pool, *generated])
        
        if len(pool) == prev_pool_size and iteration > 0:
            # Convergence: no new unique columns were added to the pool.
            # We skip breaking on iteration 0 to ensure at least one full
            # pass evaluates the newly generated columns.
            break

        selected = select_shifts_with_highs(
            instance,
            fixed_prefix,
            pool,
            start_day=config.replace_from_day,
            end_day=config.end_day,
            pressure_pricing=True,
            selector_config=SelectorConfig(
                time_limit=config.selector_time_limit,
                mip_gap=config.selector_mip_gap,
                threads=config.selector_threads,
                mip_focus=config.selector_mip_focus,
                node_limit=config.selector_node_limit,
            ),
        )
        selected = optimize_solution_times(instance, selected)
        if config.normalize_source_loads:
            selected = normalize_source_loads(instance, selected)
        repaired, repair_report = repair_quantities_with_highs(
            instance,
            selected,
            score_days=config.end_day,
            feasibility_days=config.end_day,
            quantity_objective=config.quantity_objective,
        )
        if config.normalize_source_loads:
            repaired = normalize_source_loads(instance, repaired)
        current = repaired
        score = score_prefix_with_feasibility_tail(
            instance,
            current,
            score_days=config.end_day,
            feasibility_days=config.end_day,
        )
        if _score_key(score) < _score_key(best_score):
            best_score = score
            best_solution = current

        logistic_ratio = score.scored_estimated_cost / max(1.0, score.scored_delivered_quantity)
        min_commit_doi, vuln_commit = get_vulnerabilities(instance, current, config.commit_end_day)
        next_after_commit_day = (
            config.next_after_commit_day
            if config.next_after_commit_day is not None
            else min(config.end_day, config.commit_end_day + 7)
        )
        min_next_doi, vuln_next = get_vulnerabilities(instance, current, next_after_commit_day)
        min_lookahead_doi, vuln_lookahead = get_vulnerabilities(instance, current, config.end_day)

        steps.append(
            ColumnLoopStep(
                iteration=iteration,
                generated_candidates=len(generated),
                pool_size=len(pool),
                selected_extra_shifts=max(0, len(selected.shifts) - len(fixed_prefix.shifts)),
                feasible=score.feasible,
                feasibility_errors=score.feasibility_errors,
                hard_violations=score.hard_violations,
                first_safety_breach_minute=score.first_safety_breach_minute,
                cost=score.scored_estimated_cost,
                logistic_ratio=logistic_ratio,
                min_commit_doi=min_commit_doi,
                vulnerable_commit_customers=vuln_commit,
                next_after_commit_day=next_after_commit_day,
                min_next_after_commit_doi=min_next_doi,
                vulnerable_next_after_commit_customers=vuln_next,
                min_lookahead_doi=min_lookahead_doi,
                vulnerable_lookahead_customers=vuln_lookahead,
            )
        )
        if score.feasible:
            best_solution = current
            break

    reindexed = Solution(
        shifts=tuple(replace(shift, index=index) for index, shift in enumerate(best_solution.shifts))
    )
    return reindexed, tuple(steps)


def _rescue_config(config: ColumnLoopConfig) -> RescueConfig:
    return RescueConfig(
        start_day=config.start_day,
        end_day=config.end_day,
        replace_from_day=config.replace_from_day,
        max_customers=config.max_pressure_customers,
        samples_per_customer=config.samples_per_customer,
        target_fill_ratio=config.target_fill_ratio,
        max_pre_service_fill_ratio=config.max_pre_service_fill_ratio,
        sample_lookback_days=config.sample_lookback_days,
        max_chain_length=config.max_chain_length,
        nearest_chain_neighbors=config.nearest_chain_neighbors,
        repair_quantities=False,
        normalize_source_loads=config.normalize_source_loads,
        quantity_objective=config.quantity_objective,
    )


def _pressure_customers(
    instance: Instance,
    solution: Solution,
    config: ColumnLoopConfig,
) -> list[int]:
    cutoff_step = min(instance.horizon, config.end_day * MINUTES_PER_DAY // instance.unit)
    breach_scores: dict[int, tuple[int, float]] = {}
    urgency_scores: dict[int, tuple[int, float]] = {}
    for event in tank_events(instance, solution):
        if event.step >= cutoff_step or event.point not in instance.customer_by_point:
            continue
        customer = instance.customer_by_point[event.point]
        if customer.call_in:
            continue
        deficit = max(0.0, event.safety_level - event.ending_inventory)
        if deficit > 0.0:
            first, total = breach_scores.get(event.point, (event.step, 0.0))
            breach_scores[event.point] = (min(first, event.step), total + deficit)
            continue
        urgency = max(0.0, customer.safety_level + 0.15 * customer.capacity - event.ending_inventory)
        if urgency > 0.0:
            first, total = urgency_scores.get(event.point, (event.step, 0.0))
            urgency_scores[event.point] = (min(first, event.step), total + urgency)

    breach_order = sorted(
        breach_scores,
        key=lambda point: (breach_scores[point][0], -breach_scores[point][1], point),
    )
    urgency_order = sorted(
        urgency_scores,
        key=lambda point: (urgency_scores[point][0], -urgency_scores[point][1], point),
    )
    ordered = [*breach_order]
    ordered.extend(point for point in urgency_order if point not in breach_scores)
    if not ordered:
        return _failing_customers(instance, solution, _rescue_config(config))
    return ordered[: config.max_pressure_customers]


def _generate_priced_batches(
    instance: Instance,
    prefix: Solution,
    pressure_customers: list[int],
    config: ColumnLoopConfig,
) -> list[Shift]:
    if not pressure_customers:
        return []
    batches = [
        _anchor_batch(instance, pressure_customers, anchor, config)
        for anchor in pressure_customers
    ]
    rescue_config = _rescue_config(config)

    def generate(batch: list[int]) -> list[Shift]:
        candidates = generate_rescue_candidates(instance, prefix, batch, config=rescue_config)
        candidates.extend(generate_carryover_rescue_candidates(instance, prefix, batch, config=rescue_config))
        candidates.extend(generate_chain_rescue_candidates(instance, prefix, batch, config=rescue_config))
        if config.multi_reload_columns:
            candidates.extend(
                generate_multi_reload_candidates(instance, prefix, batch, config=rescue_config)[
                    : config.max_multi_reload_per_batch
                ]
            )
        return candidates

    if config.batch_workers <= 1:
        nested = [generate(batch) for batch in batches]
    else:
        with ThreadPoolExecutor(max_workers=config.batch_workers) as executor:
            nested = list(executor.map(generate, batches))
    return [candidate for batch in nested for candidate in batch]


def _anchor_batch(
    instance: Instance,
    pressure_customers: list[int],
    anchor: int,
    config: ColumnLoopConfig,
) -> list[int]:
    neighbors = sorted(
        (customer for customer in pressure_customers if customer != anchor),
        key=lambda customer: (instance.time_matrix[anchor][customer], customer),
    )[: config.neighbors_per_anchor]
    return [anchor, *neighbors]


def _top_diverse_columns(
    instance: Instance,
    candidates: list[Shift],
    pressure,
    config: ColumnLoopConfig,
) -> list[Shift]:
    route_cache = RouteCache(instance)
    ranked = sorted(
        candidates,
        key=lambda shift: (
            -_candidate_pressure_bonus(instance, shift, pressure),
            -len(_served_customers(instance, shift)),
            route_cache.shift_distance(shift),
        ),
    )
    selected: list[Shift] = []
    seen_routes: set[tuple[int, ...]] = set()
    bucket_counts: dict[tuple[int, int, int], int] = {}
    for shift in ranked:
        customers = _served_customers(instance, shift)
        if not customers:
            continue
        route_key = (tuple(customers), shift.start // 240, shift.driver, shift.trailer)
        if route_key in seen_routes:
            continue
        bucket = (shift.driver, shift.trailer, shift.start // 240)
        if bucket_counts.get(bucket, 0) >= 12:
            continue
        seen_routes.add(route_key)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        selected.append(shift)
        if len(selected) >= config.max_candidates_per_iteration:
            break
    return selected


def _served_customers(instance: Instance, shift: Shift) -> tuple[int, ...]:
    return tuple(
        operation.point
        for operation in shift.operations
        if operation.quantity > 0 and operation.point in instance.customer_by_point
    )


def _score_key(score) -> tuple[int, int, int, float]:
    return (
        0 if score.feasible else 1,
        score.hard_violations,
        score.feasibility_errors,
        score.safety_kg_min,
    )
