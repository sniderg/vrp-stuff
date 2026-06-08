#!/usr/bin/env python3
"""Train ML route priors using structured subgradient descent.

Phase 4 improvements:
  - Multi-instance training across all B instances
  - Breach-weighted loss to prioritize hard customers
  - Feature normalization (Phase 5)
  - Validation split

Usage:
  # Single instance
  python scripts/train_ml_priors.py roadef_2016_data/set_B/.../V2.18.xml solution.xml

  # Multi-instance (provide instance dir + solutions dir)
  python scripts/train_ml_priors.py --multi \
    roadef_2016_data/set_B/Instances_B_V25-11042016/ \
    scratch/batch_results/ \
    --epochs 20 --lr 0.005
"""
import sys
import argparse
from pathlib import Path
import numpy as np
import random
import os
import concurrent.futures

sys.path.append(str(Path(__file__).parent.parent))

from roadef_tools.xml_io import load_instance, load_solution
from roadef_tools.model import Instance, Solution, Shift
from roadef_tools.solver.ml_priors import MLRoutePriors, FEATURE_NAMES, get_start_inventories
from roadef_tools.solver.highs_selector import select_shifts_with_highs, SelectorConfig
from roadef_tools.solver.targeted_rescue import (
    generate_rescue_candidates,
    RescueConfig,
    _keep_shifts_started_before,
    _baseline_window_shifts,
    _dedupe_reindex,
)
from roadef_tools.inventory import tank_events

MINUTES_PER_DAY = 1440


def get_served_customers(instance: Instance, shifts: list[Shift]) -> dict[int, float]:
    """Return binary indicators of served customers from a list of shifts."""
    served = {c.index: 0.0 for c in instance.customers}
    for shift in shifts:
        for op in shift.operations:
            if op.quantity > 0.0 and op.point in served:
                served[op.point] = 1.0
    return served


def compute_breach_weights(
    instance: Instance,
    solution: Solution,
    end_day: int,
) -> dict[int, float]:
    """Compute per-customer breach severity weights.

    Phase 4: Customers with more breach steps get higher weight in the
    subgradient update, making the model care more about getting them right.
    """
    cutoff_step = min(instance.horizon, end_day * MINUTES_PER_DAY // instance.unit)
    breach_steps: dict[int, int] = {}
    total_steps = 0

    for event in tank_events(instance, solution):
        if event.step >= cutoff_step:
            continue
        if event.point not in instance.customer_by_point:
            continue
        customer = instance.customer_by_point[event.point]
        if customer.call_in:
            continue
        total_steps += 1
        deficit = max(0.0, event.safety_level - event.ending_inventory)
        if deficit > 1e-6:
            breach_steps[event.point] = breach_steps.get(event.point, 0) + 1

    if not breach_steps or total_steps == 0:
        return {}

    weights = {}
    for c in instance.customers:
        if c.call_in:
            continue
        bs = breach_steps.get(c.index, 0)
        # Customers that breach get 1 + 10 * (fraction of steps in breach)
        weights[c.index] = 1.0 + 10.0 * (bs / max(1, total_steps))

    return weights


def load_instance_pairs(instance_dir: Path, solution_dir: Path) -> list[tuple[Path, Path]]:
    """Find matching instance-solution pairs for multi-instance training."""
    pairs = []
    for inst_path in sorted(instance_dir.glob("*.xml")):
        stem = inst_path.stem
        # Look for official rescued solutions first, then baselines
        sol_candidates = [
            solution_dir / f"{stem}_official_rescued_no_prior.xml",
            solution_dir / f"{stem}_official_rescued_ml_prior.xml",
            solution_dir / f"{stem}_rescued_no_prior.xml",
            solution_dir / f"{stem}_baseline.xml",
        ]
        for sol_path in sol_candidates:
            if sol_path.exists():
                pairs.append((inst_path, sol_path))
                break
    return pairs


def prepare_training_data(
    instance: Instance,
    target_sol: Solution,
    priors: MLRoutePriors,
    start_day: int,
    end_day: int,
    inst_name: str = "",
) -> list[dict]:
    """Pre-compute features, targets, and candidate pools for each training day."""
    days = list(range(start_day, end_day))
    training_data = []

    for day in days:
        prefix = _keep_shifts_started_before(target_sol, day * MINUTES_PER_DAY)
        current_inventories = get_start_inventories(instance, prefix, day)

        start_step = min((day * MINUTES_PER_DAY) // instance.unit, instance.horizon - 1)
        features = {}
        for customer in instance.customers:
            if customer.call_in:
                continue
            curr_inv = current_inventories.get(customer.index, customer.initial_tank_quantity)
            features[customer.index] = priors.compute_features(instance, customer, curr_inv, start_step)

        target_shifts = [
            s for s in target_sol.shifts
            if day * MINUTES_PER_DAY <= s.start < (day + 1) * MINUTES_PER_DAY
        ]
        y_target = get_served_customers(instance, target_shifts)

        rescue_config = RescueConfig(start_day=day, end_day=day + 1, replace_from_day=day)
        failing_customers = [c.index for c in instance.customers if not c.call_in]
        candidates = list(generate_rescue_candidates(instance, prefix, failing_customers, config=rescue_config))
        pool = _dedupe_reindex([*target_shifts, *candidates])

        # Compute breach weights for this day's prefix
        breach_weights = compute_breach_weights(instance, prefix, day + 1)

        training_data.append({
            "day": day,
            "prefix": prefix,
            "features": features,
            "y_target": y_target,
            "pool": pool,
            "breach_weights": breach_weights,
            "instance": instance,
            "inst_name": inst_name,
        })

    return training_data


def solve_sample_worker(args_tuple):
    """Worker function to solve a single training sample MIP in parallel."""
    (
        instance,
        prefix,
        pool,
        day,
        features,
        y_target,
        breach_weights,
        weights,
        bias,
        feature_means,
        feature_stds,
        inst_name,
        time_limit,
    ) = args_tuple

    # Reconstruct priors
    priors = MLRoutePriors(
        weights=weights,
        bias=bias,
        feature_means=feature_means,
        feature_stds=feature_stds,
    )

    try:
        selected = select_shifts_with_highs(
            instance,
            prefix,
            pool,
            start_day=day,
            end_day=day + 1,
            pressure_pricing=True,
            selector_config=SelectorConfig(
                time_limit=time_limit,
                output=False,
                selector_phase="feasibility",
            ),
            ml_priors=priors,
        )
        y_pred = get_served_customers(instance, list(selected.shifts))
    except Exception as e:
        return None

    # Compute loss and gradients
    grad_W = {name: 0.0 for name in FEATURE_NAMES}
    grad_b = 0.0
    correct = 0
    total = 0

    normed_feats = {c: priors._normalize(feat) for c, feat in features.items()}
    prizes = {}
    for c, nf in normed_feats.items():
        score = sum(weights.get(name, 0.0) * nf.get(name, 0.0) for name in FEATURE_NAMES) + bias
        prizes[c] = max(0.0, score)

    loss = sum(
        (y_pred.get(c, 0.0) - y_target.get(c, 0.0)) * prizes.get(c, 0.0)
        for c in features
    )

    for c, feat in features.items():
        diff = y_pred.get(c, 0.0) - y_target.get(c, 0.0)
        if abs(diff) > 1e-5:
            w = breach_weights.get(c, 1.0) if breach_weights else 1.0
            normed = normed_feats[c]
            for name in FEATURE_NAMES:
                grad_W[name] += w * diff * normed.get(name, 0.0)
            grad_b += w * diff

        if (y_pred.get(c, 0.0) > 0.5) == (y_target.get(c, 0.0) > 0.5):
            correct += 1
        total += 1

    return {
        "loss": loss,
        "grad_W": grad_W,
        "grad_b": grad_b,
        "correct": correct,
        "total": total,
    }


def solve_val_worker(args_tuple):
    """Worker function to solve a single validation sample MIP in parallel."""
    (
        instance,
        prefix,
        pool,
        day,
        features,
        y_target,
        weights,
        bias,
        feature_means,
        feature_stds,
        time_limit,
    ) = args_tuple

    priors = MLRoutePriors(
        weights=weights,
        bias=bias,
        feature_means=feature_means,
        feature_stds=feature_stds,
    )

    try:
        selected = select_shifts_with_highs(
            instance, prefix, pool,
            start_day=day, end_day=day + 1,
            pressure_pricing=True,
            selector_config=SelectorConfig(
                time_limit=time_limit, output=False,
                selector_phase="feasibility",
            ),
            ml_priors=priors,
        )
        y_pred = get_served_customers(instance, list(selected.shifts))
    except Exception:
        return None

    correct = 0
    total = 0
    for c in features:
        if (y_pred.get(c, 0.0) > 0.5) == (y_target.get(c, 0.0) > 0.5):
            correct += 1
        total += 1

    return {
        "correct": correct,
        "total": total,
    }


def main():
    parser = argparse.ArgumentParser(description="Train ML route priors using structured subgradient descent.")
    parser.add_argument("instance_path", type=str, help="Path to ROADEF instance XML (or dir with --multi)")
    parser.add_argument("target_path", type=str, help="Path to target solution XML (or dir with --multi)")
    parser.add_argument("--multi", action="store_true", help="Multi-instance training mode")
    parser.add_argument("--epochs", type=int, default=15, help="Number of training epochs")
    parser.add_argument("--lr", type=float, default=0.005, help="Learning rate")
    parser.add_argument("--start-day", type=int, default=3, help="Start day for training windows")
    parser.add_argument("--end-day", type=int, default=10, help="End day for training windows")
    parser.add_argument("--output", type=str, default="models/ml_priors_v2.json", help="Path to save trained weights")
    parser.add_argument("--normalize", action="store_true", default=True, help="Enable feature normalization (Phase 5)")
    parser.add_argument("--holdout", type=int, default=2, help="Number of instances to hold out for validation")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--jobs", type=int, default=None, help="Number of parallel processes to use")
    parser.add_argument("--time-limit", type=float, default=3.0, help="MIP solver time limit in seconds")
    args = parser.parse_args()

    random.seed(args.seed)
    priors = MLRoutePriors()

    # --- Load data ---
    if args.multi:
        inst_dir = Path(args.instance_path)
        sol_dir = Path(args.target_path)
        pairs = load_instance_pairs(inst_dir, sol_dir)
        if not pairs:
            print(f"No instance-solution pairs found in {inst_dir} / {sol_dir}")
            return
        print(f"Found {len(pairs)} instance-solution pairs")

        # Validation split
        random.shuffle(pairs)
        if args.holdout > 0 and len(pairs) > args.holdout + 1:
            val_pairs = pairs[:args.holdout]
            train_pairs = pairs[args.holdout:]
        else:
            val_pairs = []
            train_pairs = pairs

        print(f"Train: {len(train_pairs)} instances, Validation: {len(val_pairs)} instances")
    else:
        inst_path = Path(args.instance_path)
        sol_path = Path(args.target_path)
        train_pairs = [(inst_path, sol_path)]
        val_pairs = []

    # --- Pre-process ---
    print("Pre-processing training data...")
    all_training_data = []
    all_features_flat = []  # For normalization stats

    for inst_path, sol_path in train_pairs:
        print(f"  Loading {inst_path.name} + {sol_path.name}")
        instance = load_instance(inst_path)
        target_sol = load_solution(sol_path)
        horizon_days = (instance.horizon * instance.unit + 1439) // 1440
        end_day = min(args.end_day, horizon_days)
        start_day = min(args.start_day, end_day - 1)

        data = prepare_training_data(instance, target_sol, priors, start_day, end_day, inst_path.stem)
        all_training_data.extend(data)

        # Collect features for normalization
        for d in data:
            all_features_flat.extend(d["features"].values())

    print(f"Total training samples (instance-days): {len(all_training_data)}")

    # --- Phase 5: Feature normalization ---
    if args.normalize and all_features_flat:
        print("Computing feature normalization stats...")
        priors.compute_normalization_stats(all_features_flat)
        for name in FEATURE_NAMES:
            m = priors.feature_means[name]
            s = priors.feature_stds[name]
            print(f"  {name}: mean={m:.6f}, std={s:.6f}")

    # --- Pre-process validation data ---
    val_training_data = []
    for inst_path, sol_path in val_pairs:
        print(f"  Loading validation: {inst_path.name}")
        instance = load_instance(inst_path)
        target_sol = load_solution(sol_path)
        horizon_days = (instance.horizon * instance.unit + 1439) // 1440
        end_day = min(args.end_day, horizon_days)
        start_day = min(args.start_day, end_day - 1)
        data = prepare_training_data(instance, target_sol, priors, start_day, end_day, inst_path.stem)
        val_training_data.extend(data)

    # --- Training loop ---
    print(f"\nStarting training for {args.epochs} epochs with lr={args.lr}...")
    print(f"{'Epoch':>5} | {'Train Loss':>12} | {'Train Acc':>10} | {'Val Acc':>10}")
    print("-" * 50)

    best_val_acc = 0.0
    best_weights = priors.weights.copy()
    best_bias = priors.bias

    num_workers = args.jobs if args.jobs is not None else max(1, os.cpu_count() - 1)
    print(f"Using {num_workers} parallel workers for MIP solving")

    for epoch in range(args.epochs):
        # Shuffle training data each epoch
        random.shuffle(all_training_data)

        # Separate tasks that have pools
        train_samples = [data for data in all_training_data if data["pool"]]

        epoch_loss = 0.0
        correct_predictions = 0
        total_predictions = 0

        # We keep a single ProcessPoolExecutor open for the entire epoch's training
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            batch_size = num_workers
            for i in range(0, len(train_samples), batch_size):
                mini_batch = train_samples[i:i+batch_size]

                mini_batch_tasks = []
                for data in mini_batch:
                    mini_batch_tasks.append((
                        data["instance"],
                        data["prefix"],
                        data["pool"],
                        data["day"],
                        data["features"],
                        data["y_target"],
                        data["breach_weights"],
                        priors.weights.copy(),
                        priors.bias,
                        priors.feature_means,
                        priors.feature_stds,
                        data.get("inst_name", ""),
                        args.time_limit,
                    ))

                # Solve mini-batch in parallel
                results = list(executor.map(solve_sample_worker, mini_batch_tasks))

                # Accumulate subgradients and loss for this mini-batch
                mini_batch_grad_W = {name: 0.0 for name in FEATURE_NAMES}
                mini_batch_grad_b = 0.0
                num_valid = 0

                for res in results:
                    if res is None:
                        continue
                    num_valid += 1
                    epoch_loss += res["loss"]
                    correct_predictions += res["correct"]
                    total_predictions += res["total"]

                    # Accumulate subgradients
                    for name in FEATURE_NAMES:
                        mini_batch_grad_W[name] += res["grad_W"][name]
                    mini_batch_grad_b += res["grad_b"]

                # Apply mini-batch subgradient descent update
                if num_valid > 0:
                    step_scale = 1.0 / num_valid
                    for name in FEATURE_NAMES:
                        priors.weights[name] = priors.weights.get(name, 0.0) - args.lr * mini_batch_grad_W[name] * step_scale
                    priors.bias -= args.lr * mini_batch_grad_b * step_scale

        train_acc = correct_predictions / total_predictions if total_predictions else 0.0

        # Validation accuracy
        val_acc_str = "  N/A"
        if val_training_data:
            val_correct = 0
            val_total = 0

            val_tasks = []
            for data in val_training_data:
                if not data["pool"]:
                    continue
                val_tasks.append((
                    data["instance"],
                    data["prefix"],
                    data["pool"],
                    data["day"],
                    data["features"],
                    data["y_target"],
                    priors.weights.copy(),
                    priors.bias,
                    priors.feature_means,
                    priors.feature_stds,
                    args.time_limit,
                ))

            with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
                results = executor.map(solve_val_worker, val_tasks)
                for res in results:
                    if res is None:
                        continue
                    val_correct += res["correct"]
                    val_total += res["total"]

            val_acc = val_correct / val_total if val_total else 0.0
            val_acc_str = f"{val_acc * 100:6.2f}%"

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_weights = priors.weights.copy()
                best_bias = priors.bias

        print(f"{epoch + 1:5d} | {epoch_loss:12.2f} | {train_acc * 100:8.2f}% | {val_acc_str}")
        sys.stdout.flush()  # Force flush output to log file immediately

    # Restore best weights if validation was used
    if val_training_data and best_val_acc > 0:
        print(f"\nRestoring best validation weights (acc={best_val_acc * 100:.2f}%)")
        priors.weights = best_weights
        priors.bias = best_bias

    # Save
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    priors.save(args.output)
    print(f"\nSaved trained weights to {args.output}")

    print("\nTrained weights:")
    for k, v in sorted(priors.weights.items()):
        print(f"  {k}: {v:.4f}")
    print(f"  bias: {priors.bias:.4f}")


if __name__ == "__main__":
    main()
