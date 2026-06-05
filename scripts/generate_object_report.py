#!/usr/bin/env python3
"""Generate a compact Markdown report for one object pipeline run."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED_FITS_EXTENSIONS = {".fits", ".fit", ".fts"}
KEY_VISUALIZATION_OUTPUTS = [
    "rgb_composite.png",
    "rgb_composite_deep_sky.png",
    "rgb_crop_galaxy_detail.png",
    "rgb_crop_galaxy_detail_masked_unsharp.png",
]
KEY_DIAGNOSTIC_PATTERNS = [
    "*hist*.png",
    "*linearity*.png",
    "*mean_median*.png",
    "*distribution*.png",
]


class ObjectReportError(ValueError):
    """Raised when object-report inputs cannot be resolved."""


def _is_supported_fits(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_FITS_EXTENSIONS


def _relative(path: Path, base: Path) -> str:
    """Return a stable Markdown-friendly path relative to ``base`` when possible."""
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _list_supported_fits(directory: Path, prefix: str | None = None) -> list[Path]:
    if not directory.exists():
        return []
    files = [path for path in directory.iterdir() if path.is_file() and _is_supported_fits(path)]
    if prefix is not None:
        files = [path for path in files if path.stem.startswith(prefix)]
    return sorted(files)


def _read_warning_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _status_counts(csv_path: Path) -> Counter:
    counts: Counter = Counter()
    if not csv_path.exists():
        return counts
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "status" not in reader.fieldnames:
            return counts
        for row in reader:
            status = (row.get("status") or "unknown").strip() or "unknown"
            counts[status] += 1
    return counts


def _format_counts(counts: Counter) -> str:
    if not counts:
        return "not available"
    return ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))


def _first_existing_path(*paths: Path) -> Path:
    """Return the first existing path, or the first candidate when none exist."""
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _diagnostic_pngs(analysis_dir: Path) -> list[Path]:
    candidates: set[Path] = set()
    search_roots = [analysis_dir]
    diagnostics_dir = analysis_dir / "diagnostics"
    if diagnostics_dir.exists():
        search_roots.append(diagnostics_dir)
    for root in search_roots:
        if not root.exists():
            continue
        for pattern in KEY_DIAGNOSTIC_PATTERNS:
            candidates.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(candidates)


def _append_path_section(lines: list[str], title: str, paths: list[Path], data_root: Path) -> None:
    lines.append(f"## {title}")
    if paths:
        lines.extend(f"- `{_relative(path, data_root)}`" for path in paths)
    else:
        lines.append("- Not found.")
    lines.append("")


def generate_object_report(object_name: str, data_root: Path | str = Path("data")) -> Path:
    """Write ``data/<OBJECT_NAME>/analysis/report.md`` and return its path."""
    data_root = Path(data_root)
    object_dir = data_root / object_name
    if not object_dir.exists():
        raise ObjectReportError(f"Object directory does not exist: {object_dir}")

    stacked_dir = object_dir / "stacked"
    aligned_dir = stacked_dir / "aligned_channels"
    figures_dir = object_dir / "figures"
    analysis_dir = object_dir / "analysis"
    diagnostics_dir = analysis_dir / "diagnostics"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    stacked_files = _list_supported_fits(stacked_dir, prefix="stacked_")
    aligned_files = _list_supported_fits(aligned_dir, prefix="stacked_")
    visualization_outputs = [figures_dir / name for name in KEY_VISUALIZATION_OUTPUTS if (figures_dir / name).exists()]

    warnings_path = _first_existing_path(
        analysis_dir / "calibration_qc_warnings.txt",
        diagnostics_dir / "calibration_qc_warnings.txt",
    )
    warning_lines = _read_warning_lines(warnings_path)
    bias_stats_path = _first_existing_path(
        analysis_dir / "bias_frame_statistics.csv",
        diagnostics_dir / "bias_frame_statistics.csv",
    )
    flat_stats_path = _first_existing_path(
        analysis_dir / "flat_frame_statistics.csv",
        diagnostics_dir / "flat_frame_statistics.csv",
    )
    alignment_report_path = analysis_dir / "alignment_report.csv"
    channel_alignment_report_path = analysis_dir / "channel_alignment_report.csv"
    alignment_counts = _status_counts(alignment_report_path)
    channel_alignment_counts = _status_counts(channel_alignment_report_path)
    diagnostic_pngs = _diagnostic_pngs(analysis_dir)

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = [
        f"# {object_name} Object Report",
        "",
        f"Generated: {timestamp}",
        "",
        "## Data layout paths",
        f"- Object directory: `{_relative(object_dir, data_root)}`",
        f"- Stacked FITS directory: `{_relative(stacked_dir, data_root)}`",
        f"- Aligned channel directory: `{_relative(aligned_dir, data_root)}`",
        f"- Figures directory: `{_relative(figures_dir, data_root)}`",
        f"- Analysis directory: `{_relative(analysis_dir, data_root)}`",
        f"- Diagnostics directory: `{_relative(diagnostics_dir, data_root)}`",
        "",
    ]

    _append_path_section(lines, "Stacked FITS files", stacked_files, data_root)
    _append_path_section(lines, "Aligned channel FITS files", aligned_files, data_root)
    _append_path_section(lines, "Key visualization outputs", visualization_outputs, data_root)

    lines.extend(["## Calibration QC", f"- Warnings file: `{_relative(warnings_path, data_root)}`"])
    if warning_lines:
        lines.append("- Warning summary:")
        lines.extend(f"  - {line}" for line in warning_lines)
    else:
        lines.append("- Warning summary: none found.")
    lines.extend(
        [
            f"- Bias frame statistics: `{_relative(bias_stats_path, data_root)}`",
            f"- Flat frame statistics: `{_relative(flat_stats_path, data_root)}`",
            "",
            "## Alignment QC",
            f"- Alignment report: `{_relative(alignment_report_path, data_root)}`",
            f"- Alignment status counts: {_format_counts(alignment_counts)}",
            f"- Channel alignment report: `{_relative(channel_alignment_report_path, data_root)}`",
            f"- Channel alignment status counts: {_format_counts(channel_alignment_counts)}",
            "",
        ]
    )

    _append_path_section(lines, "Diagnostics", diagnostic_pngs, data_root)
    lines.extend(
        [
            "## Suggested next manual checks",
            f"- Inspect `{_relative(warnings_path, data_root)}` for calibration warnings.",
            "- Inspect flat linearity curves in the diagnostics directory.",
            "- Inspect `rgb_composite_deep_sky.png` and galaxy-detail crop PNGs for visualization quality.",
            "- Summary sheet: TODO; this report currently focuses on portable Markdown outputs.",
            "",
        ]
    )

    report_path = analysis_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a compact Markdown report for one object.")
    parser.add_argument("--object", dest="object_name", required=True, help="Object name under the data root.")
    parser.add_argument("--data-root", type=Path, default=Path("data"), help="Root directory containing object layouts (default: data).")
    parser.add_argument(
        "--summary-sheet",
        action="store_true",
        help="Reserved for a future object_summary_sheet.png; report.md is still generated.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        report_path = generate_object_report(args.object_name, data_root=args.data_root)
    except ObjectReportError as exc:
        parser.error(str(exc))
    if args.summary_sheet:
        print("Warning: --summary-sheet is not implemented yet; wrote Markdown report only.")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
