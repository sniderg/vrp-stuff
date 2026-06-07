#!/usr/bin/env python3
import sys
import os
import time
import pandas as pd
from pathlib import Path
import xml.etree.ElementTree as ET

# Ensure project root is in path
sys.path.append(str(Path(__file__).parent.parent))

from roadef_tools.xml_io import load_instance, load_solution, save_solution
from roadef_tools.contest import score_prefix_with_feasibility_tail
from roadef_tools.solver.column_loop import column_generation_rescue, ColumnLoopConfig
from roadef_tools.solver.ml_priors import MLRoutePriors

DATA_DIR = Path("roadef_2016_data")
SET_B_DIR = DATA_DIR / "set_B" / "Instances_B_V25-11042016"
OFFICIAL_SOL_DIR = DATA_DIR / "hust_smart_results" / "ROADEF2016-IRP-Results-master"
OUTPUT_DIR = Path("scratch/batch_results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Mapping from set_B instance name to official baseline XML name
MAPPING = {
    "V2.12": "2.12_0.xml",
    "V2.13": "2.13_0.xml",
    "V2.14": "2.14_0.xml",
    "V2.15": "2.15_0.xml",
    "V2.16.2": "2.16_0.xml",
    "V2.17": "2.17_0.xml",
    "V2.18": "2.18_0.xml",
    "V2.19": "2.19_0.xml",
    "V2.20.2": "2.20_0.xml",
    "V2.21.2": "2.21_0.xml",
    "V2.22": "2.22_0.xml",
    "V2.23": "2.23_0.xml",
    "V2.24": "2.24_0.xml",
    "V2.25": "2.25_0.xml",
    "V2.26": "2.26_0.xml",
}

# Find B instances
instances = sorted(SET_B_DIR.glob("*.xml"))
print(f"Found {len(instances)} Set B instances.")

# Load ML priors
priors_path = Path("models/ml_priors_weights.json")
ml_priors = None
if priors_path.exists():
    ml_priors = MLRoutePriors()
    ml_priors.load(priors_path)
    print(f"Loaded ML priors from {priors_path}")
else:
    print("Warning: models/ml_priors_weights.json not found. Using default priors.")
    ml_priors = MLRoutePriors()

results = []

for inst_path in instances:
    inst_name = inst_path.name
    inst_stem = inst_path.stem
    
    if inst_stem not in MAPPING:
        print(f"Skipping {inst_name} (no official baseline mapping).")
        continue
        
    baseline_filename = MAPPING[inst_stem]
    baseline_path = OFFICIAL_SOL_DIR / baseline_filename
    
    if not baseline_path.exists():
        print(f"Skipping {inst_name} (baseline file {baseline_path} not found).")
        continue

    print(f"\n==========================================")
    print(f"PROCESSING INSTANCE: {inst_name}")
    print(f"Official Baseline Solution: {baseline_filename}")
    print(f"==========================================")
    
    # 1. Load instance and baseline
    try:
        instance = load_instance(inst_path)
        baseline_sol = load_solution(baseline_path)
    except Exception as e:
        print(f"Error loading files for {inst_name}: {e}")
        continue
        
    # Get horizon
    horizon_minutes = instance.horizon * instance.unit
    horizon_days = (horizon_minutes + 1439) // 1440
    
    # Determine evaluation window W (first 2 weeks or full horizon if less)
    W = min(14, horizon_days)
    print(f"Instance Horizon: {horizon_days} days. Evaluation Window W: {W} days.")
        
    # Score baseline
    try:
        score_base = score_prefix_with_feasibility_tail(
            instance,
            baseline_sol,
            score_days=W,
            feasibility_days=W,
        )
        base_lr = score_base.scored_estimated_cost / max(1.0, score_base.scored_delivered_quantity)
        print(f"Baseline (W={W}d): Feasible={score_base.feasible}, HardViol={score_base.hard_violations}, Errors={score_base.feasibility_errors}, Cost={score_base.scored_estimated_cost:.2f}, Delivered={score_base.scored_delivered_quantity:.1f}, LR={base_lr:.6f}")
    except Exception as e:
        print(f"Error scoring baseline for {inst_name}: {e}")
        continue
        
    # 2. Column-Generation Rescue WITHOUT priors
    rescued_path = OUTPUT_DIR / f"{inst_stem}_official_rescued_no_prior.xml"
    print(f"Running column-generation rescue WITHOUT priors...")
    t0 = time.time()
    try:
        config_no_prior = ColumnLoopConfig(
            start_day=0,
            end_day=W,
            replace_from_day=3,
            iterations=3,
            selector_time_limit=45.0,  # fast time limit for batch evaluation
        )
        rescued_sol, steps_no_prior = column_generation_rescue(
            instance,
            baseline_sol,
            config=config_no_prior,
            ml_priors=None,
        )
        save_solution(rescued_sol, rescued_path)
        rescue_time = time.time() - t0
        print(f"Rescue WITHOUT priors completed in {rescue_time:.1f}s.")
        
        # Score
        score_no_prior = score_prefix_with_feasibility_tail(
            instance,
            rescued_sol,
            score_days=W,
            feasibility_days=W,
        )
        no_prior_lr = score_no_prior.scored_estimated_cost / max(1.0, score_no_prior.scored_delivered_quantity)
        print(f"Rescued No-Prior (W={W}d): Feasible={score_no_prior.feasible}, HardViol={score_no_prior.hard_violations}, Errors={score_no_prior.feasibility_errors}, Cost={score_no_prior.scored_estimated_cost:.2f}, Delivered={score_no_prior.scored_delivered_quantity:.1f}, LR={no_prior_lr:.6f}")
    except Exception as e:
        print(f"Error running rescue WITHOUT priors for {inst_name}: {e}")
        score_no_prior = None
        no_prior_lr = float('nan')
        rescue_time = float('nan')

    # 3. Column-Generation Rescue WITH ML priors
    rescued_ml_path = OUTPUT_DIR / f"{inst_stem}_official_rescued_ml_prior.xml"
    print(f"Running column-generation rescue WITH ML priors...")
    t0 = time.time()
    try:
        config_ml = ColumnLoopConfig(
            start_day=0,
            end_day=W,
            replace_from_day=3,
            iterations=3,
            selector_time_limit=45.0,  # fast time limit for batch evaluation
        )
        rescued_ml_sol, steps_ml = column_generation_rescue(
            instance,
            baseline_sol,
            config=config_ml,
            ml_priors=ml_priors,
        )
        save_solution(rescued_ml_sol, rescued_ml_path)
        rescue_ml_time = time.time() - t0
        print(f"Rescue WITH ML priors completed in {rescue_ml_time:.1f}s.")
        
        # Score
        score_ml = score_prefix_with_feasibility_tail(
            instance,
            rescued_ml_sol,
            score_days=W,
            feasibility_days=W,
        )
        ml_lr = score_ml.scored_estimated_cost / max(1.0, score_ml.scored_delivered_quantity)
        print(f"Rescued ML-Prior (W={W}d): Feasible={score_ml.feasible}, HardViol={score_ml.hard_violations}, Errors={score_ml.feasibility_errors}, Cost={score_ml.scored_estimated_cost:.2f}, Delivered={score_ml.scored_delivered_quantity:.1f}, LR={ml_lr:.6f}")
    except Exception as e:
        print(f"Error running rescue WITH ML priors for {inst_name}: {e}")
        score_ml = None
        ml_lr = float('nan')
        rescue_ml_time = float('nan')

    results.append({
        "Instance": inst_stem,
        "HorizonDays": horizon_days,
        "EvalDays": W,
        
        "Base_Feasible": score_base.feasible,
        "Base_HardViol": score_base.hard_violations,
        "Base_Errors": score_base.feasibility_errors,
        "Base_Cost": score_base.scored_estimated_cost,
        "Base_Qty": score_base.scored_delivered_quantity,
        "Base_LR": base_lr,
        
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
    })
    
    # Save partial results after each instance in case of interruption
    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_DIR / "batch_b_official_results.csv", index=False)

# Compile summary
df = pd.DataFrame(results)
print("\n" + "="*80)
print("BATCH EVALUATION COMPLETED")
print("="*80)
print(df.to_string(index=False))
