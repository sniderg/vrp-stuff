"""Rolling commit-and-advance loop with Monte Carlo hedged instances.

Decomposes a long-horizon IRP into overlapping short-horizon CG solves.
Each window uses a hedged instance built from consumption scenarios, then
commits near-term routes and advances.  The final stitched solution is
validated against the true (un-noised) instance.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from ..contest import ContestScore, score_prefix_with_feasibility_tail
from ..model import Instance, Solution
from .column_loop import ColumnLoopConfig, column_generation_rescue
from .scenario import build_hedged_instance, generate_scenarios

MINUTES_PER_DAY = 1440


@dataclass(frozen=True)
class RollingCGConfig:
    """Configuration for the robust rolling CG solver."""

    horizon_days: int = 30
    commit_days: int = 7
    lookahead_days: int = 14
    n_scenarios: int = 20
    scenario_seed: int = 42
    plan_sigma: float = 0.15
    buffer_sigma: float = 0.30
    commit_percentile: float = 50.0
    plan_percentile: float = 75.0
    buffer_percentile: float = 90.0
    # CG config for each window
    cg_iterations: int = 5
    max_pressure_customers: int = 12
    samples_per_customer: int = 8
    max_chain_length: int = 4
    nearest_chain_neighbors: int = 10
    max_candidates_per_iteration: int = 1200
    target_fill_ratio: float = 0.95
    max_pre_service_fill_ratio: float = 0.95
    normalize_source_loads: bool = True
    quantity_objective: str = "min-delivered"


@dataclass(frozen=True)
class RollingCGStep:
    """Diagnostics for one rolling window."""

    round_index: int
    commit_start_day: int
    commit_end_day: int
    solve_end_day: int
    cg_iterations: int
    feasible: bool
    feasibility_errors: int
    hard_violations: int
    first_safety_breach_minute: int | None
    committed_shifts: int
    total_shifts: int


ProgressCallback = Callable[[str], None]


def robust_rolling_rescue(
    instance: Instance,
    baseline: Solution,
    *,
    config: RollingCGConfig = RollingCGConfig(),
    progress: ProgressCallback | None = None,
) -> tuple[Solution, list[RollingCGStep]]:
    """Solve by rolling commit-and-advance with hedged consumption.

    Each round:
    1. Generate K consumption scenarios with noise growing from commit boundary
    2. Build hedged instance (percentile blend)
    3. Run CG on hedged instance for this window
    4. Commit near-term routes, advance window

    The final solution is stitched from all committed blocks and validated
    against the true (un-noised) instance.
    """
    emit = progress or (lambda _msg: None)
    instance_days = _instance_days(instance)
    horizon_days = min(config.horizon_days, instance_days)
    commit_stride = config.commit_days
    steps: list[RollingCGStep] = []

    current_solution = baseline
    committed_day = 0
    round_index = 0

    while committed_day < horizon_days:
        commit_end_day = min(committed_day + commit_stride, horizon_days)
        solve_end_day = min(committed_day + commit_stride + config.lookahead_days, horizon_days)

        emit(
            f"round={round_index} commit_days=[{committed_day},{commit_end_day}) "
            f"solve_days=[{committed_day},{solve_end_day})"
        )

        # Is this the last round? Use true data (no noise needed)
        is_last_round = commit_end_day >= horizon_days

        if is_last_round:
            hedged = instance
            emit("  last round: using true data (no noise)")
        else:
            # Generate scenarios with noise growing from commit boundary
            sigma_schedule = {
                "plan": config.plan_sigma,
                "buffer": config.buffer_sigma,
            }
            scenarios = generate_scenarios(
                instance,
                n_scenarios=config.n_scenarios,
                seed=config.scenario_seed + round_index,
                commit_end_day=commit_end_day,
                day_sigma_schedule=sigma_schedule,
            )
            hedged = build_hedged_instance(
                instance,
                scenarios,
                commit_end_day=commit_end_day,
                plan_end_day=min(commit_end_day + commit_stride, horizon_days),
                commit_percentile=config.commit_percentile,
                plan_percentile=config.plan_percentile,
                buffer_percentile=config.buffer_percentile,
            )
            emit(
                f"  generated {config.n_scenarios} scenarios, "
                f"plan_σ={config.plan_sigma}, buffer_σ={config.buffer_sigma}"
            )

        # Build CG config for this window
        # The CG scores from start_day to end_day. We want it to score
        # the full range 0..solve_end_day so the prefix is included in
        # feasibility, but replace_from_day controls which routes can
        # be generated/replaced.
        cg_config = ColumnLoopConfig(
            start_day=0,
            end_day=solve_end_day,
            replace_from_day=committed_day,
            iterations=config.cg_iterations,
            max_pressure_customers=config.max_pressure_customers,
            samples_per_customer=config.samples_per_customer,
            sample_lookback_days=max(7, committed_day),
            max_chain_length=config.max_chain_length,
            nearest_chain_neighbors=config.nearest_chain_neighbors,
            max_candidates_per_iteration=config.max_candidates_per_iteration,
            target_fill_ratio=config.target_fill_ratio,
            max_pre_service_fill_ratio=config.max_pre_service_fill_ratio,
            normalize_source_loads=config.normalize_source_loads,
            quantity_objective=config.quantity_objective,
        )

        # Run CG on the hedged instance
        window_solution, cg_steps = column_generation_rescue(
            hedged, current_solution, config=cg_config
        )

        # Report CG convergence
        for step in cg_steps:
            emit(
                f"  cg iter={step.iteration} pool={step.pool_size} "
                f"errors={step.feasibility_errors} hard={step.hard_violations} "
                f"{'✅ feasible' if step.feasible else ''}"
            )

        # Score the window solution against the TRUE instance (not hedged)
        true_score = score_prefix_with_feasibility_tail(
            instance,
            window_solution,
            score_days=solve_end_day,
            feasibility_days=solve_end_day,
        )
        emit(
            f"  true-instance score: errors={true_score.feasibility_errors} "
            f"hard={true_score.hard_violations} "
            f"feasible={true_score.feasible}"
        )

        # Commit: keep all shifts starting before commit boundary
        commit_cutoff = commit_end_day * MINUTES_PER_DAY
        committed_shifts = [
            shift for shift in window_solution.shifts
            if shift.start < commit_cutoff
        ]
        committed_count = len([
            s for s in committed_shifts
            if s.start >= committed_day * MINUTES_PER_DAY
        ])

        # For the next round, start with the full window solution as baseline.
        # This preserves the 'plan' part of the solution so the next round
        # isn't starting from an empty schedule for its lookahead window.
        current_solution = window_solution

        steps.append(
            RollingCGStep(
                round_index=round_index,
                commit_start_day=committed_day,
                commit_end_day=commit_end_day,
                solve_end_day=solve_end_day,
                cg_iterations=len(cg_steps),
                feasible=true_score.feasible,
                feasibility_errors=true_score.feasibility_errors,
                hard_violations=true_score.hard_violations,
                first_safety_breach_minute=true_score.first_safety_breach_minute,
                committed_shifts=committed_count,
                total_shifts=len(committed_shifts),
            )
        )

        committed_day = commit_end_day
        round_index += 1

    # Final validation against true instance over full horizon
    final_score = score_prefix_with_feasibility_tail(
        instance,
        current_solution,
        score_days=horizon_days,
        feasibility_days=horizon_days,
    )
    emit(
        f"FINAL: shifts={len(current_solution.shifts)} "
        f"errors={final_score.feasibility_errors} "
        f"hard={final_score.hard_violations} "
        f"feasible={final_score.feasible} "
        f"cost={final_score.scored_estimated_cost:.2f}"
    )

    # Reindex shifts
    final_solution = Solution(
        shifts=tuple(
            replace(shift, index=i)
            for i, shift in enumerate(
                sorted(current_solution.shifts, key=lambda s: (s.start, s.driver))
            )
        )
    )
    return final_solution, steps


def _instance_days(instance: Instance) -> int:
    horizon_minutes = instance.horizon * instance.unit
    return (horizon_minutes + MINUTES_PER_DAY - 1) // MINUTES_PER_DAY
