"""Science-image normalization, alignment, and stacking utilities.

These helpers extract the stacking behavior from ``doc/processing.py`` while
fixing its indexing bug: the first calibrated science image is included in the
stack and used as the reference for optional alignment.
"""

import numpy as np

from .calibration import calibrate_science_image
from .io import load_fits


def normalize_by_median(image):
    """Normalize an image by its median value.

    This mirrors the original processing notebook/script behavior of dividing
    each calibrated science image by ``np.median(image)`` before stacking.
    """
    image = np.asarray(image, dtype=float)
    median = np.median(image)
    if not np.isfinite(median) or median == 0:
        raise ValueError("image has an invalid median and cannot be normalized")
    return image / median


def _sigma_clip_fallback(image_stack, sigma, maxiters):
    """Small fallback for ``astropy.stats.sigma_clip(..., axis=0, masked=False)``.

    The project prefers Astropy when it is installed. This fallback keeps the
    package tests runnable in minimal environments by performing iterative,
    per-pixel median/std clipping and replacing clipped samples with ``NaN``.
    """
    clipped = np.asarray(image_stack, dtype=float).copy()
    iterations = 0
    while maxiters is None or iterations < maxiters:
        center = np.nanmedian(clipped, axis=0)
        spread = np.nanstd(clipped, axis=0)
        invalid_spread = ~np.isfinite(spread) | (spread == 0)
        distance = np.abs(clipped - center)
        clip_mask = (distance > sigma * spread) & ~invalid_spread
        clip_mask |= ~np.isfinite(clipped)
        new_clips = clip_mask & ~np.isnan(clipped)
        if not np.any(new_clips):
            break
        clipped[new_clips] = np.nan
        iterations += 1
    return clipped


def stack_images(image_stack, sigma=2, maxiters=10):
    """Sigma-clip and average a stack of normalized science images.

    The clipping call follows the cleaned-up ``doc/processing.py`` behavior:
    ``sigma_clip(image_stack, sigma=sigma, maxiters=maxiters, axis=0,
    masked=False)`` followed by ``np.nanmean(..., axis=0)``. The final stacked
    image is returned as ``float32``, matching the original script's output for
    floating-point image data.
    """
    image_stack = np.asarray(image_stack, dtype=float)
    if image_stack.ndim < 3 or image_stack.shape[0] == 0:
        raise ValueError("image_stack must be a non-empty stack with shape (n_images, height, width)")

    try:
        from astropy.stats import sigma_clip
    except ImportError:
        filtered_data = _sigma_clip_fallback(image_stack, sigma=sigma, maxiters=maxiters)
    else:
        filtered_data = sigma_clip(image_stack, sigma=sigma, maxiters=maxiters, axis=0, masked=False)

    final_image = np.nanmean(filtered_data, axis=0)
    return final_image.astype(np.float32, copy=False)


def _alignment_report_record(
    *,
    path,
    index,
    status,
    align,
    min_area,
    filter_name=None,
    alignment_method="astroalign",
    error="",
):
    """Build one serializable alignment report record."""
    return {
        "filter": "" if filter_name is None else str(filter_name),
        "file_path": str(path),
        "index": index,
        "status": status,
        "error": error,
        "method": alignment_method if align else "",
        "min_area": min_area,
    }


def calibrate_and_stack(
    science_files,
    master_bias,
    master_flat,
    align=True,
    min_area=12,
    sigma=2,
    maxiters=10,
    return_alignment_report=False,
    filter_name=None,
    fail_policy="raise",
    alignment_method="astroalign",
    detection_sigma=None,
):
    """Load, calibrate, optionally align, and stack science FITS images.

    Each science frame is loaded with :func:`astro_image_lab.io.load_fits`,
    calibrated via ``(image - master_bias) / master_flat`` using
    :func:`astro_image_lab.calibration.calibrate_science_image`, normalized by
    its median, and then stacked with :func:`stack_images`.

    When ``align=True``, the first calibrated and normalized science image is
    used as the registration reference and every subsequent image is aligned to
    it with ``astroalign.register(..., min_area=min_area)``. The first image is
    not skipped, correcting the indexing bug in ``doc/processing.py``. The
    ``sigma`` and ``maxiters`` arguments are forwarded to
    :func:`astro_image_lab.stacking.stack_images`. Set
    ``return_alignment_report=True`` to return ``(stacked_image, records)``
    instead of just the stacked image.
    """
    science_files = list(science_files)
    if not science_files:
        raise ValueError("science_files must contain at least one FITS file")
    if fail_policy not in {"raise", "skip"}:
        raise ValueError("fail_policy must be 'raise' or 'skip'")
    if alignment_method != "astroalign":
        raise ValueError("alignment_method must be 'astroalign'")

    if align:
        import astroalign
    else:
        astroalign = None

    normalized_images = []
    report_records = []
    reference_image = None

    for index, path in enumerate(science_files):
        science_data, _header = load_fits(path)
        calibrated = calibrate_science_image(science_data, master_bias, master_flat)
        normalized = normalize_by_median(calibrated)

        if not align:
            normalized_images.append(normalized)
            report_records.append(
                _alignment_report_record(
                    path=path,
                    index=index,
                    status="skipped",
                    align=align,
                    min_area=min_area,
                    filter_name=filter_name,
                    alignment_method=alignment_method,
                )
            )
            continue

        if reference_image is None:
            reference_image = normalized
            normalized_images.append(normalized)
            report_records.append(
                _alignment_report_record(
                    path=path,
                    index=index,
                    status="reference",
                    align=align,
                    min_area=min_area,
                    filter_name=filter_name,
                    alignment_method=alignment_method,
                )
            )
            continue

        register_kwargs = {"min_area": min_area}
        if detection_sigma is not None:
            register_kwargs["detection_sigma"] = detection_sigma
        try:
            registered_image, _footprint = astroalign.register(
                normalized, reference_image, **register_kwargs
            )
        except Exception as exc:
            report_records.append(
                _alignment_report_record(
                    path=path,
                    index=index,
                    status="failed",
                    align=align,
                    min_area=min_area,
                    filter_name=filter_name,
                    alignment_method=alignment_method,
                    error=str(exc),
                )
            )
            if fail_policy == "raise":
                raise
            continue

        normalized_images.append(registered_image)
        report_records.append(
            _alignment_report_record(
                path=path,
                index=index,
                status="aligned",
                align=align,
                min_area=min_area,
                filter_name=filter_name,
                alignment_method=alignment_method,
            )
        )

    stacked_image = stack_images(
        np.asarray(normalized_images, dtype=float), sigma=sigma, maxiters=maxiters
    )
    if return_alignment_report:
        return stacked_image, report_records
    return stacked_image
