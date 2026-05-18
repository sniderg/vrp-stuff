import re
with open('roadef_tools/solver/alns.py', 'r') as f:
    content = f.read()

# Make it print the cost and save best intermediate
new_content = content.replace(
    'print(f"DEBUG: Iteration {iteration}: Candidate score: feasible={candidate_score.feasible}, hard={candidate_score.hard_violations}, errors={candidate_score.feasibility_errors}")',
    'print(f"DEBUG: Iteration {iteration}: Candidate score: feasible={candidate_score.feasible}, hard={candidate_score.hard_violations}, errors={candidate_score.feasibility_errors}, cost={candidate_score.scored_estimated_cost}")'
)

with open('roadef_tools/solver/alns.py', 'w') as f:
    f.write(new_content)
