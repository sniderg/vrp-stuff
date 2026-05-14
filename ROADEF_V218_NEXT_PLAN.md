# ROADEF V2.18 Solver — State of the Art

## Status

| Horizon | Best Result | Cost | Feasible |
|---|---|---|---|
| **14 days** | `2.18_checkpoint_14d_feasible_column_loop.xml` | **5211.65** | ✅ |
| **14 days** | `2.18_checkpoint_14d_feasible_layover_columns.xml` | **5203.44** | ✅ |
| **21 days** | `2.18_column_loop_21d_from_markov.xml` | 5227.37 | ❌ (4337 errors, 1296 hard) |

The 14-day result is **deterministically reproducible**. See the [README](README.md) for the exact command.

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

### Failure diagnosis

The stall at ~4,300 errors / 1,296 hard across iterations is caused by **column exhaustion**:

- Pool stabilises at ~450 unique candidates
- All 273 new candidates each iteration are duplicates of existing pool entries
- `first_safety_breach_minute` stuck at 8,820 (day 6) — a narrow-window customer
  that needs a route that conflicts with driver time windows

### Next steps (priority order)

1. **`--replace-from-day 0`** — let HiGHS choose routes for the full 21-day window
   with zero frozen prefix; gives maximum flexibility (*currently running*)

2. **Richer candidate types** — the current generator only makes single-visit and
   2–3-stop chain routes. Need:
   - Multi-reload circuits (source → customers → source → customers)
   - Time-shifted variants targeting the day-6 breach customers specifically
   - Explicit route coverage for customers 8, 45, 97, 129 (fragile small tanks)
   - Routes for remote cluster 19, 60, 123, 127 (layover-relevant)

3. **Two-phase strategy** — build a good 21-day Markov baseline first (more visits,
   better coverage), then run CG on top of it. The `markov_layover_columns_21d`
   baseline is weak (first breach at day 6) because Markov doesn't anticipate
   demand accumulation.

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

## Solved Sub-problems

| Sub-problem | Result |
|---|---|
| 7-day feasible prefix | `2.18_day0_7_fleet_lookahead.xml` |
| 14-day feasible (CG loop) | `2.18_checkpoint_14d_feasible_column_loop.xml` (5211.65) |
| 14-day feasible (targeted rescue) | `2.18_checkpoint_14d_feasible_layover_columns.xml` (5203.44) |

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
