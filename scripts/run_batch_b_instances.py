#!/usr/bin/env python3
import sys
import os
import time
import pandas as pd
from pathlib import Path
import xml.etree.ElementTree as ET
import concurrent.futures

# Ensure project root is in path
sys.path.append(str(Path(__file__).parent.parent))

from roadef_tools.xml_io import load_instance, load_solution, save_solution
from roadef_tools.contest import score_prefix_with_feasibility_tail
from roadef_tools.solver.cluster_greedy import construct_cluster_solution
from roadef_tools.solver.column_loop import column_generation_rescue, ColumnLoopConfig
from roadef_tools.solver.ml_priors import MLRoutePriors

DATA_DIR = Path("roadef_2016_data")
SET_B_DIR = DATA_DIR / "set_B" / "Instances_B_V25-11042016"
OUTPUT_DIR = Path("scratch/batch_results")


def evaluate_instance_worker(args_tuple):
    """Worker function to process a single ROADEF instance in parallel."""
    inst_path, priors_path_str, output_dir_str = args_tuple
    inst_name = inst_path.name
    inst_stem = inst_path.stem
    priors_path = Path(priors_path_str) if priors_path_str else None
    output_dir = Path(output_dir_str)

    # 1. Load instance
    try:
        instance = load_instance(inst_path)
    except Exception as e:
        print(f"Error loading {inst_name}: {e}")
        return None

    # Load ML priors
    ml_priors = None
    if priors_path and priors_path.exists():
        ml_priors = MLRoutePriors()
        ml_priors.load(priors_path)

    # Get horizon
    horizon_minutes = instance.horizon * instance.unit
    horizon_days = (horizon_minutes + 1439) // 1440
    W = min(14, horizon_days)

    # 2. Build baseline solution
    baseline_path = output_dir / f"{inst_stem}_baseline.xml"
    t0 = time.time()
    try:
        baseline_sol, report = construct_cluster_solution(
            instance,
            safety_buffer=0.20,
            neighborhood_size=5,
            score_cutoff_minute=None,
        )
        save_solution(baseline_sol, baseline_path)
        construct_time = time.time() - t0
    except Exception as e:
        print(f"Error constructing baseline for {inst_name}: {e}")
        return None

    # Score baseline
    try:
        score_base = score_prefix_with_feasibility_tail(
            instance,
            baseline_sol,
            score_days=W,
            feasibility_days=W,
        )
        base_lr = score_base.scored_estimated_cost / max(1.0, score_base.scored_delivered_quantity)
    except Exception as e:
        print(f"Error scoring baseline for {inst_name}: {e}")
        return None

    # 3. Column-Generation Rescue WITHOUT priors
    rescued_path = output_dir / f"{inst_stem}_rescued_no_prior.xml"
    t0 = time.time()
    try:
        config_no_prior = ColumnLoopConfig(
            start_day=0,
            end_day=W,
            replace_from_day=3,
            iterations=3,
            selector_time_limit=45.0,
        )
        rescued_sol, steps_no_prior = column_generation_rescue(
            instance,
            baseline_sol,
            config=config_no_prior,
            ml_priors=None,
        )
        save_solution(rescued_sol, rescued_path)
        rescue_time = time.time() - t0

        # Score
        score_no_prior = score_prefix_with_feasibility_tail(
            instance,
            rescued_sol,
            score_days=W,
            feasibility_days=W,
        )
        no_prior_lr = score_no_prior.scored_estimated_cost / max(1.0, score_no_prior.scored_delivered_quantity)
    except Exception as e:
        print(f"Error running rescue WITHOUT priors for {inst_name}: {e}")
        score_no_prior = None
        no_prior_lr = float('nan')
        rescue_time = float('nan')

    # 4. Column-Generation Rescue WITH ML priors
    rescued_ml_path = output_dir / f"{inst_stem}_rescued_ml_prior.xml"
    t0 = time.time()
    try:
        config_ml = ColumnLoopConfig(
            start_day=0,
            end_day=W,
            replace_from_day=3,
            iterations=3,
            selector_time_limit=45.0,
        )
        rescued_ml_sol, steps_ml = column_generation_rescue(
            instance,
            baseline_sol,
            config=config_ml,
            ml_priors=ml_priors,
        )
        save_solution(rescued_ml_sol, rescued_ml_path)
        rescue_ml_time = time.time() - t0

        # Score
        score_ml = score_prefix_with_feasibility_tail(
            instance,
            rescued_ml_sol,
            score_days=W,
            feasibility_days=W,
        )
        ml_lr = score_ml.scored_estimated_cost / max(1.0, score_ml.scored_delivered_quantity)
    except Exception as e:
        print(f"Error running rescue WITH ML priors for {inst_name}: {e}")
        score_ml = None
        ml_lr = float('nan')
        rescue_ml_time = float('nan')

    print(f"Finished {inst_stem} (Base: Feas={score_base.feasible}/Err={score_base.feasibility_errors}, NoPrior: Feas={score_no_prior.feasible if score_no_prior else False}/Err={score_no_prior.feasibility_errors if score_no_prior else -1}, MLPrior: Feas={score_ml.feasible if score_ml else False}/Err={score_ml.feasibility_errors if score_ml else -1})")

    return {
        "Instance": inst_stem,
        "HorizonDays": horizon_days,
        "EvalDays": W,

        "Base_Feasible": score_base.feasible,
        "Base_HardViol": score_base.hard_violations,
        "Base_Errors": score_base.feasibility_errors,
        "Base_Cost": score_base.scored_estimated_cost,
        "Base_Qty": score_base.scored_delivered_quantity,
        "Base_LR": base_lr,
        "Base_BuildTime": construct_time,

        "NoPrior_Feasible": score_no_prior.feasible if score_no_prior else False,
        "NoPrior_HardViol": score_no_prior.hard_violations if score_no_prior else -1,
        "NoPrior_Errors": score_no_prior.feasibility_errors if score_no_prior else -1,
        "NoPrior_Cost": score_no_prior.scored_estimated_cost if score_no_prior else 0.0,
        "NoPrior_Qty": score_no_prior.scored_delivered_quantity if score_no_prior else 0.0,
        "NoPrior_LR": no_prior_lr,
        "NoPrior_Time": rescue_time,

        "MLPrior_Feasible": score_ml.feasible if score_ml else False,
        "MLPrior_HardViol": score_ml.hard_violations if score_ml else -1,
        "MLPrior_Errors": score_ml.feasibility_errors if score_ml else -1,
        "MLPrior_Cost": score_ml.scored_estimated_cost if score_ml else 0.0,
        "MLPrior_Qty": score_ml.scored_delivered_quantity if score_ml else 0.0,
        "MLPrior_LR": ml_lr,
        "MLPrior_Time": rescue_ml_time,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    instances = sorted(SET_B_DIR.glob("*.xml"))
    print(f"Found {len(instances)} Set B instances.")

    priors_path = Path("models/ml_priors_weights.json")
    priors_path_str = str(priors_path) if priors_path.exists() else None
    if priors_path_str:
        print(f"Using ML priors from {priors_path}")
    else:
        print("Warning: models/ml_priors_weights.json not found. Using default priors in workers.")

    # Prepare evaluation tasks
    tasks = [(inst_path, priors_path_str, str(OUTPUT_DIR)) for inst_path in instances]

    results = []
    num_workers = max(1, os.cpu_count() - 1)
    print(f"Running batch evaluation in parallel using {num_workers} workers...")

    t_start = time.time()
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
        for res in executor.map(evaluate_instance_worker, tasks):
            if res is not None:
                results.append(res)
                # Save intermediate results in case of interruption
                df = pd.DataFrame(results)
                df.to_csv(OUTPUT_DIR / "batch_b_results.csv", index=False)

    df = pd.DataFrame(results)
    print("\n" + "=" * 80)
    print(f"BATCH EVALUATION COMPLETED IN {time.time() - t_start:.1f}s")
    print("=" * 80)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
