"""Visualization helpers for calibrated astronomy images."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def scale_image_percentile(image, lower=1, upper=99):
    """Scale an image to approximately ``[0, 1]`` using finite percentiles.

    Non-finite pixels are ignored when estimating the percentile limits and are
    replaced with zero in the returned image. Values outside the percentile
    range are clipped to keep the output finite and display-friendly.
    """
    if lower >= upper:
        raise ValueError("lower percentile must be less than upper percentile")

    image = np.asarray(image, dtype=float)
    scaled = np.zeros_like(image, dtype=float)
    finite_mask = np.isfinite(image)
    if not np.any(finite_mask):
        return scaled

    finite_values = image[finite_mask]
    vmin, vmax = np.nanpercentile(finite_values, [lower, upper])
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax == vmin:
        return scaled

    scaled[finite_mask] = (image[finite_mask] - vmin) / (vmax - vmin)
    return np.clip(scaled, 0.0, 1.0)


def _save_figure(fig, output_path):
    """Save a figure when an output path is provided."""
    if output_path is None:
        return
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")


def plot_image(image, title=None, log_scale=False, output_path=None, cmap="gray"):
    """Plot a single image and optionally save it to disk.

    The displayed image is percentile-scaled before plotting. With
    ``log_scale=True``, a light logarithmic stretch is applied after percentile
    scaling so zero and NaN-heavy images remain safe to render.
    """
    display_image = scale_image_percentile(image)
    if log_scale:
        display_image = np.log1p(display_image) / np.log(2.0)

    fig, ax = plt.subplots()
    ax.imshow(display_image, origin="lower", cmap=cmap, vmin=0, vmax=1)
    ax.set_axis_off()
    if title is not None:
        ax.set_title(title)
    _save_figure(fig, output_path)
    return fig


def compute_histogram_bounds(image, lower_percentile=0.5, upper_percentile=99.5):
    """Return robust finite-pixel histogram x-axis bounds.

    NaN and infinite pixels are ignored. Constant images are given a small
    symmetric interval around the constant value, and fully invalid inputs fall
    back to ``(0, 1)`` so callers can still render an empty-but-valid plot.
    """
    if lower_percentile >= upper_percentile:
        raise ValueError("lower_percentile must be less than upper_percentile")

    image = np.asarray(image, dtype=float)
    finite_values = image[np.isfinite(image)]
    if finite_values.size == 0:
        return 0.0, 1.0

    xmin, xmax = np.percentile(finite_values, [lower_percentile, upper_percentile])
    if not np.isfinite(xmin) or not np.isfinite(xmax):
        return 0.0, 1.0
    if xmin == xmax:
        center = float(xmin)
        padding = max(abs(center) * 0.01, 0.5)
        return center - padding, center + padding
    return float(xmin), float(xmax)


def plot_histogram(
    image,
    title=None,
    output_path=None,
    bins=100,
    lower_percentile=0.5,
    upper_percentile=99.5,
):
    """Plot a robust finite-pixel histogram for an image.

    The x-axis is automatically bounded by finite-pixel percentiles so the plot
    frames the useful distribution rather than extreme outliers, saturated
    stars, cosmic rays, or non-finite values. Histogram counts are computed only
    within those bounds.
    """
    image = np.asarray(image, dtype=float)
    finite_values = image[np.isfinite(image)]
    total_pixels = image.size
    finite_fraction = finite_values.size / total_pixels if total_pixels else 0.0
    xmin, xmax = compute_histogram_bounds(
        finite_values,
        lower_percentile=lower_percentile,
        upper_percentile=upper_percentile,
    )
    bounded_values = finite_values[(finite_values >= xmin) & (finite_values <= xmax)]

    fig, ax = plt.subplots()
    counts, _edges, _patches = ax.hist(
        bounded_values,
        bins=bins,
        range=(xmin, xmax),
        label=_histogram_stats_label(finite_values, lower_percentile, upper_percentile),
    )
    max_count = float(np.max(counts)) if counts.size else 0.0
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(0, max(1.0, 1.1 * max_count))
    ax.set_xlabel("Pixel value")
    ax.set_ylabel("Count")
    ax.legend(
        title=f"finite={finite_fraction:.1%}",
        fontsize="small",
        title_fontsize="small",
    )
    if title is not None:
        ax.set_title(title)
    _save_figure(fig, output_path)
    return fig


def _histogram_stats_label(finite_values, lower_percentile, upper_percentile):
    """Return a compact label with robust finite-pixel distribution statistics."""
    if finite_values.size == 0:
        return "no finite pixels"
    p1, p99 = np.percentile(finite_values, [1, 99])
    bound_lower, bound_upper = np.percentile(
        finite_values,
        [lower_percentile, upper_percentile],
    )
    return (
        f"mean={np.mean(finite_values):.3g}\n"
        f"median={np.median(finite_values):.3g}\n"
        f"std={np.std(finite_values):.3g}\n"
        f"p1={p1:.3g}\n"
        f"p99={p99:.3g}\n"
        f"bounds p{lower_percentile:g}/p{upper_percentile:g}="
        f"{bound_lower:.3g}/{bound_upper:.3g}"
    )


def compare_images(before, after, titles=("Before", "After"), output_path=None):
    """Plot two percentile-scaled images side by side for visual comparison."""
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    for ax, image, title in zip(axes, (before, after), titles):
        ax.imshow(
            scale_image_percentile(image),
            origin="lower",
            cmap="gray",
            vmin=0,
            vmax=1,
        )
        ax.set_axis_off()
        ax.set_title(title)
    fig.tight_layout()
    _save_figure(fig, output_path)
    return fig


def make_rgb_image(red, green, blue, lower=1, upper=99):
    """Create an RGB image from red, green, and blue channel arrays."""
    channels = [
        scale_image_percentile(red, lower=lower, upper=upper),
        scale_image_percentile(green, lower=lower, upper=upper),
        scale_image_percentile(blue, lower=lower, upper=upper),
    ]
    return np.dstack(channels)
