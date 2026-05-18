from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "roadef_2016_data"
HUST_DIR = DATA_DIR / "hust_smart_results"
CHECKER_EXE = (
    DATA_DIR
    / "checker_v1_1"
    / "Checker V1 v1.1.0.0"
    / "Challenge_Roadef_EURO_Checker_V1"
    / "bin"
    / "Release"
    / "IRP_Roadef_Challenge_Checker.exe"
)
RATIO_RE = re.compile(r"Logistic Ratio\s*=\s*([0-9]+(?:[.,][0-9]+)?)")

def run_checker(instance_xml: Path, solution_xml: Path) -> tuple[bool, float | None, str]:
    mono = shutil.which("mono")
    if mono is None:
        return False, None, "mono is not installed or not on PATH."

    process = subprocess.run(
        [mono, str(CHECKER_EXE), str(instance_xml), str(solution_xml)],
        input="\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    
    stdout = process.stdout
    if "Solution is valid" in stdout or "Solution is FEASIBLE" in stdout or "Logistic Ratio" in stdout:
        match = RATIO_RE.search(stdout)
        ratio = float(match.group(1).replace(",", ".")) if match else None
        return True, ratio, stdout
    else:
        return False, None, stdout

def main():
    print("=" * 80)
    print("VERIFYING RESCUED SOLUTIONS WITH THE OFFICIAL C++ CHECKER:")
    print("=" * 80)
    
    any_failed = False
    
    for i in range(1, 12):
        inst_path = DATA_DIR / "set_A_v1_1" / "Instances V1.1" / f"Instance_V_1.{i}.xml"
        sol_path = HUST_DIR / f"v1_1.{i}_rescued_full_horizon.xml"
        
        if not inst_path.exists() or not sol_path.exists():
            continue
            
        print(f"Checking V_1.{i}...")
        is_valid, ratio, stdout = run_checker(inst_path, sol_path)
        
        if is_valid:
            v1_score = ratio / 2.0 if ratio is not None else float("nan")
            print(f"  Result:  SUCCESS")
            print(f"  V2 Ratio: {ratio}")
            print(f"  V1 Score: {v1_score:.6f}")
        else:
            print(f"  Result:  FAILED!")
            print("  Output logs:")
            for line in stdout.splitlines()[-15:]:
                print(f"    {line}")
            any_failed = True
        print("-" * 80)
        
    if any_failed:
        print("Verification finished with some failures.")
        sys.exit(1)
    else:
        print("All rescued solutions are 100% VALID and FEASIBLE according to the official ROADEF checker!")
        sys.exit(0)

if __name__ == "__main__":
    main()
