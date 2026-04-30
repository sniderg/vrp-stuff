# Solver Integration Notes

This repo is now structured as a `uv` Python project with reusable modules under
`roadef_tools/` and script entry points for experiments.

## Ready Integration Points

- `roadef_tools.xml_io`
  - load/save ROADEF instance and solution XML.
  - `save_solution()` round-trips through the official checker.

- `roadef_tools.evaluate`
  - one-row evaluation for ALNS/MILP loops.
  - includes local feasibility, soft penalties, smoothness, rolling progress, and optional official checker LR.

- `roadef_tools.penalties`
  - separates hard physical constraints from soft searchable infeasibility.
  - safety breaches are integral penalties in `kg * minutes`.

- `roadef_tools.replay`
  - point-in-time status for trucks, drivers, trailers, active arcs, loads, and customer inventories.

- `roadef_tools.rolling`
  - day-by-day cumulative demand/required-delivery monitoring.
  - useful for incremental construction from day `1` to day `n`.

- `roadef_tools.geo`
  - MDS reconstruction from distance/time matrices.
  - exports point coordinates and cluster labels for geographic targeting.

- `roadef_tools.alns_state`
  - initial ALNS state object and scoped perturbation operators.
  - supports commands like "target cluster 3 between minutes 2880 and 4320".

## Current ALNS Scaffold

`run_alns_probe.py` runs against the `alns` package and supports:

```bash
uv run python run_alns_probe.py INSTANCE.xml SOLUTION.xml \
  --geo-csv points.csv \
  --target-cluster 0 \
  --start-minute 0 \
  --end-minute 1440 \
  --iterations 1 \
  --output-xml candidate.xml
```

The current destroy/repair operators are deliberately conservative:

- `remove_targeted_operations`
- `restore_removed_operations`
- `jitter_targeted_arrivals`

The repair step currently restores removed operations rather than doing true reinsertion. This is intentional scaffolding; real next steps are cheapest-insertion, regret insertion, and MILP repair over a scoped cluster/time window.

## Suggested Next Operators

- Destroy:
  - remove all deliveries in cluster/time scope.
  - remove low-margin customers in a cluster.
  - remove high-cost arcs by route segment.
  - remove over-frontloaded deliveries in early days.

- Repair:
  - greedy feasible insertion using local rule penalties.
  - regret-k insertion using distance/time deltas.
  - small MILP repair for selected customers/shifts/trailers.
  - preserve source load balance by adjusting source quantities with customer insertions.

## MILP Boundary

Use MILP for bounded subproblems, not the whole ROADEF instance initially:

- fixed day range, e.g. day 3-4.
- fixed cluster set from MDS.
- fixed candidate shifts/trailers.
- variables for customer delivery selection, quantities, and insertion positions.

After MILP repair, write XML with `save_solution()`, run `evaluate`, then optionally run the official checker.

## Important Caution

MDS coordinates are reconstructed from matrices and are not physical coordinates. They are useful for cluster targeting and neighborhood structure, but the authoritative movement model remains the directed time/distance matrices.
