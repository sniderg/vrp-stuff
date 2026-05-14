from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "roadef_2016_data"
HUST_DIR = DATA_DIR / "hust_smart_results" / "ROADEF2016-IRP-Results-master"
HUST_RATIOS = DATA_DIR / "hust_smart_results" / "hust_smart_ratios.csv"
OFFICIAL_RATIOS = DATA_DIR / "published_best_ratios.csv"
OUTPUT_CSV = DATA_DIR / "hust_smart_results" / "hust_smart_checker_comparison.csv"
CHECKER_EXE = (
    DATA_DIR
    / "checker_v2"
    / "Challenge_Roadef_EURO_Checker_V2"
    / "bin"
    / "Release"
    / "IRP_Roadef_Challenge_Checker.exe"
)
RATIO_RE = re.compile(r"Logistic Ratio\s*=\s*([0-9]+(?:[.,][0-9]+)?)")


def find_instance(file_hint: str) -> Path:
    candidates = list(DATA_DIR.glob(f"set_B/**/{file_hint}"))
    candidates.extend(DATA_DIR.glob(f"set_X/**/{file_hint}"))
    candidates = [path for path in candidates if "/__MACOSX/" not in str(path)]
    if len(candidates) != 1:
        raise SystemExit(f"Expected one match for {file_hint}, found {len(candidates)}.")
    return candidates[0]


def load_official_best() -> dict[str, float]:
    with OFFICIAL_RATIOS.open(newline="") as file:
        return {
            row["file_hint"]: float(row["best_ratio"])
            for row in csv.DictReader(file)
            if row["phase"] == "final"
        }


def run_checker(instance_xml: Path, solution_xml: Path) -> float:
    mono = shutil.which("mono")
    if mono is None:
        raise SystemExit("`mono` is not installed or not on PATH.")

    process = subprocess.run(
        [mono, str(CHECKER_EXE), str(instance_xml), str(solution_xml)],
        input="\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            f"Checker failed for {instance_xml.name} / {solution_xml.name}.\n\n"
            f"{process.stdout}"
        )

    match = RATIO_RE.search(process.stdout)
    if not match:
        raise SystemExit(
            f"No Logistic Ratio found for {instance_xml.name} / {solution_xml.name}.\n\n"
            f"{process.stdout}"
        )
    return float(match.group(1).replace(",", "."))


def main() -> int:
    official_best = load_official_best()
    rows: list[dict[str, object]] = []

    with HUST_RATIOS.open(newline="") as file:
        for row in csv.DictReader(file):
            instance_xml = find_instance(row["file_hint"])
            solution_xml = HUST_DIR / row["solution_file"]
            expected = float(row["expected_ratio"])
            official = official_best.get(row["file_hint"])
            checker = run_checker(instance_xml, solution_xml)

            rows.append(
                {
                    "instance": row["instance"],
                    "instance_file": str(instance_xml.relative_to(ROOT)),
                    "solution_file": str(solution_xml.relative_to(ROOT)),
                    "checker_ratio": f"{checker:.10f}",
                    "hust_expected_ratio": f"{expected:.10f}",
                    "hust_delta": f"{checker - expected:.10f}",
                    "official_best_ratio": f"{official:.10f}" if official is not None else "",
                    "official_delta": f"{checker - official:.10f}" if official is not None else "",
                }
            )
            print(
                f"{row['instance']}: checker={checker:.10f}, "
                f"hust_delta={checker - expected:+.10f}"
            )

    with OUTPUT_CSV.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nwrote {OUTPUT_CSV.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
