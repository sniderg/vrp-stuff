# ROADEF V2.18 Solver — State of the Art

## Status

| Horizon | Best Result | Cost | Feasible |
|---|---|---|---|
| **A1.1 / 30 days** | `1.1_targeted_late_rescue_v2_official.xml` | logistic ratio **0.084281** | ✅ official checker |
| **14 days** | `2.18_checkpoint_14d_feasible_column_loop.xml` | **5211.65** | ✅ |
| **14 days** | `2.18_checkpoint_14d_feasible_layover_columns.xml` | **5203.44** | ✅ |
| **21 days** | `2.18_column_loop_21d_from_markov.xml` | 5227.37 | ❌ (4337 errors, 1296 hard) |

The A1.1 result is the small-instance sanity baseline. The 14-day V2.18 result is
**deterministically reproducible**. See the [README](README.md) for the exact
command.

---

## A1.1 Sanity Baseline

### Hexaly A-instance benchmark table

Saved as `roadef_2016_data/hexaly_a_benchmarks.csv`.

Important version distinction:

- Hexaly's published A-instance ratios are for **raw V1 A instances** and should
  be compared only against solutions scored with the V1 checker on files under
  `roadef_2016_data/set_A_v1_1/Instances V1.1/`.
- The older `set_A/*_ConvertedTo_V2.xml` runs are useful solver sanity tests,
  but their ratios are **not comparable** to the Hexaly A table because the
  converted V2 files/checker semantics differ.
- Any "beat Hexaly" or gap-vs-Hexaly claim must therefore use raw V1 inputs,
  raw V1-compatible output, and the V1 checker.
- Do not divide a raw V1 ratio by 2. The converted V2 score is roughly 2x the
  raw V1 score, so only converted V2 ratios should be divided by 2 for a raw-V1
  sanity comparison.
- Only fully feasible solutions may be used for A-instance benchmark claims.
  Infeasible outputs can be kept as repair diagnostics, but not as best-known
  checkpoints.

| Instance | Customers | Horizon (h) | Best known | Hexaly | Gap |
|---|---:|---:|---:|---:|---:|
| V_1.1 | 12 | 720 | 0.027466 | 0.027485 | 0.1% |
| V_1.2 | 12 | 720 | 0.027304 | 0.027477 | 0.6% |
| V_1.3 | 53 | 240 | 0.013279 | 0.013505 | 1.7% |
| V_1.4 | 64 | 240 | 0.015495 | 0.015464 | -0.2% |
| V_1.5 | 54 | 240 | 0.011877 | 0.011841 | -0.3% |
| V_1.6 | 54 | 840 | 0.012812 | 0.012880 | 0.5% |
| V_1.7 | 99 | 240 | 0.012890 | 0.012621 | -2.1% |
| V_1.8 | 99 | 82 | 0.007756 | 0.007756 | 0.0% |
| V_1.9 | 99 | 840 | 0.015279 | 0.015815 | 3.5% |
| V_1.10 | 89 | 240 | 0.018941 | 0.018371 | -3.0% |
| V_1.11 | 89 | 840 | 0.028666 | 0.028957 | 1.0% |

### Reproduction

```bash
.venv/bin/python -m roadef_tools.cli construct-solution \
  roadef_2016_data/set_A/Instance_V_1.1_ConvertedTo_V2.xml \
  roadef_2016_data/hust_smart_results/1.1_greedy_baseline.xml \
  --safety-buffer 0.20

.venv/bin/python -m roadef_tools.cli targeted-rescue \
  roadef_2016_data/set_A/Instance_V_1.1_ConvertedTo_V2.xml \
  roadef_2016_data/hust_smart_results/1.1_greedy_baseline.xml \
  roadef_2016_data/hust_smart_results/1.1_targeted_late_rescue_v2.xml \
  --start-day 27 --end-day 30 --replace-from-day 27 \
  --max-customers 5 --samples-per-customer 8 --sample-lookback-days 5 \
  --max-chain-length 3 --nearest-chain-neighbors 5 \
  --target-fill-ratio 0.95 --max-pre-service-fill-ratio 0.95 \
  --variable-quantity-columns

.venv/bin/python -m roadef_tools.cli clone-solution \
  roadef_2016_data/hust_smart_results/1.1_targeted_late_rescue_v2.xml \
  roadef_2016_data/hust_smart_results/1.1_targeted_late_rescue_v2_official.xml
```

### Result

```text
official_valid=True
official_logistic_ratio=0.084281
local_errors=0
rule_check_errors=0
tank_violations=0
```

### Bugs exposed

- Quantity repair needed chronological trailer-load constraints, not just a
  per-shift total delivery cap.
- Saved XML must be sorted by `(start, index)` and shift indices must be
  renumbered in output order, because the official checker assumes shift index
  equals XML array position.

---

## 14-Day Column-Generation Loop (Proven)

### Architecture

```
solve → detect pressure customers → generate targeted route batches
     → deduplicate / diversity-filter pool
     → HiGHS selects best subset
     → repair quantities
     → repeat
```

### Reproduction

```bash
.venv/bin/python -m roadef_tools.cli column-generation-rescue \
  roadef_2016_data/set_B/Instances_B_V25-11042016/V2.18.xml \
  roadef_2016_data/hust_smart_results/2.18_day0_14_markov_probe.xml \
  roadef_2016_data/hust_smart_results/2.18_checkpoint_14d_feasible_column_loop.xml \
  --start-day 0 --end-day 14 --iterations 10
```

### Convergence trace

```
iter 0:  446 gen,  472 pool, errors 166, hard 1, breach 12420
iter 1:  480 gen,  913 pool, errors 169, hard 0, breach 11580
iter 2:  475 gen, 1231 pool, errors 169, hard 0, breach 11580
iter 3:  431 gen, 1329 pool, errors 169, hard 0, breach 11580
iter 4:  489 gen, 1402 pool, ✅ feasible,  errors 0,  hard 0
```

### Key parameters

| Param | Value | Note |
|---|---|---|
| `--replace-from-day` | 0 (default) | all shifts replaceable |
| `--max-pressure-customers` | 12 (default) | customers targeted per iter |
| `--samples-per-customer` | 6 (default) | arrival time variants |
| `--max-chain-length` | 3 (default) | multi-stop chain length |
| `--nearest-chain-neighbors` | 4 (default) | neighbors per anchor |

---

## 21-Day Extension (In Progress)

### Situation

The 14-day checkpoint has zero routes after day 14. Extending to 21 days requires
generating and selecting a full second week of routes.

### Approaches tried

| Strategy | Errors | Hard | VMI below safety | Notes |
|---|---|---|---|---|
| Lock 14d prefix, CG days 14–21 | 15,150 | 4,352 | 85 | Only 15 new shifts selected, insufficient |
| Full CG from `markov_layover_columns_21d`, replace-from-day 3 | **4,337** | **1,296** | 39 | Best result; stalls at breach day 6 |
| Same, continued 8 more iters | 4,259 | 1,296 | 39 | Pool exhausted, identical columns |
| Full CG, replace-from-day 0 | 6,566 | 1,926 | 51 | ❌ Worse — HiGHS re-selects bad early routes |
| ALNS probe from `markov_layover_columns_21d` | 7,533 | 2,182 | 55 | Route-level ALNS smoke test; improves baseline but not best CG |
| Multi-reload CG probe | 4,981 | 1,499 | 51 | Adds route variety but first breach still stuck at 8,820 |

### Failure diagnosis

The stall at ~4,300 errors / 1,296 hard across iterations is caused by **column exhaustion**:

- Pool stabilises at ~450 unique candidates
- All 273 new candidates each iteration are duplicates of existing pool entries
- `first_safety_breach_minute` stuck at 8,820 (day 6) — a narrow-window customer
  that needs a route that conflicts with driver time windows

### Next steps (priority order)

1. **ALNS around day-6 pressure band** — use route-level destroy/repair rather
   than global CG. Current operators exist, including resource-conflict destroy,
   but repair still needs to bind the newly freed carryover route when that route
   is the reason for the destroy move.

2. **Pressure-peak arrival sampling** — generate arrival samples around pressure
   peaks for customers 75, 60, 45, 129, 106, instead of sampling only from
   breach/latest-arrival anchors.

3. **Richer candidate types** — multi-reload circuits are implemented as an
   opt-in probe (`--multi-reload-columns`) but did not yet move the first breach.
   Keep them off by default until pricing/selectivity improves.

4. **Two-phase strategy** — build a good 21-day Markov baseline first (more visits,
   better coverage), then run CG on top of it. The `markov_layover_columns_21d`
   baseline is weak (first breach at day 6) because Markov doesn't anticipate
   demand accumulation.

---

## Robust Rolling Horizon with Monte Carlo Noise

### Motivation

The current solver treats 21-day consumption forecasts as ground truth, but
uncertainty in tank levels and consumption grows with time. Even within the
ROADEF deterministic data, optimizing precise routes for day 18 based on a
day-0 forecast is over-fitting to noise that wouldn't exist in a real
deployment. The monolithic 21-day solve is not just computationally hard — it's
architecturally wrong.

Key insight: **inject artificial consumption noise that grows with forecast
distance, then solve in a rolling commit-and-advance loop.** The solver can't
over-optimize the fuzzy future, so it naturally concentrates on near-term
robustness. Each rolling window de-noises the next committed block, giving the
CG loop a 5–7 day effective horizon where it already converges.

This bridges competition scoring (final solution uses true data everywhere)
with real-world robustness (each committed block survives consumption
uncertainty).

### Physics-consistent scenario generation

Noise must respect physical constraints:

- Consumption rate ≥ 0 at every timestep
- Tank level ≥ 0 (can't consume what isn't in the tank)
- Intra-day consumption shape is preserved (perturb daily rate, not timesteps)
- Cumulative consumption over a week is more stable than hourly rate

The perturbation unit is **daily consumption rate multiplier** with tank-level
clamping:

```python
def generate_scenario(customer, base_forecast, unit, rng, day_sigma):
    steps_per_day = 1440 // unit
    noised = list(base_forecast)
    for day in range(len(base_forecast) // steps_per_day):
        multiplier = max(0.0, rng.gauss(1.0, day_sigma))
        start = day * steps_per_day
        end = min(start + steps_per_day, len(base_forecast))
        for step in range(start, end):
            noised[step] = base_forecast[step] * multiplier
    # physics clamp: cumulative consumption cannot exceed available tank
    tank = customer.initial_tank_quantity
    for step in range(len(noised)):
        if noised[step] > tank:
            noised[step] = max(0.0, tank)
        tank -= noised[step]
    return noised
```

### Monte Carlo hedged instance construction

Solvers need exact values — they can't operate on distributions. The approach
is to generate K scenarios (e.g., K=20), then build a single **hedged
instance** by taking time-dependent percentiles across scenarios:

```text
For each customer, at each timestep:
  commit window (days 0–7):   use p50 = true data (no noise applied)
  plan window (days 8–14):    use p75 across K scenarios
  buffer window (days 15–21): use p90 across K scenarios
```

This produces one deterministic `Instance` where far-future customers consume
faster than average. The existing CG/HiGHS/quantity-repair pipeline runs
unchanged on this hedged instance. The solver doesn't know it's solving a
robust problem — it just sees slightly pessimistic consumption and over-delivers
to compensate.

### Rolling protocol

```text
Round 1 (commit days 0–7):
  days 0–7:   σ = 0%    (true data)
  days 8–14:  σ = 15%   (moderate blur)
  days 15–21: σ = 30%   (heavy blur)
  → generate K=20 scenarios
  → build hedged instance (p50/p75/p90 by window)
  → CG solve (7-day effective horizon)
  → validate committed routes against all K true-data scenarios
  → commit days 0–7

Round 2 (commit days 7–14):
  days 0–7:   locked (already committed)
  days 7–14:  σ = 0%    (de-noised, true data)
  days 15–21: σ = 15%   (was 30%, now moderate)
  → CG solve days 7–21 with prefix locked
  → commit days 7–14

Round 3 (commit days 14–21):
  days 0–14:  locked
  days 14–21: σ = 0%    (de-noised, true data)
  → CG solve days 14–21
  → commit

Final: stitch all committed blocks → validate against true Instance → submit
```

### Scenario validation step

After each CG solve, validate committed routes against all K scenarios:

```text
for each scenario k in 1..K:
  reconstruct Instance with scenario-k consumption
  run tank simulation with committed routes
  if any hard violation in commit window:
    flag → tighten hedge percentile and re-solve
```

This catches cases where the hedged instance was not conservative enough. The
re-solve cost is low because it's still a 7-day CG problem.

### Implementation scope

| Component | Lines (est.) | Modifies existing code |
|---|---:|---|
| `solver/scenario.py` — scenario generator + hedged instance builder | ~80 | No |
| `solver/rolling_cg.py` — commit/advance/stitch rolling loop | ~120 | No |
| Scenario validation (tank sim under K scenarios) | ~30 | No |
| CLI command `robust-rolling-rescue` | ~60 | `cli.py` only |

The CG loop, HiGHS selector, quantity repair, pressure scoring, candidate
generators — all unchanged. Uncertainty is handled entirely at the input
(hedged instance) and validation (scenario check) layers.

### Expected benefits

- Decomposes 21-day problem into three 7-day CG solves (proven regime)
- Each committed block is robust to ±15–30% consumption uncertainty
- Terminal inventory buffers emerge naturally from pessimistic far-future data
- Final stitched solution scores on true deterministic data
- Architecture extends to any horizon length without monolithic solve
- Bridges competition solver with real-world deployment requirements

### Experimental plan

1. Implement on V_1.1 (12 customers, 30-day horizon) as proof of concept
2. Compare logistic ratio against current best (0.031523) and Hexaly (0.027485)
3. If competitive, apply to V2.18 21-day horizon
4. Tune noise parameters: σ ramp, percentile thresholds, K scenario count

---

## Tooling Roadmap

### Recommended next tooling order

1. **Add an ALNS destroy/repair loop around the column-generation solver.**
   - Status: initial route-level ALNS is implemented as `alns-rescue`.
   - Current result: 21-day smoke probe improved `markov_layover_columns_21d`
     from 8,352 errors / 2,462 hard to 7,533 errors / 2,182 hard.
   - New operator: `resource_conflict_destroy` is implemented. On raw V1
     `V_1.11` it identifies the customer-53 carryover slot using driver `1` /
     trailer `2` and removes shift `11`, the blocking driver/trailer interval.
   - Current limitation: a short 6-iteration ALNS run on `V_1.11` did not
     reduce the 331 safety-breach steps. The destroy move is correct, but the
     repair/master selection is not yet preserving the freed carryover column.
   - Next refinement: make repair local and conditional on the destroy motive:
     when `resource_conflict_destroy` removes a blocker for a concrete
     carryover candidate, force that candidate into the repair pool with a high
     pressure bonus or temporary covering constraint.

2. **Add pressure-peak arrival sampling for known day-6 blockers.**
   - Target customers: `75`, `60`, `45`, `129`, `106`.
   - Current problem: sampling is still mostly anchored to breach/latest-arrival
     logic, so it misses useful pre-buffer times around pressure peaks.
   - Desired sampling:

```text
for each pressure peak at minute T:
  sample T - 6d, T - 4d, T - 2d, T - 1d, T - 12h, T - 6h
  clip to driver/customer windows
  generate route variants around those arrivals
```

3. **Add a mini route-improvement MIP for small customer/time neighborhoods.**
   - Destroy a small neighborhood, then solve a restricted exact repair:

```text
customers = failing customer + nearest/related customers
time = 2-4 day band around first breach
resources = drivers/trailers active in that band
columns = existing routes + generated alternatives
objective = feasibility first, then cost
```

4. **Add LP-relaxation dual extraction from HiGHS if available.**
   - Goal: replace heuristic pressure scores with reduced-cost pricing signals.
   - Current pressure pricing is heuristic:

```text
route_value ≈ safety deficit relieved + chain bonus - travel cost
```

   - Desired reduced-cost style pricing:

```text
reduced_cost(route) =
    travel_cost
  - inventory_duals relieved by route
  - order_coverage_duals
  + resource_conflict_terms
```

5. **Only then consider C++/Numba for the route-pricing hot loop.**
   - Do not rewrite the solver first.
   - Accelerate only after the right route-pricing logic is identified.
   - Best candidates for acceleration:
     - candidate route enumeration
     - route feasibility checks
     - pressure/scoring of many candidate routes
     - resource-constrained shortest path pricing

### ALNS flavor to use

Use a **route-level matheuristic ALNS with column-generation repair**:

```text
incumbent solution
repeat:
  destroy route neighborhood
  generate focused columns for damaged region
  repair with HiGHS master + quantity repair
  accept/reject with simulated annealing
  update destroy operator weights
```

This is intentionally not operation-level ALNS. Operation-level perturbations
break timing, trailer load, source reloads, layovers, and driver windows too
easily. Destroy/repair should operate on whole shifts, time bands, customer
neighborhoods, and resource blocks.

### Destroy operators

Implemented first:

| Operator | Purpose |
|---|---|
| `pressure_band_destroy` | Remove shifts around the earliest safety/overfill pressure band |
| `related_customer_destroy` | Remove shifts touching travel-time-nearby customers |
| `route_block_destroy` | Remove a random block of routes in a time band |
| `resource_conflict_destroy` | Remove driver/trailer intervals that block a promising loaded-trailer carryover rescue |

Add next:

| Operator | Purpose |
|---|---|
| `fragile_tank_destroy` | Target small tanks: `8`, `45`, `97`, `129` |
| `layover_cluster_destroy` | Target remote/layover cluster: `19`, `60`, `123`, `127` |
| `driver_resource_destroy` | Remove all routes for one driver/trailer in a bad band |
| `forced_carryover_repair` | Preserve the concrete carryover candidate that motivated a resource-conflict destroy |
| `order_gap_destroy` | Target missed or under-satisfied explicit order customers |
| `overfill_destroy` | Remove routes causing overfill, then repair with lower quantities or different timing |

### Repair operators

Implemented first:

| Repair | Purpose |
|---|---|
| `column_generation_repair` | Run a bounded CG repair on the destroyed solution |
| `quantity_repair` | Re-optimize delivered quantities after route selection |

Add next:

| Repair | Purpose |
|---|---|
| `pressure_peak_repair` | Generate routes around pressure-peak arrival samples |
| `mini_mip_repair` | Small exact repair for one customer/time/resource neighborhood |
| `resource_block_repair` | Rebuild one driver/trailer schedule over a short band |
| `route_pool_repair` | Reuse successful columns from previous ALNS iterations |

### Acceptance and operator scoring

Use simulated annealing acceptance:

```text
accept if better
else accept with probability exp(-(candidate_score - current_score) / T)
cool T each iteration
```

Operator scoring:

```text
+5 if new global best
+2 if accepted improvement
+0.5 if accepted but not improved
decay if rejected
```

Primary score key:

```text
feasible first
then hard violations
then feasibility errors
then safety kg-minutes
then route cost
```

### Tools to keep

Core:

| Module | Role |
|---|---|
| `solver/alns.py` | Route-level ALNS controller |
| `solver/destroy.py` | Destroy operators |
| `solver/pressure.py` | Shared pressure extraction |
| `solver/column_loop.py` | Batched CG repair loop |
| `solver/highs_selector.py` | HiGHS route-selection master |
| `solver/targeted_rescue.py` | Candidate route generators |
| `highs_repair.py` | Quantity repair |
| `contest.py` / `inventory.py` / `rules.py` | Scoring and validation |

Baseline / experimental:

| Module | Role |
|---|---|
| `solver/greedy.py` | Basic baseline generation |
| `solver/cluster_greedy.py` | Cluster-aware baseline generation |
| `solver/rolling_highs.py` | Rolling horizon experiments |
| `solver/candidate_gen.py` | Older candidate generation path |

### Tools to remove or quarantine

Move to experimental or delete:

| Module / idea | Reason |
|---|---|
| `roadef_tools/alns_state.py` | Operation-level ALNS scaffold; too weak for route/load/window coupling |
| `jitter_targeted_arrivals` | Creates timing infeasibility without meaningful routing repair |
| `restore_removed_operations` as a main repair | Restoring operations is not real repair; route structure must change |
| Operation-level removal as primary destroy | Breaks route feasibility too easily |

### Tools to add

| Module | Purpose |
|---|---|
| `solver/neighborhood.py` | Customer relatedness: time, distance, tank-cycle, window overlap |
| `solver/repair.py` | Explicit repair operators wrapping CG, mini-MIP, quantity repair |
| `solver/route_pool.py` | Route signatures, pool aging, dedupe, diversity, reuse |
| `solver/pricing_dp.py` | Resource-constrained shortest-path pricing prototype |
| `solver/dual_pricing.py` | LP relaxation and dual/reduced-cost extraction |

### External ALNS package decision

The PyPI `alns` package is a stable generic ALNS framework (`7.0.0`, released
2024-10-21). It is useful conceptually, but should not be introduced as a hard
dependency yet. Our repair operators are specialized matheuristics: column
generation, HiGHS route selection, and quantity repair. A small in-repo ALNS loop
is easier to debug and adapt until the operator set stabilizes.

Reference: <https://pypi.org/project/alns/>

### Immediate next experiment

Run route-level ALNS around the known day-6 blockers:

```bash
.venv/bin/python -m roadef_tools.cli alns-rescue \
  roadef_2016_data/set_B/Instances_B_V25-11042016/V2.18.xml \
  roadef_2016_data/hust_smart_results/2.18_markov_layover_columns_21d.xml \
  roadef_2016_data/hust_smart_results/2.18_alns_day6_pressure.xml \
  --end-day 21 \
  --replace-from-day 3 \
  --iterations 20 \
  --repair-iterations 2 \
  --max-removed-shifts 8 \
  --max-pressure-customers 12 \
  --samples-per-customer 6 \
  --max-candidates-per-iteration 700
```

Then add pressure-peak sampling and rerun the same command. Success criterion:

```text
first_safety_breach_minute moves past 8820
hard_violations drop below 1296
feasibility_errors drop below 4337
```

---

## Comprehensive TODO Backlog

This problem was solved competitively in 2016 under a 30-minute CPU limit, and
the winning team solved all B/X final instances. Treat that as a hard reality
check: if our search is stuck, the issue is more likely formulation, route
generation, neighborhood design, or orchestration than raw CPU. Use more compute
where it multiplies a good idea; do not use it to brute-force a weak one.

### Literature and method targets

| Source | Lesson for this codebase |
|---|---|
| ROADEF/EURO 2016 final results | V2.18 was solved by team S17 within the official 30-minute CPU limit; feasible high-quality solutions are not exotic. |
| Kheiri 2020, *Heuristic Sequence Selection for Inventory Routing Problem* | The winning method used a sequence-based selection hyper-heuristic for this exact Air Liquide IRP. We should learn operator ordering, not just tune fixed parameters. |
| ROADEF scientific prize notes | Branch-cut-price, lower bounds, decomposition, and matheuristics were considered central by the committee. |
| 2020 Transportation Science special section | Strong submissions were mostly hyper-heuristic or matheuristic, not monolithic MIPs. |
| 2021-2023 IRP matheuristic / branch-price / branch-cut literature | Restricted exact repairs, path-flow formulations, route modification, and pricing subproblems are mature tools. |
| `alns` package | Useful design reference, but keep our implementation in-repo until repair operators stabilize. |

References:

- ROADEF final results: <https://roadef.org/challenge/2016/en/finalResults.php>
- ROADEF subject and checker: <https://roadef.org/challenge/2016/en/instances.php>
- Kheiri 2020: <https://doi.org/10.1287/trsc.2019.0934>
- Transportation Science special section: <https://doi.org/10.1287/trsc.2019.0972>
- ALNS package: <https://pypi.org/project/alns/>

### Must-track metrics

Feasibility metrics:

| Metric | Why it matters |
|---|---|
| `feasibility_errors` | Main checker error count; broad but noisy. |
| `hard_violations` | Better feasibility target than warning count. |
| `feasibility_warnings` | Diagnostic only unless tied to penalty/cost. |
| `first_safety_breach_minute` | Earliest hard failure; primary local repair anchor. |
| `first_overfill_minute` | Finds bad quantity/timing choices. |
| `vmi_customers_below_safety` | Counts breadth of inventory failure. |
| `customer_breach_minutes[c]` | Per-customer earliest failure. |
| `kg_min_below_safety[c]` | Severity, not just binary failure. |
| `kg_min_negative[c]` | Severe stockout severity. |
| `kg_min_over_max[c]` | Overfill severity. |
| `orders_missed`, `orders_late`, `orders_underfilled` | Call-in/order-specific feasibility. |
| `route_time_window_errors` | Customer/driver opening-hour conflicts. |
| `resource_overlap_errors` | Driver/trailer/source resource conflicts. |
| `trailer_capacity_errors` | Load infeasibility, especially multi-stop chains. |

Cost and operating metrics:

| Metric | Why it matters |
|---|---|
| `checker_cost` | Final objective; secondary until feasible. |
| `route_count` | Complexity and driver burden. |
| `operation_count` | Route fragmentation. |
| `loaded_quantity` | Trailer utilization denominator. |
| `delivered_quantity` | Actual useful flow. |
| `wasted_capacity` | Indicates poor chaining. |
| `reload_count` | Important after multi-circuit logic. |
| `layover_count` | Remote-cluster handling quality. |
| `driver_hours_by_day` | Workload smoothing target. |
| `truck_hours_by_day` | Resource bottleneck metric. |
| `source_load_by_day` | Depot/source congestion. |
| `weekend_workload` | Weekday/weekend imbalance. |
| `distance_minutes_total` | Routing cost proxy. |
| `service_minutes_total` | Fill-time burden. |
| `idle_minutes_total` | Window-waiting penalty. |

Route-pool metrics:

| Metric | Why it matters |
|---|---|
| `generated_columns` | Candidate generation scale. |
| `unique_columns` | Detects duplicate exhaustion. |
| `duplicate_columns` | Generator diversity failure. |
| `selected_columns` | Master utilization. |
| `selected_by_route_type` | Shows which generator families matter. |
| `columns_touching_customer[c]` | Coverage of pressure customers. |
| `columns_arriving_in_bucket[c,t]` | Time coverage around need windows. |
| `columns_with_positive_pressure_score` | Quality of candidate pool. |
| `pool_age_distribution` | Old columns vs fresh columns. |
| `removed_by_dedupe_reason` | Signature too coarse/fine diagnosis. |
| `selected_column_reuse_rate` | Whether ALNS recycles good structure. |

ALNS metrics:

| Metric | Why it matters |
|---|---|
| `destroy_operator_attempts` | Operator exploration. |
| `repair_operator_attempts` | Repair workload. |
| `operator_accept_rate` | Detects dead operators. |
| `operator_new_best_rate` | Operator value. |
| `mean_score_delta_by_operator` | Operator contribution. |
| `temperature` | SA schedule sanity. |
| `accepted_worse_moves` | Ability to escape local minima. |
| `destroyed_shifts` | Damage size. |
| `repaired_shifts` | Repair effectiveness. |
| `unrepaired_customers` | Gaps after repair. |

Runtime metrics:

| Metric | Why it matters |
|---|---|
| `candidate_generation_seconds` | First acceleration target. |
| `highs_master_seconds` | Solver bottleneck. |
| `quantity_repair_seconds` | Load integration bottleneck. |
| `checker_seconds` | Validation bottleneck. |
| `cache_hit_rate` | Whether memoization is paying off. |
| `routes_scored_per_second` | Pricing throughput. |
| `parallel_batch_efficiency` | Whether multiprocessing helps. |

### Reproducibility and experiment hygiene

- Preserve all current feasible 14-day checkpoints; never overwrite them.
- Add a single experiment manifest CSV/JSONL with command, git hash, instance,
  baseline, output file, seed, horizon, parameters, feasibility metrics, cost,
  runtime, and notes.
- Use deterministic seeds for every stochastic operator.
- Write one summary row per iteration, not just final output.
- Save the best incumbent at every improvement, not only at the end.
- Name files by instance, horizon, method, seed, and date or run id.
- Keep failed but informative 21-day outputs until their diagnostics are copied
  into the manifest.
- Add a `--dry-run-diagnostics` mode that validates parsing, route pool stats,
  pressure customers, and baseline score without running optimization.
- Add a `--resume-from-manifest-run` path so long experiments can continue.
- Record checker version and instance file checksum.
- Record Python version, HiGHS/SciPy version, platform, and CPU count.

### Validation and invariants

- Build a fast internal validator that catches obvious route/resource/load errors
  before calling the official checker.
- Every generated route must satisfy driver windows, customer windows, source
  windows, travel times, setup/service times, trailer capacity, compatible source,
  compatible product/trailer/customer restrictions, and route duration.
- Quantity repair must prove no delivery exceeds tank maximum at delivery time.
- Quantity repair must prove no route exceeds trailer loaded volume.
- For VMI customers, report tank level immediately before delivery and
  immediately after delivery.
- For call-in customers, separate order satisfaction from tank-level logic.
- Add unit tests for:
  - 1-minute consumption interpolation.
  - tank-level simulation.
  - closed-hours masking.
  - earliest and latest feasible service time.
  - 75% threshold logic.
  - safety threshold breach detection.
  - route signature/dedupe stability.
  - multi-stop load accounting.
  - multi-reload load accounting.
  - layover timing.
  - checker-output parsing.
- Add regression tests for:
  - 14-day feasible checkpoint remains feasible.
  - 21-day best known remains at or below 4337 / 1296 unless intentionally
    replaced.
  - day-6 first breach detection returns minute 8820 for the current failing
    baseline.

### Candidate generation

- Generate around earliest feasible service time, 75% threshold crossing, pressure
  peak, latest safe service time, and just-before-closed boundary.
- Generate before and after opening transitions for narrow-window customers.
- Generate routes that arrive early and wait if waiting is allowed/cheap.
- Generate routes that deliberately underfill tanks to preserve later chaining.
- Generate routes that fill to max when isolated/remote and expensive to revisit.
- Generate small-tank-first variants when capacity is scarce.
- Generate large-tank-first variants only when small tanks can still be covered.
- Generate chain routes anchored at fragile customers 8, 45, 97, 129.
- Generate chain routes anchored at remote/layover customers 19, 60, 123, 127.
- Generate route variants around day-6 blockers 75, 60, 45, 129, 106.
- Generate source-first and truck-start-first variants separately when departure
  location differs from fill source.
- Generate multiple circuits per truck per day, not just one shift/circuit.
- Generate reload-at-source variants for high-utilization days.
- Generate weekend-light variants with more weekday pre-service.
- Generate day-before-closure buffer variants for customers closed on weekends.
- Generate co-located customer synchronization variants: if two nearby customers
  have compatible tank cycles, try serving both in a repeating pattern.
- Generate anti-bunching variants that move service out of 280-320 hour pressure
  peak when feasible.
- Generate route variants that preserve enough trailer space for downstream
  fragile customers.
- Generate route variants that intentionally leave trailer residual capacity only
  when the return/reload economics justify it.
- Generate single-customer direct emergency routes for each hard blocker as a
  fallback column.
- Generate two-customer bridge routes from pressure customer to nearest compatible
  customer.
- Generate three-customer cluster routes only when load and windows are plausible.
- Generate route candidates from both greedy nearest-neighbor and regret insertion.
- Generate candidate departures, not only candidate arrivals.
- Ensure generator can produce columns for customers with narrow opening hours
  even if their latest-safe time falls during closure.
- Add a coverage report showing pressure customers with zero useful candidate
  arrivals.

### Integrated load and quantity modeling

- Treat delivery quantity as a function of arrival time, current tank level,
  safety target, 75% threshold, max tank, and downstream route load.
- Do not hard-wire fixed delivery quantity at route generation time unless that
  route is explicitly fixed.
- For each candidate stop, compute:
  - minimum useful delivery.
  - max legal delivery at that arrival time.
  - delivery to 75%.
  - delivery to max.
  - delivery preserving trailer capacity for later stops.
  - delivery required to survive to next planned visit.
- Add load-sharing repair: choose stop quantities jointly across a route, not
  greedily per stop.
- Add route-level knapsack repair: distribute trailer load across stops based on
  urgency, future visit availability, and tank slack.
- Add route-pool metadata for delivered quantity ranges, not just route sequence.
- Add master columns with quantity modes: small buffer, to 75%, to max, future-safe.
- Add local LP/MIP for quantity assignment on selected routes in a time band.
- Penalize overfilling and pointless early service before 75%, but allow it when
  it prevents a hard future breach.
- For multi-reload routes, ensure each circuit's quantity state is independent.
- For layovers, include carried load across route segments if allowed by rules.
- Track `kg delivered per driving minute` and `kg delivered per route minute`.

### Column-generation master

- Keep feasibility-first objective with lexicographic weights:
  hard violations, total checker errors, kg-minutes below safety, route cost.
- Add explicit customer/time coverage constraints for pressure customers.
- Add resource capacity constraints by driver/trailer/time bucket if exact
  interval overlap constraints are too large.
- Add conflict constraints between mutually incompatible route columns.
- Add set-partitioning constraints for existing locked shifts when freezing a
  prefix.
- Add set-covering constraints for explicit call-in orders.
- Add slack variables with huge penalties to diagnose impossible neighborhoods.
- Export LP/MPS for failing mini-masters.
- Extract duals from LP relaxation when available.
- Use dual/reduced-cost signals to guide candidate generation.
- Add column aging and pruning: keep selected, near-selected, high-pressure, and
  diverse columns; drop stale dominated columns.
- Add dominance filters:
  - same customers, later arrival, higher travel, lower delivered quantity.
  - same anchor customer/time bucket but worse cost and worse slack relief.
  - same resource block but lower coverage.
- Add route diversity constraints or penalties to avoid selecting clones.
- Add warm-start from previous selected columns.
- Add rolling overlap constraints so boundary inventory is not exploited.

### Dual pricing and route pricing

- First obtain LP relaxation duals from HiGHS if SciPy exposes them reliably.
- If SciPy wrappers do not expose enough dual data, call `highspy` directly.
- Map inventory/time/customer duals into route-stop reward.
- Build a simple reduced-cost route scorer:
  `travel + service + resource cost - inventory relief reward - order reward`.
- Use reduced-cost scorer to rank generated columns before master solve.
- Prototype resource-constrained shortest path pricing for one source/trailer
  and a small customer set.
- Start with label-setting over time buckets, not continuous minutes.
- Include trailer capacity, opening windows, and max route duration in labels.
- Add dominance rules for labels: time, load, cost, visited set approximation,
  and inventory relief.
- Compare heuristic candidate generation against pricing-DP candidates.
- Keep pricing-DP optional until it beats heuristic generation on day-6 blockers.

### ALNS / hyper-heuristic orchestration

- Keep the route-level ALNS controller in-repo.
- Add operator classes with consistent input/output stats.
- Implement destroy operators:
  - pressure-band destroy. Implemented.
  - related-customer destroy. Implemented.
  - random route-block destroy. Implemented.
  - resource-conflict destroy. Implemented; finds the V_1.11 customer-53
    driver/trailer blocker but needs paired forced repair/selection.
  - fragile-small-tank destroy.
  - layover-cluster destroy.
  - driver-resource destroy.
  - trailer-resource destroy.
  - source-congestion destroy.
  - order-gap destroy.
  - overfill destroy.
  - peak-bunching destroy.
  - weekend-smoothing destroy.
  - worst-cost route destroy.
  - low-utilization route destroy.
  - high-idle-time route destroy.
  - conflict-neighborhood destroy.
- Implement repair operators:
  - bounded CG repair.
  - forced carryover repair after resource-conflict destroy.
  - repair-pool pinning or high-pressure bonus for destroy-motivating columns.
  - pressure-peak repair.
  - nearest-neighbor chain repair.
  - regret insertion repair.
  - route-pool reuse repair.
  - mini-MIP repair.
  - quantity LP repair.
  - source/reload repair.
  - layover-specific repair.
  - multi-circuit day repair.
- Add sequence-based operator selection inspired by Kheiri:
  learn short sequences of destroy/repair/scoring moves that work on this
  instance class instead of selecting one operator independently each iteration.
- Add reinforcement-style operator weights using accepted improvement, new best,
  and failure-repair success.
- Add simulated annealing acceptance.
- Add late-acceptance hill climbing as a comparison.
- Add restart from best incumbent after N stagnant iterations.
- Add elite pool of best incumbents and path relinking between them.
- Add adaptive destroy size: small when near feasible, larger when stuck.
- Add explicit pressure-band mode for first hard failure.
- Add broad-diversification mode when duplicate column rate exceeds threshold.

### Mini-MIP / matheuristic repairs

- For a failing customer, build a time-space neighborhood:
  failing customer, nearest customers, same source-compatible customers,
  customers sharing driver/trailer conflict, and customers with nearby due times.
- Time band should start before earliest useful service and end after breach.
- Resources should include only drivers/trailers/sources active or available in
  the band.
- Columns should include incumbent routes, generated alternatives, direct
  emergency routes, and local chain routes.
- Objective should be lexicographic:
  1. remove hard violations.
  2. minimize kg-minutes below safety.
  3. minimize resource conflicts.
  4. minimize incremental cost.
- Use integer selection for routes and continuous/integer quantities as needed.
- Export infeasible neighborhoods for inspection.
- Use mini-MIP result as a route-pool seed even if it does not replace incumbent.
- Compare HiGHS MIP vs OR-Tools CP-SAT vs commercial solvers only on these small
  neighborhoods, not the full problem.

### Rolling horizon and boundary handling

- Continue using rolling horizons, but advance in 1-2 day increments rather than
  locking a full 7-day block blindly.
- Use overlap windows: optimize days 0-7, commit days 0-2, re-optimize days 2-9,
  commit days 2-4, and so on.
- Store boundary state:
  tank levels, truck/trailer locations, driver duty states, layovers, source
  availability, and in-progress routes.
- Penalize bad terminal inventory: tanks below a future-safe threshold at horizon
  end should be costly even if not yet infeasible.
- Add one-delivery lookahead for each serviced customer.
- Earliest next service should include current route remaining time plus travel
  from the relevant source/current location.
- Do not filter out customers simply because they survive the visible horizon if
  they become urgent just after the boundary.
- Add terminal value variants:
  - survive 1 extra day.
  - survive 2 extra days.
  - survive to next opening day.
  - survive to next likely route cycle.
- Validate rolling output by stitching committed blocks and running official
  checker on the stitched solution.

### Workload smoothing and peak flattening

- Track daily and hourly delivery volume.
- Track daily and hourly driver/truck/source utilization.
- Identify pressure peaks like the 280-320 hour bunching in V2.18.
- Add pre-service moves that shift load from peak days into earlier open days.
- Add weekend-aware smoothing: less work on weekend unless necessary.
- Add route selection penalty for adding volume into already-congested buckets.
- Add reward for flattening hard-pressure customers across days.
- Add constraint/penalty for maximum daily truck workload if it helps feasibility.
- Compare smoothing on:
  - total delivery volume by day.
  - number of routes by day.
  - selected route starts by day.
  - latest-departure black-line distribution from notebook diagnostics.
- Ensure smoothing does not create early overfill or waste capacity on tanks above
  75%.

### Time-space clustering and synchronization

- Build customer relatedness matrix from:
  - drive time.
  - common source compatibility.
  - overlapping opening hours.
  - similar tank size.
  - similar consumption rate.
  - similar time-to-75%.
  - similar time-to-safety.
  - historical co-selection in feasible routes.
  - call-in vs VMI type.
- Use clustering to propose synchronized service cycles.
- For nearby customers with compatible consumption, test repeated service motifs.
- For staggered but overlapping cycles, test waterfall routes where one full
  truck visits customers in a stable order.
- Use MDS map as a diagnostic only; route generation must use true matrix times.
- Add cluster reports:
  - total demand per cluster.
  - routeable demand per truckload.
  - opening-hour bottlenecks.
  - recurring cycle length.
- Do not force bad synchronization; score it against direct pressure relief.

### Multi-circuit and layover routing

- A truck can do more than one circuit per day; this must be native, not a probe.
- Generate two-circuit day templates:
  - morning short fragile route, reload, afternoon cluster route.
  - remote route, reload, local cleanup route.
  - local pre-service route before narrow-window route.
- Ensure route selection can chain circuits for the same driver/truck without
  false overlap.
- Include travel from end of previous circuit to source/start of next circuit.
- Layover routes need distinct generation, scoring, and validation.
- Add layover route families for remote high-consumption customers.
- Use red-line layover diagnostics from notebook to verify latest departure logic.
- Compare layover vs no-layover alternatives in same route pool.
- Penalize layover only through true cost/resource terms; do not exclude it if it
  resolves remote pressure.

### Customer classes requiring special treatment

Fragile small tanks:

- Customers 8, 45, 97, 129.
- Prioritize earlier in route construction when capacity is scarce.
- Generate more frequent smaller deliveries.
- Avoid consuming all capacity on a large tank before serving them.
- Monitor time below 75%, time below safety, and missed visit opportunities.

Remote / layover cluster:

- Customers 19, 60, 123, 127.
- Generate remote routes with full-route economics.
- Try synchronized cycles and layover-specific repair.
- Avoid isolated emergency trips unless they are required for feasibility.

Day-6 blockers:

- Customers 75, 60, 45, 129, 106.
- Generate direct, paired, and cluster columns around hours before minute 8820.
- Force coverage report for these customers in every 21-day iteration.
- Treat moving first breach past minute 8820 as the next milestone.

Call-in customers:

- Plot and solve separately from tank-level VMI logic.
- Ensure total aggregate consumption includes call-ins where appropriate.
- Track order due date, volume, source compatibility, route insertion options,
  and missed-order penalties.
- Add order-gap destroy/repair.

### Solver backend decisions

- Keep HiGHS as default because integration is already working.
- Use `highspy` if needed for direct LP relaxation duals, basis reuse, or faster
  repeated solves.
- Test Gurobi only after exporting the restricted master and mini-MIP cleanly.
- Test Hexaly only for local routing/sequence neighborhoods if licensing/setup is
  easy and it can model the time/resource constraints naturally.
- Do not switch solvers to compensate for weak candidate pools.
- Add backend comparison on identical route pools:
  - solve time.
  - selected objective.
  - feasibility after quantity repair.
  - reproducibility.
  - dual availability.

### Acceleration plan

- Profile before rewriting.
- First optimize Python data structures:
  - precomputed travel matrix slices.
  - cached route feasibility.
  - cached tank simulation between events.
  - vectorized pressure scoring.
  - route signature hashing.
- Add multiprocessing for independent candidate batches:
  - by pressure customer.
  - by source/trailer class.
  - by time bucket.
  - by destroy neighborhood.
- Batch generator outputs and dedupe once per batch.
- Use shared read-only problem data to avoid serialization overhead.
- Consider Numba for:
  - route feasibility loops.
  - time-window scanning.
  - tank-level simulation.
  - pressure score arrays.
- Consider C++ only for:
  - resource-constrained shortest path pricing.
  - very hot route enumeration.
  - checker-like simulation if Python remains bottleneck.
- Keep Python orchestration even if pricing kernel moves native.

### Benchmark suite

- Always run V2.18 14-day feasibility regression.
- Always run V2.18 21-day current best regression.
- Add smaller A/B smoke instances for fast tests.
- Add at least one narrow-window-heavy instance.
- Add at least one remote/layover-heavy instance.
- Add at least one call-in-heavy instance.
- Add weekend-crossing horizons: 5d, 7d, 10d, 14d, 21d.
- For every algorithm change, collect:
  - best final feasibility.
  - time to first feasible, if any.
  - first breach movement.
  - candidate uniqueness.
  - selected route mix.
  - runtime.
- Compare against current baselines, not just previous run.

### Visualization and diagnostics

- Keep notebook plots for:
  - per-customer rate/tank levels.
  - safety and max tank lines.
  - 75% line.
  - closed-hour shading.
  - latest service bars.
  - latest departure lines.
  - layover lines.
  - aggregate consumption including call-ins.
  - aggregate delivery volume over time.
  - MDS customer map with VMI/call-in/layover/source/start markers.
- Add plot for selected route starts by hour/day.
- Add plot for pressure score by customer over time.
- Add plot for route-pool coverage by customer and time bucket.
- Add plot comparing desired delivery volume vs selected delivery volume.
- Add plot for remaining slack-to-safety after selected deliveries.
- Add before/after plots for every ALNS accepted improvement.
- Export diagnostic CSVs so plots do not require re-running optimization.

### Tool cleanup

- Keep:
  - `solver/alns.py`
  - `solver/destroy.py`
  - `solver/pressure.py`
  - `solver/column_loop.py`
  - `solver/highs_selector.py`
  - `solver/targeted_rescue.py`
  - `highs_repair.py`
  - `contest.py`
  - `inventory.py`
  - `rules.py`
- Add or formalize:
  - `solver/neighborhood.py`
  - `solver/repair.py`
  - `solver/route_pool.py`
  - `solver/dual_pricing.py`
  - `solver/pricing_dp.py`
  - `solver/metrics.py`
  - `solver/experiment_log.py`
  - `solver/profiling.py`
  - `solver/mini_mip.py`
- Quarantine:
  - operation-level ALNS state code.
  - generic jitter arrival code.
  - restore-removed-operations as primary repair.
  - weak Markov-only baselines if they are not feeding a stronger repair.
- Remove only after replacement tests pass and current checkpoints are preserved.

### V2.18 21-day execution ladder

1. Add full metrics/manifest logging.
2. Add pressure-peak sampling around 75, 60, 45, 129, 106.
3. Add route-pool coverage report for those customers.
4. Add integrated quantity modes for route candidates.
5. Rerun 21-day CG from `markov_layover_columns_21d`.
6. If first breach remains 8820, run pressure-band ALNS destroy/repair.
7. If candidate uniqueness remains low, add clustering/synchronization variants.
8. If resource conflicts dominate, add mini-MIP repair for day-5 to day-7 band.
9. If quantity errors dominate, add route-level load-sharing LP/MIP.
10. If selection is unstable, add LP dual pricing and pool pruning.
11. Once 21-day feasible, reduce cost with smoothing and route improvement.
12. Freeze a new 21-day checkpoint and document exact reproduction command.

### Explicit stop/go criteria

Do not continue tuning a path if:

- duplicate column rate stays above 80% for three iterations.
- first breach minute does not move after three targeted repairs.
- selected columns do not touch the failing customers.
- quantity repair creates new overfills repeatedly.
- runtime doubles without improving any feasibility metric.
- smoothing improves workload but worsens first breach.

Continue investing in a path if:

- first breach moves later.
- hard violations drop.
- kg-minutes below safety drop.
- pressure-customer coverage improves.
- selected routes include new useful customer chains.
- route-pool uniqueness improves.
- the 14-day feasible regression remains intact.

### What success looks like

Short term:

- 21-day first breach moves past minute 8820.
- Hard violations drop below 1000.
- Candidate pool for day-6 blockers contains useful selected routes.

Medium term:

- V2.18 21-day feasible checkpoint.
- Rolling 1-2 day overlap process can extend beyond 21 days without collapsing.
- ALNS improves or repairs CG solutions without breaking known feasible prefixes.

Long term:

- Solver handles A/B/X-style instances from arbitrary starts.
- Hyper-heuristic learns operator sequences per instance class.
- Matheuristic repairs are strong enough that solver backend choice is a speed
  improvement, not a correctness dependency.

---

## Known Failure Structure

### Fragile small tanks (always fail first)

```
customers: 8, 45, 97, 129
traits: small/medium tank, low slack after day 7, some trailer restrictions
```

### Remote high-consumption cluster

```
customers: 19, 60, 123, 127
traits: far from source, large demand, layover-relevant
```

### Narrow-window / timing-sensitive

```
customers: 75, 114
```

---

## Official B-Solution Resource Patterns

We inspected the external `ROADEF2016-IRP-Results-master/*_0.xml` B solutions
against their matching B instances. Summary saved as:

`roadef_2016_data/hust_smart_results/b_official_resource_pattern_summary.csv`

The official solutions use several resource patterns that our constructors only
partially model:

| Pattern | Evidence |
|---|---|
| Loaded trailer carryover | Present in every inspected B solution. Example V2.18 has 47 positive-carryover shifts. |
| Shifts starting without source | Present in every inspected B solution. Example V2.18 has 42/73 shifts. |
| Source after customer / mid-route reload | Present in every inspected B solution. Example V2.18 has 32 shifts. |
| Multiple reloads in one shift | Present in every inspected B solution. Example V2.18 has 19 shifts; V2.22 has 77. |
| Partial source loads | Present in every inspected B solution. Example V2.18 has 17 shifts. |
| Layover-enabled routes | Present in many B solutions. Example V2.18 has 18 shifts. |
| Trailer handoff between drivers | Present in B instances with shared trailers. Example V2.18 has 36 handoff shifts, 25 with positive loaded handoff. |
| Delayed shift starts | Near-universal. Example V2.18 has 60/73 delayed starts. |

### Encoding priority from official-solution evidence

1. **Resource-state route generation**
   - Generate candidates from actual `(driver, trailer, start_load, available_time)`
     states, not only `source -> customer chain` templates.
   - Allow route templates to begin with customer deliveries if `start_load > 0`.
   - Status: first carryover candidate type added in `targeted_rescue` and
     `column_loop`. It can generate direct customer visits without a source
     operation when a trailer has positive carried load.

2. **Loaded trailer carryover and handoff**
   - Treat trailer load as a planned state variable across shifts.
   - Add candidate columns that intentionally end with positive load for future use.
   - Allow a later driver to use that loaded trailer when trailer permissions permit.

3. **Mid-route and multi-reload templates**
   - Generalize from one optional reload to repeated segments:

```text
customer* -> source(partial/full) -> customer* -> source(partial/full) -> customer*
```

4. **Partial source-load decision**
   - Stop normalizing every source visit to fill-to-capacity in all contexts.
   - Quantity repair should choose source load quantities jointly with delivery
     quantities and trailer load bounds.
   - Status: `contest-highs-repair` now includes source load operations as LP
     variables. This removed trailer load/capacity errors on the near-feasible
     V_1.7 repair without using fill-to-capacity normalization.

5. **Delayed-start sampling**
   - Sample starts inside driver windows around inventory pressure times, not just
     at window starts or latest-arrival backsolves.

6. **Layover route pricing**
   - Explicitly generate long routes that include a layover customer and exploit
     the driving reset.

7. **Driver/trailer compatibility graph**
   - Build route candidates over the bipartite permission graph, not fixed
     driver-trailer identity pairs.

These patterns are not edge cases; they are core to the published B solutions.
They should be encoded before further heavy tuning of ALNS/CG scoring.

### A-instance rerun after source-load/carryover update

| Instance | Result |
|---|---|
| V_1.2 | Valid via archived V1 seed, official ratio 0.030032 |
| V_1.7 | Source-load variable repair removes trailer-load errors; remaining issue is 17 safety-breach steps for customers 17/79 caused by timing |
| V_1.11 | Carryover generator finds a direct customer-53 route using loaded trailer state; appending it fixes inventory but conflicts with an existing driver/trailer interval. `resource_conflict_destroy` now finds and removes the blocker, but ALNS repair did not yet accept an improved solution; still 331 safety-breach steps / 0 hard violations after the smoke run. Forced test `v1_1.11_forced_carryover_minus_shift11.xml` reduced safety-breach steps to 209 but introduced 78 hard negative-tank steps, so forced repair must replace the displaced service, not only insert customer 53 |
| V_1.6 | Still structurally infeasible after source-load repair; remaining mix includes overfill and safety breaches, so needs broader route replacement |

Next implementation step: add a **forced carryover repair path** after
`resource_conflict_destroy`. The destroy side now frees the resource slot; the
repair side must preserve the specific carryover route that motivated the
destroy move, either by pinning it in the repair pool for one iteration or by
adding a temporary high-pressure covering constraint for the failing customer.
The V_1.11 forced-carryover test shows this is not sufficient alone: removing
the blocking shift also removes service for other customers, so the repair must
simultaneously re-cover the customers displaced by the removed resource-conflict
shift.

---

## Solved Sub-problems

| Sub-problem | Result |
|---|---|
| 7-day feasible prefix | `2.18_day0_7_fleet_lookahead.xml` |
| 14-day feasible (CG loop) | `2.18_checkpoint_14d_feasible_column_loop.xml` (5211.65) |
| 14-day feasible (targeted rescue) | `2.18_checkpoint_14d_feasible_layover_columns.xml` (5203.44) |

### Raw V1 A1.1 Checkpoint

Hexaly's public A-instance table is for raw V1, so A1.1 needs to be scored with
the V1 checker rather than the converted V2 instance. Current best local
checkpoint:

| Instance | Solution | Official valid | Official ratio | Cost | Delivered | Shifts | Notes |
|---|---|---:|---:|---:|---:|---:|---|
| V_1.1 raw | `v1_1.1_cached_expand3_pruned_maxfill.xml` | yes | 0.031523 | 27981.0 | 887626.0 | 50 | current fully feasible raw V1 A1.1 checkpoint |

Prior checkpoints:

| Solution | Official ratio | Cost | Delivered | Notes |
|---|---:|---:|---:|---|
| official sample | 0.036105 | 32817.0 | 908929.0 | archive feasible solution |
| `v1_1.1_sample_pruned.xml` | 0.035640 | 31217.0 | 875894.171875 | shift/source pruning |
| `v1_1.1_route_reorder_best.xml` | 0.035564 | 31150.0 | 875894.171875 | same quantities, shorter per-shift routes |
| `v1_1.1_route_reorder_maxfill_clean.xml` | 0.034518 | 30577.0 | 885829.0 | max-fill LP on fixed routes |
| `v1_1.1_maxfill_reorder2.xml` | 0.034243 | 30333.0 | 885829.0 | second reorder/max-fill checkpoint |
| `v1_1.1_cached_expand2_pruned_maxfill.xml` | 0.032041 | 28574.0 | 891784.0 | cached best-order route expansion |
| `v1_1.1_cached_merge_pruned_maxfill.xml` | 0.031673 | 28015.0 | 884497.0 | cached singleton-route merge |
| `v1_1.1_cached_expand3_pruned_maxfill.xml` | 0.031523 | 27981.0 | 887626.0 | current raw V1 A1.1 checkpoint |

Rejected/non-benchmark checkpoint:

| Solution | Raw V1 ratio | Cost | Delivered | Status | Notes |
|---|---:|---:|---:|---|---|
| `v1_1.1_rescued_full_horizon.xml` | 0.032369 | 26282.0 | 811955.0 | infeasible: 514 safety-breach errors | The misleading ~0.01618 value came from dividing this raw V1 ratio by 2 again. Do not use for Hexaly comparisons. |

Important lesson: quantity repair should not only minimize deliveries. For a
fixed route set, the benchmark objective is improved by maximizing feasible
delivered quantity because distance cost is unchanged. Use
`contest-highs-repair --quantity-objective max-delivered` for this pass.

Second lesson: memoized route ordering helps enough to make local route
structure search practical. `RouteCache.best_order(...)` was used to convert
direct or low-yield singleton routes into cached best-order chains before
max-fill repair.

### Raw V1 A-instance spot comparison

Saved as `roadef_2016_data/hust_smart_results/a_v1_hexaly_comparison.csv`.

| Instance | Current ratio | Hexaly | Gap vs Hexaly | Notes |
|---|---:|---:|---:|---|
| V_1.1 | 0.031523 | 0.027485 | +14.7% | cached route expansion/merge checkpoint |
| V_1.3 | 0.036594 | 0.013505 | +171.0% | max-fill only; route structure still poor |
| V_1.4 | 0.038188 | 0.015464 | +146.9% | max-fill only; route structure still poor |
| V_1.5 | 0.018545 | 0.011841 | +56.6% | max-fill only |
| V_1.8 | 0.015479 | 0.007756 | +99.6% | max-fill only |
| V_1.10 | 0.041155 | 0.018371 | +124.0% | max-fill only |

Current greedy baselines are still infeasible for V_1.2, V_1.6, V_1.7, V_1.9,
and V_1.11. Before trying to optimize those, produce any official-valid seed
solution.

---

## Baseline Lineage

```
2.18_day0_14_markov_probe.xml          ← CG loop baseline (359 errors, 5 hard)
  └─ column_generation_rescue (iters 0–4)
       └─ 2.18_checkpoint_14d_feasible_column_loop.xml  ✅ 14d feasible, cost 5211.65

2.18_markov_layover_columns_21d.xml    ← 21d Markov baseline (8352 errors, 2462 hard)
  └─ column_generation_rescue (5 iters, replace-from-day 3)
       └─ 2.18_column_loop_21d_from_markov.xml (4337 errors, 1296 hard)
            └─ column_generation_rescue (8 iters, replace-from-day 3)  [exhausted]
                 └─ 2.18_column_loop_21d_from_markov_v2.xml (4259 errors, 1296 hard)
```

---

## Solver Design Notes

### Why the CG loop works for 14 days

At 14 days, the pressure customer set (customers nearing breach) is small enough
that generating ~450–1400 targeted route candidates and running HiGHS selection
produces a feasible cover in ≤5 iterations. The master problem stays tractable
because the pool is bounded by `max_candidates_per_iteration`.

### Why 21 days is harder

1. **More customers to cover**: 131 VMI customers over 21 days vs 14 days
2. **Pool exhaustion**: same candidate templates regenerated after 2–3 iterations
3. **Time-window conflicts**: some customers have narrow windows in week 2 that
   the current generator's `sample_lookback_days` heuristic doesn't reach well
4. **Markov baseline quality**: the 21-day Markov probe wasn't designed to be
   a CG input — it has premature breaches that corrupt inventory projections
   used by the candidate generator

### Parameter tuning log

| Run | replace-from | pressure-cust | samples | candidates/iter | Result |
|---|---|---|---|---|---|
| 14d baseline | 0 | 12 | 6 | unlimited | ✅ feasible iter 4 |
| 21d from 14d prefix | 14 | 30 | 12 | 1500 | 15150 errors, stalled |
| 21d from markov | 3 | 12 | 8 | 800 | 4337 errors after 5 iters |
| 21d from markov | 3 | 12 | 8 | 800 | 4259 errors, pool exhausted |
| 21d from markov | 0 | 12 | 8 | 800 | *running* |
