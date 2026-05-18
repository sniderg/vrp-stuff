#!/bin/bash
INSTANCES=("1.2" "1.3" "1.6")

echo "instance,total_quantity,logistics_cost,lr,breaches,overfills" > robust_batch_results.csv

for INST in "${INSTANCES[@]}"; do
    echo "Processing Instance $INST..."
    
    INST_PATH="roadef_2016_data/set_A_v1_1/Instances V1.1/Instance_V_${INST}.xml"
    BASE_PATH="roadef_2016_data/hust_smart_results/v1_${INST}_greedy_baseline.xml"
    OUT_PATH="roadef_2016_data/hust_smart_results/v1_${INST}_robust_rolling.xml"
    
    # Run Solver (unbuffered to see progress if redirected)
    PYTHONUNBUFFERED=1 .venv/bin/python -m roadef_tools.cli robust-rolling-rescue \
      "$INST_PATH" "$BASE_PATH" "$OUT_PATH" \
      --horizon-days 30 --commit-days 7 --lookahead-days 14 \
      --cg-iterations 3 --plan-sigma 0.05 --buffer-sigma 0.10 \
      --plan-percentile 60 --buffer-percentile 75 \
      --quantity-objective max-delivered
    
    # Score
    .venv/bin/python -c "
from roadef_tools.xml_io import load_instance, load_solution
from roadef_tools.contest import score_prefix_with_feasibility_tail
instance = load_instance('$INST_PATH')
solution = load_solution('$OUT_PATH')
score = score_prefix_with_feasibility_tail(instance, solution, score_days=30, feasibility_days=30)
lr = score.scored_estimated_cost / score.scored_delivered_quantity if score.scored_delivered_quantity > 0 else 0
print(f'$INST,{score.scored_delivered_quantity:.2f},{score.scored_estimated_cost:.2f},{lr:.6f},{score.tank_safety_breach_steps},{score.tank_overfill_steps}')
" >> robust_batch_results.csv
done

cat robust_batch_results.csv
