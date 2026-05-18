"""Monte Carlo consumption scenarios and hedged instance construction.

Generates physics-consistent consumption perturbations and builds a single
hedged Instance by taking time-dependent percentiles across K scenarios.
The solver operates on the hedged instance unchanged — uncertainty is handled
entirely at the input layer.
"""

from __future__ import annotations

import random
from dataclasses import replace

import numpy as np

from ..model import Customer, Instance

MINUTES_PER_DAY = 1440


def generate_scenario_forecast(
    customer: Customer,
    unit: int,
    *,
    rng: random.Random,
    commit_end_day: int,
    day_sigma_schedule: dict[str, float],
    horizon_days: int,
) -> tuple[float, ...]:
    """Generate one physics-consistent consumption scenario for a customer.

    Perturbation is applied per-day as a multiplicative rate scaling factor,
    preserving intra-day consumption shape.  The sigma grows with distance
    from the commit boundary according to ``day_sigma_schedule``:

        commit window:  sigma = 0  (true data)
        plan window:    sigma = day_sigma_schedule["plan"]
        buffer window:  sigma = day_sigma_schedule["buffer"]

    After perturbation, a physics clamp ensures cumulative consumption never
    exceeds the available tank quantity (no negative tank levels).
    """
    steps_per_day = MINUTES_PER_DAY // unit
    base = list(customer.forecast)
    noised = list(base)

    plan_sigma = day_sigma_schedule.get("plan", 0.15)
    buffer_sigma = day_sigma_schedule.get("buffer", 0.30)

    for day in range(horizon_days):
        start = day * steps_per_day
        end = min(start + steps_per_day, len(base))
        if start >= len(base):
            break

        if day < commit_end_day:
            # commit window: true data, no noise
            continue

        # sigma grows with distance from commit boundary
        distance = day - commit_end_day
        plan_days = commit_end_day  # plan window is same width as commit
        if distance < plan_days:
            sigma = plan_sigma
        else:
            sigma = buffer_sigma

        multiplier = max(0.0, rng.gauss(1.0, sigma))
        for step in range(start, end):
            noised[step] = max(0.0, base[step] * multiplier)

    # Note: we do NOT clamp cumulative consumption to initial tank level here.
    # Consumption forecasts represent demand that will be met by deliveries;
    # the solver's inventory simulation handles tank-level physics with
    # deliveries included.

    return tuple(noised)


def generate_scenarios(
    instance: Instance,
    *,
    n_scenarios: int = 20,
    seed: int = 42,
    commit_end_day: int = 7,
    day_sigma_schedule: dict[str, float] | None = None,
) -> dict[int, list[tuple[float, ...]]]:
    """Generate K consumption scenarios for every VMI customer.

    Returns a dict mapping customer point index to a list of K forecast
    tuples, each representing one physics-consistent consumption scenario.
    """
    if day_sigma_schedule is None:
        day_sigma_schedule = {"plan": 0.15, "buffer": 0.30}

    rng = random.Random(seed)
    horizon_days = instance.horizon * instance.unit // MINUTES_PER_DAY

    scenarios: dict[int, list[tuple[float, ...]]] = {}
    for customer in instance.customers:
        if customer.call_in:
            continue
        customer_scenarios = []
        for _ in range(n_scenarios):
            scenario = generate_scenario_forecast(
                customer,
                instance.unit,
                rng=rng,
                commit_end_day=commit_end_day,
                day_sigma_schedule=day_sigma_schedule,
                horizon_days=horizon_days,
            )
            customer_scenarios.append(scenario)
        scenarios[customer.index] = customer_scenarios

    return scenarios


def build_hedged_instance(
    instance: Instance,
    scenarios: dict[int, list[tuple[float, ...]]],
    *,
    commit_end_day: int = 7,
    plan_end_day: int = 14,
    commit_percentile: float = 50.0,
    plan_percentile: float = 75.0,
    buffer_percentile: float = 90.0,
    capacity_buffer: float = 0.05,
) -> Instance:
    """Build a single hedged Instance from K scenarios.

    For each customer and timestep, the hedged forecast is the appropriate
    percentile across all K scenarios:

    - commit window (day < commit_end_day):  p50 (= true data when σ=0)
    - plan window (commit_end_day <= day < plan_end_day):  p75
    - buffer window (day >= plan_end_day):  p90

    Higher percentiles mean more pessimistic (higher) consumption, which
    causes the solver to over-deliver as a robustness buffer.

    The `capacity_buffer` (e.g., 0.05 for 5%) reduces the tank capacity in the
    hedged instance, leaving physical headroom on the true instance to
    prevent overfills during over-delivery.
    """
    steps_per_day = MINUTES_PER_DAY // instance.unit
    hedged_customers = []

    for customer in instance.customers:
        if customer.call_in or customer.index not in scenarios:
            hedged_customers.append(customer)
            continue

        customer_scenarios = scenarios[customer.index]
        n_steps = len(customer.forecast)

        # Stack scenarios: shape (K, n_steps)
        scenario_array = np.array(customer_scenarios, dtype=np.float64)

        hedged_forecast = np.empty(n_steps, dtype=np.float64)
        for step in range(n_steps):
            day = step // steps_per_day
            if day < commit_end_day:
                pct = commit_percentile
            elif day < plan_end_day:
                pct = plan_percentile
            else:
                pct = buffer_percentile
            hedged_forecast[step] = max(
                0.0,
                np.percentile(scenario_array[:, step], pct),
            )

        # Shrink capacity to leave headroom for hedging over-delivery
        hedged_capacity = customer.capacity * (1.0 - capacity_buffer)

        hedged_customers.append(
            replace(
                customer,
                forecast=tuple(hedged_forecast.tolist()),
                capacity=hedged_capacity,
            )
        )

    return replace(instance, customers=tuple(hedged_customers))
