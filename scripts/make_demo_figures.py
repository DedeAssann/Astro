#!/usr/bin/env python3
"""Generate demo PNG figures from object-based stacked FITS outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow ``python scripts/make_demo_figures.py`` from a source checkout without
# requiring an editable install.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import matplotlib.pyplot as plt

from astro_image_lab import enhancement, visualization
from astro_image_lab.io import discover_fits_files, load_fits


class DemoFigureError(ValueError):
    """Raised when demo figure inputs cannot be resolved."""


VISUALIZATION_PRESETS = {
    "diagnostic": {
        "limits": "zscale",
        "scale": "linear",
        "background_neutralization": "none",
        "color_balance": "none",
        "color_balance_strength": 1.0,
        "channel_scales": (1.0, 1.0, 1.0),
        "balance_region": "full",
        "smooth_sigma": None,
        "unsharp_sigma": None,
        "unsharp_amount": None,
    },
    "natural": {
        "limits": "zscale",
        "scale": "squared",
        "background_neutralization": "equalize",
        "color_balance": "background",
        "color_balance_strength": 1.0,
        "channel_scales": (1.0, 1.0, 1.0),
        "balance_region": "full",
        "smooth_sigma": None,
        "unsharp_sigma": None,
        "unsharp_amount": None,
    },
    "deep_sky": {
        "limits": "zscale",
        "scale": "cubed",
        "background_neutralization": "equalize",
        "color_balance": "background",
        "color_balance_strength": 1.0,
        "channel_scales": (1.0, 1.0, 1.0),
        "balance_region": "full",
        "smooth_sigma": None,
        "unsharp_sigma": None,
        "unsharp_amount": None,
    },
    "galaxy_detail": {
        "limits": "zscale",
        "scale": "squared",
        "background_neutralization": "equalize",
        "color_balance": "background",
        "color_balance_strength": 0.4,
        "channel_scales": (1.0, 0.9, 1.0),
        "balance_region": "full",
        "smooth_sigma": None,
        "unsharp_sigma": 2.0,
        "unsharp_amount": 0.6,
    },
}


def _validate_color_control_options(
    color_balance_strength: float | None = None,
    channel_scales: tuple[float, float, float] | list[float] | None = None,
) -> None:
    """Validate display-only color-balance strength and manual channel scales."""
    if color_balance_strength is not None:
        strength = float(color_balance_strength)
        if not 0 <= strength <= 1:
            raise DemoFigureError("color_balance_strength must be between 0 and 1")
    if channel_scales is not None:
        if len(channel_scales) != 3:
            raise DemoFigureError("channel_scales must contain R, G, and B values")
        scales = tuple(float(scale) for scale in channel_scales)
        if not all(scale > 0 for scale in scales):
            raise DemoFigureError("channel_scales must be positive")


def _resolve_display_options(
    preset: str | None = None,
    rgb_limits: str | None = None,
    rgb_scale: str | None = None,
    background_neutralization: str | None = None,
    color_balance: str | None = None,
    color_balance_strength: float | None = None,
    channel_scales: tuple[float, float, float] | list[float] | None = None,
    balance_region: str | None = None,
    smooth_sigma: float | None = None,
    unsharp_sigma: float | None = None,
    unsharp_amount: float | None = None,
) -> dict[str, object]:
    """Resolve preset display options, with explicit values overriding presets."""
    options = {
        "limits": "zscale",
        "scale": rgb_scale,
        "background_neutralization": "none",
        "color_balance": "none",
        "color_balance_strength": 1.0,
        "channel_scales": (1.0, 1.0, 1.0),
        "balance_region": "full",
        "smooth_sigma": smooth_sigma,
        "unsharp_sigma": unsharp_sigma,
        "unsharp_amount": unsharp_amount,
    }
    if preset is not None:
        if preset not in VISUALIZATION_PRESETS:
            raise DemoFigureError(f"Unknown visualization preset: {preset}")
        options.update(VISUALIZATION_PRESETS[preset])

    if rgb_limits is not None:
        options["limits"] = rgb_limits
    if rgb_scale is not None:
        options["scale"] = rgb_scale
    if background_neutralization is not None:
        options["background_neutralization"] = background_neutralization
    if color_balance is not None:
        options["color_balance"] = color_balance
    _validate_color_control_options(color_balance_strength, channel_scales)
    if color_balance_strength is not None:
        options["color_balance_strength"] = color_balance_strength
    if channel_scales is not None:
        options["channel_scales"] = tuple(float(scale) for scale in channel_scales)
    if balance_region is not None:
        options["balance_region"] = balance_region
    if smooth_sigma is not None:
        options["smooth_sigma"] = smooth_sigma
    if unsharp_sigma is not None:
        options["unsharp_sigma"] = unsharp_sigma
    if unsharp_amount is not None:
        options["unsharp_amount"] = unsharp_amount
    return options


def _interpret_crop_center(crop_center, crop_center_origin: int = 0):
    """Convert requested x/y crop center to zero-based x/y coordinates."""
    if crop_center is None:
        return None
    if crop_center_origin not in {0, 1}:
        raise DemoFigureError("crop_center_origin must be 0 or 1")
    if len(crop_center) != 2:
        raise DemoFigureError("crop_center must contain X and Y coordinates")
    center_x = float(crop_center[0]) - crop_center_origin
    center_y = float(crop_center[1]) - crop_center_origin
    return [center_x, center_y]


def _discover_stacked_files(stacked_dir: Path) -> dict[str, Path]:
    """Discover stacked FITS files and map filter names to file paths."""
    if not stacked_dir.exists():
        raise DemoFigureError(f"Stacked directory does not exist: {stacked_dir}")
    if not stacked_dir.is_dir():
        raise DemoFigureError(f"Stacked path is not a directory: {stacked_dir}")

    stacked_files = {
        path.stem.removeprefix("stacked_"): path
        for path in discover_fits_files(stacked_dir)
        if path.stem.startswith("stacked_")
    }
    if not stacked_files:
        raise DemoFigureError(f"No stacked FITS files found in {stacked_dir}")
    return stacked_files


def _discover_filters(stacked_dir: Path) -> list[str]:
    """Discover filters from supported ``stacked_*`` FITS files."""
    return sorted(_discover_stacked_files(stacked_dir))


def _resolve_stacked_files(
    data_root: Path,
    object_name: str,
    filters: list[str] | None = None,
) -> dict[str, Path]:
    """Resolve filter names to stacked FITS files for demo figure generation."""
    stacked_dir = data_root / object_name / "stacked"
    discovered_files = _discover_stacked_files(stacked_dir)
    selected_filters = filters if filters is not None else sorted(discovered_files)

    stacked_files: dict[str, Path] = {}
    missing: list[str] = []
    for filter_name in selected_filters:
        stacked_file = discovered_files.get(filter_name)
        if stacked_file is None:
            missing.append(filter_name)
        else:
            stacked_files[filter_name] = stacked_file

    if missing:
        missing_filters = ", ".join(missing)
        raise DemoFigureError(f"Stacked FITS file(s) not found for filter(s): {missing_filters}")
    if not stacked_files:
        raise DemoFigureError(f"No stacked FITS files found in {stacked_dir}")
    return stacked_files


def _aligned_channel_path(stacked_dir: Path, filter_name: str) -> Path:
    """Return the expected aligned-channel FITS path for a filter."""
    return stacked_dir / "aligned_channels" / f"stacked_{filter_name}_aligned.fits"


def _resolve_rgb_channel_files(stacked_dir: Path, stacked_files: dict[str, Path]) -> dict[str, Path]:
    """Resolve RGB source files, preferring aligned channels when present."""
    rgb_files: dict[str, Path] = {}
    for filter_name in ("red", "green", "blue"):
        aligned_path = _aligned_channel_path(stacked_dir, filter_name)
        if aligned_path.exists():
            rgb_files[filter_name] = aligned_path
        else:
            rgb_files[filter_name] = stacked_files[filter_name]
    return rgb_files


def _print_processing_settings(label: str, **settings) -> None:
    """Print a compact processing-settings line for generated RGB products."""
    formatted = ", ".join(f"{key}={value}" for key, value in settings.items())
    print(f"{label} settings: {formatted}")


def _save_rgb(path: Path, rgb, written_paths: list[Path], label: str, **settings) -> None:
    """Save an RGB image, record its path, and print path plus settings."""
    plt.imsave(path, rgb, origin="lower")
    written_paths.append(path)
    print(path)
    _print_processing_settings(label, **settings)


def _crop_method_suffix(smooth_sigma, unsharp_sigma, unsharp_amount) -> str:
    """Return the filename suffix describing crop post-processing."""
    has_smooth = smooth_sigma is not None
    has_unsharp = unsharp_sigma is not None or unsharp_amount is not None
    if has_smooth and has_unsharp:
        return "_smooth_unsharp"
    if has_smooth:
        return "_smooth"
    if has_unsharp:
        return "_unsharp"
    return ""


def _print_crop_interpretation(image_shape, requested_center, interpreted_center, crop_size) -> None:
    """Log how CLI x/y crop coordinates map to NumPy row/column bounds."""
    if requested_center is None or interpreted_center is None or crop_size is None:
        return
    row_start, row_stop, col_start, col_stop = enhancement.crop_bounds(
        image_shape, interpreted_center, crop_size
    )
    print(
        "Crop center requested X,Y="
        f"({requested_center[0]}, {requested_center[1]}); "
        "interpreted NumPy row,col="
        f"({interpreted_center[1]}, {interpreted_center[0]}); "
        "crop bounds rows="
        f"{row_start}:{row_stop}, cols={col_start}:{col_stop}"
    )


def _scaled_rgb_for_color_log(
    rgb_channel_data: dict[str, object],
    limits: str,
    zscale_contrast: float,
    lower: float,
    upper: float,
    crop_center=None,
    crop_size=None,
):
    """Build a linear normalized RGB image for color-adjustment logging."""
    red = enhancement.crop_image(rgb_channel_data["red"], center=crop_center, size=crop_size)
    green = enhancement.crop_image(rgb_channel_data["green"], center=crop_center, size=crop_size)
    blue = enhancement.crop_image(rgb_channel_data["blue"], center=crop_center, size=crop_size)
    return enhancement.make_display_rgb(
        red,
        green,
        blue,
        limits=limits,
        scale="linear",
        zscale_contrast=zscale_contrast,
        lower=lower,
        upper=upper,
        background_neutralization="none",
        color_balance="none",
    )


def _print_color_adjustment_log(
    label: str,
    rgb_channel_data: dict[str, object],
    limits: str,
    zscale_contrast: float,
    lower: float,
    upper: float,
    background_neutralization: str,
    background_percentile: float,
    color_balance: str,
    color_balance_strength: float = 1.0,
    channel_scales=(1.0, 1.0, 1.0),
    balance_region: str = "full",
    crop_center=None,
    crop_size=None,
) -> None:
    """Print background estimates and balance factors when RGB color controls are active."""
    manual_scales_are_neutral = tuple(channel_scales) == (1.0, 1.0, 1.0)
    if (
        background_neutralization == "none"
        and color_balance == "none"
        and color_balance_strength == 1.0
        and manual_scales_are_neutral
    ):
        return

    log_crop_center = crop_center if balance_region == "crop" else None
    log_crop_size = crop_size if balance_region == "crop" else None
    scaled_rgb = _scaled_rgb_for_color_log(
        rgb_channel_data,
        limits=limits,
        zscale_contrast=zscale_contrast,
        lower=lower,
        upper=upper,
        crop_center=log_crop_center,
        crop_size=log_crop_size,
    )
    backgrounds = [
        enhancement.estimate_channel_background(scaled_rgb[..., channel], background_percentile)
        for channel in range(3)
    ]
    neutralized = enhancement.neutralize_rgb_background(
        scaled_rgb,
        percentile=background_percentile,
        mode=background_neutralization,
    )
    balance_factors = enhancement.rgb_channel_balance_factors(
        neutralized,
        method=color_balance,
        percentile=background_percentile,
    )
    effective_factors = enhancement.effective_rgb_channel_balance_factors(
        balance_factors, color_balance_strength=color_balance_strength
    )
    background_text = ", ".join(
        f"{name}={value:.6g}" for name, value in zip(("red", "green", "blue"), backgrounds)
    )
    factor_text = ", ".join(
        f"{name}={value:.6g}" for name, value in zip(("red", "green", "blue"), balance_factors)
    )
    effective_factor_text = ", ".join(
        f"{name}={value:.6g}" for name, value in zip(("red", "green", "blue"), effective_factors)
    )
    scale_text = ", ".join(
        f"{name}={value:.6g}" for name, value in zip(("red", "green", "blue"), channel_scales)
    )
    print(f"{label} balance region: {balance_region}")
    print(f"{label} background estimates ({background_percentile:g}th percentile): {background_text}")
    print(f"{label} color balance factors ({color_balance}): {factor_text}")
    print(f"{label} effective balance factors (strength={color_balance_strength:g}): {effective_factor_text}")
    print(f"{label} manual channel scales: {scale_text}")


def _make_galaxy_detail_grid(
    rgb_channel_data: dict[str, object],
    output_path: Path,
    crop_center=None,
    crop_size=None,
    zscale_contrast: float = 0.25,
    lower: float = 0.5,
    upper: float = 99.5,
    gamma: float = 1.0,
    stretch: float = 5.0,
    smooth_sigma: float = 0.8,
    unsharp_sigma: float = 2.0,
    unsharp_amount: float = 0.6,
    background_neutralization: str = "none",
    background_percentile: float = 10,
    color_balance: str = "none",
    color_balance_strength: float = 1.0,
    channel_scales=(1.0, 1.0, 1.0),
    balance_region: str = "full",
) -> Path:
    """Create the six-panel galaxy detail grid requested by the CLI."""
    panels = [
        ("zscale + linear crop", {"scale": "linear"}),
        ("zscale + squared crop", {"scale": "squared"}),
        ("zscale + cubed crop", {"scale": "cubed"}),
        ("zscale + squared + smoothing crop", {"scale": "squared", "smooth_sigma": smooth_sigma}),
        (
            "zscale + squared + unsharp crop",
            {"scale": "squared", "unsharp_sigma": unsharp_sigma, "unsharp_amount": unsharp_amount},
        ),
        (
            "zscale + asinh + unsharp crop",
            {"scale": "asinh", "unsharp_sigma": unsharp_sigma, "unsharp_amount": unsharp_amount},
        ),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(12, 8))
    for ax, (title, panel_kwargs) in zip(axes.ravel(), panels):
        rgb = enhancement.make_processed_rgb(
            rgb_channel_data["red"],
            rgb_channel_data["green"],
            rgb_channel_data["blue"],
            limits="zscale",
            zscale_contrast=zscale_contrast,
            lower=lower,
            upper=upper,
            gamma=gamma,
            stretch=stretch,
            crop_center=crop_center,
            crop_size=crop_size,
            background_neutralization=background_neutralization,
            background_percentile=background_percentile,
            color_balance=color_balance,
            color_balance_strength=color_balance_strength,
            channel_scales=channel_scales,
            balance_region=balance_region,
            **panel_kwargs,
        )
        ax.imshow(rgb, origin="lower")
        ax.set_axis_off()
        ax.set_title(title, fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    print(output_path)
    _print_processing_settings(
        "galaxy-detail-grid",
        limits="zscale",
        crop_center=crop_center,
        crop_size=crop_size,
        smooth_sigma=smooth_sigma,
        unsharp_sigma=unsharp_sigma,
        unsharp_amount=unsharp_amount,
        gamma=gamma,
        stretch=stretch,
        background_neutralization=background_neutralization,
        background_percentile=background_percentile,
        color_balance=color_balance,
        color_balance_strength=color_balance_strength,
        channel_scales=channel_scales,
        balance_region=balance_region,
    )
    return output_path


def make_demo_figures(
    object_name: str,
    data_root: Path | str = Path("data"),
    filters: list[str] | None = None,
    enhance_rgb: bool = False,
    stretch: float = 5.0,
    gamma: float = 1.0,
    background_percentile: float = 10,
    lower: float = 0.5,
    upper: float = 99.5,
    ds9like: bool = False,
    preset: str | None = None,
    rgb_limits: str | None = None,
    rgb_scale: str | None = None,
    zscale_contrast: float = 0.25,
    smooth_sigma: float | None = None,
    unsharp_sigma: float | None = None,
    unsharp_amount: float | None = None,
    crop_center: list[float] | tuple[float, float] | None = None,
    crop_size: float | None = None,
    crop_center_origin: int = 0,
    galaxy_detail_grid: bool = False,
    background_neutralization: str | None = None,
    color_balance: str | None = None,
    color_balance_strength: float | None = None,
    channel_scales: tuple[float, float, float] | list[float] | None = None,
    balance_region: str | None = None,
) -> list[Path]:
    """Create PNG demo figures from stacked FITS files for one object.

    Presets and advanced display controls are visualization-only PNG
    post-processing steps. Calibrated and stacked FITS data are never modified.
    """
    data_root = Path(data_root)
    stacked_dir = data_root / object_name / "stacked"
    stacked_files = _resolve_stacked_files(data_root, object_name, filters)
    figures_dir = data_root / object_name / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    display_options = _resolve_display_options(
        preset=preset,
        rgb_limits=rgb_limits,
        rgb_scale=rgb_scale,
        background_neutralization=background_neutralization,
        color_balance=color_balance,
        color_balance_strength=color_balance_strength,
        channel_scales=channel_scales,
        balance_region=balance_region,
        smooth_sigma=smooth_sigma,
        unsharp_sigma=unsharp_sigma,
        unsharp_amount=unsharp_amount,
    )
    effective_limits = str(display_options["limits"])
    effective_scale = display_options["scale"]
    effective_background_neutralization = str(display_options["background_neutralization"])
    effective_color_balance = str(display_options["color_balance"])
    effective_color_balance_strength = float(display_options["color_balance_strength"])
    effective_channel_scales = tuple(display_options["channel_scales"])
    effective_balance_region = str(display_options["balance_region"])
    effective_smooth_sigma = display_options["smooth_sigma"]
    effective_unsharp_sigma = display_options["unsharp_sigma"]
    effective_unsharp_amount = display_options["unsharp_amount"]
    interpreted_crop_center = _interpret_crop_center(crop_center, crop_center_origin)

    written_paths: list[Path] = []
    for filter_name, stacked_file in sorted(stacked_files.items()):
        data, _header = load_fits(stacked_file)

        image_path = figures_dir / f"stacked_{filter_name}.png"
        fig = visualization.plot_image(
            data,
            title=f"{object_name} stacked {filter_name}",
            output_path=image_path,
        )
        plt.close(fig)
        written_paths.append(image_path)
        print(image_path)

        histogram_path = figures_dir / f"histogram_{filter_name}.png"
        fig = visualization.plot_histogram(
            data,
            title=f"{object_name} {filter_name} pixel histogram",
            output_path=histogram_path,
        )
        plt.close(fig)
        written_paths.append(histogram_path)
        print(histogram_path)

    if {"red", "green", "blue"}.issubset(stacked_files):
        rgb_files = _resolve_rgb_channel_files(stacked_dir, stacked_files)
        rgb_channel_data = {}
        for filter_name in ("red", "green", "blue"):
            rgb_channel_data[filter_name], _header = load_fits(rgb_files[filter_name])
        source_summary = ", ".join(
            f"{filter_name}={rgb_files[filter_name]}" for filter_name in ("red", "green", "blue")
        )
        print(f"RGB composite sources: {source_summary}")
        rgb = visualization.make_rgb_image(
            rgb_channel_data["red"],
            rgb_channel_data["green"],
            rgb_channel_data["blue"],
        )
        rgb_path = figures_dir / "rgb_composite.png"
        plt.imsave(rgb_path, rgb, origin="lower")
        written_paths.append(rgb_path)
        print(rgb_path)

        if enhance_rgb:
            enhanced_rgb = enhancement.make_enhanced_rgb(
                rgb_channel_data["red"],
                rgb_channel_data["green"],
                rgb_channel_data["blue"],
                lower=lower,
                upper=upper,
                background_percentile=background_percentile,
                stretch=stretch,
                gamma=gamma,
            )
            enhanced_rgb_path = figures_dir / "rgb_composite_enhanced.png"
            plt.imsave(enhanced_rgb_path, enhanced_rgb, origin="lower")
            written_paths.append(enhanced_rgb_path)
            print(enhanced_rgb_path)

        if ds9like:
            ds9_rgb = enhancement.make_display_rgb(
                rgb_channel_data["red"],
                rgb_channel_data["green"],
                rgb_channel_data["blue"],
                limits="zscale",
                scale="squared",
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                gamma=gamma,
                stretch=stretch,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
            )
            _save_rgb(
                figures_dir / "rgb_composite_ds9like.png",
                ds9_rgb,
                written_paths,
                "ds9like",
                limits="zscale",
                scale="squared",
                zscale_contrast=zscale_contrast,
                gamma=gamma,
                stretch=stretch,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
                balance_region=effective_balance_region,
            )
            _print_color_adjustment_log(
                "ds9like",
                rgb_channel_data,
                limits="zscale",
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
                balance_region=effective_balance_region,
            )

        if preset is not None and preset != "galaxy_detail":
            if effective_scale is None:
                raise DemoFigureError(f"Preset {preset} did not define an RGB scale")
            preset_rgb = enhancement.make_display_rgb(
                rgb_channel_data["red"],
                rgb_channel_data["green"],
                rgb_channel_data["blue"],
                limits=effective_limits,
                scale=effective_scale,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                gamma=gamma,
                stretch=stretch,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
            )
            _save_rgb(
                figures_dir / f"rgb_composite_{preset}.png",
                preset_rgb,
                written_paths,
                f"preset:{preset}",
                limits=effective_limits,
                scale=effective_scale,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                gamma=gamma,
                stretch=stretch,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
                balance_region=effective_balance_region,
            )
            _print_color_adjustment_log(
                f"preset:{preset}",
                rgb_channel_data,
                limits=effective_limits,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
                balance_region=effective_balance_region,
            )

        if preset is None and rgb_scale is not None:
            advanced_rgb = enhancement.make_display_rgb(
                rgb_channel_data["red"],
                rgb_channel_data["green"],
                rgb_channel_data["blue"],
                limits=effective_limits,
                scale=effective_scale,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                gamma=gamma,
                stretch=stretch,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
            )
            _save_rgb(
                figures_dir / f"rgb_composite_{effective_limits}_{effective_scale}.png",
                advanced_rgb,
                written_paths,
                "rgb-scale",
                limits=effective_limits,
                scale=effective_scale,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                gamma=gamma,
                stretch=stretch,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
                balance_region=effective_balance_region,
            )
            _print_color_adjustment_log(
                "rgb-scale",
                rgb_channel_data,
                limits=effective_limits,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
                balance_region=effective_balance_region,
            )

        crop_requested = interpreted_crop_center is not None or crop_size is not None or preset == "galaxy_detail"
        if crop_requested:
            if interpreted_crop_center is None or crop_size is None:
                if preset == "galaxy_detail":
                    print("Warning: --preset galaxy_detail requested without crop-center/crop-size; using full image.")
                    crop_center_for_output = None
                    crop_size_for_output = None
                else:
                    print(
                        "Warning: both --crop-center and --crop-size are required for crop "
                        "outputs; no crop output was written."
                    )
                    crop_center_for_output = None
                    crop_size_for_output = None
            else:
                crop_center_for_output = interpreted_crop_center
                crop_size_for_output = crop_size
                _print_crop_interpretation(
                    rgb_channel_data["red"].shape, crop_center, interpreted_crop_center, crop_size
                )

            if preset == "galaxy_detail" or (crop_center_for_output is not None and crop_size_for_output is not None):
                crop_scale = effective_scale or ("squared" if ds9like else "squared")
                suffix = _crop_method_suffix(
                    effective_smooth_sigma, effective_unsharp_sigma, effective_unsharp_amount
                )
                output_name = (
                    "rgb_crop_galaxy_detail.png"
                    if preset == "galaxy_detail"
                    else f"rgb_crop_{effective_limits}_{crop_scale}{suffix}.png"
                )
                crop_rgb = enhancement.make_processed_rgb(
                    rgb_channel_data["red"],
                    rgb_channel_data["green"],
                    rgb_channel_data["blue"],
                    limits=effective_limits,
                    scale=crop_scale,
                    zscale_contrast=zscale_contrast,
                    lower=lower,
                    upper=upper,
                    gamma=gamma,
                    stretch=stretch,
                    crop_center=crop_center_for_output,
                    crop_size=crop_size_for_output,
                    smooth_sigma=effective_smooth_sigma,
                    unsharp_sigma=effective_unsharp_sigma,
                    unsharp_amount=effective_unsharp_amount,
                    background_neutralization=effective_background_neutralization,
                    background_percentile=background_percentile,
                    color_balance=effective_color_balance,
                    color_balance_strength=effective_color_balance_strength,
                    channel_scales=effective_channel_scales,
                    balance_region=effective_balance_region,
                )
                _save_rgb(
                    figures_dir / output_name,
                    crop_rgb,
                    written_paths,
                    "crop" if preset != "galaxy_detail" else "preset:galaxy_detail",
                    limits=effective_limits,
                    scale=crop_scale,
                    crop_center=crop_center_for_output,
                    crop_size=crop_size_for_output,
                    smooth_sigma=effective_smooth_sigma,
                    unsharp_sigma=effective_unsharp_sigma,
                    unsharp_amount=effective_unsharp_amount,
                    gamma=gamma,
                    stretch=stretch,
                    background_neutralization=effective_background_neutralization,
                    background_percentile=background_percentile,
                    color_balance=effective_color_balance,
                    color_balance_strength=effective_color_balance_strength,
                    channel_scales=effective_channel_scales,
                    balance_region=effective_balance_region,
                )
                _print_color_adjustment_log(
                    "crop" if preset != "galaxy_detail" else "preset:galaxy_detail",
                    rgb_channel_data,
                    limits=effective_limits,
                    zscale_contrast=zscale_contrast,
                    lower=lower,
                    upper=upper,
                    background_neutralization=effective_background_neutralization,
                    background_percentile=background_percentile,
                    color_balance=effective_color_balance,
                    color_balance_strength=effective_color_balance_strength,
                    channel_scales=effective_channel_scales,
                    balance_region=effective_balance_region,
                    crop_center=crop_center_for_output,
                    crop_size=crop_size_for_output,
                )

        if galaxy_detail_grid:
            if interpreted_crop_center is None or crop_size is None:
                print("Warning: --galaxy-detail-grid requested without crop-center/crop-size; using full image.")
                grid_crop_center = None
                grid_crop_size = None
            else:
                grid_crop_center = interpreted_crop_center
                grid_crop_size = crop_size
                _print_crop_interpretation(
                    rgb_channel_data["red"].shape, crop_center, interpreted_crop_center, crop_size
                )
            grid_path = _make_galaxy_detail_grid(
                rgb_channel_data,
                figures_dir / "galaxy_detail_grid.png",
                crop_center=grid_crop_center,
                crop_size=grid_crop_size,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                gamma=gamma,
                stretch=stretch,
                smooth_sigma=0.8 if effective_smooth_sigma is None else effective_smooth_sigma,
                unsharp_sigma=2.0 if effective_unsharp_sigma is None else effective_unsharp_sigma,
                unsharp_amount=0.6 if effective_unsharp_amount is None else effective_unsharp_amount,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
                balance_region=effective_balance_region,
            )
            written_paths.append(grid_path)
            _print_color_adjustment_log(
                "galaxy-detail-grid",
                rgb_channel_data,
                limits="zscale",
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                background_neutralization=effective_background_neutralization,
                background_percentile=background_percentile,
                color_balance=effective_color_balance,
                color_balance_strength=effective_color_balance_strength,
                channel_scales=effective_channel_scales,
                balance_region=effective_balance_region,
                crop_center=grid_crop_center,
                crop_size=grid_crop_size,
            )

    return written_paths


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Generate PNG demo figures from object stacked FITS outputs.",
    )
    parser.add_argument(
        "--object",
        dest="object_name",
        required=True,
        help="Object name under the data root, for example M83.",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        help="Root directory containing object layouts (default: data).",
    )
    parser.add_argument(
        "--filters",
        nargs="+",
        help="Optional filter names to render, for example blue green red.",
    )
    parser.add_argument(
        "--enhance-rgb",
        action="store_true",
        help="Also write display-enhanced rgb_composite_enhanced.png when RGB channels exist.",
    )
    parser.add_argument(
        "--stretch",
        type=float,
        default=5.0,
        help="Asinh/log stretch strength for enhanced and DS9-like RGB outputs (default: 5.0).",
    )
    parser.add_argument(
        "--gamma",
        type=float,
        default=1.0,
        help="Gamma for enhanced RGB output (default: 1.0).",
    )
    parser.add_argument(
        "--background-percentile",
        type=float,
        default=10,
        help="Finite-pixel background percentile for RGB enhancement and color controls (default: 10).",
    )
    parser.add_argument(
        "--background-neutralization",
        choices=["none", "subtract", "equalize"],
        default=None,
        help="Advanced override for display RGB background neutralization.",
    )
    parser.add_argument(
        "--color-balance",
        choices=["none", "background", "median", "max"],
        default=None,
        help="Advanced override for display RGB channel balancing method.",
    )
    parser.add_argument(
        "--color-balance-strength",
        type=float,
        default=None,
        help="Blend automatic RGB balance factors toward one: 0 disables, 1 applies fully.",
    )
    parser.add_argument(
        "--channel-scales",
        nargs=3,
        type=float,
        metavar=("R", "G", "B"),
        default=None,
        help="Manual positive red/green/blue display multipliers applied after automatic balance.",
    )
    parser.add_argument(
        "--balance-region",
        choices=["full", "crop"],
        default=None,
        help="Region used to estimate crop background/color balance (default: full).",
    )
    parser.add_argument(
        "--lower",
        type=float,
        default=0.5,
        help="Lower finite-pixel percentile for RGB normalization (default: 0.5).",
    )
    parser.add_argument(
        "--upper",
        type=float,
        default=99.5,
        help="Upper finite-pixel percentile for RGB normalization (default: 99.5).",
    )
    parser.add_argument(
        "--ds9like",
        action="store_true",
        help="Write legacy rgb_composite_ds9like.png with zscale limits and squared display scale.",
    )
    parser.add_argument(
        "--preset",
        choices=["diagnostic", "natural", "deep_sky", "galaxy_detail"],
        help="Recommended named visualization workflow to write a preset output PNG.",
    )
    parser.add_argument(
        "--rgb-limits",
        choices=["zscale", "percentile"],
        default=None,
        help="Advanced override for display limits used by preset or named RGB outputs.",
    )
    parser.add_argument(
        "--rgb-scale",
        choices=["linear", "squared", "cubed", "sqrt", "log", "asinh", "gamma"],
        help="Advanced override for display scale used by preset or named RGB outputs.",
    )
    parser.add_argument(
        "--zscale-contrast",
        type=float,
        default=0.25,
        help="Contrast parameter for zscale display limits (default: 0.25).",
    )
    parser.add_argument(
        "--smooth-sigma",
        type=float,
        default=None,
        help="Optional Gaussian smoothing sigma for crop outputs (default: disabled).",
    )
    parser.add_argument(
        "--unsharp-sigma",
        type=float,
        default=None,
        help="Optional unsharp-mask blur sigma for crop outputs (default: disabled).",
    )
    parser.add_argument(
        "--unsharp-amount",
        type=float,
        default=None,
        help="Optional unsharp-mask amount for crop outputs (default: disabled).",
    )
    parser.add_argument(
        "--crop-center",
        nargs=2,
        type=float,
        metavar=("X", "Y"),
        help="Galaxy crop center as X Y display coordinates (column row).",
    )
    parser.add_argument(
        "--crop-size",
        type=float,
        help="Square galaxy crop size in pixels.",
    )
    parser.add_argument(
        "--crop-center-origin",
        type=int,
        choices=[0, 1],
        default=0,
        help="Coordinate origin for --crop-center X Y: 0 for Python zero-based, 1 for DS9 one-based.",
    )
    parser.add_argument(
        "--galaxy-detail-grid",
        action="store_true",
        help="Write galaxy_detail_grid.png with zscale crop scale/post-processing comparisons.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the demo figure CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        make_demo_figures(
            object_name=args.object_name,
            data_root=args.data_root,
            filters=args.filters,
            enhance_rgb=args.enhance_rgb,
            stretch=args.stretch,
            gamma=args.gamma,
            background_percentile=args.background_percentile,
            lower=args.lower,
            upper=args.upper,
            ds9like=args.ds9like,
            preset=args.preset,
            rgb_limits=args.rgb_limits,
            rgb_scale=args.rgb_scale,
            zscale_contrast=args.zscale_contrast,
            smooth_sigma=args.smooth_sigma,
            unsharp_sigma=args.unsharp_sigma,
            unsharp_amount=args.unsharp_amount,
            crop_center=args.crop_center,
            crop_size=args.crop_size,
            crop_center_origin=args.crop_center_origin,
            galaxy_detail_grid=args.galaxy_detail_grid,
            background_neutralization=args.background_neutralization,
            color_balance=args.color_balance,
            color_balance_strength=args.color_balance_strength,
            channel_scales=args.channel_scales,
            balance_region=args.balance_region,
        )
    except DemoFigureError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
