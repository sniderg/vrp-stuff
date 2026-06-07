# Stochastic IRP TODO

Goal: use hedged/statistical forecasts without losing deterministic feasibility.

## Stage 1: Incumbent-Preserving Acceptance Gate

- [x] Evaluate every rolling candidate against the true instance through the
      commit boundary.
- [x] Evaluate every rolling candidate against all generated scenarios through
      the commit boundary.
- [x] If the incumbent prefix is feasible, reject any candidate with an
      infeasible true prefix.
- [x] If scenario validation fails, retry with tighter hedge parameters; if all
      retries fail, keep the incumbent prefix.
- [x] Rank accepted candidates by true feasibility, scenario failures, hard
      violations, feasibility errors, then cost.

## Stage 2: Explicit Risk/Score Model

- [x] Add a named window-evaluation object with true feasibility, scenario
      failure count/rate, cost, and rejection reason.
- [x] Expose accepted/rejected status in rolling diagnostics.
- [x] Stop using anonymous tuples for stochastic attempt ranking.

## Stage 3: Forecast Distribution Interface

- [x] Add a forecast distribution container for deterministic paths, sampled
      paths, and quantile paths.
- [x] Keep synthetic Monte Carlo as one producer of that interface.
- [x] Add an external forecast-input loader for TabPFN outputs without making
      TabPFN a dependency.
- [x] Build hedged instances from quantile paths when available, falling back to
      percentiles over samples.

## Stage 4: CLI Modes

- [x] Add explicit `deterministic`, `hedged`, and `robust` rolling modes.
- [x] In deterministic mode, use true/p50 forecasts and no stochastic hedge.
- [x] In hedged mode, use percentile hedging plus scenario validation.
- [x] In robust mode, use stricter percentile/capacity-buffer defaults and
      stricter scenario acceptance.

## Stage 5: Regression Tests

- [x] A1.1 first 7 days remains feasible in deterministic mode.
- [x] A1.1 first 7 days remains feasible in hedged mode.
- [x] Infeasible candidates are rejected, not written as benchmark solutions.
- [x] Existing A-instance ratio conversion tests continue to pass.

## Stage 6: Backtesting and Calibration Loop

- [x] Convert quantile-only forecasts into fixed stress scenarios for
      validation and backtesting.
- [x] Add a scenario backtest harness with feasibility, cost, stockout/safety,
      and overfill metrics.
- [x] Expose a CLI backtest command without adding an optimizer dependency.
- [x] Add historical realized-consumption ingestion for calibration reports.
- [x] Add policy sweep support over robust solver parameters.
