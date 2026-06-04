"""Display-only enhancement helpers for astronomy image visualization.

These helpers operate on in-memory arrays intended for PNG previews and RGB
figures. They do not modify calibrated or stacked FITS products on disk.
"""

from __future__ import annotations

import numpy as np


def _finite_values(image: np.ndarray) -> np.ndarray:
    """Return the finite values in ``image`` as a one-dimensional float array."""
    image = np.asarray(image, dtype=float)
    return image[np.isfinite(image)]


def estimate_background(image, percentile=10) -> float:
    """Estimate a scalar background level from finite pixels.

    Parameters
    ----------
    image : array-like
        Image data. Non-finite pixels are ignored.
    percentile : float, optional
        Percentile used as the background estimator. Defaults to 10.

    Returns
    -------
    float
        The requested finite-pixel percentile. Returns ``0.0`` when no finite
        pixels are available.
    """
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
    """Percentile-normalize one image channel into ``[0, 1]`` safely.

    Non-finite input pixels are ignored when calculating percentiles and become
    zero in the output. Constant images, invalid percentile ranges, and all-NaN
    images return zeros with the same shape as the input.
    """
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
    """Apply an asinh display stretch to values expected in ``[0, 1]``.

    Larger ``stretch`` values brighten faint structures while the normalized
    ``asinh`` denominator keeps highlights within display range.
    """
    if stretch <= 0:
        raise ValueError("stretch must be greater than zero")

    image = np.asarray(image, dtype=float)
    safe_image = np.nan_to_num(image, nan=0.0, posinf=1.0, neginf=0.0)
    safe_image = np.clip(safe_image, 0.0, 1.0)
    stretched = np.arcsinh(stretch * safe_image) / np.arcsinh(stretch)
    return np.clip(stretched, 0.0, 1.0)


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
    """Create a display-enhanced RGB array clipped to ``[0, 1]``.

    The per-channel workflow is background subtraction, percentile
    normalization, optional color balancing, asinh stretch, and gamma
    correction. This is intended for visualization products only.
    """
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
