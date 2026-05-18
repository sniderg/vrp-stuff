from __future__ import annotations

import time
from pathlib import Path

from roadef_tools.xml_io import load_instance, load_solution, save_solution
from roadef_tools.contest import score_prefix_with_feasibility_tail
from roadef_tools.solver.targeted_rescue import targeted_rescue, RescueConfig

# Mapping from instance to the best starting solution
BEST_SOLUTIONS = {
    1: "v1_1.1_improved.xml",
    2: "v1_1.2_improved.xml",
    3: "v1_1.3_improved_squeezed.xml",
    4: "v1_1.4_improved_squeezed.xml",
    5: "v1_1.5_improved_squeezed.xml",
    6: "v1_1.6_improved_squeezed.xml",
    7: "v1_1.7_improved_squeezed.xml",
    8: "v1_1.8_improved_squeezed.xml",
    9: "v1_1.9_repaired.xml",
    10: "v1_1.10_improved_squeezed.xml",
    11: "v1_1.11_carryover_appended_repaired.xml",
}

# Hexaly published V1 scores for comparison
HEXALY_V1 = {
    1: 0.027485,
    3: 0.013505,
    4: 0.015464,
    5: 0.011841,
    8: 0.007756,
    10: 0.018371,
}

def main():
    data_dir = Path("roadef_2016_data")
    instances_dir = data_dir / "set_A_v1_1" / "Instances V1.1"
    hust_dir = data_dir / "hust_smart_results"
    
    results = []
    
    print("=" * 90)
    print(
        f"{'Instance':<10} | {'Days':<5} | {'Base Raw V1':<15} | "
        f"{'Rescued Raw V1':<15} | {'Hexaly V1':<15} | {'Gap %':<10} | "
        f"{'Errors':<8} | {'Hard':<6} | {'Feasible':<10}"
    )
    print("-" * 90)

    for i in range(1, 12):
        inst_path = instances_dir / f"Instance_V_1.{i}.xml"
        if not inst_path.exists():
            print(f"Skipping V_1.{i} (instance not found)")
            continue
            
        sol_filename = BEST_SOLUTIONS.get(i)
        sol_path = hust_dir / sol_filename
        if not sol_path.exists():
            print(f"Skipping V_1.{i} (solution {sol_filename} not found)")
            continue

        instance = load_instance(str(inst_path))
        solution = load_solution(str(sol_path))

        days = (instance.horizon * instance.unit) // 1440

        # Dynamically customize targeted rescue windows based on horizon length
        if days <= 3:
            start_day = 0
            end_day = days
            replace_from_day = 1
        elif days <= 10:
            start_day = 1
            end_day = 7
            replace_from_day = 3
        else:
            start_day = 5
            end_day = 15
            replace_from_day = 7

        config = RescueConfig(
            start_day=start_day,
            end_day=end_day,
            replace_from_day=replace_from_day,
            max_customers=15,
            samples_per_customer=8,
            target_fill_ratio=0.50,
            max_pre_service_fill_ratio=0.80,
            sample_lookback_days=5,
            max_chain_length=3,
            nearest_chain_neighbors=5,
            variable_quantity_columns=True,
            pressure_pricing=True,
            normalize_source_loads=True
        )

        # 1. Base raw V1 score (before rescue)
        score_base = score_prefix_with_feasibility_tail(instance, solution, score_days=days, feasibility_days=days)
        base_ratio = score_base.scored_estimated_cost / max(1.0, score_base.scored_delivered_quantity)

        # 2. Targeted Rescue
        t0 = time.time()
        temp_sol, report = targeted_rescue(instance, solution, config=config)
        elapsed = time.time() - t0

        # 3. Rescued raw V1 score (after rescue)
        score_rescued = score_prefix_with_feasibility_tail(instance, temp_sol, score_days=days, feasibility_days=days)
        rescued_ratio = score_rescued.scored_estimated_cost / max(1.0, score_rescued.scored_delivered_quantity)

        hexaly_v1 = HEXALY_V1.get(i, float("nan"))
        hexaly_str = f"{hexaly_v1:.6f}" if i in HEXALY_V1 else "N/A"
        is_feasible = score_rescued.feasible
        gap = (
            100.0 * (rescued_ratio / hexaly_v1 - 1.0)
            if i in HEXALY_V1 and is_feasible
            else float("nan")
        )
        gap_str = f"{gap:.1f}" if i in HEXALY_V1 and is_feasible else "N/A"
        rescued_sol_filename = f"v1_1.{i}_rescued_full_horizon.xml"
        rescued_sol_path = hust_dir / rescued_sol_filename
        saved_path = ""
        if is_feasible:
            save_solution(temp_sol, str(rescued_sol_path))
            saved_path = str(rescued_sol_path)

        print(
            f"V_1.{i:<7} | {days:<5} | {base_ratio:<15.6f} | "
            f"{rescued_ratio:<15.6f} | {hexaly_str:<15} | {gap_str:<10} | "
            f"{score_rescued.feasibility_errors:<8} | {score_rescued.hard_violations:<6} | "
            f"{str(is_feasible):<10}"
        )
        
        results.append({
            "instance": f"V_1.{i}",
            "days": days,
            "base_ratio": base_ratio,
            "rescued_ratio": rescued_ratio,
            "hexaly_v1": hexaly_str,
            "gap_vs_hexaly_pct": gap_str,
            "feasible": is_feasible,
            "feasibility_errors": score_rescued.feasibility_errors,
            "hard_violations": score_rescued.hard_violations,
            "saved_path": saved_path,
            "elapsed": elapsed
        })

    print("=" * 90)

if __name__ == "__main__":
    main()
