import subprocess

instances = [
    ("1.3", "v1_1.3_cached_improved.xml"),
    ("1.4", "v1_1.4_cached_improved.xml"),
    ("1.5", "v1_1.5_cached_improved.xml"),
    ("1.8", "v1_1.8_cached_improved.xml"),
    ("1.10", "v1_1.10_cached_improved.xml"),
]

for inst_num, xml_file in instances:
    inst_path = f"roadef_2016_data/set_A_v1_1/Instances V1.1/Instance_V_{inst_num}.xml"
    in_xml = f"roadef_2016_data/hust_smart_results/{xml_file}"
    out_xml = f"roadef_2016_data/hust_smart_results/v1_{inst_num}_improved_squeezed.xml"
    
    print(f"=== Squeezing Instance {inst_num} ===")
    subprocess.run([
        ".venv/bin/python", "scripts/improve_a_instance_cached.py",
        inst_path, in_xml, out_xml,
        "--passes", "1", "--max-extra-customers", "1",
        "--max-route-customers", "4", "--merge-rounds", "1"
    ])
    
    # Check if the output file is valid and compare scores
    print(f"=== Verifying {out_xml} ===")
    subprocess.run(
        ["mono", "roadef_2016_data/checker_v1_1/Checker V1 v1.1.0.0/Challenge_Roadef_EURO_Checker_V1/bin/Release/IRP_Roadef_Challenge_Checker.exe",
         inst_path, out_xml],
        input="\n", text=True
    )
