import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astro_image_lab import enhancement


def test_estimate_background_uses_only_finite_pixels():
    image = np.array([0.0, 10.0, np.nan, np.inf, -np.inf, 20.0])

    assert enhancement.estimate_background(image, percentile=50) == pytest.approx(10.0)


def test_estimate_background_returns_zero_for_all_nonfinite_pixels():
    image = np.array([[np.nan, np.inf], [-np.inf, np.nan]])

    assert enhancement.estimate_background(image) == 0.0


def test_subtract_background_preserves_nonfinite_pixels():
    image = np.array([[10.0, 20.0], [np.nan, np.inf]])

    result = enhancement.subtract_background(image, percentile=50)

    assert result[0, 0] == pytest.approx(-5.0)
    assert result[0, 1] == pytest.approx(5.0)
    assert np.isnan(result[1, 0])
    assert np.isposinf(result[1, 1])


def test_normalize_channel_scales_finite_pixels_and_zeroes_nonfinite_pixels():
    image = np.array([[0.0, 5.0, 10.0], [np.nan, np.inf, -np.inf]])

    result = enhancement.normalize_channel(image, lower=0, upper=100)

    expected = np.array([[0.0, 0.5, 1.0], [0.0, 0.0, 0.0]])
    np.testing.assert_allclose(result, expected)


def test_normalize_channel_is_robust_to_constant_and_all_nan_images():
    np.testing.assert_allclose(
        enhancement.normalize_channel(np.full((2, 2), 7.0)),
        np.zeros((2, 2)),
    )
    np.testing.assert_allclose(
        enhancement.normalize_channel(np.full((2, 2), np.nan)),
        np.zeros((2, 2)),
    )


def test_normalize_channel_validates_percentile_order():
    with pytest.raises(ValueError, match="lower percentile"):
        enhancement.normalize_channel(np.arange(3), lower=99, upper=1)


def test_asinh_stretch_clips_output_and_boosts_faint_values():
    image = np.array([-1.0, 0.0, 0.1, 1.0, np.nan, np.inf])

    result = enhancement.asinh_stretch(image, stretch=5.0)

    assert result.shape == image.shape
    assert np.all((0.0 <= result) & (result <= 1.0))
    assert result[2] > image[2]
    assert result[3] == pytest.approx(1.0)
    assert result[4] == pytest.approx(0.0)
    assert result[5] == pytest.approx(1.0)


def test_asinh_stretch_validates_stretch():
    with pytest.raises(ValueError, match="stretch"):
        enhancement.asinh_stretch(np.ones((2, 2)), stretch=0)


def test_gamma_correct_validates_gamma_and_preserves_range():
    image = np.array([0.0, 0.25, 1.0, np.nan, np.inf, -np.inf])

    result = enhancement.gamma_correct(image, gamma=2.0)

    expected = np.array([0.0, 0.5, 1.0, 0.0, 1.0, 0.0])
    np.testing.assert_allclose(result, expected)
    with pytest.raises(ValueError, match="gamma"):
        enhancement.gamma_correct(image, gamma=0)


def test_make_enhanced_rgb_returns_rgb_shape_and_range_with_nonfinite_inputs():
    red = np.array([[0.0, 1.0], [2.0, np.nan]])
    green = np.array([[0.0, 2.0], [4.0, np.inf]])
    blue = np.array([[0.0, 3.0], [6.0, -np.inf]])

    rgb = enhancement.make_enhanced_rgb(
        red,
        green,
        blue,
        lower=0,
        upper=100,
        background_percentile=0,
        stretch=3.0,
        gamma=1.0,
        balance="percentile",
    )

    assert rgb.shape == (2, 2, 3)
    assert np.all(np.isfinite(rgb))
    assert np.all((0.0 <= rgb) & (rgb <= 1.0))


def test_make_enhanced_rgb_constant_channels_return_zero_image():
    rgb = enhancement.make_enhanced_rgb(
        np.ones((3, 3)),
        np.ones((3, 3)) * 2,
        np.ones((3, 3)) * 3,
    )

    np.testing.assert_allclose(rgb, np.zeros((3, 3, 3)))


def test_make_enhanced_rgb_validates_balance_mode():
    with pytest.raises(ValueError, match="balance"):
        enhancement.make_enhanced_rgb(
            np.arange(4).reshape(2, 2),
            np.ones((2, 2)),
            np.ones((2, 2)),
            balance="bad",
        )
