import subprocess
from pathlib import Path

instances = [
    ("1.12", "1.12_greedy_baseline.xml"),
    ("1.13", "1.13_greedy_baseline.xml"),
    ("1.14", "1.14_greedy_baseline.xml"),
    ("1.15", "1.15_greedy_baseline.xml"),
    ("1.16", "1.16_greedy_baseline.xml"),
    ("1.17", "1.17_greedy_baseline.xml"),
    ("1.18", "1.18_greedy_baseline.xml"),
]

for inst_num, xml_file in instances:
    inst_path = f"roadef_2016_data/set_A_v1_1/Instances V1.1/Instance_V_{inst_num}.xml"
    in_xml = f"roadef_2016_data/hust_smart_results/{xml_file}"
    out_xml = f"roadef_2016_data/hust_smart_results/v1_{inst_num}_improved.xml"
    
    print(f"=== Squeezing Instance {inst_num} ===")
    
    # Run the squeezer
    subprocess.run([
        ".venv/bin/python", "scripts/improve_a_instance_cached.py",
        inst_path, in_xml, out_xml,
        "--passes", "1", "--max-extra-customers", "1",
        "--max-route-customers", "4", "--merge-rounds", "1"
    ])
    
    # Verify the output
    print(f"=== Verifying {out_xml} ===")
    subprocess.run(
        ["mono", "roadef_2016_data/checker_v1_1/Checker V1 v1.1.0.0/Challenge_Roadef_EURO_Checker_V1/bin/Release/IRP_Roadef_Challenge_Checker.exe",
         inst_path, out_xml],
        input="\n", text=True
    )
