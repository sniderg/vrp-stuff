# Set A V1 Solution Comparison

This note records the current feasible Set A solution artifacts in
`roadef_2016_data/hust_smart_results/` and compares them with the Hexaly V1
benchmark table in `roadef_2016_data/hexaly_a_benchmarks.csv`.

Ratios in the table are V1 checker ratios from the bundled historical Set A
checker. They are useful for comparing against Hexaly's published V1 numbers,
but they should not be treated as the main solver objective for later contest
work. V1 used different route-cost weights, and those weights were later
changed for the contest. The robust/hedged solver should remain focused on the
intended modern objective while keeping this V1 comparison as historical
reporting.

| Instance | Selected solution | Official V1 | Hexaly V1 | Gap |
| --- | --- | ---: | ---: | ---: |
| V_1.1 | `v1_1.1_cached_expand3_pruned_maxfill.xml` | 0.031523 | 0.027485 | +14.7% |
| V_1.2 | `v1_1.2_improved.xml` | 0.029765 | 0.027477 | +8.3% |
| V_1.3 | `v1_1.3_improved_squeezed.xml` | 0.036594 | 0.013505 | +171.0% |
| V_1.4 | `v1_1.4_official_greedy.xml` | 0.038107 | 0.015464 | +146.4% |
| V_1.5 | `v1_1.5_improved_squeezed.xml` | 0.018545 | 0.011841 | +56.6% |
| V_1.6 | `v1_1.6_improved_squeezed.xml` | 0.023762 | 0.012880 | +84.5% |
| V_1.7 | `v1_1.7_improved_squeezed.xml` | 0.052122 | 0.012621 | +313.0% |
| V_1.8 | `v1_1.8_improved_squeezed.xml` | 0.015479 | 0.007756 | +99.6% |
| V_1.9 | `v1_1.9_rescued_feasible.xml` | 0.026426 | 0.015815 | +67.1% |
| V_1.10 | `v1_1.10_official_greedy.xml` | 0.040454 | 0.018371 | +120.2% |
| V_1.11 | `v1_1.11_rescued.xml` | 0.061461 | 0.028957 | +112.2% |

## Interpretation

- All listed solutions are intended to be fully feasible Set A solution
  artifacts. V_1.9 uses `v1_1.9_rescued_feasible.xml`; earlier V_1.9 rescued
  files should not be used for claims unless rechecked for feasibility.
- V_1.1 and V_1.2 have zero driver `TimeCost`, so their gaps are direct
  route-quality gaps under V1.
- V_1.3 through V_1.11 have nonzero driver `TimeCost`. The large V1 gaps are
  partly explained by the fact that the current solver work was not tuned to
  preserve this historical V1 weighting.
- `v1_1.4_official_greedy.xml` and `v1_1.10_official_greedy.xml` are
  deliberately V1-only artifacts produced by an official-checker-gated cleanup.
  They are kept separate so they do not steer the main objective.
- The previous V1/V2 confusion should not be preserved: do not divide or double
  these values when comparing against the Hexaly V1 table.

## Reproduction

Use the bundled V1 checker for these historical Set A files:

```bash
mono 'roadef_2016_data/checker_v1_1/Checker V1 v1.1.0.0/Challenge_Roadef_EURO_Checker_V1/bin/Release/IRP_Roadef_Challenge_Checker.exe' \
  'roadef_2016_data/set_A_v1_1/Instances V1.1/Instance_V_1.9.xml' \
  'roadef_2016_data/hust_smart_results/v1_1.9_rescued_feasible.xml'
```

For future historical V1-only experiments, use
`scripts/official_greedy_improve_a.py`; keep those outputs separate from the
main solver objective.
