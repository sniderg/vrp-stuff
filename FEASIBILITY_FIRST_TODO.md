# Feasibility-First Solver TODO

## Current Ground Truth

- Feasibility is the primary objective; ratio improvement is only useful inside the feasible region.
- V2.12 first-week has a feasible incumbent path from route priors.
- Weak-prior restarts can select many good-looking routes but still produce infeasible plans.
- Single-route swaps and small 1-for-1 / 2-for-2 neighborhoods did not improve V2.12.
- Atomic customer-bundle transactions did improve V2.12 while preserving feasibility:
  - ratio improved from `0.005347753240` to `0.005334826076`
  - errors stayed `0`
  - hard violations stayed `0`

## Next Solver Steps

1. Generate atomic bundle candidates from reference/prior routes.
   - Bundle by shared customers, route neighborhoods, resource conflicts, and time bands.
   - Keep the incumbent feasible solution as the base plan.
   - Replay a full remove/add transaction before considering it commit-ready.

2. Add an incremental feasibility scorer.
   - Current full replay costs roughly seconds per V2.12 first-week candidate.
   - Cache route metrics, affected customer inventories, and affected resource timelines.
   - Use exact full replay as the final commit gate.

3. Use Gurobi for compatible bundle selection.
   - Build a small set-packing / knapsack model over pre-screened atomic bundles.
   - Enforce driver/trailer conflict constraints.
   - Preserve or improve delivered quantity.
   - Optimize estimated ratio improvement.
   - Replay the combined transaction exactly and commit only if feasible.

4. Add move memory.
   - Store successful and failed bundle signatures.
   - Prioritize bundle sequences that historically preserve feasibility.
   - Down-rank candidates that repeatedly fail exact replay.

5. Extend the acceptance suite.
   - V2.12 first-week: keep zero errors and improve from the current feasible ratio.
   - V2.18 first-week: recover a feasible prefix before optimizing ratio.
   - Track progress against published first-week plans, but never force them as truth.

## Guardrails

- Do not commit a move that temporarily introduces errors.
- Do not let restarts discard the feasible scaffold unless the replacement is already feasible.
- Do not use best solutions as constraints; use them only as optional priors and warm-start material.
- Keep rebalancing and final clipping opt-in for rescue runs.
