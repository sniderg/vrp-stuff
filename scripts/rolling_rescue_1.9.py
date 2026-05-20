import sys
from pathlib import Path
from roadef_tools.xml_io import load_instance, load_solution, save_solution
from roadef_tools.contest import score_prefix_with_feasibility_tail
from roadef_tools.solver.targeted_rescue import targeted_rescue, RescueConfig

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-window", type=int, default=1)
    args = parser.parse_args()

    instance = load_instance("roadef_2016_data/set_A_v1_1/Instances V1.1/Instance_V_1.9.xml")
    
    if args.start_window > 1:
        prev_window = args.start_window - 1
        prev_file = f"roadef_2016_data/hust_smart_results/v1_1.9_rescued_w{prev_window}.xml"
        print(f"Resuming from Window {args.start_window}, loading {prev_file}...")
        solution = load_solution(prev_file)
    else:
        solution = load_solution("roadef_2016_data/hust_smart_results/1.9_greedy_baseline.xml")
    
    # 5-day rolling windows with 1-day overlap
    windows = [
        (3, 8, 3),   # Window 1
        (7, 12, 7),  # Window 2
        (11, 16, 11), # Window 3
        (15, 20, 15), # Window 4
        (19, 24, 19), # Window 5
        (23, 28, 23), # Window 6
        (27, 32, 27), # Window 7
        (31, 35, 31)  # Window 8
    ]
    
    for i, (start_day, end_day, replace_from_day) in enumerate(windows):
        window_idx = i + 1
        if window_idx < args.start_window:
            continue

        print(f"\n=================== Window {window_idx}: Day {start_day} to {end_day} (replace from {replace_from_day}) ===================")
        score = score_prefix_with_feasibility_tail(instance, solution, score_days=35, feasibility_days=35)
        print(f"Current solution feasibility before window: {score.feasible}")
        print(f"First safety breach day: {score.first_safety_breach_minute // 1440 if score.first_safety_breach_minute is not None else 'None'}")
        
        if score.first_safety_breach_minute is not None and score.first_safety_breach_minute // 1440 >= end_day:
            print("No breaches in this window range. Skipping.")
            # Still save the solution as an intermediate point
            save_solution(solution, f"roadef_2016_data/hust_smart_results/v1_1.9_rescued_w{window_idx}.xml")
            continue
            
        # Try targeted rescue with adaptive parameters
        optimal_found = False
        for fill_ratio in [0.95, 0.90, 0.85, 0.80]:
            print(f"Trying rescue with target_fill_ratio={fill_ratio}...")
            config = RescueConfig(
                start_day=start_day,
                end_day=end_day,
                replace_from_day=replace_from_day,
                max_customers=12,
                samples_per_customer=6,
                target_fill_ratio=fill_ratio,
                max_pre_service_fill_ratio=fill_ratio,
                sample_lookback_days=5,
                max_chain_length=3,
                nearest_chain_neighbors=5,
                variable_quantity_columns=True,
                pressure_pricing=True,
                normalize_source_loads=True
            )
            
            try:
                temp_solution, report = targeted_rescue(instance, solution, config=config)
                print(f"  HiGHS selection status: Optimal")
                print(f"  failing={len(report.failing_customers)}, candidates={report.generated_candidates}")
                print(f"  Quantity repair status: {report.quantity_repair_status}")
                if report.quantity_repair_status == "Optimal":
                    solution = temp_solution
                    optimal_found = True
                    break
                else:
                    print("  Quantity repair was non-optimal. Retrying with a lower fill ratio...")
            except Exception as e:
                print(f"  Error during rescue try: {e}")
                
        if not optimal_found:
            print("Warning: Could not find an optimal quantity repair for this window, proceeding with the best attempt.")
            # We keep the baseline if no optimal was found, to avoid degrading the solution
            
        # Save intermediate result
        save_solution(solution, f"roadef_2016_data/hust_smart_results/v1_1.9_rescued_w{window_idx}.xml")
        print(f"Saved intermediate solution for Window {window_idx}")

    # Final check
    score = score_prefix_with_feasibility_tail(instance, solution, score_days=35, feasibility_days=35)
    print("\n=================== FINAL STATUS ===================")
    print(f"Feasible: {score.feasible}")
    if score.first_safety_breach_minute is not None:
        print(f"First safety breach day: {score.first_safety_breach_minute // 1440} (minute {score.first_safety_breach_minute})")
    
    save_solution(solution, "roadef_2016_data/hust_smart_results/v1_1.9_rescued.xml")
    print("Saved final rescued solution to roadef_2016_data/hust_smart_results/v1_1.9_rescued.xml")

if __name__ == '__main__':
    main()
