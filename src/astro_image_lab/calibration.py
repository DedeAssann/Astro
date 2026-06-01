"""Calibration helpers following the original TP ``doc/processing.py`` logic."""

import numpy as np

from .io import load_fits


def _combine_frames(frames, method):
    """Combine a stack of frames; the TP default is a per-pixel median."""
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
    """Build a master bias from individual bias frames.

    This follows the original TP ``doc/processing.py`` behavior: load all bias
    images into a 3D stack and compute ``np.nanmedian(stack, axis=0)`` by
    default.
    """
    bias_files = list(bias_files)
    if not bias_files:
        raise ValueError("bias_files must contain at least one FITS file")

    bias_stack = np.asarray([_load_image_data(path) for path in bias_files], dtype=float)
    return _combine_frames(bias_stack, method)


def make_master_flat(flat_files, master_bias, combine_method="mean"):
    """Build a normalized master flat after subtracting the master bias.

    This preserves the original TP ``doc/processing.py`` scientific behavior by
    default: each flat is bias-subtracted, normalized by ``np.median`` of that
    bias-subtracted flat, combined with an arithmetic mean via equal-weight
    accumulation, and the resulting master flat is renormalized by
    ``np.median(master_flat)``.
    """
    if combine_method != "mean":
        raise ValueError("make_master_flat follows doc/processing.py and supports combine_method='mean'")

    flat_files = list(flat_files)
    if not flat_files:
        raise ValueError("flat_files must contain at least one FITS file")

    master_bias = np.asarray(master_bias, dtype=float)
    first_flat = _load_image_data(flat_files[0])
    master_flat = np.zeros(np.shape(first_flat), dtype=float)

    for index, path in enumerate(flat_files):
        flat_data = first_flat if index == 0 else _load_image_data(path)
        bias_subtracted = flat_data - master_bias
        flat_median = np.median(bias_subtracted)
        if not np.isfinite(flat_median) or flat_median == 0:
            raise ValueError("bias-subtracted flat frame has an invalid median")
        # Match doc/processing.py exactly for valid pixels:
        # master_flat += tmp / np.median(tmp) / len(list_flat)
        master_flat += bias_subtracted / flat_median / len(flat_files)

    master_flat_median = np.median(master_flat)
    if not np.isfinite(master_flat_median) or master_flat_median == 0:
        raise ValueError("master flat has an invalid median")

    # Match doc/processing.py exactly for valid pixels:
    # master_flat /= np.median(master_flat)
    master_flat = master_flat / master_flat_median

    # Keep valid-pixel behavior identical to doc/processing.py, but prevent
    # downstream division by zero or invalid flat values where they occur.
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
