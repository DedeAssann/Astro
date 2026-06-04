"""Display-only enhancement helpers for astronomy image visualization.

These helpers operate on in-memory arrays intended for PNG previews and RGB
figures. They do not modify calibrated or stacked FITS products on disk.
"""

from __future__ import annotations

import numpy as np


_DISPLAY_SCALES = {"linear", "squared", "cubed", "sqrt", "log", "asinh", "gamma"}
_LIMIT_MODES = {"zscale", "percentile"}
_CHANNEL_MODES = {"per-channel", "global"}
_BACKGROUND_NEUTRALIZATION_MODES = {"none", "subtract", "equalize"}
_COLOR_BALANCE_METHODS = {"none", "background", "median", "max"}
_BALANCE_REGIONS = {"full", "crop"}


def _finite_values(image: np.ndarray) -> np.ndarray:
    """Return the finite values in ``image`` as a one-dimensional float array."""
    image = np.asarray(image, dtype=float)
    return image[np.isfinite(image)]


def _ordered_limits_from_values(values: np.ndarray) -> tuple[float, float]:
    """Return finite ordered fallback limits for a finite one-dimensional array."""
    if values.size == 0:
        return 0.0, 1.0
    vmin = float(np.nanmin(values))
    vmax = float(np.nanmax(values))
    if not np.isfinite(vmin) or not np.isfinite(vmax):
        return 0.0, 1.0
    if vmax <= vmin:
        padding = 0.5 if vmin == 0 else max(abs(vmin) * 0.01, 0.5)
        return vmin - padding, vmax + padding
    return vmin, vmax


def _percentile_limits(image, lower=0.5, upper=99.5) -> tuple[float, float]:
    """Return robust finite-pixel percentile limits with ordered fallback bounds."""
    if lower >= upper:
        raise ValueError("lower percentile must be less than upper percentile")
    values = _finite_values(image)
    if values.size == 0:
        return 0.0, 1.0
    vmin, vmax = np.nanpercentile(values, [lower, upper])
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        return _ordered_limits_from_values(values)
    return float(vmin), float(vmax)


def zscale_limits(image, contrast=0.25, samples=1000, random_seed=42) -> tuple[float, float]:
    """Estimate DS9-like zscale display limits from finite pixels.

    A deterministic random sample of finite pixels is sorted, fit with a line,
    and expanded around the sample median using ``contrast``. If fitting cannot
    produce finite ordered bounds, finite-pixel percentile limits are returned.
    """
    if contrast <= 0:
        raise ValueError("contrast must be greater than zero")
    if samples <= 0:
        raise ValueError("samples must be greater than zero")

    values = _finite_values(image)
    if values.size == 0:
        return 0.0, 1.0
    if values.size < 8:
        return _percentile_limits(values, lower=0.5, upper=99.5)

    rng = np.random.default_rng(random_seed)
    sample_size = min(int(samples), values.size)
    if sample_size < values.size:
        values = rng.choice(values, size=sample_size, replace=False)
    sample = np.sort(values.astype(float, copy=False))

    x = np.arange(sample.size, dtype=float)
    y = sample
    mask = np.isfinite(y)
    for _ in range(3):
        if np.count_nonzero(mask) < 2:
            return _percentile_limits(sample, lower=0.5, upper=99.5)
        slope, intercept = np.polyfit(x[mask], y[mask], 1)
        residuals = y - (slope * x + intercept)
        scatter = np.nanstd(residuals[mask])
        if not np.isfinite(scatter) or scatter == 0:
            break
        new_mask = np.abs(residuals) <= 2.5 * scatter
        if np.array_equal(new_mask, mask):
            break
        mask = new_mask

    if np.count_nonzero(mask) < 2:
        return _percentile_limits(sample, lower=0.5, upper=99.5)
    slope, intercept = np.polyfit(x[mask], y[mask], 1)
    if not np.isfinite(slope) or not np.isfinite(intercept) or slope == 0:
        return _percentile_limits(sample, lower=0.5, upper=99.5)

    center_index = (sample.size - 1) / 2.0
    median = float(np.median(sample))
    z1 = median + (0.0 - center_index) * slope / contrast
    z2 = median + (sample.size - 1 - center_index) * slope / contrast
    data_min, data_max = _ordered_limits_from_values(sample)
    vmin = max(min(z1, z2), data_min)
    vmax = min(max(z1, z2), data_max)
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        return _percentile_limits(sample, lower=0.5, upper=99.5)
    return float(vmin), float(vmax)


def scale_to_limits(image, vmin, vmax) -> np.ndarray:
    """Map ``image`` to ``[0, 1]`` using display limits and finite-safe clipping."""
    image = np.asarray(image, dtype=float)
    scaled = np.zeros_like(image, dtype=float)
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        return scaled
    finite_mask = np.isfinite(image)
    scaled[finite_mask] = (image[finite_mask] - vmin) / (vmax - vmin)
    return np.clip(scaled, 0.0, 1.0)


def apply_display_scale(image, scale="linear", gamma=1.0, stretch=5.0) -> np.ndarray:
    """Apply a display stretch to values expected in ``[0, 1]``.

    Supported scales are ``linear``, ``squared``, ``cubed``, ``sqrt``, ``log``,
    ``asinh``, and ``gamma``. Outputs are finite and clipped to ``[0, 1]``.
    """
    if scale not in _DISPLAY_SCALES:
        raise ValueError(f"scale must be one of {sorted(_DISPLAY_SCALES)}")
    if gamma <= 0:
        raise ValueError("gamma must be greater than zero")
    if scale in {"log", "asinh"} and stretch <= 0:
        raise ValueError("stretch must be greater than zero for log/asinh scales")

    x = np.asarray(image, dtype=float)
    x = np.nan_to_num(x, nan=0.0, posinf=1.0, neginf=0.0)
    x = np.clip(x, 0.0, 1.0)
    if scale == "linear":
        scaled = x
    elif scale == "squared":
        scaled = x**2
    elif scale == "cubed":
        scaled = x**3
    elif scale == "sqrt":
        scaled = np.sqrt(x)
    elif scale == "log":
        scaled = np.log1p(stretch * x) / np.log1p(stretch)
    elif scale == "asinh":
        scaled = np.arcsinh(stretch * x) / np.arcsinh(stretch)
    else:  # gamma
        scaled = x**gamma
    return np.clip(scaled, 0.0, 1.0)


def _fallback_gaussian_filter(image: np.ndarray, sigma: float) -> np.ndarray:
    """Small NumPy-only separable Gaussian-filter fallback."""
    if sigma == 0:
        return image.copy()
    radius = max(1, int(np.ceil(3.0 * sigma)))
    positions = np.arange(-radius, radius + 1, dtype=float)
    kernel = np.exp(-(positions**2) / (2.0 * sigma**2))
    kernel /= kernel.sum()

    def convolve_axis(array: np.ndarray, axis: int) -> np.ndarray:
        pad_width = [(0, 0)] * array.ndim
        pad_width[axis] = (radius, radius)
        padded = np.pad(array, pad_width, mode="edge")
        return np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="valid"), axis, padded)

    smoothed = image.astype(float, copy=True)
    smoothed = convolve_axis(smoothed, 0)
    smoothed = convolve_axis(smoothed, 1)
    return smoothed


def gaussian_smooth(image, sigma=0.8) -> np.ndarray:
    """Gaussian-smooth a 2D or RGB image while preserving its shape."""
    if sigma < 0:
        raise ValueError("sigma must be non-negative")
    array = np.asarray(image, dtype=float)
    if sigma == 0:
        return array.copy()
    try:
        from scipy.ndimage import gaussian_filter
    except ImportError:
        return _fallback_gaussian_filter(array, float(sigma))

    if array.ndim == 3 and array.shape[-1] in {3, 4}:
        sigma_spec = (float(sigma), float(sigma), 0.0)
    else:
        sigma_spec = float(sigma)
    return gaussian_filter(array, sigma=sigma_spec)


def unsharp_mask(image, sigma=2.0, amount=0.6) -> np.ndarray:
    """Sharpen a normalized image with unsharp masking and clip to ``[0, 1]``."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    array = np.asarray(image, dtype=float)
    safe = np.nan_to_num(array, nan=0.0, posinf=1.0, neginf=0.0)
    blurred = gaussian_smooth(safe, sigma=sigma)
    enhanced = safe + amount * (safe - blurred)
    return np.clip(enhanced, 0.0, 1.0)


def crop_bounds(image_shape, center, size) -> tuple[int, int, int, int]:
    """Return clipped crop bounds for a DS9-style ``[x, y]`` center.

    Parameters
    ----------
    image_shape : tuple
        Shape of a 2D image or RGB array. Only the first two dimensions are
        used as ``height, width``.
    center : sequence of float
        Zero-based image coordinates as ``[x, y]`` (column, row). This mirrors
        DS9's x/y order, while the returned bounds are NumPy row/column slices.
    size : float
        Requested square crop size in pixels. Bounds are clipped at image edges.

    Returns
    -------
    tuple[int, int, int, int]
        ``(row_start, row_stop, col_start, col_stop)`` suitable for NumPy
        slicing.
    """
    if len(image_shape) < 2:
        raise ValueError("image_shape must include height and width")
    if size <= 0:
        raise ValueError("size must be greater than zero")
    if len(center) != 2:
        raise ValueError("center must contain X and Y coordinates")

    height, width = int(image_shape[0]), int(image_shape[1])
    center_x, center_y = float(center[0]), float(center[1])
    crop_size = int(round(float(size)))
    if crop_size <= 0:
        raise ValueError("size must round to at least one pixel")

    # Use x/y image coordinates for the requested center, then convert to
    # NumPy row/column slices. Odd sizes put the center pixel in the middle;
    # even sizes are biased one pixel toward lower row/column indices.
    col_start = int(np.floor(center_x - (crop_size - 1) / 2.0))
    row_start = int(np.floor(center_y - (crop_size - 1) / 2.0))
    col_stop = col_start + crop_size
    row_stop = row_start + crop_size

    row_start = max(0, row_start)
    col_start = max(0, col_start)
    row_stop = max(row_start, min(height, row_stop))
    col_stop = max(col_start, min(width, col_stop))
    return row_start, row_stop, col_start, col_stop


def crop_image(image, center=None, size=None) -> np.ndarray:
    """Crop a 2D or RGB image using a zero-based ``[x, y]`` center.

    ``center`` is accepted as image/display coordinates ``[x, y]`` (column,
    row), matching DS9's coordinate order. Internally this is converted to NumPy
    ``row, col = y, x`` indexing. If ``center`` or ``size`` is omitted, the
    original image object is returned. Crop bounds are clipped safely at image
    edges.
    """
    array = np.asarray(image)
    if center is None or size is None:
        return array
    if array.ndim not in {2, 3}:
        raise ValueError("crop_image supports 2D grayscale or RGB-like arrays")

    row_start, row_stop, col_start, col_stop = crop_bounds(array.shape, center, size)
    if array.ndim == 3:
        return array[row_start:row_stop, col_start:col_stop, ...]
    return array[row_start:row_stop, col_start:col_stop]


def estimate_channel_background(channel, percentile=10) -> float:
    """Estimate one channel's finite-pixel display background percentile.

    Non-finite pixels are ignored. All-non-finite channels return ``0.0`` so
    color-neutralization steps can remain safe on masked or empty previews.
    """
    finite_values = _finite_values(channel)
    if finite_values.size == 0:
        return 0.0
    return float(np.percentile(finite_values, percentile))


def _as_rgb_array(rgb) -> np.ndarray:
    """Return a finite-safe RGB float array clipped to display range."""
    rgb = np.asarray(rgb, dtype=float)
    if rgb.ndim != 3 or rgb.shape[-1] != 3:
        raise ValueError("rgb must have shape (height, width, 3)")
    rgb = np.nan_to_num(rgb, nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip(rgb, 0.0, 1.0)


def _rgb_backgrounds(rgb: np.ndarray, percentile=10) -> np.ndarray:
    """Return finite display-background estimates for RGB channels."""
    return np.array(
        [
            estimate_channel_background(rgb[..., channel], percentile=percentile)
            for channel in range(3)
        ],
        dtype=float,
    )


def neutralize_rgb_background(rgb, percentile=10, mode="subtract") -> np.ndarray:
    """Neutralize RGB display backgrounds without modifying FITS data.

    ``subtract`` removes each channel's background estimate independently.
    ``equalize`` shifts channels so those estimates match their median value.
    ``none`` returns the finite-safe clipped RGB image unchanged.
    """
    if mode not in _BACKGROUND_NEUTRALIZATION_MODES:
        raise ValueError(f"mode must be one of {sorted(_BACKGROUND_NEUTRALIZATION_MODES)}")
    safe_rgb = _as_rgb_array(rgb)
    if mode == "none":
        return safe_rgb

    backgrounds = _rgb_backgrounds(safe_rgb, percentile=percentile)
    if mode == "subtract":
        neutralized = safe_rgb - backgrounds.reshape(1, 1, 3)
    else:  # equalize
        target = float(np.median(backgrounds[np.isfinite(backgrounds)]))
        neutralized = safe_rgb + (target - backgrounds).reshape(1, 1, 3)
    return np.clip(neutralized, 0.0, 1.0)


def _positive_channel_stat(channel: np.ndarray, method: str, percentile=10) -> float:
    """Return the statistic used for RGB channel balancing."""
    finite_values = channel[np.isfinite(channel)]
    if finite_values.size == 0:
        return 0.0
    if method == "background":
        statistic = np.percentile(finite_values, percentile)
    elif method == "median":
        statistic = np.median(finite_values)
    elif method == "max":
        statistic = np.percentile(finite_values, 99.5)
        if not np.isfinite(statistic) or statistic <= 0:
            statistic = np.max(finite_values)
    else:
        raise ValueError(f"method must be one of {sorted(_COLOR_BALANCE_METHODS)}")
    if not np.isfinite(statistic) or statistic <= 0:
        return 0.0
    return float(statistic)


def rgb_channel_balance_factors(rgb: np.ndarray, method="background", percentile=10) -> np.ndarray:
    """Return safe multiplicative channel factors for display RGB balancing."""
    if method not in _COLOR_BALANCE_METHODS:
        raise ValueError(f"method must be one of {sorted(_COLOR_BALANCE_METHODS)}")
    if method == "none":
        return np.ones(3, dtype=float)

    stats = np.array(
        [
            _positive_channel_stat(rgb[..., channel], method, percentile=percentile)
            for channel in range(3)
        ],
        dtype=float,
    )
    valid_stats = stats[np.isfinite(stats) & (stats > 0)]
    if valid_stats.size == 0:
        return np.ones(3, dtype=float)
    target = float(np.median(valid_stats))
    factors = np.ones(3, dtype=float)
    valid_mask = np.isfinite(stats) & (stats > 0)
    factors[valid_mask] = target / stats[valid_mask]
    return factors


def _validate_color_balance_strength(color_balance_strength: float) -> float:
    """Return a validated color-balance strength in ``[0, 1]``."""
    strength = float(color_balance_strength)
    if not np.isfinite(strength) or strength < 0 or strength > 1:
        raise ValueError("color_balance_strength must be between 0 and 1")
    return strength


def effective_rgb_channel_balance_factors(
    factors, color_balance_strength=1.0
) -> np.ndarray:
    """Blend full RGB balance factors toward one by ``color_balance_strength``."""
    strength = _validate_color_balance_strength(color_balance_strength)
    factors = np.asarray(factors, dtype=float)
    if factors.shape != (3,):
        raise ValueError("factors must contain red, green, and blue values")
    return 1.0 + strength * (factors - 1.0)


def _validate_channel_scales(channel_scales) -> np.ndarray:
    """Return positive manual RGB channel scales as a three-value array."""
    scales = np.asarray(channel_scales, dtype=float)
    if scales.shape != (3,):
        raise ValueError("channel_scales must contain red, green, and blue scales")
    if not np.all(np.isfinite(scales)) or np.any(scales <= 0):
        raise ValueError("channel_scales must be positive finite values")
    return scales


def balance_rgb_channels(
    rgb,
    method="background",
    percentile=10,
    color_balance_strength=1.0,
    channel_scales=(1.0, 1.0, 1.0),
) -> np.ndarray:
    """Balance RGB display channel levels and keep values in ``[0, 1]``.

    ``background`` scales channels so finite background percentiles match,
    ``median`` matches channel medians, ``max`` matches high-percentile highlight
    levels, and ``none`` leaves the finite-safe clipped RGB image unchanged.
    Channels with zero or invalid statistics receive a factor of one.
    ``color_balance_strength`` blends automatic factors toward one, and
    ``channel_scales`` applies manual red/green/blue multipliers after that.
    """
    safe_rgb = _as_rgb_array(rgb)
    factors = rgb_channel_balance_factors(safe_rgb, method=method, percentile=percentile)
    effective_factors = effective_rgb_channel_balance_factors(
        factors, color_balance_strength=color_balance_strength
    )
    manual_scales = _validate_channel_scales(channel_scales)
    total_factors = effective_factors * manual_scales
    return np.clip(safe_rgb * total_factors.reshape(1, 1, 3), 0.0, 1.0)


def _limits_for_channel(channel, limits, lower, upper, zscale_contrast) -> tuple[float, float]:
    if limits == "zscale":
        return zscale_limits(channel, contrast=zscale_contrast)
    if limits == "percentile":
        return _percentile_limits(channel, lower=lower, upper=upper)
    raise ValueError(f"limits must be one of {sorted(_LIMIT_MODES)}")


def _channel_limit_pairs(channels, limits, lower, upper, zscale_contrast, channel_mode):
    """Return per-channel display limits for three source channels."""
    if channel_mode == "global":
        combined = np.concatenate([_finite_values(channel) for channel in channels])
        vmin, vmax = _limits_for_channel(combined, limits, lower, upper, zscale_contrast)
        return [(vmin, vmax)] * 3
    return [
        _limits_for_channel(channel, limits, lower, upper, zscale_contrast)
        for channel in channels
    ]


def _scale_channels_to_rgb(channels, limit_pairs) -> np.ndarray:
    """Scale three channels to one linear RGB array using supplied limits."""
    scaled_channels = [
        scale_to_limits(channel, vmin, vmax)
        for channel, (vmin, vmax) in zip(channels, limit_pairs)
    ]
    return np.clip(np.dstack(scaled_channels), 0.0, 1.0)


def rgb_color_adjustment_factors(
    rgb,
    percentile=10,
    background_neutralization="none",
    color_balance="none",
) -> tuple[np.ndarray, np.ndarray]:
    """Return background estimates and balance factors for a normalized RGB array."""
    reference_rgb = _as_rgb_array(rgb)
    backgrounds = _rgb_backgrounds(reference_rgb, percentile=percentile)
    neutralized_reference = neutralize_rgb_background(
        reference_rgb,
        percentile=percentile,
        mode=background_neutralization,
    )
    factors = rgb_channel_balance_factors(
        neutralized_reference,
        method=color_balance,
        percentile=percentile,
    )
    return backgrounds, factors


def _apply_rgb_color_adjustments(
    rgb,
    percentile=10,
    background_neutralization="none",
    color_balance="none",
    color_balance_strength=1.0,
    channel_scales=(1.0, 1.0, 1.0),
    reference_rgb=None,
) -> np.ndarray:
    """Apply background neutralization and channel balance using a reference region."""
    target_rgb = _as_rgb_array(rgb)
    reference_rgb = target_rgb if reference_rgb is None else _as_rgb_array(reference_rgb)
    backgrounds, factors = rgb_color_adjustment_factors(
        reference_rgb,
        percentile=percentile,
        background_neutralization=background_neutralization,
        color_balance=color_balance,
    )

    if background_neutralization == "none":
        adjusted = target_rgb
    elif background_neutralization == "subtract":
        adjusted = target_rgb - backgrounds.reshape(1, 1, 3)
    elif background_neutralization == "equalize":
        target = float(np.median(backgrounds[np.isfinite(backgrounds)]))
        adjusted = target_rgb + (target - backgrounds).reshape(1, 1, 3)
    else:
        raise ValueError(
            f"background_neutralization must be one of {sorted(_BACKGROUND_NEUTRALIZATION_MODES)}"
        )
    adjusted = np.clip(adjusted, 0.0, 1.0)
    effective_factors = effective_rgb_channel_balance_factors(
        factors, color_balance_strength=color_balance_strength
    )
    manual_scales = _validate_channel_scales(channel_scales)
    total_factors = effective_factors * manual_scales
    return np.clip(adjusted * total_factors.reshape(1, 1, 3), 0.0, 1.0)


def make_display_rgb(
    red,
    green,
    blue,
    limits="zscale",
    scale="squared",
    zscale_contrast=0.25,
    lower=0.5,
    upper=99.5,
    gamma=1.0,
    stretch=5.0,
    channel_mode="per-channel",
    background_neutralization="none",
    background_percentile=10,
    color_balance="none",
    color_balance_strength=1.0,
    channel_scales=(1.0, 1.0, 1.0),
) -> np.ndarray:
    """Create a display-scaled RGB preview clipped to ``[0, 1]``.

    Processing order is: channel limit scaling, optional RGB background
    neutralization, optional channel balancing, display-scale transform, and
    final clipping. All steps are display-only and operate on normalized arrays.
    """
    if channel_mode not in _CHANNEL_MODES:
        raise ValueError(f"channel_mode must be one of {sorted(_CHANNEL_MODES)}")
    channels = [np.asarray(channel, dtype=float) for channel in (red, green, blue)]
    if any(channel.shape != channels[0].shape for channel in channels):
        raise ValueError("red, green, and blue channels must have matching shapes")

    limit_pairs = _channel_limit_pairs(
        channels, limits, lower, upper, zscale_contrast, channel_mode
    )
    rgb = _scale_channels_to_rgb(channels, limit_pairs)
    rgb = _apply_rgb_color_adjustments(
        rgb,
        percentile=background_percentile,
        background_neutralization=background_neutralization,
        color_balance=color_balance,
        color_balance_strength=color_balance_strength,
        channel_scales=channel_scales,
    )
    rgb = apply_display_scale(rgb, scale=scale, gamma=gamma, stretch=stretch)
    return np.clip(rgb, 0.0, 1.0)


def make_processed_rgb(
    red,
    green,
    blue,
    limits="zscale",
    scale="squared",
    zscale_contrast=0.25,
    lower=0.5,
    upper=99.5,
    gamma=1.0,
    stretch=5.0,
    channel_mode="per-channel",
    crop_center=None,
    crop_size=None,
    smooth_sigma=None,
    unsharp_sigma=None,
    unsharp_amount=None,
    background_neutralization="none",
    background_percentile=10,
    color_balance="none",
    color_balance_strength=1.0,
    channel_scales=(1.0, 1.0, 1.0),
    balance_region="full",
) -> np.ndarray:
    """Build a display RGB image with optional galaxy crop and post-processing.

    With ``balance_region="full"`` (the default), cropped outputs estimate
    display limits, background neutralization, and channel balance from the full
    source channels before applying those full-frame corrections to the crop.
    With ``balance_region="crop"``, those estimates are local to the crop.
    """
    if balance_region not in _BALANCE_REGIONS:
        raise ValueError(f"balance_region must be one of {sorted(_BALANCE_REGIONS)}")

    channels = [np.asarray(channel, dtype=float) for channel in (red, green, blue)]
    if any(channel.shape != channels[0].shape for channel in channels):
        raise ValueError("red, green, and blue channels must have matching shapes")

    if crop_center is None or crop_size is None or balance_region == "crop":
        red_crop = crop_image(red, center=crop_center, size=crop_size)
        green_crop = crop_image(green, center=crop_center, size=crop_size)
        blue_crop = crop_image(blue, center=crop_center, size=crop_size)
        rgb = make_display_rgb(
            red_crop,
            green_crop,
            blue_crop,
            limits=limits,
            scale=scale,
            zscale_contrast=zscale_contrast,
            lower=lower,
            upper=upper,
            gamma=gamma,
            stretch=stretch,
            channel_mode=channel_mode,
            background_neutralization=background_neutralization,
            background_percentile=background_percentile,
            color_balance=color_balance,
            color_balance_strength=color_balance_strength,
            channel_scales=channel_scales,
        )
    else:
        limit_pairs = _channel_limit_pairs(
            channels, limits, lower, upper, zscale_contrast, channel_mode
        )
        full_linear_rgb = _scale_channels_to_rgb(channels, limit_pairs)
        crop_linear_rgb = crop_image(full_linear_rgb, center=crop_center, size=crop_size)
        rgb = _apply_rgb_color_adjustments(
            crop_linear_rgb,
            percentile=background_percentile,
            background_neutralization=background_neutralization,
            color_balance=color_balance,
            color_balance_strength=color_balance_strength,
            channel_scales=channel_scales,
            reference_rgb=full_linear_rgb,
        )
        rgb = apply_display_scale(rgb, scale=scale, gamma=gamma, stretch=stretch)

    if smooth_sigma is not None:
        rgb = np.clip(gaussian_smooth(rgb, sigma=smooth_sigma), 0.0, 1.0)
    if unsharp_sigma is not None or unsharp_amount is not None:
        sigma = 2.0 if unsharp_sigma is None else unsharp_sigma
        amount = 0.6 if unsharp_amount is None else unsharp_amount
        rgb = unsharp_mask(rgb, sigma=sigma, amount=amount)
    return np.clip(rgb, 0.0, 1.0)


# Existing enhancement helpers retained for compatibility.
def estimate_background(image, percentile=10) -> float:
    """Estimate a scalar background level from finite pixels."""
    return estimate_channel_background(image, percentile=percentile)


def subtract_background(image, percentile=10) -> np.ndarray:
    """Subtract an estimated scalar background while preserving NaN/Inf pixels."""
    image = np.asarray(image, dtype=float)
    background = estimate_background(image, percentile=percentile)
    result = image.copy()
    finite_mask = np.isfinite(result)
    result[finite_mask] = result[finite_mask] - background
    return result


def normalize_channel(image, lower=1, upper=99.5) -> np.ndarray:
    """Percentile-normalize one image channel into ``[0, 1]`` safely."""
    if lower >= upper:
        raise ValueError("lower percentile must be less than upper percentile")

    image = np.asarray(image, dtype=float)
    normalized = np.zeros_like(image, dtype=float)
    finite_mask = np.isfinite(image)
    if not np.any(finite_mask):
        return normalized

    finite_values = image[finite_mask]
    vmin, vmax = np.percentile(finite_values, [lower, upper])
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        return normalized

    normalized[finite_mask] = (image[finite_mask] - vmin) / (vmax - vmin)
    return np.clip(normalized, 0.0, 1.0)


def asinh_stretch(image, stretch=5.0) -> np.ndarray:
    """Apply an asinh display stretch to values expected in ``[0, 1]``."""
    if stretch <= 0:
        raise ValueError("stretch must be greater than zero")

    return apply_display_scale(image, scale="asinh", stretch=stretch)


def gamma_correct(image, gamma=1.0) -> np.ndarray:
    """Apply display gamma correction to a normalized image."""
    if gamma <= 0:
        raise ValueError("gamma must be greater than zero")

    image = np.asarray(image, dtype=float)
    safe_image = np.nan_to_num(image, nan=0.0, posinf=1.0, neginf=0.0)
    safe_image = np.clip(safe_image, 0.0, 1.0)
    return np.clip(safe_image ** (1.0 / gamma), 0.0, 1.0)


def _channel_balance_stat(channel: np.ndarray, balance: str) -> float:
    """Return a positive display statistic for channel balancing."""
    finite_values = channel[np.isfinite(channel)]
    positive_values = finite_values[finite_values > 0]
    values = positive_values if positive_values.size else finite_values
    if values.size == 0:
        return 0.0
    if balance == "median":
        statistic = np.median(values)
    elif balance == "percentile":
        statistic = np.percentile(values, 90)
    else:
        raise ValueError("balance must be 'median', 'percentile', 'none', or None")
    if not np.isfinite(statistic) or statistic <= 0:
        return 0.0
    return float(statistic)


def _balance_channels(channels: list[np.ndarray], balance: str | None) -> list[np.ndarray]:
    """Scale normalized channels to a common median or percentile level."""
    if balance is None or balance == "none":
        return channels
    if balance not in {"median", "percentile"}:
        raise ValueError("balance must be 'median', 'percentile', 'none', or None")

    stats = np.array([_channel_balance_stat(channel, balance) for channel in channels])
    valid_stats = stats[np.isfinite(stats) & (stats > 0)]
    if valid_stats.size == 0:
        return channels

    target = float(np.median(valid_stats))
    balanced = []
    for channel, statistic in zip(channels, stats):
        if np.isfinite(statistic) and statistic > 0:
            balanced.append(np.clip(channel * (target / statistic), 0.0, 1.0))
        else:
            balanced.append(channel)
    return balanced


def make_enhanced_rgb(
    red,
    green,
    blue,
    lower=1,
    upper=99.5,
    background_percentile=10,
    stretch=5.0,
    gamma=1.0,
    balance="median",
) -> np.ndarray:
    """Create a display-enhanced RGB array clipped to ``[0, 1]``."""
    channels = [
        normalize_channel(
            subtract_background(channel, percentile=background_percentile),
            lower=lower,
            upper=upper,
        )
        for channel in (red, green, blue)
    ]
    channels = _balance_channels(channels, balance=balance)
    channels = [
        gamma_correct(asinh_stretch(channel, stretch=stretch), gamma=gamma)
        for channel in channels
    ]
    return np.clip(np.dstack(channels), 0.0, 1.0)
