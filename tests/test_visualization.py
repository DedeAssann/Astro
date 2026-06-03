from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astro_image_lab import visualization


def test_scale_image_percentile_clips_to_unit_range_and_handles_nan():
    image = np.array([[0, 1, np.nan], [2, 3, np.inf]], dtype=float)

    scaled = visualization.scale_image_percentile(image, lower=0, upper=100)

    assert scaled.shape == image.shape
    assert np.all(np.isfinite(scaled))
    assert scaled.min() >= 0
    assert scaled.max() <= 1
    assert scaled[0, 2] == 0
    assert scaled[1, 2] == 0
    np.testing.assert_allclose(
        scaled[:2, :2],
        np.array([[0, 1 / 3], [2 / 3, 1]], dtype=float),
    )


def test_scale_image_percentile_returns_zeros_for_all_nan_or_constant_image():
    all_nan = np.full((2, 3), np.nan)
    constant = np.full((2, 3), 5.0)

    np.testing.assert_array_equal(
        visualization.scale_image_percentile(all_nan),
        np.zeros((2, 3)),
    )
    np.testing.assert_array_equal(
        visualization.scale_image_percentile(constant),
        np.zeros((2, 3)),
    )


def test_make_rgb_image_stacks_scaled_channels():
    red = np.array([[0, 1], [2, 3]], dtype=float)
    green = np.array([[3, 2], [1, 0]], dtype=float)
    blue = np.array([[np.nan, 10], [20, 30]], dtype=float)

    rgb = visualization.make_rgb_image(red, green, blue, lower=0, upper=100)

    assert rgb.shape == (2, 2, 3)
    assert np.all(np.isfinite(rgb))
    assert rgb.min() >= 0
    assert rgb.max() <= 1
    np.testing.assert_allclose(rgb[..., 0], red / 3)
    np.testing.assert_allclose(rgb[..., 1], green / 3)
    np.testing.assert_allclose(rgb[..., 2], np.array([[0, 0], [0.5, 1]], dtype=float))


def test_plotting_functions_save_files(tmp_path):
    image = np.arange(16, dtype=float).reshape(4, 4)
    image[0, 0] = np.nan

    image_path = tmp_path / "image.png"
    hist_path = tmp_path / "hist.png"
    compare_path = tmp_path / "compare.png"

    fig_image = visualization.plot_image(
        image,
        title="Image",
        log_scale=True,
        output_path=image_path,
    )
    fig_hist = visualization.plot_histogram(
        image,
        title="Histogram",
        output_path=hist_path,
        bins=5,
    )
    fig_compare = visualization.compare_images(image, image + 1, output_path=compare_path)

    try:
        assert image_path.exists() and image_path.stat().st_size > 0
        assert hist_path.exists() and hist_path.stat().st_size > 0
        assert compare_path.exists() and compare_path.stat().st_size > 0
        assert fig_image.__class__.__name__ == "Figure"
        assert fig_hist.__class__.__name__ == "Figure"
        assert fig_compare.__class__.__name__ == "Figure"
    finally:
        plt.close(fig_image)
        plt.close(fig_hist)
        plt.close(fig_compare)
