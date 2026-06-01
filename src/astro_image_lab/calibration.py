"""Calibration helpers extracted from the original astronomy notebook."""

import numpy as np

from .io import load_fits


def _combine_frames(frames, method):
    """Combine a stack of frames with the requested notebook-style method."""
    if method == "median":
        return np.nanmedian(frames, axis=0)
    if method == "mean":
        return np.nanmean(frames, axis=0)
    raise ValueError("method must be 'median' or 'mean'")


def _load_image_data(path):
    """Load only image data from a FITS path."""
    data, _header = load_fits(path)
    return np.asarray(data, dtype=float)


def make_master_bias(bias_files, method="median"):
    """Build a master bias by combining individual bias frames."""
    if not bias_files:
        raise ValueError("bias_files must contain at least one FITS file")

    bias_stack = np.asarray([_load_image_data(path) for path in bias_files], dtype=float)
    return _combine_frames(bias_stack, method)


def make_master_flat(flat_files, master_bias, method="median"):
    """Build a normalized master flat after subtracting the master bias."""
    if not flat_files:
        raise ValueError("flat_files must contain at least one FITS file")

    master_bias = np.asarray(master_bias, dtype=float)
    normalized_flats = []

    for path in flat_files:
        flat_data = _load_image_data(path)
        bias_subtracted = flat_data - master_bias
        flat_median = np.nanmedian(bias_subtracted)
        if not np.isfinite(flat_median) or flat_median == 0:
            raise ValueError("bias-subtracted flat frame has an invalid median")
        normalized_flats.append(bias_subtracted / flat_median)

    master_flat = _combine_frames(np.asarray(normalized_flats, dtype=float), method)
    master_flat_median = np.nanmedian(master_flat)
    if not np.isfinite(master_flat_median) or master_flat_median == 0:
        raise ValueError("master flat has an invalid median")

    master_flat = master_flat / master_flat_median
    invalid = ~np.isfinite(master_flat) | (master_flat == 0)
    if np.any(invalid):
        master_flat = master_flat.copy()
        master_flat[invalid] = np.nan
    return master_flat


def calibrate_science_image(science_data, master_bias, master_flat):
    """Calibrate a science image with ``(science_data - master_bias) / master_flat``."""
    science_data = np.asarray(science_data, dtype=float)
    master_bias = np.asarray(master_bias, dtype=float)
    master_flat = np.asarray(master_flat, dtype=float)

    safe_flat = np.where(np.isfinite(master_flat) & (master_flat != 0), master_flat, np.nan)
    return (science_data - master_bias) / safe_flat
