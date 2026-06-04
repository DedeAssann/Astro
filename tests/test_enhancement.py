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


def test_zscale_limits_returns_finite_ordered_limits_with_nonfinite_pixels():
    image = np.arange(100, dtype=float).reshape(10, 10)
    image[0, 0] = np.nan
    image[1, 1] = np.inf

    vmin, vmax = enhancement.zscale_limits(image, random_seed=123)

    assert np.isfinite(vmin)
    assert np.isfinite(vmax)
    assert vmin < vmax


def test_scale_to_limits_maps_to_unit_interval_and_zeroes_nonfinite_pixels():
    image = np.array([-1.0, 0.0, 5.0, 10.0, 12.0, np.nan, np.inf])

    scaled = enhancement.scale_to_limits(image, 0.0, 10.0)

    expected = np.array([0.0, 0.0, 0.5, 1.0, 1.0, 0.0, 0.0])
    np.testing.assert_allclose(scaled, expected)


def test_apply_display_scale_named_power_scales():
    assert enhancement.apply_display_scale(np.array([0.5]), scale="squared")[0] == pytest.approx(
        0.25
    )
    assert enhancement.apply_display_scale(np.array([0.5]), scale="cubed")[0] == pytest.approx(
        0.125
    )
    assert enhancement.apply_display_scale(np.array([0.25]), scale="sqrt")[0] == pytest.approx(
        0.5
    )


def test_crop_image_supports_2d_and_rgb_and_clips_edges():
    image = np.arange(25).reshape(5, 5)
    rgb = np.dstack([image, image + 100, image + 200])

    crop_2d = enhancement.crop_image(image, center=[0, 0], size=4)
    crop_rgb = enhancement.crop_image(rgb, center=[2, 2], size=3)

    assert crop_2d.shape == (2, 2)
    np.testing.assert_array_equal(crop_2d, image[:2, :2])
    assert crop_rgb.shape == (3, 3, 3)
    np.testing.assert_array_equal(crop_rgb[..., 0], image[1:4, 1:4])



def test_crop_image_uses_xy_center_as_col_row():
    image = np.arange(100).reshape(10, 10)

    crop = enhancement.crop_image(image, center=[7, 3], size=3)

    assert crop.shape == (3, 3)
    assert crop[1, 1] == image[3, 7]
    np.testing.assert_array_equal(crop, image[2:5, 6:9])


def test_make_display_rgb_returns_rgb_shape_and_range():
    red = np.arange(16, dtype=float).reshape(4, 4)
    green = red + 1
    blue = red + 2

    rgb = enhancement.make_display_rgb(
        red, green, blue, limits="percentile", scale="squared", lower=0, upper=100
    )

    assert rgb.shape == (4, 4, 3)
    assert np.all(np.isfinite(rgb))
    assert np.all((0 <= rgb) & (rgb <= 1))


def test_unsharp_mask_changes_synthetic_image_and_preserves_shape_and_range():
    image = np.zeros((7, 7), dtype=float)
    image[3, 3] = 1.0

    sharpened = enhancement.unsharp_mask(image, sigma=1.0, amount=0.8)

    assert sharpened.shape == image.shape
    assert np.all((0 <= sharpened) & (sharpened <= 1))
    assert not np.allclose(sharpened, image * 0)


def test_neutralize_rgb_background_makes_tinted_background_more_neutral():
    rgb = np.zeros((6, 6, 3), dtype=float)
    rgb[..., 0] = 0.10
    rgb[..., 1] = 0.20
    rgb[..., 2] = 0.40
    rgb[3, 3] = [0.8, 0.7, 0.6]

    neutralized = enhancement.neutralize_rgb_background(rgb, percentile=10, mode="equalize")
    backgrounds = [
        enhancement.estimate_channel_background(neutralized[..., channel], percentile=10)
        for channel in range(3)
    ]

    assert max(backgrounds) - min(backgrounds) < 1e-12
    assert np.all((0 <= neutralized) & (neutralized <= 1))


def test_balance_rgb_channels_avoids_division_by_zero():
    rgb = np.zeros((4, 4, 3), dtype=float)
    rgb[..., 0] = 0.0
    rgb[..., 1] = 0.2
    rgb[..., 2] = 0.4

    balanced = enhancement.balance_rgb_channels(rgb, method="background", percentile=10)

    assert balanced.shape == rgb.shape
    assert np.all(np.isfinite(balanced))
    assert np.all((0 <= balanced) & (balanced <= 1))


def test_make_display_rgb_with_color_balance_options_returns_valid_image():
    base = np.arange(25, dtype=float).reshape(5, 5)

    rgb = enhancement.make_display_rgb(
        base,
        base * 1.5,
        base * 2.0,
        limits="percentile",
        lower=0,
        upper=100,
        background_neutralization="equalize",
        background_percentile=10,
        color_balance="max",
    )

    assert rgb.shape == (5, 5, 3)
    assert np.all(np.isfinite(rgb))
    assert np.all((0 <= rgb) & (rgb <= 1))


def test_full_and_crop_balance_regions_use_different_channel_factors():
    rgb = np.full((8, 8, 3), 0.1, dtype=float)
    rgb[2:6, 2:6, 1] = 0.8
    crop = enhancement.crop_image(rgb, center=[3.5, 3.5], size=4)

    _full_backgrounds, full_factors = enhancement.rgb_color_adjustment_factors(
        rgb,
        percentile=10,
        background_neutralization="none",
        color_balance="background",
    )
    _crop_backgrounds, crop_factors = enhancement.rgb_color_adjustment_factors(
        crop,
        percentile=10,
        background_neutralization="none",
        color_balance="background",
    )

    assert not np.allclose(full_factors, crop_factors)
    np.testing.assert_allclose(full_factors, np.ones(3))
    assert crop_factors[1] < full_factors[1]


def test_make_processed_rgb_balance_region_full_differs_from_crop_region():
    red = np.full((8, 8), 0.1, dtype=float)
    green = np.full((8, 8), 0.1, dtype=float)
    blue = np.full((8, 8), 0.1, dtype=float)
    green[2:6, 2:6] = 0.8

    full_balanced = enhancement.make_processed_rgb(
        red,
        green,
        blue,
        limits="percentile",
        lower=0,
        upper=100,
        scale="linear",
        crop_center=[3.5, 3.5],
        crop_size=4,
        background_neutralization="none",
        color_balance="background",
        balance_region="full",
    )
    crop_balanced = enhancement.make_processed_rgb(
        red,
        green,
        blue,
        limits="percentile",
        lower=0,
        upper=100,
        scale="linear",
        crop_center=[3.5, 3.5],
        crop_size=4,
        background_neutralization="none",
        color_balance="background",
        balance_region="crop",
    )

    assert not np.allclose(full_balanced, crop_balanced)


def test_color_balance_strength_blends_factors_toward_one():
    factors = np.array([0.5, 1.0, 2.0])

    np.testing.assert_allclose(
        enhancement.effective_rgb_channel_balance_factors(factors, color_balance_strength=0.0),
        np.ones(3),
    )
    np.testing.assert_allclose(
        enhancement.effective_rgb_channel_balance_factors(factors, color_balance_strength=1.0),
        factors,
    )
    np.testing.assert_allclose(
        enhancement.effective_rgb_channel_balance_factors(factors, color_balance_strength=0.5),
        np.array([0.75, 1.0, 1.5]),
    )


def test_channel_scales_modify_rgb_after_automatic_balance():
    rgb = np.ones((2, 2, 3), dtype=float) * 0.5

    scaled = enhancement.balance_rgb_channels(
        rgb,
        method="none",
        channel_scales=(1.0, 0.5, 1.5),
    )

    np.testing.assert_allclose(scaled[..., 0], 0.5)
    np.testing.assert_allclose(scaled[..., 1], 0.25)
    np.testing.assert_allclose(scaled[..., 2], 0.75)


def test_color_balance_strength_and_channel_scales_validate_ranges():
    with pytest.raises(ValueError, match="color_balance_strength"):
        enhancement.effective_rgb_channel_balance_factors(np.ones(3), color_balance_strength=-0.1)
    with pytest.raises(ValueError, match="channel_scales"):
        enhancement.balance_rgb_channels(np.ones((2, 2, 3)), method="none", channel_scales=(1, 0, 1))


def test_make_processed_rgb_contrast_region_crop_estimates_limits_from_crop(monkeypatch):
    red = np.arange(100, dtype=float).reshape(10, 10)
    green = red + 100
    blue = red + 200
    calls = []

    def fake_limits(channel, limits, lower, upper, zscale_contrast):
        calls.append(np.asarray(channel).shape)
        return float(np.nanmin(channel)), float(np.nanmax(channel))

    monkeypatch.setattr(enhancement, "_limits_for_channel", fake_limits)

    enhancement.make_processed_rgb(
        red,
        green,
        blue,
        limits="percentile",
        scale="linear",
        crop_center=[5, 5],
        crop_size=4,
        contrast_region="crop",
        balance_region="crop",
    )

    assert calls == [(4, 4), (4, 4), (4, 4)]


def test_make_processed_rgb_balance_region_full_estimates_factors_from_full_when_cropped(monkeypatch):
    red = np.arange(100, dtype=float).reshape(10, 10)
    green = red + 100
    blue = red + 200
    reference_shapes = []
    original_apply = enhancement._apply_rgb_color_adjustments

    def spy_apply(rgb, *args, reference_rgb=None, **kwargs):
        reference_shapes.append(np.asarray(reference_rgb).shape)
        return original_apply(rgb, *args, reference_rgb=reference_rgb, **kwargs)

    monkeypatch.setattr(enhancement, "_apply_rgb_color_adjustments", spy_apply)

    enhancement.make_processed_rgb(
        red,
        green,
        blue,
        limits="percentile",
        lower=0,
        upper=100,
        scale="linear",
        crop_center=[5, 5],
        crop_size=4,
        contrast_region="crop",
        balance_region="full",
        background_neutralization="equalize",
        color_balance="background",
    )

    assert reference_shapes == [(10, 10, 3)]


def test_masked_unsharp_preserves_dark_background_more_than_raw_unsharp():
    rgb = np.zeros((21, 21, 3), dtype=float)
    rgb[8:13, 8:13, :] = 0.45
    rgb[10, 10, :] = 0.7
    rgb[0, 0, :] = 0.08

    raw = enhancement.unsharp_mask(rgb, sigma=1.0, amount=0.8)
    masked = enhancement.masked_unsharp_mask(
        rgb,
        sigma=1.0,
        amount=0.8,
        mask_percentile=95,
        mask_softness=0.0,
    )

    np.testing.assert_allclose(masked[0, 0], rgb[0, 0])
    assert not np.allclose(raw[10, 10], rgb[10, 10])
    assert not np.allclose(masked[10, 10], rgb[10, 10])


def test_signal_mask_validates_percentile_and_softness():
    rgb = np.ones((2, 2, 3), dtype=float)

    with pytest.raises(ValueError, match="percentile"):
        enhancement.signal_mask_from_luminance(rgb, percentile=101)
    with pytest.raises(ValueError, match="softness"):
        enhancement.signal_mask_from_luminance(rgb, softness=-1)
