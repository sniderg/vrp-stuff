# ROADEF V2.18 Next Solver Plan

## Current Baseline

Instance:

```text
roadef_2016_data/set_B/Instances_B_V25-11042016/V2.18.xml
```

Best 7-day feasible prefix:

```text
roadef_2016_data/hust_smart_results/2.18_day0_7_fleet_lookahead.xml
```

This prefix is feasible through day 7 and includes fleet-aware boundary lookahead for customers `8`, `117`, and `129`.

Best 14-day exploratory result so far:

```text
roadef_2016_data/hust_smart_results/2.18_day0_14_markov_probe.xml
```

Checker summary:

```text
feasible: False
feasibility_errors: 359
hard_violations: 5
vmi_customers_below_safety: 8
first_safety_breach_minute: 11820
```

## Important Finding

A truck can do more than one circuit inside a driver window. The current probes underuse this.

The candidate generator should produce full daily shifts such as:

```text
source -> small tank chain -> source -> remote cluster -> source -> return
```

This matters because the second-week failures combine small fragile tanks with a remote high-volume cluster.

The day-7-to-day-14 frozen-prefix strategy is too brittle. A first `candidate_gen.py` +
HiGHS selection over the whole second week produced:

```text
solution: roadef_2016_data/hust_smart_results/2.18_highs_select_candidategen.xml
generated_candidates: 481
HiGHS_status: Optimal
feasible: False
feasibility_errors: 933
hard_violations: 141
vmi_customers_below_safety: 16
first_safety_breach_minute: 11880
```

That is worse than the Markov probe. The main reason is not that HiGHS is useless; it is
that selecting a whole week from a frozen inventory state with daily inventory
checkpoints loses too much timing detail. The next solver should move forward one or
two days at a time, lock the accepted slice, regenerate inventory state, and then plan
the next slice.

## Current Failure Structure

Small / fragile tanks:

```text
8, 45, 97, 129
```

Common traits:

```text
small or medium tank
low slack after day 7
some trailer restrictions
often easy to overrun if delayed
```

Remote high-consumption cluster:

```text
19, 60, 123, 127
```

Common traits:

```text
far from source/base
very close to each other
large demand
layover-relevant customers present
```

Other narrow-window / timing-sensitive customers seen in earlier failures:

```text
75, 114
```

## Next Implementation Plan

1. Keep `2.18_day0_7_fleet_lookahead.xml` as the best known feasible day-0-to-day-7
   reference, but do not treat day 7 as the only planning restart point.

2. Restart from day 0 with a receding horizon:

```text
plan days 0-2
score/check days 0-2 plus short tail
lock accepted shifts through day 1 or day 2
recompute driver, trailer, and inventory state
generate fresh candidates for the next 1-2 days
repeat until day 14
```

The lock size can be shorter than the lookahead size:

```text
lookahead: 2 days
commit: 1 day
```

This lets the solver see one delivery ahead while still keeping options open.

3. Generate multi-circuit full-shift candidates for each rolling window.

4. Inside each candidate shift, prefer circuits in this order:

```text
fragile small tanks
narrow-window customers
remote high-volume cluster
large flexible tanks
```

5. Generate route variants:

```text
small-tank circuit + reload + remote-cluster circuit
remote-cluster circuit + reload + small-tank circuit
Markov local chains
juggler staggered chains
peak-smoothing routes
single urgent rescue routes
```

6. Use HiGHS as a route selector over generated candidate shifts, but only within the
   rolling window.

Start relaxed:

```text
maximize covered safety obligations
penalize uncovered customers heavily
penalize daily overload
avoid driver/trailer overlaps
```

Then tighten:

```text
driver rest constraints
trailer overlap constraints
delivery-before-breach constraints
daily smoothing constraints
```

7. Validate each selected schedule with:

```text
.venv/bin/python -m roadef_tools.cli contest-score \
  roadef_2016_data/set_B/Instances_B_V25-11042016/V2.18.xml \
  <solution.xml> \
  --score-days 14 \
  --feasibility-days 14 \
  --ignore-tail-call-ins
```

For rolling runs, also score after each commit:

```text
--score-days <committed_day>
--feasibility-days <committed_day + 1 or 2>
```

The short feasibility tail should catch plans that survive the committed day only by
creating an impossible next-day cliff.

## Rolling Horizon Design

At each iteration:

1. Truncate/lock the current accepted solution at `commit_day * 1440`.

2. Derive true state from the locked prefix:

```text
driver available time
next driver time window
trailer available time
trailer remaining quantity
customer scheduled deliveries
customer inventory projection
```

3. Screen candidate customers using a small time buffer:

```text
must consider: breach or safety-critical inside lookahead + buffer
should consider: below 75% tank level inside lookahead
optional: route-neighbor customers that can be synchronized cheaply
```

4. For each customer, generate at least one delivery-ahead option:

```text
earliest service time = max(
    first time tank <= 75% capacity,
    driver/trailer availability + source lead + route lead
)

latest service time = latest legal arrival before safety breach
```

5. For candidate generation, account for trucks already mid-route:

```text
minimum service time for a future customer should include:
remaining time on current route
time to reach a compatible source or current loaded-trailer state
source-to-customer travel time
```

6. Select shifts/routes with HiGHS.

7. Check the actual selected XML with the contest feasibility code, not just the MILP
   row status.

8. Commit only the first day if the second day is mainly lookahead. Commit two days only
   when the tail check remains clean and there is no bunching cliff immediately after.

## Immediate Code Changes

1. Add a rolling command, probably:

```text
.venv/bin/python -m roadef_tools.cli rolling-highs-select \
  <instance.xml> \
  <output.xml> \
  --start-day 0 \
  --end-day 14 \
  --lookahead-days 2 \
  --commit-days 1
```

2. Reuse `generate_shift_candidates`, but make its window explicit:

```text
start_day=current_day
end_day=current_day + lookahead_days
```

3. Update the HiGHS selector constraints from daily checkpoints to finer checkpoints:

```text
customer safety breach step
latest legal service step
end of each driver window
every 6h or 12h fallback checkpoint
```

Daily inventory constraints are too coarse for V2.18.

4. Keep selected route intervals, not just day buckets, for resource constraints.
Current day-level driver/trailer constraints are acceptable for early probing but are
too coarse for multi-circuit/multi-shift days.

5. Add an explicit peak-smoothing term per rolling window:

```text
penalize delivery volume bunched into 280-320h
reward filling underused weekday capacity
discount weekend capacity
```

## Scoring Ideas To Keep

Use 75 percent tank level as the earliest economic service line:

```text
arrival >= first time tank <= 75% capacity
```

Exceptions:

```text
fleet-aware boundary lookahead customers may be pre-serviced before 75%
```

Prioritize:

```text
low days-above-safety
small tank capacity
restricted compatible trailers
narrow opening windows
close route neighbors
daily smoothing underload
```

Avoid:

```text
1-unit repeated top-ups
serving large flexible tanks before fragile small tanks
leaving 280-320h demand bunched together
single-circuit-only route candidates
```

## First Target

Beat the current best Markov probe:

```text
feasibility_errors < 359
hard_violations <= 5
vmi_customers_below_safety < 8
```

Then push toward full 14-day feasibility.
