# Solver Integration Notes

## Current Architecture

The production solver pipeline is a **batched column-generation rescue loop**
implemented in `roadef_tools/solver/`. ALNS scaffolding (`run_alns_probe.py`,
`roadef_tools/alns_state.py`) is superseded by this approach.

### Module Map

| Module | Role |
|---|---|
| `solver/column_loop.py` | Outer CG rescue loop driver |
| `solver/targeted_rescue.py` | Single-iteration rescue: pressure detection, candidate generation, HiGHS selection |
| `solver/highs_selector.py` | HiGHS master problem: shift selection with pressure pricing and order-coverage constraints |
| `solver/candidate_gen.py` | Route candidate generation with diverse top-K filtering |
| `solver/rolling_highs.py` | Rolling horizon HiGHS selection (experimental) |
| `solver/cluster_greedy.py` | Cluster-aware greedy constructor (baseline generation) |
| `solver/greedy.py` | Basic greedy constructor |
| `roadef_tools/highs_repair.py` | HiGHS-based quantity repair after shift selection |

### Integration Points

**Load/save:**
```python
from roadef_tools.xml_io import load_instance, load_solution, save_solution
instance = load_instance("V2.18.xml")
solution = load_solution(instance, "baseline.xml")
save_solution(instance, solution, "output.xml")
```

**Evaluate:**
```python
from roadef_tools.contest import score_prefix_with_feasibility_tail
score = score_prefix_with_feasibility_tail(instance, solution, score_days=14, feasibility_days=14)
# score.feasible, score.feasibility_errors, score.hard_violations, score.first_safety_breach_minute
```

**Column-generation loop:**
```python
from roadef_tools.solver.column_loop import column_generation_rescue, ColumnLoopConfig
config = ColumnLoopConfig(
    start_day=0, end_day=14, replace_from_day=0,
    iterations=10, max_pressure_customers=12,
    samples_per_customer=6, max_chain_length=3,
)
best_solution, steps = column_generation_rescue(instance, baseline, config=config)
```

**Single targeted rescue pass:**
```python
from roadef_tools.solver.targeted_rescue import targeted_rescue, RescueConfig
config = RescueConfig(start_day=0, end_day=14, replace_from_day=7)
rescued, report = targeted_rescue(instance, solution, config=config)
```

---

## CLI Commands

### Primary workflow

```bash
# Score a solution (14-day window, ignore tail after day 14)
.venv/bin/python -m roadef_tools.cli contest-score \
  INSTANCE.xml SOLUTION.xml \
  --score-days 14 --feasibility-days 14 --ignore-tail-call-ins

# Run column-generation rescue loop
.venv/bin/python -m roadef_tools.cli column-generation-rescue \
  INSTANCE.xml BASELINE.xml OUTPUT.xml \
  --start-day 0 --end-day 14 --iterations 10

# Run single targeted rescue pass
.venv/bin/python -m roadef_tools.cli targeted-rescue \
  INSTANCE.xml BASELINE.xml OUTPUT.xml \
  --start-day 0 --end-day 14 --replace-from-day 7

# Tank and rule diagnostics
.venv/bin/python -m roadef_tools.cli tank-check INSTANCE.xml SOLUTION.xml --limit 10
.venv/bin/python -m roadef_tools.cli rule-check INSTANCE.xml SOLUTION.xml --limit 10

# DOI (days-of-inventory) urgency report
.venv/bin/python -m roadef_tools.cli doi-report INSTANCE.xml SOLUTION.xml
```

---

## HiGHS Boundary

The HiGHS master problem in `highs_selector.py` selects a subset of candidate
shifts to minimise a weighted penalty objective subject to:

- **Driver non-overlap**: no two selected shifts for the same driver overlap in time
- **Trailer non-overlap**: no two selected shifts for the same trailer overlap in time
- **Order coverage**: each customer order in the window must be covered at least once
- **Pressure pricing**: safety-critical customers get higher reward for being served

HiGHS is called once per CG iteration. Pool size is capped by
`max_candidates_per_iteration` to keep the master problem tractable. Typical
solve time: 5–30 seconds at pool sizes of 400–1500.

**Important:** HiGHS selects *routes*; quantities are fixed up afterward by
`highs_repair.py`, which re-solves a small QP to maximise delivered quantity
subject to tank capacity and safety constraints.

---

## MILP Boundary

Gurobi (`gurobipy`) is listed as an optional dependency but is not used in the
current pipeline. HiGHS (`highspy`) is the active solver for both shift selection
and quantity repair.

---

## Inventory Model

Safety breaches are penalised as `kg × minutes` (deficit × `instance.unit`).
This is the contest scoring metric and drives both pressure detection and the
HiGHS objective. See `roadef_tools/penalties.py` and `roadef_tools/inventory.py`.

MDS coordinates (from `roadef_tools/geo.py`) are reconstructed from distance/time
matrices and are used for cluster targeting and neighborhood structure in candidate
generation. They are **not** physical coordinates — all routing uses the directed
time/distance matrices.
