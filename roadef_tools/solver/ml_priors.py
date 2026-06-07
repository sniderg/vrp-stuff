from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass, field
import numpy as np

from ..model import Instance, Customer, Solution
from ..inventory import days_of_inventory, tank_events

FEATURE_NAMES = [
    "inv_ratio",
    "safety_ratio",
    "doi",
    "avg_demand",
    "distance_depot",
    "distance_source",
]


@dataclass
class MLRoutePriors:
    weights: dict[str, float] = field(default_factory=lambda: {
        "inv_ratio": -200.0,
        "safety_ratio": 300.0,
        "doi": -500.0,
        "avg_demand": 0.5,
        "distance_depot": -0.1,
        "distance_source": -0.5,
    })
    bias: float = 1000.0

    def save(self, path: str | Path) -> None:
        """Save weights to a JSON file."""
        data = {
            "weights": self.weights,
            "bias": self.bias,
        }
        with Path(path).open("w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str | Path) -> None:
        """Load weights from a JSON file."""
        with Path(path).open() as f:
            data = json.load(f)
        self.weights = data["weights"]
        self.bias = data["bias"]

    def compute_features(
        self,
        instance: Instance,
        customer: Customer,
        current_inventory: float,
        start_step: int,
    ) -> dict[str, float]:
        """Compute the feature vector for a customer at the start of a planning horizon."""
        inv_ratio = current_inventory / max(1.0, customer.capacity)
        safety_ratio = customer.safety_level / max(1.0, customer.capacity)
        
        # Calculate average demand
        avg_demand = (
            sum(customer.forecast) / len(customer.forecast)
            if customer.forecast
            else 0.0
        )
        
        # Distance to depot and source
        distance_depot = float(instance.time_matrix[instance.base_index][customer.index])
        distance_source = float(
            min(
                instance.time_matrix[source.index][customer.index]
                for source in instance.sources
            )
            if instance.sources
            else distance_depot
        )

        # DOI calculation
        doi = days_of_inventory(
            instance,
            customer,
            current_inventory,
            start_step=start_step,
            lead_time_minutes=distance_source,
        )

        return {
            "inv_ratio": inv_ratio,
            "safety_ratio": safety_ratio,
            "doi": doi,
            "avg_demand": avg_demand,
            "distance_depot": distance_depot,
            "distance_source": distance_source,
        }

    def predict_prizes(
        self,
        instance: Instance,
        current_inventories: dict[int, float],
        start_day: int,
    ) -> dict[int, float]:
        """Predict the priority prizes for each customer at the start of a given day."""
        start_step = min((start_day * 1440) // instance.unit, instance.horizon - 1)
        prizes = {}
        for customer in instance.customers:
            if customer.call_in:
                continue
            curr_inv = current_inventories.get(customer.index, customer.initial_tank_quantity)
            features = self.compute_features(instance, customer, curr_inv, start_step)
            
            # Linear model prediction: score = sum(w * x) + b
            score = sum(self.weights[name] * features[name] for name in FEATURE_NAMES) + self.bias
            # Prizes must be non-negative in prize-collecting formulations
            prizes[customer.index] = max(0.0, score)
        return prizes

    def update_weights(
        self,
        features_by_customer: dict[int, dict[str, float]],
        predicted_y: dict[int, float],
        target_y: dict[int, float],
        lr: float,
    ) -> None:
        """Perform a structured subgradient descent step.
        
        Target y and predicted y are binary (1 if served, 0 otherwise).
        Loss = theta * y_predicted - theta * y_target
        Gradient w.r.t theta = y_predicted - y_target
        Gradient w.r.t W = sum_c (y_predicted_c - y_target_c) * x_c
        """
        grad_W = {name: 0.0 for name in FEATURE_NAMES}
        grad_b = 0.0

        for c, feat in features_by_customer.items():
            diff = predicted_y.get(c, 0.0) - target_y.get(c, 0.0)
            if abs(diff) > 1e-5:
                for name in FEATURE_NAMES:
                    grad_W[name] += diff * feat[name]
                grad_b += diff

        # Apply gradient descent update
        for name in FEATURE_NAMES:
            self.weights[name] -= lr * grad_W[name]
        self.bias -= lr * grad_b


def get_start_inventories(
    instance: Instance,
    solution: Solution,
    start_day: int,
) -> dict[int, float]:
    """Calculate the inventory of each customer at the start of start_day."""
    if start_day == 0:
        return {c.index: c.initial_tank_quantity for c in instance.customers}
    
    # Otherwise, project solution to get tank events
    events = tank_events(instance, solution)
    step_cutoff = (start_day * 1440) // instance.unit - 1
    
    inventories = {}
    for event in events:
        if event.step == step_cutoff:
            inventories[event.point] = event.ending_inventory
            
    # Fallback to initial quantity if not found
    for c in instance.customers:
        if c.index not in inventories:
            inventories[c.index] = c.initial_tank_quantity
            
    return inventories

