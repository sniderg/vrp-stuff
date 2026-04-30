from roadef_tools.xml_io import load_instance, load_solution
from roadef_tools.analysis import summarize_solution, customer_inventory_summary, point_visit_counts
from roadef_tools.smoothness import period_buckets, smoothness_summary
import pandas as pd

instance = load_instance("roadef_2016_data/set_B/Instances_B_V25-11042016/V2.12.xml")
solution = load_solution("roadef_2016_data/hust_smart_results/ROADEF2016-IRP-Results-master/2.12_0.xml")

shift_summaries = summarize_solution(instance, solution)
inventory_summaries = customer_inventory_summary(instance, solution)
visit_counts = point_visit_counts(solution)
buckets = period_buckets(instance, solution)
smoothness = smoothness_summary(buckets)

# Convert to DataFrames for easier analysis
df_shifts = pd.DataFrame([vars(s) for s in shift_summaries])
df_inventory = pd.DataFrame([vars(s) for s in inventory_summaries])

print(f"Total shifts: {len(df_shifts)}")
print(f"Average operations per shift: {df_shifts['operations'].mean():.2f}")
print(f"Max operations per shift: {df_shifts['operations'].max()}")
print(f"Average delivered quantity per shift: {df_shifts['delivered_quantity'].mean():.2f}")
print(f"Average shift distance: {df_shifts['distance'].mean():.2f}")

print("\nInventory Summary:")
print(f"Average deliveries per customer: {df_inventory['deliveries'].mean():.2f}")
print(f"Percentage of customers with multiple deliveries: {(df_inventory['deliveries'] > 1).mean() * 100:.2f}%")

print("\nSmoothness Summary:")
print(f"Delivered CV: {smoothness.delivered_cv:.4f}")
print(f"Shift Starts CV: {smoothness.shift_starts_cv:.4f}")
print(f"First period share: {smoothness.delivered_first_period_share:.4f}")

# Analyze operations per shift distribution
print("\nOperations per shift distribution:")
print(df_shifts['operations'].value_counts().sort_index())
