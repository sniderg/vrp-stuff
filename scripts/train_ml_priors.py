#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
import numpy as np

# Ensure project root is in path
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

MINUTES_PER_DAY = 1440


def get_served_customers(instance: Instance, shifts: list[Shift]) -> dict[int, float]:
    """Return binary indicators of served customers from a list of shifts."""
    served = {c.index: 0.0 for c in instance.customers}
    for shift in shifts:
        for op in shift.operations:
            if op.quantity > 0.0 and op.point in served:
                served[op.point] = 1.0
    return served


def main():
    parser = argparse.ArgumentParser(description="Train ML route priors using structured subgradient descent.")
    parser.add_argument("instance_path", type=str, help="Path to ROADEF instance XML file")
    parser.add_argument("target_path", type=str, help="Path to target/best solution XML file")
    parser.add_argument("--epochs", type=int, default=10, help="Number of training epochs")
    parser.add_argument("--lr", type=float, default=0.01, help="Learning rate")
    parser.add_argument("--start-day", type=int, default=3, help="Start day for training windows")
    parser.add_argument("--end-day", type=int, default=10, help="End day for training windows")
    parser.add_argument("--output", type=str, default="models/ml_priors_weights.json", help="Path to save trained weights")
    args = parser.parse_args()

    print(f"Loading instance: {args.instance_path}")
    instance = load_instance(args.instance_path)
    print(f"Loading target solution: {args.target_path}")
    target_sol = load_solution(args.target_path)

    # Initialize priors
    priors = MLRoutePriors()
    print("Initial weights:")
    for k, v in priors.weights.items():
        print(f"  {k}: {v:.4f}")
    print(f"  bias: {priors.bias:.4f}")

    # Prepare training days
    days = list(range(args.start_day, args.end_day))
    
    # Store pools and targets to avoid rebuilding them every epoch
    training_data = []
    print("Pre-processing training features and candidate pools...")
    for day in days:
        # 1. Prefix is target solution before day d
        prefix = _keep_shifts_started_before(target_sol, day * MINUTES_PER_DAY)
        
        # 2. Extract starting inventories at day d
        current_inventories = get_start_inventories(instance, prefix, day)
        
        # 3. Compute features for all customers at day d
        start_step = min((day * MINUTES_PER_DAY) // instance.unit, instance.horizon - 1)
        features = {}
        for customer in instance.customers:
            if customer.call_in:
                continue
            curr_inv = current_inventories.get(customer.index, customer.initial_tank_quantity)
            features[customer.index] = priors.compute_features(instance, customer, curr_inv, start_step)
            
        # 4. Target shifts on day d
        target_shifts = [
            s for s in target_sol.shifts 
            if day * MINUTES_PER_DAY <= s.start < (day + 1) * MINUTES_PER_DAY
        ]
        y_target = get_served_customers(instance, target_shifts)

        # 5. Build candidate pool for day d
        # We generate rescue candidates and combine them with the target shifts
        rescue_config = RescueConfig(start_day=day, end_day=day + 1, replace_from_day=day)
        failing_customers = [c.index for c in instance.customers if not c.call_in]
        candidates = list(generate_rescue_candidates(instance, prefix, failing_customers, config=rescue_config))
        
        pool = _dedupe_reindex([*target_shifts, *candidates])
        
        training_data.append({
            "day": day,
            "prefix": prefix,
            "features": features,
            "y_target": y_target,
            "pool": pool,
        })
    
    print(f"Starting training for {args.epochs} epochs with lr={args.lr}...")
    for epoch in range(args.epochs):
        epoch_loss = 0.0
        correct_predictions = 0
        total_predictions = 0
        
        for data in training_data:
            day = data["day"]
            prefix = data["prefix"]
            features = data["features"]
            y_target = data["y_target"]
            pool = data["pool"]

            # Predict prizes under current weights
            prizes = {}
            for c, feat in features.items():
                score = sum(priors.weights[name] * feat[name] for name in FEATURE_NAMES) + priors.bias
                prizes[c] = max(0.0, score)

            # Temporarily apply prizes to a mock MLRoutePriors
            epoch_priors = MLRoutePriors(weights=priors.weights.copy(), bias=priors.bias)
            
            # Solve selector to get predicted served status
            selected = select_shifts_with_highs(
                instance,
                prefix,
                pool,
                start_day=day,
                end_day=day + 1,
                pressure_pricing=True,
                selector_config=SelectorConfig(
                    time_limit=10.0,  # fast time limit for training
                    output=False,
                    selector_phase="feasibility",
                ),
                ml_priors=epoch_priors,
            )
            
            y_pred = get_served_customers(instance, list(selected.shifts))
            
            # Compute loss: sum(y_pred * prize - y_target * prize)
            loss = sum((y_pred.get(c, 0.0) - y_target.get(c, 0.0)) * prizes.get(c, 0.0) for c in features)
            epoch_loss += loss

            # Update weights using subgradient step
            priors.update_weights(features, y_pred, y_target, args.lr)

            # Compute classification accuracy
            for c in features:
                if (y_pred.get(c, 0.0) > 0.5) == (y_target.get(c, 0.0) > 0.5):
                    correct_predictions += 1
                total_predictions += 1

        accuracy = correct_predictions / total_predictions if total_predictions else 0.0
        print(f"Epoch {epoch + 1:2d}/{args.epochs:2d} | Loss: {epoch_loss:10.2f} | Served-Accuracy: {accuracy * 100:6.2f}%")

    print(f"Saving trained weights to {args.output}")
    priors.save(args.output)

    print("Trained weights:")
    for k, v in priors.weights.items():
        print(f"  {k}: {v:.4f}")
    print(f"  bias: {priors.bias:.4f}")


if __name__ == "__main__":
    main()
