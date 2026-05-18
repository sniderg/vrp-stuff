import sys
from roadef_tools.xml_io import load_instance, load_solution
from roadef_tools.rules import derive_solution

def main():
    instance = load_instance("roadef_2016_data/set_A/Instance_V_1.1_ConvertedTo_V2.xml")
    solution = load_solution("roadef_2016_data/hust_smart_results/A1-V1_polished_v5.xml")
    
    # Calculate total demand / deliveries
    total_qty = 0
    total_travel_time = 0
    total_setup_time = 0
    
    derived = derive_solution(instance, solution)
    for ds in derived:
        if not ds.operations:
            continue
        # sum of travel times for each operation
        shift_travel = sum(op.travel_time_from_previous for op in ds.operations)
        # plus travel time from last customer to base
        last_op_point = ds.operations[-1].point
        return_time = instance.time_matrix[last_op_point][instance.base_index]
        shift_travel += return_time
        
        total_travel_time += shift_travel
        
        for op in ds.shift.operations:
            if op.quantity > 0:
                total_qty += op.quantity
                if op.point in instance.customer_by_point:
                    total_setup_time += instance.customer_by_point[op.point].setup_time
                
    print(f"--- Instance & Solution Metrics (A1-V1) ---")
    print(f"Total delivered quantity: {total_qty:,.2f} kg")
    print(f"Total travel (driving) time: {total_travel_time:,.2f} minutes")
    print(f"Total setup time: {total_setup_time:,.2f} minutes")
    
    # Trailer Capacity Limits
    max_trailer_cap = max(t.capacity for t in instance.trailers)
    min_loads = total_qty / max_trailer_cap
    print(f"Max trailer capacity: {max_trailer_cap:,.2f} kg")
    print(f"Absolute minimum trailer reloads needed: {min_loads:.2f}")
    
    # Max Driving Duration limits
    max_drive = max(d.max_driving_duration for d in instance.drivers)
    min_shifts_by_drive = total_travel_time / max_drive
    print(f"Max driver driving duration: {max_drive} minutes")
    print(f"Absolute minimum shifts based on driving time: {min_shifts_by_drive:.2f}")
    
    # Shift duration limits (max_driving_duration + setup_time + reloads etc)
    # Average travel time per shift in current solution
    avg_travel_per_shift = total_travel_time / len(solution.shifts)
    print(f"Current shifts: {len(solution.shifts)}")
    print(f"Average travel time per shift: {avg_travel_per_shift:.2f} minutes")

if __name__ == '__main__':
    main()
