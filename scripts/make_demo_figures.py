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

from astro_image_lab import visualization
from astro_image_lab.io import load_fits


class DemoFigureError(ValueError):
    """Raised when demo figure inputs cannot be resolved."""


def _stacked_path(data_root: Path, object_name: str, filter_name: str) -> Path:
    """Return the expected stacked FITS path for an object/filter pair."""
    return data_root / object_name / "stacked" / f"stacked_{filter_name}.fits"


def _discover_filters(stacked_dir: Path) -> list[str]:
    """Discover filters from ``stacked_*.fits`` files in a stacked directory."""
    if not stacked_dir.exists():
        raise DemoFigureError(f"Stacked directory does not exist: {stacked_dir}")
    if not stacked_dir.is_dir():
        raise DemoFigureError(f"Stacked path is not a directory: {stacked_dir}")

    filters = sorted(
        path.stem.removeprefix("stacked_")
        for path in stacked_dir.glob("stacked_*.fits")
        if path.is_file()
    )
    if not filters:
        raise DemoFigureError(f"No stacked FITS files found in {stacked_dir}")
    return filters


def _resolve_stacked_files(
    data_root: Path,
    object_name: str,
    filters: list[str] | None = None,
) -> dict[str, Path]:
    """Resolve filter names to stacked FITS files for demo figure generation."""
    stacked_dir = data_root / object_name / "stacked"
    selected_filters = filters if filters is not None else _discover_filters(stacked_dir)

    stacked_files: dict[str, Path] = {}
    missing: list[Path] = []
    for filter_name in selected_filters:
        stacked_file = _stacked_path(data_root, object_name, filter_name)
        if stacked_file.is_file():
            stacked_files[filter_name] = stacked_file
        else:
            missing.append(stacked_file)

    if missing:
        missing_paths = ", ".join(str(path) for path in missing)
        raise DemoFigureError(f"Stacked FITS file(s) not found: {missing_paths}")
    if not stacked_files:
        raise DemoFigureError(f"No stacked FITS files found in {stacked_dir}")
    return stacked_files


def make_demo_figures(
    object_name: str,
    data_root: Path | str = Path("data"),
    filters: list[str] | None = None,
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
        from files matching ``stacked_*.fits``.

    Returns
    -------
    list[pathlib.Path]
        Paths written, in print order.
    """
    data_root = Path(data_root)
    stacked_files = _resolve_stacked_files(data_root, object_name, filters)
    figures_dir = data_root / object_name / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    channel_data: dict[str, object] = {}

    for filter_name, stacked_file in sorted(stacked_files.items()):
        data, _header = load_fits(stacked_file)
        channel_data[filter_name] = data

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

    if {"red", "green", "blue"}.issubset(channel_data):
        rgb = visualization.make_rgb_image(
            channel_data["red"],
            channel_data["green"],
            channel_data["blue"],
        )
        rgb_path = figures_dir / "rgb_composite.png"
        plt.imsave(rgb_path, rgb, origin="lower")
        written_paths.append(rgb_path)
        print(rgb_path)

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
        )
    except DemoFigureError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
