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
    rgb_limits: str = "zscale",
    rgb_scale: str | None = None,
    zscale_contrast: float = 0.25,
    smooth_sigma: float | None = None,
    unsharp_sigma: float | None = None,
    unsharp_amount: float | None = None,
    crop_center: list[float] | tuple[float, float] | None = None,
    crop_size: float | None = None,
    galaxy_detail_grid: bool = False,
) -> list[Path]:
    """Create PNG demo figures from stacked FITS files for one object.

    All DS9-like scaling, crops, smoothing, and sharpening are visualization-only
    PNG post-processing steps. Calibrated and stacked FITS data are never
    modified by this command.
    """
    data_root = Path(data_root)
    stacked_dir = data_root / object_name / "stacked"
    stacked_files = _resolve_stacked_files(data_root, object_name, filters)
    figures_dir = data_root / object_name / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

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
            )

        if rgb_scale is not None:
            scaled_rgb = enhancement.make_display_rgb(
                rgb_channel_data["red"],
                rgb_channel_data["green"],
                rgb_channel_data["blue"],
                limits=rgb_limits,
                scale=rgb_scale,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                gamma=gamma,
                stretch=stretch,
            )
            _save_rgb(
                figures_dir / f"rgb_composite_{rgb_limits}_{rgb_scale}.png",
                scaled_rgb,
                written_paths,
                "rgb-scale",
                limits=rgb_limits,
                scale=rgb_scale,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                gamma=gamma,
                stretch=stretch,
            )

        crop_requested = crop_center is not None or crop_size is not None
        if crop_requested:
            if crop_center is None or crop_size is None:
                print(
                    "Warning: both --crop-center and --crop-size are required for crop "
                    "outputs; no crop output was written."
                )
            else:
                crop_scale = rgb_scale or ("squared" if ds9like else "squared")
                suffix = _crop_method_suffix(smooth_sigma, unsharp_sigma, unsharp_amount)
                crop_rgb = enhancement.make_processed_rgb(
                    rgb_channel_data["red"],
                    rgb_channel_data["green"],
                    rgb_channel_data["blue"],
                    limits=rgb_limits,
                    scale=crop_scale,
                    zscale_contrast=zscale_contrast,
                    lower=lower,
                    upper=upper,
                    gamma=gamma,
                    stretch=stretch,
                    crop_center=crop_center,
                    crop_size=crop_size,
                    smooth_sigma=smooth_sigma,
                    unsharp_sigma=unsharp_sigma,
                    unsharp_amount=unsharp_amount,
                )
                _save_rgb(
                    figures_dir / f"rgb_crop_{rgb_limits}_{crop_scale}{suffix}.png",
                    crop_rgb,
                    written_paths,
                    "crop",
                    limits=rgb_limits,
                    scale=crop_scale,
                    crop_center=crop_center,
                    crop_size=crop_size,
                    smooth_sigma=smooth_sigma,
                    unsharp_sigma=unsharp_sigma,
                    unsharp_amount=unsharp_amount,
                    gamma=gamma,
                    stretch=stretch,
                )

        if galaxy_detail_grid:
            if crop_center is None or crop_size is None:
                print("Warning: --galaxy-detail-grid requested without crop-center/crop-size; using full image.")
            grid_path = _make_galaxy_detail_grid(
                rgb_channel_data,
                figures_dir / "galaxy_detail_grid.png",
                crop_center=crop_center,
                crop_size=crop_size,
                zscale_contrast=zscale_contrast,
                lower=lower,
                upper=upper,
                gamma=gamma,
                stretch=stretch,
                smooth_sigma=0.8 if smooth_sigma is None else smooth_sigma,
                unsharp_sigma=2.0 if unsharp_sigma is None else unsharp_sigma,
                unsharp_amount=0.6 if unsharp_amount is None else unsharp_amount,
            )
            written_paths.append(grid_path)

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
        help="Finite-pixel percentile subtracted as background per RGB channel (default: 10).",
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
        help="Write rgb_composite_ds9like.png with zscale limits and squared display scale.",
    )
    parser.add_argument(
        "--rgb-limits",
        choices=["zscale", "percentile"],
        default="zscale",
        help="Display limits for named RGB outputs (default: zscale).",
    )
    parser.add_argument(
        "--rgb-scale",
        choices=["linear", "squared", "cubed", "sqrt", "log", "asinh", "gamma"],
        help="Display scale for named RGB outputs.",
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
            rgb_limits=args.rgb_limits,
            rgb_scale=args.rgb_scale,
            zscale_contrast=args.zscale_contrast,
            smooth_sigma=args.smooth_sigma,
            unsharp_sigma=args.unsharp_sigma,
            unsharp_amount=args.unsharp_amount,
            crop_center=args.crop_center,
            crop_size=args.crop_size,
            galaxy_detail_grid=args.galaxy_detail_grid,
        )
    except DemoFigureError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
