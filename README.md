# ROADEF 2016 IRP Tools

Local tooling for ROADEF/EURO 2016 inventory routing experiments.

## Setup

```bash
uv sync
uv sync --extra milp   # for HiGHS / Gurobi solver support
```

Run tools with:

```bash
uv run roadef-tools --help
# or inside a venv:
.venv/bin/python -m roadef_tools.cli --help
```

## Architecture

```
roadef_tools/
├── cli.py                 # CLI entry point (all subcommands)
├── model.py               # Instance / Solution data model
├── xml_io.py              # ROADEF XML load / save
├── inventory.py           # Tank inventory projection & violations
├── contest.py             # Prefix scoring with feasibility tail
├── evaluate.py            # One-row evaluation for solver loops
├── rules.py               # Full rule-check (DYN, QS, TR, etc.)
├── penalties.py           # Soft penalty breakdown
├── replay.py              # Point-in-time resource & customer state
├── rolling.py             # Day-by-day cumulative delivery monitoring
├── smoothness.py          # Delivery smoothness metrics
├── highs_repair.py        # HiGHS-based quantity repair
├── improve.py             # Pruning, trimming, source removal
├── analysis.py            # Solution & inventory summaries
├── movement.py            # Distance/time matrix analysis
├── geo.py                 # MDS coordinate reconstruction
├── alns_state.py          # ALNS state scaffold
└── solver/
    ├── column_loop.py     # Column-generation rescue loop
    ├── targeted_rescue.py # Rescue candidate generation
    ├── highs_selector.py  # HiGHS shift selection (master problem)
    ├── candidate_gen.py   # Route candidate generation
    ├── rolling_cg.py      # Rolling commit-and-advance with scenario hedging
    ├── scenario.py        # Scenario forecasting and distribution tools
    ├── rolling_highs.py   # Rolling horizon HiGHS selection
    ├── cluster_greedy.py  # Cluster-aware greedy constructor
    └── greedy.py          # Basic greedy constructor
```

## Key Commands

### Week-ahead CI Rescue (Long-horizon planning under uncertainty)

Plans and optimizes routing sequences over a long-horizon lookahead (e.g. 21 or 30 days) using an external forecast confidence interval (CI) file. Commits and outputs only the near-term week (Day 0..7) to guarantee physical feasibility without tail-end overfitting.

During the solve, the progress logger displays real-time milestone tags, cost/logistic ratio KPIs, and remaining Days of Inventory (DOI) danger alerts:

```bash
uv run python -m roadef_tools.cli week-ahead-ci-rescue \
  roadef_2016_data/set_B/Instances_B_V25-11042016/V2.18.xml \
  roadef_2016_data/hust_smart_results/2.18_day0_14_markov_probe.xml \
  /private/tmp/v218_week_ci.csv \
  output.xml \
  --planning-horizon-days 30 \
  --lookahead-days 21
```

### Column-generation rescue (current best approach)

Solve → detect pressure → generate targeted route batches → add columns → repeat.

```bash
.venv/bin/python -m roadef_tools.cli column-generation-rescue \
  roadef_2016_data/set_B/Instances_B_V25-11042016/V2.18.xml \
  roadef_2016_data/hust_smart_results/2.18_day0_14_markov_probe.xml \
  output.xml \
  --start-day 0 --end-day 14 --iterations 10
```

### Evaluate a solution

```bash
.venv/bin/python -m roadef_tools.cli contest-score \
  roadef_2016_data/set_B/Instances_B_V25-11042016/V2.18.xml \
  solution.xml \
  --score-days 14 --feasibility-days 14 --ignore-tail-call-ins
```

### Tank and rule checks

```bash
.venv/bin/python -m roadef_tools.cli tank-check INSTANCE.xml SOLUTION.xml
.venv/bin/python -m roadef_tools.cli rule-check INSTANCE.xml SOLUTION.xml
```

## V2.18 Reproduction Recipe

The column-generation loop on the 14-day V2.18 case is **deterministically reproducible**:

```bash
.venv/bin/python -m roadef_tools.cli column-generation-rescue \
  roadef_2016_data/set_B/Instances_B_V25-11042016/V2.18.xml \
  roadef_2016_data/hust_smart_results/2.18_day0_14_markov_probe.xml \
  roadef_2016_data/hust_smart_results/2.18_checkpoint_14d_feasible_column_loop.xml \
  --start-day 0 --end-day 14 --iterations 10
```

Expected trace:

```
iter 0:  446 generated,  472 pool, errors 166, hard 1
iter 1:  480 generated,  913 pool, errors 169, hard 0
iter 2:  475 generated, 1231 pool, errors 169, hard 0
iter 3:  431 generated, 1329 pool, errors 169, hard 0
iter 4:  489 generated, 1402 pool, feasible, errors 0, hard 0
```

Result: **feasible, cost 5211.65**, zero tank breaches.

## Key Checkpoints

| File | Description | Cost | Feasible |
|---|---|---|---|
| `2.18_day0_14_markov_probe.xml` | CG loop baseline | 4805.57 | ❌ (5 hard) |
| `2.18_checkpoint_14d_feasible_column_loop.xml` | Best CG result | 5211.65 | ✅ |
| `2.18_checkpoint_14d_feasible_layover_columns.xml` | Best targeted-rescue | 5203.44 | ✅ |
| `2.18_day0_7_fleet_lookahead.xml` | Best 7-day prefix | — | ✅ (7d) |

## Additional Documentation

- [ROADEF_V218_NEXT_PLAN.md](ROADEF_V218_NEXT_PLAN.md) — V2.18 solver development plan and failure analysis
- [SOLVER_INTEGRATION.md](SOLVER_INTEGRATION.md) — Module integration points and MILP boundary design
- [RESEARCH.md](RESEARCH.md) — IRP patterns from analysis of competitive solutions

## Data

- `roadef_2016_data/set_A/` — Set A instances (converted to V2 format)
- `roadef_2016_data/set_B/` — Set B instances (V2.25 format)
- `roadef_2016_data/set_X/` — Set X instances
- `roadef_2016_data/hust_smart_results/` — HUST SMART reference solutions and our checkpoints
- `roadef_2016_data/checker_v2/` — Official Mono checker executable

The official checker requires [Mono](https://www.mono-project.com/). Use `--official` with the `evaluate` command.
