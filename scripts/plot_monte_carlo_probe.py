from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
import numpy as np


def load_summary(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def load_events(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def day_columns(rows: list[dict[str, str]]) -> list[tuple[int, str]]:
    columns: list[tuple[int, str]] = []
    for key in rows[0]:
        if key.startswith("served_by_day") and key.endswith("_freq"):
            day = int(key[len("served_by_day") : -len("_freq")])
            columns.append((day, key))
    columns.sort()
    return columns


def sort_rows(rows: list[dict[str, str]], day_cols: list[tuple[int, str]]) -> list[dict[str, str]]:
    first_key = "served_by_day1_freq"
    return sorted(
        rows,
        key=lambda row: (
            -float(row.get(first_key, 0.0) or 0.0),
            float(row.get("mean_first_service_day") or 9_999),
            -float(row.get(day_cols[-1][1], 0.0) or 0.0),
            int(row["point"]),
        ),
    )


def plot_heatmap(rows: list[dict[str, str]], day_cols: list[tuple[int, str]], output_path: Path) -> None:
    points = [int(row["point"]) for row in rows]
    matrix = np.array(
        [[float(row[column] or 0.0) for _, column in day_cols] for row in rows],
        dtype=float,
    )

    fig_height = max(5.5, 0.38 * len(rows) + 1.8)
    fig, ax = plt.subplots(figsize=(10.5, fig_height))
    im = ax.imshow(matrix, aspect="auto", interpolation="nearest", cmap="viridis", vmin=0.0, vmax=1.0)

    ax.set_title("Monte Carlo Service Confidence by Customer and Day", pad=14, fontsize=14)
    ax.set_xlabel("Served by day")
    ax.set_ylabel("Customer point")
    ax.set_xticks(range(len(day_cols)))
    ax.set_xticklabels([str(day) for day, _ in day_cols])
    ax.set_yticks(range(len(points)))
    ax.set_yticklabels([str(point) for point in points])

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Service frequency")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)


def plot_repeat_counts(rows: list[dict[str, str]], report_day: int, output_path: Path, top_n: int) -> None:
    service_key = f"service_count_mean_by_day{report_day}"
    min_key = f"service_count_min_by_day{report_day}"
    max_key = f"service_count_max_by_day{report_day}"
    selected = sorted(
        rows,
        key=lambda row: (-float(row.get(service_key, 0.0) or 0.0), int(row["point"])),
    )[:top_n]

    points = [str(row["point"]) for row in selected]
    means = np.array([float(row.get(service_key, 0.0) or 0.0) for row in selected], dtype=float)
    mins = np.array([float(row.get(min_key, 0.0) or 0.0) for row in selected], dtype=float)
    maxs = np.array([float(row.get(max_key, 0.0) or 0.0) for row in selected], dtype=float)
    lower = means - mins
    upper = maxs - means

    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    x = np.arange(len(points))
    ax.bar(x, means, color="#5b8e7d", width=0.72)
    ax.errorbar(x, means, yerr=np.vstack([lower, upper]), fmt="none", ecolor="#2f3e46", capsize=4, linewidth=1.3)

    ax.set_title(f"Mean Repeat Service Count by Day {report_day}", pad=14, fontsize=14)
    ax.set_xlabel("Customer point")
    ax.set_ylabel("Mean service count")
    ax.set_xticks(x)
    ax.set_xticklabels(points)
    ax.grid(True, axis="y", alpha=0.24)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)


def plot_stability_scatter(rows: list[dict[str, str]], report_day: int, output_path: Path) -> None:
    x = []
    y = []
    color = []
    labels = []
    size = []
    for row in rows:
        first_day = row.get("mean_first_service_day")
        if not first_day:
            continue
        service_mean = float(row.get(f"service_count_mean_by_day{report_day}", 0.0) or 0.0)
        day1_freq = float(row.get("served_by_day1_freq", 0.0) or 0.0)
        served_any = int(row.get("served_in_any_scenario", 0) or 0)
        x.append(float(first_day))
        y.append(service_mean)
        color.append(day1_freq)
        size.append(35 + 12 * served_any)
        labels.append(row["point"])

    fig, ax = plt.subplots(figsize=(9.8, 6.2))
    scatter = ax.scatter(x, y, c=color, s=size, cmap="plasma", alpha=0.82, edgecolor="white", linewidth=0.8)
    for xi, yi, label in zip(x, y, labels):
        ax.text(xi + 0.04, yi + 0.04, label, fontsize=8, color="#333333")

    ax.set_title("Customer Stability Map", pad=14, fontsize=14)
    ax.set_xlabel("Mean first service day")
    ax.set_ylabel(f"Mean service count by day {report_day}")
    ax.grid(True, alpha=0.22)
    cbar = fig.colorbar(scatter, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label("Served by day 1 frequency")
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)


def plot_customer_service_density(
    events: list[dict[str, str]],
    *,
    customer_point: int,
    output_path: Path,
    max_day: int | None = None,
) -> None:
    customer_events = [row for row in events if int(row["point"]) == customer_point]
    if not customer_events:
        raise RuntimeError(f"no event rows for customer {customer_point}")

    days = np.array([int(row["day"]) for row in customer_events], dtype=int)
    scenarios = np.array([int(row["scenario"]) for row in customer_events], dtype=int)
    visits = np.array([int(row["visit_index"]) for row in customer_events], dtype=int)
    day_limit = max_day or int(days.max())
    bins = np.arange(0.5, day_limit + 1.5, 1.0)
    hist_counts, _ = np.histogram(days, bins=bins)

    fig, (ax_hist, ax_strip) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.2),
        sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1.4]},
    )

    centers = np.arange(1, day_limit + 1)
    ax_hist.bar(centers, hist_counts, width=0.82, color="#4f772d", edgecolor="white", linewidth=0.8)
    ax_hist.set_title(f"Customer {customer_point} Service-Day Density Across Monte Carlo Scenarios", pad=14, fontsize=14)
    ax_hist.set_ylabel("Service events")
    ax_hist.grid(True, axis="y", alpha=0.24)

    jitter = ((visits % 5) - 2) * 0.045
    ax_strip.scatter(days + jitter, scenarios, c=visits, cmap="plasma", s=42, alpha=0.85, edgecolor="white", linewidth=0.5)
    ax_strip.set_xlabel("Day")
    ax_strip.set_ylabel("Scenario")
    ax_strip.grid(True, axis="x", alpha=0.18)
    ax_strip.grid(True, axis="y", alpha=0.10)
    ax_strip.set_xlim(0.5, day_limit + 0.5)
    ax_strip.set_xticks(centers)

    fig.tight_layout()
    fig.savefig(output_path, dpi=180)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Monte Carlo probe outputs")
    parser.add_argument("summary_csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--events-csv", type=Path)
    parser.add_argument("--customer-point", type=int)
    parser.add_argument("--max-day", type=int)
    parser.add_argument("--top-n", type=int, default=12)
    args = parser.parse_args()

    rows = load_summary(args.summary_csv)
    if not rows:
        raise RuntimeError("summary CSV is empty")
    day_cols = day_columns(rows)
    rows = sort_rows(rows, day_cols)
    report_day = day_cols[-1][0]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    plot_heatmap(rows, day_cols, args.output_dir / "service_confidence_heatmap.png")
    plot_repeat_counts(rows, report_day, args.output_dir / "repeat_service_counts.png", args.top_n)
    plot_stability_scatter(rows, report_day, args.output_dir / "customer_stability_scatter.png")

    print(f"wrote,{args.output_dir / 'service_confidence_heatmap.png'}")
    print(f"wrote,{args.output_dir / 'repeat_service_counts.png'}")
    print(f"wrote,{args.output_dir / 'customer_stability_scatter.png'}")
    if args.events_csv and args.customer_point is not None:
        events = load_events(args.events_csv)
        density_path = args.output_dir / f"customer_{args.customer_point}_service_density.png"
        plot_customer_service_density(
            events,
            customer_point=args.customer_point,
            output_path=density_path,
            max_day=args.max_day,
        )
        print(f"wrote,{density_path}")


if __name__ == "__main__":
    main()
