from roadef_tools.xml_io import load_instance, load_solution

solution = load_solution("roadef_2016_data/hust_smart_results/A1-V1_polished_v5.xml")
print("Total shifts in solution:", len(solution.shifts))
for s in solution.shifts[:5]:
    print(f"Shift index {s.index}, driver {s.driver}, trailer {s.trailer}, start {s.start}")
    for op in s.operations:
        print(f"  Op: point {op.point}, arrival {op.arrival}, qty {op.quantity}")
