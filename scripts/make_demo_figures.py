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


def make_demo_figures(
    object_name: str,
    data_root: Path | str = Path("data"),
    filters: list[str] | None = None,
    enhance_rgb: bool = False,
    stretch: float = 5.0,
    gamma: float = 1.0,
    background_percentile: float = 10,
    lower: float = 1,
    upper: float = 99.5,
) -> list[Path]:
    """Create PNG demo figures from stacked FITS files for one object.

    Parameters
    ----------
    object_name : str
        Name of the object directory under ``data_root``.
    data_root : pathlib.Path or str, optional
        Root directory containing object-based data layouts. Defaults to
        ``data``.
    filters : list[str] or None, optional
        Optional list of filters to render. If omitted, filters are discovered
        from supported FITS files whose stems start with ``stacked_``.
    enhance_rgb : bool, optional
        When true, also write an enhanced display-only RGB PNG.
    stretch, gamma, background_percentile, lower, upper : float, optional
        Enhancement controls used only for ``rgb_composite_enhanced.png``.

    Returns
    -------
    list[pathlib.Path]
        Paths written, in print order.
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
        help="Asinh stretch strength for enhanced RGB output (default: 5.0).",
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
        default=1,
        help="Lower finite-pixel percentile for enhanced RGB normalization (default: 1).",
    )
    parser.add_argument(
        "--upper",
        type=float,
        default=99.5,
        help="Upper finite-pixel percentile for enhanced RGB normalization (default: 99.5).",
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
        )
    except DemoFigureError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
