from __future__ import annotations

import csv
import math
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
import numpy as np


SEED = 42
DAYS = 122  # roughly four months
HOURS_PER_DAY = 24
HOURS = DAYS * HOURS_PER_DAY
START_DATETIME = datetime(2026, 1, 1)
CAPACITY = 100.0
MEAN_DAILY_USE = 5.8
DAILY_USE_VARIATION = 0.45
REFILL_INTERVAL_RANGE = (7, 14)
LAPLACE_S_VALUES = [0.0] + [i / 1_000 for i in range(1, 401)]


def build_refill_hours(hours: int) -> set[int]:
    rng = random.Random(SEED)
    refill_hours = {0}
    hour = rng.randint(
        REFILL_INTERVAL_RANGE[0] * HOURS_PER_DAY,
        REFILL_INTERVAL_RANGE[1] * HOURS_PER_DAY,
    )

    while hour < hours:
        refill_hours.add(hour)
        hour += rng.randint(
            REFILL_INTERVAL_RANGE[0] * HOURS_PER_DAY,
            REFILL_INTERVAL_RANGE[1] * HOURS_PER_DAY,
        )

    return refill_hours


def simulate() -> list[dict[str, object]]:
    rng = random.Random(SEED + 1)
    refill_hours = build_refill_hours(HOURS)
    level = CAPACITY
    hourly_use = MEAN_DAILY_USE / HOURS_PER_DAY
    rows: list[dict[str, object]] = []

    for hour_index in range(HOURS):
        if hour_index % HOURS_PER_DAY == 0:
            daily_use = rng.uniform(
                MEAN_DAILY_USE - DAILY_USE_VARIATION,
                MEAN_DAILY_USE + DAILY_USE_VARIATION,
            )
            hourly_use = daily_use / HOURS_PER_DAY

        current_timestamp = START_DATETIME + timedelta(hours=hour_index)
        time_days = hour_index / HOURS_PER_DAY
        refilled = hour_index in refill_hours

        if refilled:
            level = CAPACITY

        rows.append(
            {
                "timestamp": current_timestamp.isoformat(timespec="hours"),
                "hour": hour_index,
                "time_days": round(time_days, 6),
                "tank_level": round(level, 2),
                "refilled": refilled,
            }
        )

        level = max(0.0, level - hourly_use)

    return rows


def write_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    with output_path.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["timestamp", "hour", "time_days", "tank_level", "refilled"],
        )
        writer.writeheader()
        writer.writerows(rows)


def plot(rows: list[dict[str, object]], output_path: Path) -> None:
    timestamps = [datetime.fromisoformat(str(row["timestamp"])) for row in rows]
    levels = [float(row["tank_level"]) for row in rows]
    refill_timestamps = [timestamps[i] for i, row in enumerate(rows) if row["refilled"]]
    refill_levels = [levels[i] for i, row in enumerate(rows) if row["refilled"]]

    fig, ax = plt.subplots(figsize=(12, 5.8))
    ax.plot(timestamps, levels, color="#1f6f8b", linewidth=2.0)
    ax.scatter(
        refill_timestamps,
        refill_levels,
        color="#d1495b",
        edgecolor="white",
        linewidth=1.2,
        s=72,
        zorder=3,
        label="Refill",
    )

    ax.set_title("Tank Level with Periodic Refills Over Four Months", pad=16, fontsize=15)
    ax.set_ylabel("Tank level (% of capacity)")
    ax.set_xlabel("Date")
    ax.set_ylim(0, 108)
    ax.grid(True, axis="y", alpha=0.28)
    ax.grid(True, axis="x", alpha=0.12)
    ax.legend(frameon=False, loc="lower left")

    note = (
        "Assumptions: refill every 7-14 days; "
        f"daily consumption {MEAN_DAILY_USE - DAILY_USE_VARIATION:.1f}-"
        f"{MEAN_DAILY_USE + DAILY_USE_VARIATION:.1f}% of capacity; hourly sampling"
    )
    fig.text(0.01, 0.015, note, ha="left", va="bottom", fontsize=9, color="#555555")
    fig.autofmt_xdate()
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_path, dpi=180)


def finite_laplace_transform(rows: list[dict[str, object]]) -> list[dict[str, float]]:
    times = [float(row["time_days"]) for row in rows]
    levels = [float(row["tank_level"]) for row in rows]
    transform_rows: list[dict[str, float]] = []

    for s_value in LAPLACE_S_VALUES:
        integral = 0.0

        for left_index in range(len(times) - 1):
            t0 = times[left_index]
            t1 = times[left_index + 1]
            y0 = levels[left_index] * math.exp(-s_value * t0)
            y1 = levels[left_index + 1] * math.exp(-s_value * t1)
            integral += 0.5 * (y0 + y1) * (t1 - t0)

        transform_rows.append(
            {
                "s": round(s_value, 3),
                "laplace_transform": integral,
            }
        )

    return transform_rows


def write_laplace_csv(rows: list[dict[str, float]], output_path: Path) -> None:
    with output_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["s", "laplace_transform"])
        writer.writeheader()
        writer.writerows(rows)


def plot_laplace(rows: list[dict[str, float]], output_path: Path) -> None:
    s_values = [row["s"] for row in rows]
    transform_values = [row["laplace_transform"] for row in rows]

    fig, ax = plt.subplots(figsize=(10, 5.8))
    ax.plot(s_values, transform_values, color="#3a5a40", linewidth=2.4)

    ax.set_title("Finite Laplace Transform of Tank Level Signal", pad=16, fontsize=15)
    ax.set_xlabel("s, in 1/days")
    ax.set_ylabel("F(s), level-days")
    ax.set_yscale("log")
    ax.grid(True, which="major", alpha=0.28)
    ax.grid(True, which="minor", axis="y", alpha=0.12)

    note = "Computed numerically over the 122-day simulated window using trapezoidal integration."
    fig.text(0.01, 0.015, note, ha="left", va="bottom", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_path, dpi=180)


def fourier_transform(rows: list[dict[str, object]]) -> list[dict[str, float]]:
    levels = np.array([float(row["tank_level"]) for row in rows])
    centered_levels = levels - levels.mean()
    sample_spacing_days = 1.0 / HOURS_PER_DAY

    frequencies = np.fft.rfftfreq(len(centered_levels), d=sample_spacing_days)
    fft_values = np.fft.rfft(centered_levels)
    amplitudes = (2.0 / len(centered_levels)) * np.abs(fft_values)

    transform_rows: list[dict[str, float]] = []
    for frequency, amplitude in zip(frequencies, amplitudes):
        period_days = math.inf if frequency == 0 else 1.0 / frequency
        transform_rows.append(
            {
                "frequency_cycles_per_day": frequency,
                "period_days": period_days,
                "amplitude": amplitude,
            }
        )

    return transform_rows


def write_fourier_csv(rows: list[dict[str, float]], output_path: Path) -> None:
    with output_path.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["frequency_cycles_per_day", "period_days", "amplitude"],
        )
        writer.writeheader()
        writer.writerows(rows)


def plot_fourier(rows: list[dict[str, float]], output_path: Path) -> None:
    nonzero_rows = [row for row in rows if row["frequency_cycles_per_day"] > 0]
    frequencies = [row["frequency_cycles_per_day"] for row in nonzero_rows]
    amplitudes = [row["amplitude"] for row in nonzero_rows]

    fig, ax = plt.subplots(figsize=(10, 5.8))
    ax.plot(frequencies, amplitudes, color="#6d597a", linewidth=2.0)
    ax.fill_between(frequencies, amplitudes, color="#6d597a", alpha=0.18)

    refill_min_frequency = 1.0 / REFILL_INTERVAL_RANGE[1]
    refill_max_frequency = 1.0 / REFILL_INTERVAL_RANGE[0]
    ax.axvspan(
        refill_min_frequency,
        refill_max_frequency,
        color="#d1495b",
        alpha=0.16,
        label="Expected refill band",
    )

    top_nonzero = max(nonzero_rows, key=lambda row: row["amplitude"])
    ax.scatter(
        [top_nonzero["frequency_cycles_per_day"]],
        [top_nonzero["amplitude"]],
        color="#d1495b",
        edgecolor="white",
        linewidth=1.0,
        s=70,
        zorder=3,
        label=f"Peak: {top_nonzero['period_days']:.1f} days",
    )

    ax.set_title("Fourier Spectrum of Tank Level Signal", pad=16, fontsize=15)
    ax.set_xlabel("Frequency, cycles/day")
    ax.set_ylabel("Amplitude, % of tank capacity")
    ax.grid(True, alpha=0.25)
    ax.legend(frameon=False, loc="upper right")

    note = (
        "Computed with real FFT on hourly samples after subtracting the mean tank level. "
        "Shaded band marks 7-14 day refill rhythm."
    )
    fig.text(0.01, 0.015, note, ha="left", va="bottom", fontsize=9, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_path, dpi=180)


def main() -> None:
    rows = simulate()
    laplace_rows = finite_laplace_transform(rows)
    fourier_rows = fourier_transform(rows)

    write_csv(rows, Path("tank_sawtooth_hourly_data.csv"))
    write_laplace_csv(laplace_rows, Path("tank_sawtooth_hourly_laplace.csv"))
    write_fourier_csv(fourier_rows, Path("tank_sawtooth_hourly_fourier.csv"))
    plot(rows, Path("tank_sawtooth_hourly.png"))
    plot_laplace(laplace_rows, Path("tank_sawtooth_hourly_laplace.png"))
    plot_fourier(fourier_rows, Path("tank_sawtooth_hourly_fourier.png"))


if __name__ == "__main__":
    main()
