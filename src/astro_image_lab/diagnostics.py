"""Pixel-distribution diagnostics for calibration and stacking products."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np

from .calibration import calibrate_science_image
from .io import load_fits

STATISTICS_FIELDNAMES = [
    "stage",
    "filter",
    "label",
    "source_path",
    "mean",
    "median",
    "std",
    "min",
    "max",
    "p1",
    "p5",
    "p95",
    "p99",
    "finite_fraction",
    "n_finite",
]

DEFAULT_DIAGNOSTIC_CONFIG = {
    "enabled": False,
    "random_seed": 42,
    "bins": 100,
    "lower_percentile": 0.5,
    "upper_percentile": 99.5,
    "max_pixels": 1_000_000,
}


def finite_pixels(array: Any) -> np.ndarray:
    """Return a flattened float array containing only finite pixels."""
    pixels = np.asarray(array, dtype=float).ravel()
    return pixels[np.isfinite(pixels)]


def sample_finite_pixels(array: Any, max_pixels: int | None, random_seed: int | None) -> np.ndarray:
    """Return finite pixels, deterministically sampled when there are too many."""
    pixels = finite_pixels(array)
    if max_pixels is None or max_pixels <= 0 or pixels.size <= max_pixels:
        return pixels
    rng = np.random.default_rng(random_seed)
    indices = rng.choice(pixels.size, size=max_pixels, replace=False)
    return pixels[indices]


def select_random_file(paths: list[Path] | tuple[Path, ...], random_seed: int | None) -> Path:
    """Select one path reproducibly from a sorted path list."""
    sorted_paths = sorted(Path(path) for path in paths)
    if not sorted_paths:
        raise ValueError("paths must contain at least one file")
    rng = np.random.default_rng(random_seed)
    return sorted_paths[int(rng.integers(0, len(sorted_paths)))]


def compute_pixel_statistics(
    array: Any,
    *,
    stage: str = "",
    filter_name: str | None = None,
    label: str = "",
    source_path: str | Path = "",
) -> dict[str, Any]:
    """Compute finite-pixel summary statistics for one image array."""
    all_pixels = np.asarray(array, dtype=float).ravel()
    pixels = all_pixels[np.isfinite(all_pixels)]
    total_pixels = int(all_pixels.size)
    n_finite = int(pixels.size)
    finite_fraction = (n_finite / total_pixels) if total_pixels else 0.0

    record: dict[str, Any] = {
        "stage": stage,
        "filter": "" if filter_name is None else filter_name,
        "label": label,
        "source_path": str(source_path),
        "finite_fraction": finite_fraction,
        "n_finite": n_finite,
    }
    if n_finite == 0:
        record.update({key: np.nan for key in ("mean", "median", "std", "min", "max", "p1", "p5", "p95", "p99")})
        return record

    record.update(
        {
            "mean": float(np.mean(pixels)),
            "median": float(np.median(pixels)),
            "std": float(np.std(pixels)),
            "min": float(np.min(pixels)),
            "max": float(np.max(pixels)),
            "p1": float(np.percentile(pixels, 1)),
            "p5": float(np.percentile(pixels, 5)),
            "p95": float(np.percentile(pixels, 95)),
            "p99": float(np.percentile(pixels, 99)),
        }
    )
    return record


def compute_histogram_x_limits(
    first_array: Any,
    second_array: Any,
    *,
    lower_percentile: float = 0.5,
    upper_percentile: float = 99.5,
    max_pixels: int | None = None,
    random_seed: int | None = None,
) -> tuple[float, float]:
    """Compute robust histogram x-limits from percentiles across both arrays."""
    first = sample_finite_pixels(first_array, max_pixels, random_seed)
    second = sample_finite_pixels(second_array, max_pixels, None if random_seed is None else random_seed + 1)
    combined = np.concatenate([first, second])
    if combined.size == 0:
        return 0.0, 1.0
    lower, upper = np.percentile(combined, [lower_percentile, upper_percentile])
    lower = float(lower)
    upper = float(upper)
    if not np.isfinite(lower) or not np.isfinite(upper):
        return 0.0, 1.0
    if lower == upper:
        padding = max(abs(lower) * 0.05, 1.0)
        return lower - padding, upper + padding
    return lower, upper


def _legend_label(label: str, stats: dict[str, Any]) -> str:
    return (
        f"{label}: mean={stats['mean']:.4g}, median={stats['median']:.4g}, "
        f"std={stats['std']:.4g}, finite={stats['finite_fraction']:.3f}"
    )


def _histogram_y_limit(first_pixels: np.ndarray, second_pixels: np.ndarray, bins: int, x_limits: tuple[float, float]) -> float:
    counts = []
    for pixels in (first_pixels, second_pixels):
        in_range = pixels[(pixels >= x_limits[0]) & (pixels <= x_limits[1])]
        if in_range.size:
            hist_counts, _edges = np.histogram(in_range, bins=bins, range=x_limits)
            counts.append(int(hist_counts.max(initial=0)))
    max_count = max(counts, default=1)
    return max_count * 1.10 if max_count > 0 else 1.0


def plot_histogram_comparison(
    first_array: Any,
    second_array: Any,
    *,
    first_label: str,
    second_label: str,
    title: str,
    output_path: Path,
    bins: int = 100,
    lower_percentile: float = 0.5,
    upper_percentile: float = 99.5,
    max_pixels: int | None = 1_000_000,
    random_seed: int | None = 42,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Plot overlaid finite-pixel histograms and write them to ``output_path``."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    first_stats = compute_pixel_statistics(first_array, label=first_label)
    second_stats = compute_pixel_statistics(second_array, label=second_label)
    first_pixels = sample_finite_pixels(first_array, max_pixels, random_seed)
    second_pixels = sample_finite_pixels(second_array, max_pixels, None if random_seed is None else random_seed + 1)
    x_limits = compute_histogram_x_limits(
        first_pixels,
        second_pixels,
        lower_percentile=lower_percentile,
        upper_percentile=upper_percentile,
    )
    y_limit = _histogram_y_limit(first_pixels, second_pixels, bins, x_limits)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(first_pixels, bins=bins, range=x_limits, alpha=0.55, label=_legend_label(first_label, first_stats))
    ax.hist(second_pixels, bins=bins, range=x_limits, alpha=0.55, label=_legend_label(second_label, second_stats))
    if np.isfinite(first_stats["mean"]):
        ax.axvline(first_stats["mean"], color="C0", linestyle="--", linewidth=1.5)
    if np.isfinite(second_stats["mean"]):
        ax.axvline(second_stats["mean"], color="C1", linestyle="--", linewidth=1.5)
    ax.set_xlim(*x_limits)
    ax.set_ylim(0, y_limit)
    ax.set_xlabel("Pixel value")
    ax.set_ylabel("Count")
    ax.set_title(title)
    ax.legend(fontsize="small")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return first_stats, second_stats


def _write_statistics_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=STATISTICS_FIELDNAMES)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in STATISTICS_FIELDNAMES})


def _normalized_flat_from_file(flat_path: Path, master_bias: Any) -> np.ndarray:
    flat_data, _header = load_fits(flat_path)
    bias_subtracted = np.asarray(flat_data, dtype=float) - np.asarray(master_bias, dtype=float)
    median = np.nanmedian(bias_subtracted)
    if not np.isfinite(median) or median == 0:
        raise ValueError(f"Flat frame has an invalid bias-subtracted median: {flat_path}")
    return bias_subtracted / median


def run_pipeline_diagnostics(
    *,
    bias_files: list[Path],
    flat_files: dict[str, list[Path]],
    science_files: dict[str, list[Path]],
    master_bias: Any,
    master_bias_path: Path,
    master_flats: dict[str, Any],
    master_flat_paths: dict[str, Path],
    stacked_images: dict[str, Any],
    stacked_paths: dict[str, Path],
    output_dir: Path,
    config: dict[str, Any] | None = None,
) -> list[Path]:
    """Create calibration/stacking diagnostic plots and ``pixel_statistics.csv``."""
    options = {**DEFAULT_DIAGNOSTIC_CONFIG, **(config or {})}
    output_dir.mkdir(parents=True, exist_ok=True)
    seed = options["random_seed"]
    plot_kwargs = {
        "bins": int(options["bins"]),
        "lower_percentile": float(options["lower_percentile"]),
        "upper_percentile": float(options["upper_percentile"]),
        "max_pixels": int(options["max_pixels"]),
        "random_seed": None if seed is None else int(seed),
    }

    written: list[Path] = []
    records: list[dict[str, Any]] = []

    bias_path = select_random_file(bias_files, seed)
    raw_bias, _header = load_fits(bias_path)
    plot_path = output_dir / "bias_random_vs_master_hist.png"
    plot_histogram_comparison(
        raw_bias,
        master_bias,
        first_label="random raw bias",
        second_label="master bias",
        title="Bias diagnostic: random raw bias vs master bias",
        output_path=plot_path,
        **plot_kwargs,
    )
    written.append(plot_path)
    records.extend(
        [
            compute_pixel_statistics(raw_bias, stage="bias", label="random raw bias", source_path=bias_path),
            compute_pixel_statistics(master_bias, stage="bias", label="master bias", source_path=master_bias_path),
        ]
    )

    for filter_name in sorted(science_files):
        flat_path = select_random_file(flat_files[filter_name], seed)
        normalized_flat = _normalized_flat_from_file(flat_path, master_bias)
        master_flat = master_flats[filter_name]
        plot_path = output_dir / f"flat_{filter_name}_random_vs_master_hist.png"
        plot_histogram_comparison(
            normalized_flat,
            master_flat,
            first_label="random flat after bias subtraction + normalization",
            second_label="master flat",
            title=f"Flat diagnostic ({filter_name}): normalized random flat vs master flat",
            output_path=plot_path,
            **plot_kwargs,
        )
        written.append(plot_path)
        records.extend(
            [
                compute_pixel_statistics(normalized_flat, stage="flat", filter_name=filter_name, label="random normalized flat", source_path=flat_path),
                compute_pixel_statistics(master_flat, stage="flat", filter_name=filter_name, label="master flat", source_path=master_flat_paths[filter_name]),
            ]
        )

        science_path = select_random_file(science_files[filter_name], seed)
        raw_science, _header = load_fits(science_path)
        calibrated_science = calibrate_science_image(raw_science, master_bias, master_flat)
        plot_path = output_dir / f"science_{filter_name}_before_after_calibration_hist.png"
        plot_histogram_comparison(
            raw_science,
            calibrated_science,
            first_label="raw science",
            second_label="calibrated science",
            title=f"Science calibration diagnostic ({filter_name}): raw vs calibrated",
            output_path=plot_path,
            **plot_kwargs,
        )
        written.append(plot_path)
        records.extend(
            [
                compute_pixel_statistics(raw_science, stage="science_calibration", filter_name=filter_name, label="raw science", source_path=science_path),
                compute_pixel_statistics(calibrated_science, stage="science_calibration", filter_name=filter_name, label="calibrated science", source_path=science_path),
            ]
        )

        plot_path = output_dir / f"science_{filter_name}_calibrated_vs_stacked_hist.png"
        plot_histogram_comparison(
            calibrated_science,
            stacked_images[filter_name],
            first_label="calibrated science",
            second_label="stacked science",
            title=f"Stacking diagnostic ({filter_name}): calibrated frame vs stacked image",
            output_path=plot_path,
            **plot_kwargs,
        )
        written.append(plot_path)
        records.extend(
            [
                compute_pixel_statistics(calibrated_science, stage="stacking", filter_name=filter_name, label="calibrated science", source_path=science_path),
                compute_pixel_statistics(stacked_images[filter_name], stage="stacking", filter_name=filter_name, label="stacked science", source_path=stacked_paths[filter_name]),
            ]
        )

    statistics_path = output_dir / "pixel_statistics.csv"
    _write_statistics_csv(records, statistics_path)
    written.append(statistics_path)
    return written
