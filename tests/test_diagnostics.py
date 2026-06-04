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


def test_bias_frame_statistics_csv_and_distribution_plot(tmp_path, monkeypatch):
    from astro_image_lab import diagnostics

    bias_files = [tmp_path / "bias_2.fits", tmp_path / "bias_1.fits"]
    for path in bias_files:
        path.write_text("placeholder", encoding="utf-8")
    arrays = {
        bias_files[0]: np.array([[10.0, 12.0], [np.nan, np.inf]]),
        bias_files[1]: np.array([[20.0, 22.0], [24.0, 26.0]]),
    }

    monkeypatch.setattr(diagnostics, "load_fits", lambda path: (arrays[Path(path)], {}))

    records = diagnostics.compute_bias_frame_statistics(bias_files)
    csv_path = tmp_path / "bias_frame_statistics.csv"
    png_path = tmp_path / "bias_frame_mean_distribution.png"
    diagnostics.write_bias_frame_statistics_csv(records, csv_path)
    diagnostics.plot_bias_frame_mean_distribution(records, master_bias=np.array([[15.0, 17.0]]), output_path=png_path)

    assert [Path(record["file"]).name for record in records] == ["bias_1.fits", "bias_2.fits"]
    assert records[0]["mean"] == 23.0
    assert records[0]["finite_fraction"] == 1.0
    assert records[1]["mean"] == 11.0
    assert records[1]["finite_fraction"] == 0.5
    assert csv_path.exists()
    assert "file,mean,median,std,min,max,p1,p99,finite_fraction" in csv_path.read_text(encoding="utf-8")
    assert png_path.exists()
    assert png_path.read_bytes().startswith(b"\x89PNG")
