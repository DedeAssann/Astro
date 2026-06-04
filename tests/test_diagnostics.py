from pathlib import Path
import sys

import numpy as np

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astro_image_lab.diagnostics import (
    compute_histogram_x_limits,
    compute_pixel_statistics,
    plot_histogram_comparison,
    select_random_file,
)


def test_compute_pixel_statistics_ignores_nan_and_inf():
    stats = compute_pixel_statistics(
        np.array([1.0, 2.0, np.nan, np.inf, -np.inf, 5.0]),
        stage="science",
        filter_name="red",
        label="sample",
        source_path="sample.fits",
    )

    assert stats["stage"] == "science"
    assert stats["filter"] == "red"
    assert stats["label"] == "sample"
    assert stats["source_path"] == "sample.fits"
    assert stats["n_finite"] == 3
    assert stats["finite_fraction"] == 0.5
    assert stats["mean"] == np.mean([1.0, 2.0, 5.0])
    assert stats["median"] == 2.0
    assert stats["min"] == 1.0
    assert stats["max"] == 5.0


def test_compute_histogram_x_limits_uses_percentiles():
    first = np.array([0.0, 10.0, 20.0])
    second = np.array([30.0, 40.0, 1000.0])

    lower, upper = compute_histogram_x_limits(
        first,
        second,
        lower_percentile=0,
        upper_percentile=50,
    )

    assert lower == 0.0
    assert upper == 25.0


def test_plot_histogram_comparison_writes_png(tmp_path):
    output_path = tmp_path / "diagnostic.png"

    plot_histogram_comparison(
        np.arange(20, dtype=float),
        np.arange(20, 40, dtype=float),
        first_label="before",
        second_label="after",
        title="Before vs after",
        output_path=output_path,
        bins=10,
        max_pixels=100,
        random_seed=7,
    )

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes().startswith(b"\x89PNG")


def test_select_random_file_is_deterministic_and_sorts_paths(tmp_path):
    paths = [tmp_path / "c.fits", tmp_path / "a.fits", tmp_path / "b.fits"]
    for path in paths:
        path.write_text("placeholder", encoding="utf-8")

    first = select_random_file(paths, random_seed=42)
    second = select_random_file(list(reversed(paths)), random_seed=42)

    assert first == second
    assert first in paths
