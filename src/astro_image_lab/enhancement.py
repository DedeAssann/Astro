"""Display-only enhancement helpers for astronomy image visualization.

These helpers operate on in-memory arrays intended for PNG previews and RGB
figures. They do not modify calibrated or stacked FITS products on disk.
"""

from __future__ import annotations

import numpy as np


_DISPLAY_SCALES = {"linear", "squared", "cubed", "sqrt", "log", "asinh", "gamma"}
_LIMIT_MODES = {"zscale", "percentile"}
_CHANNEL_MODES = {"per-channel", "global"}


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


def crop_image(image, center=None, size=None) -> np.ndarray:
    """Crop a 2D or RGB image using an ``[x, y]`` center convention.

    ``center`` is documented and accepted as image/display coordinates
    ``[x, y]`` (column, row). Internally this is converted to NumPy row/column
    indexing. If ``center`` or ``size`` is omitted, the original image object is
    returned. Crop bounds are clipped safely at image edges.
    """
    array = np.asarray(image)
    if center is None or size is None:
        return array
    if array.ndim not in {2, 3}:
        raise ValueError("crop_image supports 2D grayscale or RGB-like arrays")
    if size <= 0:
        raise ValueError("size must be greater than zero")
    if len(center) != 2:
        raise ValueError("center must contain X and Y coordinates")

    center_x, center_y = float(center[0]), float(center[1])
    crop_size = int(round(float(size)))
    half = crop_size / 2.0
    x0 = max(0, int(np.floor(center_x - half)))
    x1 = min(array.shape[1], int(np.ceil(center_x + half)))
    y0 = max(0, int(np.floor(center_y - half)))
    y1 = min(array.shape[0], int(np.ceil(center_y + half)))
    return array[y0:y1, x0:x1, ...] if array.ndim == 3 else array[y0:y1, x0:x1]


def _limits_for_channel(channel, limits, lower, upper, zscale_contrast) -> tuple[float, float]:
    if limits == "zscale":
        return zscale_limits(channel, contrast=zscale_contrast)
    if limits == "percentile":
        return _percentile_limits(channel, lower=lower, upper=upper)
    raise ValueError(f"limits must be one of {sorted(_LIMIT_MODES)}")


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
) -> np.ndarray:
    """Create a display-scaled RGB preview clipped to ``[0, 1]``."""
    if channel_mode not in _CHANNEL_MODES:
        raise ValueError(f"channel_mode must be one of {sorted(_CHANNEL_MODES)}")
    channels = [np.asarray(channel, dtype=float) for channel in (red, green, blue)]
    if any(channel.shape != channels[0].shape for channel in channels):
        raise ValueError("red, green, and blue channels must have matching shapes")

    if channel_mode == "global":
        combined = np.concatenate([_finite_values(channel) for channel in channels])
        vmin, vmax = _limits_for_channel(combined, limits, lower, upper, zscale_contrast)
        limit_pairs = [(vmin, vmax)] * 3
    else:
        limit_pairs = [
            _limits_for_channel(channel, limits, lower, upper, zscale_contrast)
            for channel in channels
        ]
    scaled_channels = [
        apply_display_scale(
            scale_to_limits(channel, vmin, vmax),
            scale=scale,
            gamma=gamma,
            stretch=stretch,
        )
        for channel, (vmin, vmax) in zip(channels, limit_pairs)
    ]
    return np.clip(np.dstack(scaled_channels), 0.0, 1.0)


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
) -> np.ndarray:
    """Build a display RGB image with optional galaxy crop and post-processing.

    The optional crop is applied to raw channels first, before display limits,
    display scales, smoothing, or unsharp masking are applied.
    """
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
    )
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
    finite_values = _finite_values(image)
    if finite_values.size == 0:
        return 0.0
    return float(np.percentile(finite_values, percentile))


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
