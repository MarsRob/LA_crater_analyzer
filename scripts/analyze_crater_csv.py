from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


DEFAULT_UM_PER_PIXEL = 1.3421


@dataclass
class CraterRow:
    index: int
    status: str
    expected_frame: float | None
    measurement_frame: float | None
    rim_present: bool | None
    inner_diameter: float | None
    outer_diameter: float | None
    notes: str


def parse_float(value: str | None) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_bool(value: str | None) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def load_rows(path: Path) -> list[CraterRow]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            status = (raw.get("status") or "").strip().lower()
            if status == "unreviewed":
                continue
            index_value = parse_float(raw.get("index"))
            if index_value is None:
                continue
            rows.append(
                CraterRow(
                    index=int(index_value),
                    status=status,
                    expected_frame=parse_float(raw.get("expected_frame_index")),
                    measurement_frame=parse_float(raw.get("measurement_frame_index")),
                    rim_present=parse_bool(raw.get("rim_present")),
                    inner_diameter=parse_float(raw.get("inner_diameter_px")),
                    outer_diameter=parse_float(raw.get("outer_diameter_px")),
                    notes=raw.get("notes") or "",
                )
            )
    return rows


def gaussian_pdf(x_values: np.ndarray, mean: float, std: float) -> np.ndarray:
    variance = std**2
    return (1.0 / np.sqrt(2 * np.pi * variance)) * np.exp(-((x_values - mean) ** 2) / (2 * variance))


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    if len(values) == 0:
        return values
    output = np.empty_like(values, dtype=float)
    half_window = max(1, window) // 2
    for idx in range(len(values)):
        start = max(0, idx - half_window)
        stop = min(len(values), idx + half_window + 1)
        output[idx] = np.nanmean(values[start:stop])
    return output


def binned_stats(x_values: np.ndarray, y_values: np.ndarray, bins: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(x_values) == 0:
        return np.array([]), np.array([]), np.array([])
    edges = np.linspace(float(np.nanmin(x_values)), float(np.nanmax(x_values)), bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    means = np.full(bins, np.nan)
    stds = np.full(bins, np.nan)
    for idx in range(bins):
        if idx == bins - 1:
            mask = (x_values >= edges[idx]) & (x_values <= edges[idx + 1])
        else:
            mask = (x_values >= edges[idx]) & (x_values < edges[idx + 1])
        if np.any(mask):
            means[idx] = np.nanmean(y_values[mask])
            if np.count_nonzero(mask) > 1:
                stds[idx] = np.nanstd(y_values[mask], ddof=1)
            else:
                stds[idx] = 0.0
    return centers, means, stds


def save_distribution(
    output_dir: Path,
    stem: str,
    title: str,
    values: np.ndarray,
    unit_label: str,
) -> dict[str, float]:
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    median = float(np.median(values))
    q1, q3 = np.percentile(values, [25, 75])

    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    counts, bins, _ = axis.hist(
        values,
        bins="auto",
        color="#4C78A8",
        alpha=0.72,
        edgecolor="white",
        label="Measured diameters",
    )
    if std > 0:
        x_fit = np.linspace(float(np.min(values)), float(np.max(values)), 400)
        bin_width = float(np.mean(np.diff(bins)))
        y_fit = gaussian_pdf(x_fit, mean, std) * len(values) * bin_width
        axis.plot(x_fit, y_fit, color="#F58518", linewidth=2.4, label="Gaussian fit")

    axis.axvline(mean, color="#E45756", linestyle="--", linewidth=1.8, label=f"Mean = {mean:.2f}")
    axis.axvspan(mean - std, mean + std, color="#F58518", alpha=0.14, label=f"+/- 1 SD = {std:.2f}")
    axis.set_title(title)
    axis.set_xlabel(unit_label)
    axis.set_ylabel("Count")
    axis.legend()
    axis.grid(alpha=0.22)
    figure.savefig(output_dir / f"{stem}.png", dpi=220)
    plt.close(figure)

    return {
        "count": float(len(values)),
        "mean": mean,
        "std": std,
        "median": median,
        "q1": float(q1),
        "q3": float(q3),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }


def save_scan_development(
    output_dir: Path,
    rows: list[CraterRow],
    window: int,
    bins: int,
    um_per_pixel: float,
) -> None:
    visible = [row for row in rows if row.status == "visible" and row.inner_diameter is not None]
    indices = np.array([row.index for row in visible], dtype=float)
    diameters = np.array([row.inner_diameter * um_per_pixel for row in visible], dtype=float)
    frames = np.array(
        [
            row.measurement_frame if row.measurement_frame is not None else np.nan
            for row in visible
        ],
        dtype=float,
    )

    order = np.argsort(indices)
    indices = indices[order]
    diameters = diameters[order]
    frames = frames[order]
    smoothed = rolling_mean(diameters, window)

    figure, axis = plt.subplots(figsize=(10, 5), constrained_layout=True)
    axis.scatter(indices, diameters, s=18, color="#4C78A8", alpha=0.72, label="Measured crater")
    axis.plot(indices, smoothed, color="#E45756", linewidth=2.0, label=f"Rolling mean, n={window}")
    axis.set_title("Inner crater diameter along scan")
    axis.set_xlabel("Crater index")
    axis.set_ylabel("Inner diameter (um)")
    axis.grid(alpha=0.22)
    axis.legend()
    figure.savefig(output_dir / "02_inner_diameter_along_scan.png", dpi=220)
    plt.close(figure)

    centers, means, stds = binned_stats(indices, diameters, bins)
    figure, axis = plt.subplots(figsize=(10, 5), constrained_layout=True)
    axis.errorbar(
        centers,
        means,
        yerr=stds,
        fmt="o-",
        color="#54A24B",
        ecolor="#9AC77D",
        capsize=3,
        label="Binned mean +/- SD",
    )
    axis.set_title("Binned crater diameter development")
    axis.set_xlabel("Crater index")
    axis.set_ylabel("Inner diameter (um)")
    axis.grid(alpha=0.22)
    axis.legend()
    figure.savefig(output_dir / "03_binned_scan_development.png", dpi=220)
    plt.close(figure)

    valid_frame_mask = ~np.isnan(frames)
    if np.any(valid_frame_mask):
        figure, axis = plt.subplots(figsize=(10, 5), constrained_layout=True)
        axis.scatter(frames[valid_frame_mask], diameters[valid_frame_mask], s=18, color="#72B7B2", alpha=0.72)
        axis.set_title("Inner crater diameter by video frame")
        axis.set_xlabel("Measurement frame index")
        axis.set_ylabel("Inner diameter (um)")
        axis.grid(alpha=0.22)
        figure.savefig(output_dir / "04_inner_diameter_by_frame.png", dpi=220)
        plt.close(figure)


def save_status_and_rim(output_dir: Path, rows: list[CraterRow]) -> None:
    indices = np.array([row.index for row in rows], dtype=float)
    status_code = np.array(
        [1 if row.status == "visible" else 0 if row.status == "missing" else np.nan for row in rows],
        dtype=float,
    )
    rim_code = np.array(
        [
            1 if row.rim_present is True else 0 if row.rim_present is False else np.nan
            for row in rows
        ],
        dtype=float,
    )

    figure, axes = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True, constrained_layout=True)
    axes[0].scatter(indices, status_code, color="#4C78A8", s=18)
    axes[0].set_yticks([0, 1])
    axes[0].set_yticklabels(["Missing", "Visible"])
    axes[0].set_title("Reviewed crater visibility along scan")
    axes[0].grid(alpha=0.22)

    valid_rim = ~np.isnan(rim_code)
    axes[1].scatter(indices[valid_rim], rim_code[valid_rim], color="#B279A2", s=18)
    axes[1].set_yticks([0, 1])
    axes[1].set_yticklabels(["No rim", "Rim"])
    axes[1].set_title("Rim classification along scan")
    axes[1].set_xlabel("Crater index")
    axes[1].grid(alpha=0.22)
    figure.savefig(output_dir / "05_visibility_and_rim_along_scan.png", dpi=220)
    plt.close(figure)


def save_frame_spacing(output_dir: Path, rows: list[CraterRow]) -> dict[str, float]:
    measured = [
        row
        for row in rows
        if row.status == "visible"
        and row.measurement_frame is not None
    ]
    measured.sort(key=lambda row: row.index)
    if len(measured) < 2:
        return {}

    indices = np.array([row.index for row in measured], dtype=float)
    frames = np.array([row.measurement_frame for row in measured], dtype=float)
    frame_gaps = np.diff(frames) / np.diff(indices)

    figure, axis = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
    axis.plot(indices[1:], frame_gaps, marker="o", markersize=3, linewidth=1.2, color="#F58518")
    axis.axhline(np.mean(frame_gaps), color="#E45756", linestyle="--", label=f"Mean = {np.mean(frame_gaps):.2f}")
    axis.set_title("Frame spacing between reviewed visible craters")
    axis.set_xlabel("Crater index")
    axis.set_ylabel("Frames per crater index")
    axis.grid(alpha=0.22)
    axis.legend()
    figure.savefig(output_dir / "06_frame_spacing_diagnostics.png", dpi=220)
    plt.close(figure)

    return {
        "frame_gap_mean": float(np.mean(frame_gaps)),
        "frame_gap_std": float(np.std(frame_gaps, ddof=1)) if len(frame_gaps) > 1 else 0.0,
        "frame_gap_min": float(np.min(frame_gaps)),
        "frame_gap_max": float(np.max(frame_gaps)),
    }


def save_summary(
    output_dir: Path,
    csv_path: Path,
    rows: list[CraterRow],
    inner_stats_px: dict[str, float],
    inner_stats_um: dict[str, float],
    outer_stats_px: dict[str, float] | None,
    outer_stats_um: dict[str, float] | None,
    frame_stats: dict[str, float],
    um_per_pixel: float,
) -> None:
    status_counts = {
        "visible": sum(1 for row in rows if row.status == "visible"),
        "missing": sum(1 for row in rows if row.status == "missing"),
        "reviewed_total": len(rows),
    }
    rim_count = sum(1 for row in rows if row.rim_present is True)
    no_rim_count = sum(1 for row in rows if row.rim_present is False)

    summary_rows = [
        ("input_csv", str(csv_path)),
        ("micrometer_per_pixel", um_per_pixel),
        ("reviewed_total_excluding_unreviewed", status_counts["reviewed_total"]),
        ("visible_count", status_counts["visible"]),
        ("missing_count", status_counts["missing"]),
        ("rim_present_count", rim_count),
        ("rim_absent_count", no_rim_count),
    ]
    for prefix, stats in [
        ("inner_diameter_px", inner_stats_px),
        ("inner_diameter_um", inner_stats_um),
        ("outer_diameter_px", outer_stats_px or {}),
        ("outer_diameter_um", outer_stats_um or {}),
    ]:
        for key, value in stats.items():
            summary_rows.append((f"{prefix}_{key}", value))
    for key, value in frame_stats.items():
        summary_rows.append((key, value))

    with (output_dir / "summary_statistics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerows(summary_rows)

    visible_with_inner = [
        row
        for row in rows
        if row.status == "visible"
        and row.inner_diameter is not None
    ]
    if visible_with_inner and inner_stats_px["std"] > 0:
        mean = inner_stats_px["mean"]
        std = inner_stats_px["std"]
        outliers = [
            row
            for row in visible_with_inner
            if abs(float(row.inner_diameter) - mean) > 2 * std
        ]
    else:
        outliers = []

    with (output_dir / "inner_diameter_outliers_gt_2sd.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["index", "status", "inner_diameter_px", "inner_diameter_um", "measurement_frame_index", "notes"]
        )
        for row in outliers:
            writer.writerow(
                [
                    row.index,
                    row.status,
                    row.inner_diameter,
                    None if row.inner_diameter is None else row.inner_diameter * um_per_pixel,
                    row.measurement_frame,
                    row.notes,
                ]
            )


def analyze(csv_path: Path, output_dir: Path, rolling_window: int, bins: int, um_per_pixel: float) -> None:
    rows = load_rows(csv_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    inner_values = np.array(
        [
            row.inner_diameter
            for row in rows
            if row.status == "visible"
            and row.inner_diameter is not None
        ],
        dtype=float,
    )
    if len(inner_values) == 0:
        raise RuntimeError("No visible rows with inner_diameter_px were found after excluding unreviewed rows.")

    inner_stats_px = {
        "count": float(len(inner_values)),
        "mean": float(np.mean(inner_values)),
        "std": float(np.std(inner_values, ddof=1)) if len(inner_values) > 1 else 0.0,
        "median": float(np.median(inner_values)),
        "q1": float(np.percentile(inner_values, 25)),
        "q3": float(np.percentile(inner_values, 75)),
        "min": float(np.min(inner_values)),
        "max": float(np.max(inner_values)),
    }
    inner_values_um = inner_values * um_per_pixel
    inner_stats_um = save_distribution(
        output_dir,
        "01_inner_diameter_distribution_gaussian",
        "Inner crater diameter distribution with Gaussian fit",
        inner_values_um,
        "Inner diameter (um)",
    )

    outer_values = np.array(
        [
            row.outer_diameter
            for row in rows
            if row.status == "visible"
            and row.outer_diameter is not None
        ],
        dtype=float,
    )
    outer_stats_px = None
    outer_stats_um = None
    if len(outer_values) > 0:
        outer_stats_px = {
            "count": float(len(outer_values)),
            "mean": float(np.mean(outer_values)),
            "std": float(np.std(outer_values, ddof=1)) if len(outer_values) > 1 else 0.0,
            "median": float(np.median(outer_values)),
            "q1": float(np.percentile(outer_values, 25)),
            "q3": float(np.percentile(outer_values, 75)),
            "min": float(np.min(outer_values)),
            "max": float(np.max(outer_values)),
        }
        outer_stats_um = save_distribution(
            output_dir,
            "07_outer_diameter_distribution_gaussian",
            "Outer rim diameter distribution with Gaussian fit",
            outer_values * um_per_pixel,
            "Outer diameter (um)",
        )

    save_scan_development(output_dir, rows, rolling_window, bins, um_per_pixel)
    save_status_and_rim(output_dir, rows)
    frame_stats = save_frame_spacing(output_dir, rows)
    save_summary(
        output_dir,
        csv_path,
        rows,
        inner_stats_px,
        inner_stats_um,
        outer_stats_px,
        outer_stats_um,
        frame_stats,
        um_per_pixel,
    )

    print(f"Analyzed {csv_path}")
    print(f"Reviewed rows included: {len(rows)}")
    print(f"Visible crater diameters: {int(inner_stats_um['count'])}")
    print(f"Conversion factor: {um_per_pixel:.4f} um/px")
    print(f"Inner diameter mean: {inner_stats_um['mean']:.3f} um ({inner_stats_px['mean']:.3f} px)")
    print(f"Inner diameter standard deviation: {inner_stats_um['std']:.3f} um ({inner_stats_px['std']:.3f} px)")
    print(f"Outputs written to: {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze LA crater CSV measurements.")
    parser.add_argument("csv_path", type=Path, help="CSV exported by the crater analyzer.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for figures and summary CSV files. Defaults to <csv stem>_analysis.",
    )
    parser.add_argument("--rolling-window", type=int, default=15, help="Rolling mean window in crater count.")
    parser.add_argument("--bins", type=int, default=12, help="Number of bins for scan-development summary.")
    parser.add_argument(
        "--um-per-pixel",
        type=float,
        default=DEFAULT_UM_PER_PIXEL,
        help=f"Micrometer conversion factor. Default: {DEFAULT_UM_PER_PIXEL} um/px.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir or args.csv_path.with_name(f"{args.csv_path.stem}_analysis")
    analyze(args.csv_path, output_dir, args.rolling_window, args.bins, args.um_per_pixel)


if __name__ == "__main__":
    main()
