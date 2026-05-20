"""Historical Set-A V1 checker wrapper.

This script is intentionally separate from the main solver objective. It gates
candidate edits with the bundled V1 checker for comparisons against historical
Set-A outputs, where V1's weighting differs from the later contest objective.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from roadef_tools.contest import score_prefix_with_feasibility_tail
from roadef_tools.improve import (
    move_single_customer_shifts,
    prune_redundant_shifts,
    remove_redundant_source_visits,
)
from roadef_tools.xml_io import load_instance, load_solution, save_solution


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "roadef_2016_data"
INSTANCES_DIR = DATA_DIR / "set_A_v1_1" / "Instances V1.1"
RESULTS_DIR = DATA_DIR / "hust_smart_results"
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

BEST_SOLUTIONS = {
    1: "v1_1.1_improved.xml",
    2: "v1_1.2_improved.xml",
    3: "v1_1.3_improved_squeezed.xml",
    4: "v1_1.4_improved_squeezed.xml",
    5: "v1_1.5_improved_squeezed.xml",
    6: "v1_1.6_improved_squeezed.xml",
    7: "v1_1.7_improved_squeezed.xml",
    8: "v1_1.8_improved_squeezed.xml",
    9: "v1_1.9_rescued_feasible.xml",
    10: "v1_1.10_improved_squeezed.xml",
    11: "v1_1.11_rescued.xml",
}


def run_official_checker(instance_xml: Path, solution_xml: Path) -> tuple[bool, float | None]:
    mono = shutil.which("mono")
    if mono is None:
        raise SystemExit("`mono` is required for official scoring.")
    process = subprocess.run(
        [mono, str(CHECKER_EXE), str(instance_xml), str(solution_xml)],
        input="\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    valid = "THIS OUTPUT IS VALID" in process.stdout
    match = RATIO_RE.search(process.stdout)
    ratio = float(match.group(1).replace(",", ".")) if match else None
    return valid, ratio


def instance_days(instance) -> int:
    return (instance.horizon * instance.unit + 1439) // 1440


def improve_instance(inst_num: int, *, passes: int, output_suffix: str) -> None:
    instance_xml = INSTANCES_DIR / f"Instance_V_1.{inst_num}.xml"
    input_xml = RESULTS_DIR / BEST_SOLUTIONS[inst_num]
    output_xml = RESULTS_DIR / f"v1_1.{inst_num}_{output_suffix}.xml"

    instance = load_instance(instance_xml)
    current = load_solution(input_xml)
    days = instance_days(instance)

    with tempfile.TemporaryDirectory(prefix=f"official_a_{inst_num}_") as temp_name:
        temp_dir = Path(temp_name)
        current_xml = temp_dir / "current.xml"
        save_solution(current, current_xml)
        valid, best_ratio = run_official_checker(instance_xml, current_xml)
        if not valid or best_ratio is None:
            print(f"V_1.{inst_num},start_invalid,{input_xml}")
            return

        print(f"V_1.{inst_num},start,{best_ratio:.12f},{input_xml.name}")
        accepted = 0
        for pass_index in range(1, passes + 1):
            candidates = []
            pruned, report = prune_redundant_shifts(
                instance,
                current,
                score_days=days,
                feasibility_days=days,
                max_passes=1,
            )
            candidates.append((f"prune:{report.removed_shifts}", pruned))
            candidates.append((
                "remove_sources",
                remove_redundant_source_visits(
                    instance,
                    current,
                    score_days=days,
                    feasibility_days=days,
                    max_rounds=3,
                ),
            ))
            candidates.append((
                "move_single",
                move_single_customer_shifts(
                    instance,
                    current,
                    score_days=days,
                    feasibility_days=days,
                    max_moves=2,
                ),
            ))

            changed = False
            for label, candidate in candidates:
                score = score_prefix_with_feasibility_tail(
                    instance,
                    candidate,
                    score_days=days,
                    feasibility_days=days,
                )
                if not score.feasible:
                    continue
                candidate_xml = temp_dir / f"candidate_{pass_index}_{accepted}.xml"
                save_solution(candidate, candidate_xml)
                valid, ratio = run_official_checker(instance_xml, candidate_xml)
                if not valid or ratio is None or ratio >= best_ratio - 1e-9:
                    continue
                print(f"V_1.{inst_num},accept,{label},{best_ratio:.12f},{ratio:.12f}")
                current = candidate
                best_ratio = ratio
                accepted += 1
                changed = True
                break
            if not changed:
                print(f"V_1.{inst_num},pass_{pass_index},no_accept,{best_ratio:.12f}")
                break

        if accepted:
            save_solution(current, output_xml)
            print(f"V_1.{inst_num},wrote,{best_ratio:.12f},{output_xml}")
        else:
            print(f"V_1.{inst_num},unchanged,{best_ratio:.12f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Official-checker-gated A instance improver.")
    parser.add_argument("instances", nargs="+", type=int)
    parser.add_argument("--passes", type=int, default=8)
    parser.add_argument("--output-suffix", default="official_greedy")
    args = parser.parse_args()

    for inst_num in args.instances:
        improve_instance(inst_num, passes=args.passes, output_suffix=args.output_suffix)


if __name__ == "__main__":
    main()
