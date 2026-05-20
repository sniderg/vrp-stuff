from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "roadef_2016_data"
PUBLISHED_RATIOS = DATA_DIR / "published_best_ratios.csv"
CHECKER_EXE = (
    DATA_DIR
    / "checker_v2"
    / "Challenge_Roadef_EURO_Checker_V2"
    / "bin"
    / "Release"
    / "IRP_Roadef_Challenge_Checker.exe"
)
RATIO_RE = re.compile(r"Logistic Ratio\s*=\s*([0-9]+(?:[.,][0-9]+)?)")


def load_reference(instance: str, phase: str | None) -> dict[str, str] | None:
    with PUBLISHED_RATIOS.open(newline="") as file:
        rows = list(csv.DictReader(file))

    matches = [
        row
        for row in rows
        if instance in {row["instance"], row["file_hint"]}
        and (phase is None or row["phase"] == phase)
    ]
    if not matches:
        return None
    if len(matches) > 1:
        phases = ", ".join(row["phase"] for row in matches)
        raise SystemExit(
            f"Multiple published ratios match {instance!r}: {phases}. "
            "Pass --phase to disambiguate."
        )
    return matches[0]


def run_checker(instance_xml: Path, solution_xml: Path) -> str:
    mono = shutil.which("mono")
    if mono is None:
        raise SystemExit(
            "Cannot run the bundled Windows checker because `mono` is not installed. "
            "Install Mono or run the checker on Windows, then compare the printed ratio."
        )

    command = [mono, str(CHECKER_EXE), str(instance_xml), str(solution_xml)]
    process = subprocess.run(
        command,
        input="\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            f"Checker exited with code {process.returncode}.\n\n{process.stdout}"
        )
    return process.stdout


def extract_ratio(checker_output: str) -> float:
    match = RATIO_RE.search(checker_output)
    if not match:
        print(checker_output)
        raise SystemExit("Checker output did not contain a `Logistic Ratio = ...` line.")
    return float(match.group(1).replace(",", "."))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the ROADEF 2016 checker and compare the ratio to published references."
    )
    parser.add_argument("instance_xml", type=Path)
    parser.add_argument("solution_xml", type=Path)
    parser.add_argument(
        "--phase",
        choices=["sprint", "qualification", "final"],
        help="Published-results phase to compare against.",
    )
    args = parser.parse_args()

    checker_output = run_checker(args.instance_xml, args.solution_xml)
    ratio = extract_ratio(checker_output)

    reference = load_reference(args.instance_xml.name, args.phase)
    print(f"checker_ratio,{ratio:.12f}")

    if reference is None:
        print("published_ratio,")
        print("delta,")
        print("status,no published reference matched this instance")
        return

    published = float(reference["best_ratio"])
    print(f"published_phase,{reference['phase']}")
    print(f"published_instance,{reference['instance']}")
    print(f"published_ratio,{published:.12f}")
    print(f"delta,{ratio - published:.12f}")
    print(f"relative_delta,{(ratio - published) / published:.12f}")


if __name__ == "__main__":
    sys.exit(main())
