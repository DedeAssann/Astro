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

BIAS_FRAME_STATISTICS_FIELDNAMES = [
    "file",
    "mean",
    "median",
    "std",
    "min",
    "max",
    "p1",
    "p99",
    "finite_fraction",
    "shape",
    "EXPTIME",
    "GAIN",
    "OFFSET",
    "CCD-TEMP",
    "TEMP",
    "DATE-OBS",
]

FLAT_FRAME_STATISTICS_FIELDNAMES = [
    "file",
    "filter",
    "EXPTIME",
    "mean",
    "median",
    "std",
    "min",
    "max",
    "p1",
    "p99",
    "finite_fraction",
    "shape",
]

DEFAULT_CALIBRATION_QC_CONFIG = {
    "enabled": False,
    "bias": {
        "enabled": True,
        "group_tolerance_adu": 5.0,
        "reject_outliers": False,
    },
    "flats": {
        "enabled": True,
        "linear_fit_threshold_seconds": 4.0,
        "saturation_adu": None,
        "max_mean_fraction_of_saturation": 0.8,
        "reject_non_linear": False,
    },
}

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



def write_bias_frame_statistics_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    """Write per-bias-frame statistics to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=BIAS_FRAME_STATISTICS_FIELDNAMES)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in BIAS_FRAME_STATISTICS_FIELDNAMES})


def _autoscaled_y_limits(values: np.ndarray) -> tuple[float, float]:
    finite_values = values[np.isfinite(values)]
    if finite_values.size == 0:
        return 0.0, 1.0
    lower = float(np.min(finite_values))
    upper = float(np.max(finite_values))
    if lower == upper:
        padding = max(abs(lower) * 0.01, 1.0)
    else:
        padding = (upper - lower) * 0.10
    return lower - padding, upper + padding


def plot_bias_frame_mean_distribution(
    records: list[dict[str, Any]],
    *,
    master_bias: Any,
    output_path: Path,
) -> None:
    """Plot per-bias-frame mean/median ADU with master-bias reference lines."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    indices = np.arange(len(records))
    means = np.asarray([record["mean"] for record in records], dtype=float)
    medians = np.asarray([record["median"] for record in records], dtype=float)
    master_stats = compute_pixel_statistics(master_bias)
    master_mean = float(master_stats["mean"])
    master_median = float(master_stats["median"])

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(indices, means, marker="o", label="bias frame mean")
    ax.plot(indices, medians, marker="s", label="bias frame median")
    if np.isfinite(master_mean):
        ax.axhline(master_mean, color="C0", linestyle="--", linewidth=1.5, label=f"master bias mean={master_mean:.4g}")
    if np.isfinite(master_median):
        ax.axhline(master_median, color="C1", linestyle="--", linewidth=1.5, label=f"master bias median={master_median:.4g}")

    all_y_values = np.concatenate([means, medians, np.asarray([master_mean, master_median])])
    ax.set_ylim(*_autoscaled_y_limits(all_y_values))
    ax.set_xlabel("Bias frame index")
    ax.set_ylabel("ADU")
    ax.set_title("Bias frame mean/median distribution")
    ax.set_xticks(indices)
    ax.set_xticklabels([Path(record["file"]).name for record in records], rotation=45, ha="right")
    ax.legend(fontsize="small")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


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
    normalize_before_stack: bool = False,
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

    bias_frame_records = compute_bias_frame_statistics(bias_files)
    bias_statistics_path = output_dir / "bias_frame_statistics.csv"
    write_bias_frame_statistics_csv(bias_frame_records, bias_statistics_path)
    written.append(bias_statistics_path)

    bias_distribution_path = output_dir / "bias_frame_mean_distribution.png"
    plot_bias_frame_mean_distribution(
        bias_frame_records,
        master_bias=master_bias,
        output_path=bias_distribution_path,
    )
    written.append(bias_distribution_path)

    normalization_label = "enabled" if normalize_before_stack else "disabled"

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

        if normalize_before_stack:
            normalized_science = calibrated_science / np.nanmedian(calibrated_science)
            plot_path = output_dir / f"science_{filter_name}_calibrated_vs_normalized_hist.png"
            plot_histogram_comparison(
                calibrated_science,
                normalized_science,
                first_label="calibrated science",
                second_label="median-normalized calibrated science",
                title=f"Stacking normalization diagnostic ({filter_name}): calibrated vs median-normalized",
                output_path=plot_path,
                **plot_kwargs,
            )
            written.append(plot_path)
            records.extend(
                [
                    compute_pixel_statistics(calibrated_science, stage="stacking_normalization", filter_name=filter_name, label="calibrated science", source_path=science_path),
                    compute_pixel_statistics(normalized_science, stage="stacking_normalization", filter_name=filter_name, label="median-normalized calibrated science", source_path=science_path),
                ]
            )

        plot_path = output_dir / f"science_{filter_name}_calibrated_vs_stacked_hist.png"
        plot_histogram_comparison(
            calibrated_science,
            stacked_images[filter_name],
            first_label="calibrated science",
            second_label="stacked science",
            title=(
                f"Stacking diagnostic ({filter_name}): calibrated frame vs stacked image "
                f"(median normalization {normalization_label})"
            ),
            output_path=plot_path,
            **plot_kwargs,
        )
        written.append(plot_path)
        records.extend(
            [
                compute_pixel_statistics(calibrated_science, stage="stacking", filter_name=filter_name, label="calibrated science", source_path=science_path),
                compute_pixel_statistics(
                    stacked_images[filter_name],
                    stage="stacking",
                    filter_name=filter_name,
                    label=f"stacked science (median normalization {normalization_label})",
                    source_path=stacked_paths[filter_name],
                ),
            ]
        )

    statistics_path = output_dir / "pixel_statistics.csv"
    _write_statistics_csv(records, statistics_path)
    written.append(statistics_path)
    return written


def _header_value(header: Any, *keys: str) -> Any:
    """Return the first present FITS header value from ``keys``."""
    if header is None:
        return ""
    for key in keys:
        try:
            value = header.get(key, "")
        except AttributeError:
            value = ""
        if value not in (None, ""):
            return value
    return ""


def _shape_label(array: Any) -> str:
    """Return a compact, CSV-friendly image-shape label."""
    return "x".join(str(item) for item in np.shape(array))


def _frame_stats_record(path: Path, data: Any, header: Any, *, filter_name: str | None = None) -> dict[str, Any]:
    stats = compute_pixel_statistics(data, source_path=path, filter_name=filter_name)
    record: dict[str, Any] = {
        "file": str(path),
        "mean": stats["mean"],
        "median": stats["median"],
        "std": stats["std"],
        "min": stats["min"],
        "max": stats["max"],
        "p1": stats["p1"],
        "p99": stats["p99"],
        "finite_fraction": stats["finite_fraction"],
        "shape": _shape_label(data),
    }
    if filter_name is not None:
        record["filter"] = filter_name
    return record


def compute_bias_frame_statistics(bias_files: list[Path] | tuple[Path, ...]) -> list[dict[str, Any]]:
    """Compute finite-pixel statistics and acquisition metadata for every bias frame."""
    records: list[dict[str, Any]] = []
    for bias_path in sorted(Path(path) for path in bias_files):
        bias_data, header = load_fits(bias_path)
        record = _frame_stats_record(bias_path, bias_data, header)
        record.update(
            {
                "EXPTIME": _header_value(header, "EXPTIME"),
                "GAIN": _header_value(header, "GAIN"),
                "OFFSET": _header_value(header, "OFFSET"),
                "CCD-TEMP": _header_value(header, "CCD-TEMP"),
                "TEMP": _header_value(header, "TEMP"),
                "DATE-OBS": _header_value(header, "DATE-OBS"),
            }
        )
        records.append(record)
    return records


def compute_flat_frame_statistics(flat_files: dict[str, list[Path]] | dict[str, tuple[Path, ...]]) -> list[dict[str, Any]]:
    """Compute finite-pixel statistics and exposure metadata for every flat frame."""
    records: list[dict[str, Any]] = []
    for filter_name in sorted(flat_files):
        for flat_path in sorted(Path(path) for path in flat_files[filter_name]):
            flat_data, header = load_fits(flat_path)
            record = _frame_stats_record(flat_path, flat_data, header, filter_name=filter_name)
            record["EXPTIME"] = _header_value(header, "EXPTIME")
            records.append(record)
    return records


def write_flat_frame_statistics_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    """Write per-flat-frame statistics to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FLAT_FRAME_STATISTICS_FIELDNAMES)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in FLAT_FRAME_STATISTICS_FIELDNAMES})


def detect_bias_regime_warnings(records: list[dict[str, Any]], group_tolerance_adu: float) -> list[str]:
    """Return warnings when per-frame bias means span multiple ADU regimes."""
    means = np.asarray([record.get("mean", np.nan) for record in records], dtype=float)
    means = means[np.isfinite(means)]
    if means.size == 0:
        return ["Bias QC could not compute finite means for any bias frame."]
    min_mean = float(np.min(means))
    max_mean = float(np.max(means))
    mean_range = max_mean - min_mean
    if mean_range > group_tolerance_adu:
        return [
            "Bias frames appear to contain multiple ADU regimes: "
            f"min mean={min_mean:.1f}, max mean={max_mean:.1f}, range={mean_range:.1f} ADU."
        ]
    return []


def _write_calibration_qc_messages(messages: list[str], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(messages)
    if text:
        text += "\n"
    output_path.write_text(text, encoding="utf-8")


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _sanitized_filter_name(filter_name: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in filter_name)


def plot_flat_linearity_curve(
    records: list[dict[str, Any]],
    *,
    filter_name: str,
    linear_fit_threshold_seconds: float,
    output_path: Path,
) -> list[str]:
    """Plot mean ADU vs EXPTIME and a short-exposure linear fit for one flat filter."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    filter_records = [record for record in records if record.get("filter") == filter_name]
    exposures = np.asarray([_safe_float(record.get("EXPTIME")) for record in filter_records], dtype=float)
    means = np.asarray([_safe_float(record.get("mean")) for record in filter_records], dtype=float)
    p99_values = np.asarray([_safe_float(record.get("p99")) for record in filter_records], dtype=float)
    valid = np.isfinite(exposures) & np.isfinite(means)
    warnings: list[str] = []

    if not np.all(np.isfinite(exposures)):
        missing_count = int(np.size(exposures) - np.count_nonzero(np.isfinite(exposures)))
        warnings.append(
            f"Flat QC for filter {filter_name} has {missing_count} frame(s) with missing or invalid EXPTIME; "
            "linearity fitting used only valid EXPTIME values."
        )

    order = np.argsort(exposures[valid]) if np.any(valid) else np.asarray([], dtype=int)
    valid_exposures = exposures[valid][order] if np.any(valid) else np.asarray([], dtype=float)
    valid_means = means[valid][order] if np.any(valid) else np.asarray([], dtype=float)
    linear_mask = valid_exposures <= linear_fit_threshold_seconds
    linear_exposures = valid_exposures[linear_mask]
    linear_means = valid_means[linear_mask]

    slope = float("nan")
    intercept = float("nan")
    if linear_exposures.size >= 2:
        slope, intercept = [float(value) for value in np.polyfit(linear_exposures, linear_means, 1)]
    else:
        warnings.append(
            f"Flat QC for filter {filter_name} has insufficient EXPTIME points in the linear region "
            f"(<= {linear_fit_threshold_seconds:g} s) for a fit."
        )

    max_mean = float(np.nanmax(means)) if means.size and np.any(np.isfinite(means)) else float("nan")
    max_p99 = float(np.nanmax(p99_values)) if p99_values.size and np.any(np.isfinite(p99_values)) else float("nan")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].plot(valid_exposures, valid_means, marker="o", linestyle="-", label="all flats")
    axes[0].set_title(f"Flat linearity ({filter_name})")
    axes[0].set_xlabel("EXPTIME (s)")
    axes[0].set_ylabel("Mean ADU")
    axes[0].grid(alpha=0.25)
    axes[0].legend(fontsize="small")

    axes[1].plot(linear_exposures, linear_means, marker="o", linestyle="", label="linear-region flats")
    if np.isfinite(slope) and np.isfinite(intercept) and linear_exposures.size:
        x_fit = np.linspace(float(np.min(linear_exposures)), float(np.max(linear_exposures)), 100)
        axes[1].plot(x_fit, slope * x_fit + intercept, linestyle="--", label="linear fit")
    axes[1].set_title(f"Linear fit: EXPTIME <= {linear_fit_threshold_seconds:g} s")
    axes[1].set_xlabel("EXPTIME (s)")
    axes[1].set_ylabel("Mean ADU")
    axes[1].grid(alpha=0.25)
    axes[1].legend(fontsize="small")
    axes[1].text(
        0.03,
        0.97,
        "\n".join(
            [
                f"slope={slope:.4g}",
                f"intercept={intercept:.4g}",
                f"max mean={max_mean:.4g} ADU",
                f"max p99={max_p99:.4g} ADU",
                f"n linear={linear_exposures.size}",
            ]
        ),
        transform=axes[1].transAxes,
        va="top",
        ha="left",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8},
        fontsize="small",
    )
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return warnings


def _flat_qc_messages(
    records: list[dict[str, Any]],
    *,
    saturation_adu: float | None,
    max_mean_fraction_of_saturation: float,
) -> list[str]:
    messages: list[str] = []
    for filter_name in sorted({str(record.get("filter", "")) for record in records}):
        filter_records = [record for record in records if record.get("filter") == filter_name]
        means = np.asarray([_safe_float(record.get("mean")) for record in filter_records], dtype=float)
        p99_values = np.asarray([_safe_float(record.get("p99")) for record in filter_records], dtype=float)
        max_mean = float(np.nanmax(means)) if means.size and np.any(np.isfinite(means)) else float("nan")
        max_p99 = float(np.nanmax(p99_values)) if p99_values.size and np.any(np.isfinite(p99_values)) else float("nan")
        if saturation_adu is None:
            messages.append(f"Flat QC filter {filter_name}: max mean={max_mean:.1f} ADU, max p99={max_p99:.1f} ADU.")
            continue
        threshold = max_mean_fraction_of_saturation * saturation_adu
        if np.isfinite(max_mean) and max_mean > threshold:
            messages.append(
                f"Flat frames for filter {filter_name} exceed the configured saturation safety threshold: "
                f"max mean={max_mean:.1f} ADU, threshold={threshold:.1f} ADU "
                f"({max_mean_fraction_of_saturation:.2g} x saturation_adu={saturation_adu:.1f})."
            )
    return messages


def select_linear_flat_files(flat_records: list[dict[str, Any]], linear_fit_threshold_seconds: float) -> dict[str, list[Path]]:
    """Return flat files with valid EXPTIME values inside the configured linear region."""
    selected: dict[str, list[Path]] = {}
    for record in flat_records:
        exptime = _safe_float(record.get("EXPTIME"))
        if np.isfinite(exptime) and exptime <= linear_fit_threshold_seconds:
            selected.setdefault(str(record["filter"]), []).append(Path(record["file"]))
    return {filter_name: sorted(paths) for filter_name, paths in selected.items()}


def run_calibration_qc(
    *,
    bias_files: list[Path],
    flat_files: dict[str, list[Path]],
    master_bias: Any,
    output_dir: Path,
    config: dict[str, Any] | None = None,
) -> tuple[list[Path], list[str], list[Path], dict[str, list[Path]]]:
    """Run V2.7 calibration-frame QC and return written files plus optional filtered inputs."""
    options = {**DEFAULT_CALIBRATION_QC_CONFIG, **(config or {})}
    bias_options = {**DEFAULT_CALIBRATION_QC_CONFIG["bias"], **options.get("bias", {})}
    flat_options = {**DEFAULT_CALIBRATION_QC_CONFIG["flats"], **options.get("flats", {})}
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    messages: list[str] = []
    selected_bias_files = [Path(path) for path in bias_files]
    selected_flat_files = {name: [Path(path) for path in paths] for name, paths in flat_files.items()}

    if bias_options["enabled"]:
        bias_records = compute_bias_frame_statistics(bias_files)
        bias_csv = output_dir / "bias_frame_statistics.csv"
        write_bias_frame_statistics_csv(bias_records, bias_csv)
        written.append(bias_csv)
        bias_plot = output_dir / "bias_frame_mean_median_distribution.png"
        plot_bias_frame_mean_distribution(bias_records, master_bias=master_bias, output_path=bias_plot)
        written.append(bias_plot)
        messages.extend(detect_bias_regime_warnings(bias_records, float(bias_options["group_tolerance_adu"])))
        if bias_options.get("reject_outliers"):
            means = np.asarray([_safe_float(record.get("mean")) for record in bias_records], dtype=float)
            median_mean = float(np.nanmedian(means)) if np.any(np.isfinite(means)) else float("nan")
            kept = [
                Path(record["file"])
                for record in bias_records
                if np.isfinite(_safe_float(record.get("mean")))
                and abs(_safe_float(record.get("mean")) - median_mean) <= float(bias_options["group_tolerance_adu"])
            ]
            if kept:
                selected_bias_files = sorted(kept)
                messages.append(
                    f"Bias QC reject_outliers enabled: using {len(selected_bias_files)} of {len(bias_records)} bias frame(s)."
                )
            else:
                messages.append("Bias QC reject_outliers enabled but no frames passed; retaining all bias frames.")

    if flat_options["enabled"]:
        flat_records = compute_flat_frame_statistics(flat_files)
        flat_csv = output_dir / "flat_frame_statistics.csv"
        write_flat_frame_statistics_csv(flat_records, flat_csv)
        written.append(flat_csv)
        threshold = float(flat_options["linear_fit_threshold_seconds"])
        for filter_name in sorted(flat_files):
            flat_plot = output_dir / f"flat_{_sanitized_filter_name(filter_name)}_linearity_curve.png"
            messages.extend(
                plot_flat_linearity_curve(
                    flat_records,
                    filter_name=filter_name,
                    linear_fit_threshold_seconds=threshold,
                    output_path=flat_plot,
                )
            )
            written.append(flat_plot)
        saturation = flat_options.get("saturation_adu")
        saturation_value = None if saturation is None else float(saturation)
        messages.extend(
            _flat_qc_messages(
                flat_records,
                saturation_adu=saturation_value,
                max_mean_fraction_of_saturation=float(flat_options["max_mean_fraction_of_saturation"]),
            )
        )
        if flat_options.get("reject_non_linear"):
            linear_files = select_linear_flat_files(flat_records, threshold)
            for filter_name in selected_flat_files:
                if linear_files.get(filter_name):
                    selected_flat_files[filter_name] = linear_files[filter_name]
                    messages.append(
                        f"Flat QC reject_non_linear enabled for filter {filter_name}: "
                        f"using {len(linear_files[filter_name])} of {len(flat_files[filter_name])} flat frame(s)."
                    )
                else:
                    messages.append(
                        f"Flat QC reject_non_linear enabled for filter {filter_name} but no valid linear-region flats passed; "
                        "retaining all flat frames for this filter."
                    )

    warning_path = output_dir / "calibration_qc_warnings.txt"
    _write_calibration_qc_messages(messages, warning_path)
    written.append(warning_path)
    return written, messages, selected_bias_files, selected_flat_files
