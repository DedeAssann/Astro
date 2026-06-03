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


def plot_histogram(image, title=None, output_path=None, bins=100):
    """Plot a histogram of the finite pixel values in an image."""
    image = np.asarray(image, dtype=float)
    finite_values = image[np.isfinite(image)]

    fig, ax = plt.subplots()
    ax.hist(finite_values, bins=bins)
    ax.set_xlabel("Pixel value")
    ax.set_ylabel("Count")
    if title is not None:
        ax.set_title(title)
    _save_figure(fig, output_path)
    return fig


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
