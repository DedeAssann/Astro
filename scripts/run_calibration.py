#!/usr/bin/env python3
"""Run the calibration and stacking pipeline from a YAML configuration file."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

# Allow ``python scripts/run_calibration.py`` from a source checkout without
# requiring an editable install.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astro_image_lab.io import SUPPORTED_FITS_EXTENSIONS, discover_fits_files

make_master_bias = None
make_master_flat = None
load_fits = None
save_fits = None
calibrate_and_stack = None
align_stacked_channels = None
run_pipeline_diagnostics = None

EXPLICIT_INPUT_FIELDS = ("bias_files", "flat_files", "science_files")
COMPACT_INPUT_FIELDS = ("object_name", "data_root", "filters")
OUTPUT_DIR_FIELDS = ("calibrated", "stacked", "figures", "analysis")


def _parse_scalar(value: str) -> Any:
    """Parse a scalar from the small YAML subset used by pipeline configs."""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none", "~"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _load_minimal_yaml(config_path: Path) -> Any:
    """Load the simple mapping/list YAML subset needed for pipeline configs.

    PyYAML is preferred when installed. This fallback keeps the CLI runnable in
    lightweight teaching environments that do not include optional YAML
    dependencies, while still supporting the documented config shape.
    """
    tokens: list[tuple[int, str]] = []
    config_lines = config_path.read_text(encoding="utf-8").splitlines()
    for line_number, raw_line in enumerate(config_lines, start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if "\t" in raw_line[:indent]:
            raise ConfigError(f"YAML tabs are not supported at line {line_number}")
        tokens.append((indent, raw_line.strip()))

    if not tokens:
        return None

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(tokens):
            return {}, index

        current_indent, content = tokens[index]
        if current_indent < indent:
            return {}, index
        if current_indent != indent:
            raise ConfigError(f"Invalid YAML indentation near: {content}")

        if content.startswith("- "):
            items = []
            while index < len(tokens):
                item_indent, item_content = tokens[index]
                if item_indent < indent:
                    break
                if item_indent != indent or not item_content.startswith("- "):
                    break
                item_value = item_content[2:].strip()
                if item_value:
                    items.append(_parse_scalar(item_value))
                    index += 1
                else:
                    child, index = parse_block(index + 1, indent + 2)
                    items.append(child)
            return items, index

        mapping: dict[str, Any] = {}
        while index < len(tokens):
            item_indent, item_content = tokens[index]
            if item_indent < indent:
                break
            if item_indent != indent:
                raise ConfigError(f"Invalid YAML indentation near: {item_content}")
            if item_content.startswith("- "):
                break
            key, separator, value = item_content.partition(":")
            if not separator or not key.strip():
                raise ConfigError(f"Invalid YAML mapping entry: {item_content}")
            value = value.strip()
            if value:
                mapping[key.strip()] = _parse_scalar(value)
                index += 1
            else:
                mapping[key.strip()], index = parse_block(index + 1, indent + 2)
        return mapping, index

    parsed, final_index = parse_block(0, tokens[0][0])
    if final_index != len(tokens):
        raise ConfigError("Unable to parse the complete YAML config")
    return parsed


class ConfigError(ValueError):
    """Raised when the pipeline configuration is missing required values."""


def _load_yaml_config(config_path: Path) -> dict[str, Any]:
    """Load a YAML config file and return a mapping."""
    try:
        import yaml as yaml_module
    except ImportError:
        yaml_module = None

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    if not config_path.is_file():
        raise ConfigError(f"Config path is not a file: {config_path}")

    if yaml_module is not None:
        with config_path.open("r", encoding="utf-8") as config_file:
            config = yaml_module.safe_load(config_file)
    else:
        config = _load_minimal_yaml(config_path)

    if config is None:
        raise ConfigError(f"Config file is empty: {config_path}")
    if not isinstance(config, dict):
        raise ConfigError("Config file must contain a YAML mapping at the top level")
    return config


def _require_non_empty_list(config: dict[str, Any], field: str) -> list[str]:
    """Return a required non-empty list field from the config."""
    value = config.get(field)
    if not isinstance(value, list) or not value:
        raise ConfigError(f"Config field '{field}' must be a non-empty list of FITS paths")
    if any(not isinstance(item, str) or not item for item in value):
        raise ConfigError(f"Config field '{field}' must contain only non-empty path strings")
    return value


def _require_filter_mapping(config: dict[str, Any], field: str) -> dict[str, list[str]]:
    """Return a required mapping of filter names to non-empty path lists."""
    value = config.get(field)
    if not isinstance(value, dict) or not value:
        raise ConfigError(
            f"Config field '{field}' must map each filter to a non-empty list of FITS paths"
        )

    normalized: dict[str, list[str]] = {}
    for filter_name, file_list in value.items():
        if not isinstance(filter_name, str) or not filter_name:
            raise ConfigError(f"Config field '{field}' contains an invalid filter name: {filter_name!r}")
        if not isinstance(file_list, list) or not file_list:
            raise ConfigError(f"Config field '{field}.{filter_name}' must be a non-empty list of FITS paths")
        if any(not isinstance(item, str) or not item for item in file_list):
            raise ConfigError(
                f"Config field '{field}.{filter_name}' must contain only non-empty path strings"
            )
        normalized[filter_name] = file_list
    return normalized


def _require_non_empty_string(config: dict[str, Any], field: str) -> str:
    """Return a required non-empty string field from the config."""
    value = config.get(field)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"Config field '{field}' must be a non-empty string")
    return value


def _require_filters(config: dict[str, Any]) -> list[str]:
    """Return compact-config filters as a non-empty list of strings."""
    value = config.get("filters")
    if not isinstance(value, list) or not value:
        raise ConfigError("Config field 'filters' must be a non-empty list of filter names")
    if any(not isinstance(item, str) or not item for item in value):
        raise ConfigError("Config field 'filters' must contain only non-empty strings")
    return value


def _discover_fits_files(directory: Path, label: str) -> list[Path]:
    """Return sorted FITS-like files in ``directory`` or raise a clear config error."""
    if not directory.exists():
        raise ConfigError(f"Required {label} directory does not exist: {directory}")
    if not directory.is_dir():
        raise ConfigError(f"Required {label} path is not a directory: {directory}")

    fits_files = discover_fits_files(directory)
    if not fits_files:
        extensions = ", ".join(sorted(SUPPORTED_FITS_EXTENSIONS))
        raise ConfigError(f"No FITS files ({extensions}) found in required {label} directory: {directory}")
    return fits_files


def _infer_input_files(
    object_dir: Path, filters: list[str]
) -> tuple[list[Path], dict[str, list[Path]], dict[str, list[Path]]]:
    """Discover input FITS files from the standard object directory layout."""
    bias_files = _discover_fits_files(object_dir / "calibration" / "bias", "bias")
    flat_files = {
        filter_name: _discover_fits_files(
            object_dir / "calibration" / "flats" / filter_name,
            f"flat for filter '{filter_name}'",
        )
        for filter_name in filters
    }
    science_files = {
        filter_name: _discover_fits_files(
            object_dir / "raw" / filter_name,
            f"science for filter '{filter_name}'",
        )
        for filter_name in filters
    }
    return bias_files, flat_files, science_files


def _validate_alignment_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return normalized alignment options with legacy ``align`` compatibility."""
    legacy_align = config.get("align", True)
    if not isinstance(legacy_align, bool):
        raise ConfigError("Config field 'align' must be true or false")

    alignment = {
        "enabled": legacy_align,
        "method": "astroalign",
        "min_area": 12,
        "detection_sigma": None,
        "reference": "first",
        "fail_policy": "raise",
    }

    alignment_config = config.get("alignment")
    if alignment_config is None:
        return alignment
    if not isinstance(alignment_config, dict):
        raise ConfigError("Config field 'alignment' must be a mapping")

    if "enabled" in alignment_config:
        enabled = alignment_config["enabled"]
        if not isinstance(enabled, bool):
            raise ConfigError("Config field 'alignment.enabled' must be true or false")
        alignment["enabled"] = enabled

    if "method" in alignment_config:
        method = alignment_config["method"]
        if method != "astroalign":
            raise ConfigError("Config field 'alignment.method' must be 'astroalign'")
        alignment["method"] = method

    if "min_area" in alignment_config:
        min_area = alignment_config["min_area"]
        if not isinstance(min_area, int) or min_area <= 0:
            raise ConfigError("Config field 'alignment.min_area' must be a positive integer")
        alignment["min_area"] = min_area

    if "detection_sigma" in alignment_config:
        detection_sigma = alignment_config["detection_sigma"]
        if detection_sigma is not None and (
            not isinstance(detection_sigma, (int, float)) or detection_sigma <= 0
        ):
            raise ConfigError("Config field 'alignment.detection_sigma' must be a positive number or null")
        alignment["detection_sigma"] = detection_sigma

    if "reference" in alignment_config:
        reference = alignment_config["reference"]
        if reference != "first":
            raise ConfigError("Config field 'alignment.reference' must be 'first'")
        alignment["reference"] = reference

    if "fail_policy" in alignment_config:
        fail_policy = alignment_config["fail_policy"]
        if fail_policy not in {"raise", "skip"}:
            raise ConfigError("Config field 'alignment.fail_policy' must be 'raise' or 'skip'")
        alignment["fail_policy"] = fail_policy

    return alignment


def _validate_channel_alignment_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return normalized final stacked-channel alignment options."""
    channel_alignment = {
        "enabled": False,
        "reference_filter": None,
        "method": "astroalign",
        "min_area": 12,
        "fail_policy": "raise",
    }

    channel_config = config.get("channel_alignment")
    if channel_config is None:
        return channel_alignment
    if not isinstance(channel_config, dict):
        raise ConfigError("Config field 'channel_alignment' must be a mapping")

    if "enabled" in channel_config:
        enabled = channel_config["enabled"]
        if not isinstance(enabled, bool):
            raise ConfigError("Config field 'channel_alignment.enabled' must be true or false")
        channel_alignment["enabled"] = enabled

    if "reference_filter" in channel_config:
        reference_filter = channel_config["reference_filter"]
        if reference_filter is not None and (not isinstance(reference_filter, str) or not reference_filter):
            raise ConfigError(
                "Config field 'channel_alignment.reference_filter' must be a non-empty string or null"
            )
        channel_alignment["reference_filter"] = reference_filter

    if "method" in channel_config:
        method = channel_config["method"]
        if method != "astroalign":
            raise ConfigError("Config field 'channel_alignment.method' must be 'astroalign'")
        channel_alignment["method"] = method

    if "min_area" in channel_config:
        min_area = channel_config["min_area"]
        if not isinstance(min_area, int) or min_area <= 0:
            raise ConfigError("Config field 'channel_alignment.min_area' must be a positive integer")
        channel_alignment["min_area"] = min_area

    if "fail_policy" in channel_config:
        fail_policy = channel_config["fail_policy"]
        if fail_policy not in {"raise", "skip"}:
            raise ConfigError("Config field 'channel_alignment.fail_policy' must be 'raise' or 'skip'")
        channel_alignment["fail_policy"] = fail_policy

    return channel_alignment


def _normalize_output_dirs(config: dict[str, Any], object_dir: Path | None) -> dict[str, Path]:
    """Return configured or inferred output directories."""
    output_dirs_value = config.get("output_dirs")
    if output_dirs_value is not None:
        if not isinstance(output_dirs_value, dict):
            raise ConfigError("Config field 'output_dirs' must map output types to path strings")
        output_dirs: dict[str, Path] = {}
        for field in OUTPUT_DIR_FIELDS:
            path_value = output_dirs_value.get(field)
            if not isinstance(path_value, str) or not path_value:
                raise ConfigError(f"Config field 'output_dirs.{field}' must be a non-empty path string")
            output_dirs[field] = Path(path_value)
        return output_dirs

    output_dir = config.get("output_dir")
    if output_dir is not None:
        if not isinstance(output_dir, str) or not output_dir:
            raise ConfigError("Config field 'output_dir' must be a non-empty path string")
        legacy_output_dir = Path(output_dir)
        return {field: legacy_output_dir for field in OUTPUT_DIR_FIELDS}

    if object_dir is None:
        raise ConfigError("Config must provide output_dirs, output_dir, or compact object_name/data_root")
    return {field: object_dir / field for field in OUTPUT_DIR_FIELDS}




def _validate_stacking_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return normalized stacking options."""
    stacking = {"normalize_before_stack": False}
    stacking_config = config.get("stacking")
    if stacking_config is None:
        return stacking
    if not isinstance(stacking_config, dict):
        raise ConfigError("Config field 'stacking' must be a mapping")

    if "normalize_before_stack" in stacking_config:
        normalize_before_stack = stacking_config["normalize_before_stack"]
        if not isinstance(normalize_before_stack, bool):
            raise ConfigError("Config field 'stacking.normalize_before_stack' must be true or false")
        stacking["normalize_before_stack"] = normalize_before_stack

    return stacking

def _validate_diagnostics_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return normalized diagnostics options."""
    diagnostics = {
        "enabled": False,
        "random_seed": 42,
        "bins": 100,
        "lower_percentile": 0.5,
        "upper_percentile": 99.5,
        "max_pixels": 1_000_000,
    }
    diagnostics_config = config.get("diagnostics")
    if diagnostics_config is None:
        return diagnostics
    if not isinstance(diagnostics_config, dict):
        raise ConfigError("Config field 'diagnostics' must be a mapping")

    if "enabled" in diagnostics_config:
        enabled = diagnostics_config["enabled"]
        if not isinstance(enabled, bool):
            raise ConfigError("Config field 'diagnostics.enabled' must be true or false")
        diagnostics["enabled"] = enabled

    if "random_seed" in diagnostics_config:
        random_seed = diagnostics_config["random_seed"]
        if random_seed is not None and (not isinstance(random_seed, int) or isinstance(random_seed, bool)):
            raise ConfigError("Config field 'diagnostics.random_seed' must be an integer or null")
        diagnostics["random_seed"] = random_seed

    if "bins" in diagnostics_config:
        bins = diagnostics_config["bins"]
        if not isinstance(bins, int) or isinstance(bins, bool) or bins <= 0:
            raise ConfigError("Config field 'diagnostics.bins' must be a positive integer")
        diagnostics["bins"] = bins

    for field in ("lower_percentile", "upper_percentile"):
        if field in diagnostics_config:
            percentile = diagnostics_config[field]
            if not isinstance(percentile, (int, float)) or isinstance(percentile, bool):
                raise ConfigError(f"Config field 'diagnostics.{field}' must be a number")
            diagnostics[field] = float(percentile)

    if not 0 <= diagnostics["lower_percentile"] < diagnostics["upper_percentile"] <= 100:
        raise ConfigError(
            "Config fields 'diagnostics.lower_percentile' and 'diagnostics.upper_percentile' "
            "must satisfy 0 <= lower < upper <= 100"
        )

    if "max_pixels" in diagnostics_config:
        max_pixels = diagnostics_config["max_pixels"]
        if not isinstance(max_pixels, int) or isinstance(max_pixels, bool) or max_pixels <= 0:
            raise ConfigError("Config field 'diagnostics.max_pixels' must be a positive integer")
        diagnostics["max_pixels"] = max_pixels

    return diagnostics

def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate config shape, discover compact inputs, and fill optional defaults."""
    has_explicit_inputs = all(field in config for field in EXPLICIT_INPUT_FIELDS)
    has_any_explicit_input = any(field in config for field in EXPLICIT_INPUT_FIELDS)
    has_compact_inputs = all(field in config for field in COMPACT_INPUT_FIELDS)

    object_name = config.get("object_name")
    if object_name is not None and (not isinstance(object_name, str) or not object_name):
        raise ConfigError("Config field 'object_name' must be a non-empty string when provided")

    object_dir: Path | None = None
    if has_compact_inputs:
        data_root = _require_non_empty_string(config, "data_root")
        filters = _require_filters(config)
        object_dir = Path(data_root) / _require_non_empty_string(config, "object_name")

    if has_explicit_inputs:
        bias_files = [Path(path) for path in _require_non_empty_list(config, "bias_files")]
        flat_files = {
            name: [Path(path) for path in paths]
            for name, paths in _require_filter_mapping(config, "flat_files").items()
        }
        science_files = {
            name: [Path(path) for path in paths]
            for name, paths in _require_filter_mapping(config, "science_files").items()
        }
    elif has_any_explicit_input:
        missing_fields = [field for field in EXPLICIT_INPUT_FIELDS if field not in config]
        missing = ", ".join(missing_fields)
        raise ConfigError(
            "Config must provide all explicit input fields "
            f"(missing: {missing}) or use compact object_name/data_root/filters discovery"
        )
    elif has_compact_inputs:
        bias_files, flat_files, science_files = _infer_input_files(object_dir, filters)
    else:
        raise ConfigError(
            "Config must provide either explicit bias_files, flat_files, science_files "
            "or compact object_name, data_root, filters"
        )

    flat_filters = set(flat_files)
    science_filters = set(science_files)
    if flat_filters != science_filters:
        missing_flat = sorted(science_filters - flat_filters)
        missing_science = sorted(flat_filters - science_filters)
        details = []
        if missing_flat:
            details.append(f"missing flat_files for filter(s): {', '.join(missing_flat)}")
        if missing_science:
            details.append(f"missing science_files for filter(s): {', '.join(missing_science)}")
        raise ConfigError("Config filter mismatch: " + "; ".join(details))

    output_dirs = _normalize_output_dirs(config, object_dir)

    alignment = _validate_alignment_config(config)
    channel_alignment = _validate_channel_alignment_config(config)
    stacking = _validate_stacking_config(config)
    diagnostics = _validate_diagnostics_config(config)

    sigma = config.get("sigma", 2)
    if not isinstance(sigma, (int, float)) or sigma <= 0:
        raise ConfigError("Config field 'sigma' must be a positive number")

    maxiters = config.get("maxiters", 10)
    if maxiters is not None and (not isinstance(maxiters, int) or maxiters < 0):
        raise ConfigError("Config field 'maxiters' must be a non-negative integer or null")

    return {
        "bias_files": bias_files,
        "flat_files": flat_files,
        "science_files": science_files,
        "object_name": object_name,
        "object_dir": object_dir,
        "output_dirs": output_dirs,
        "align": alignment["enabled"],
        "alignment": alignment,
        "channel_alignment": channel_alignment,
        "stacking": stacking,
        "diagnostics": diagnostics,
        "sigma": sigma,
        "maxiters": maxiters,
    }


def _input_paths(config: dict[str, Any]) -> list[Path]:
    """Collect all configured input FITS paths."""
    paths = list(config["bias_files"])
    for files_by_filter in (config["flat_files"], config["science_files"]):
        for file_list in files_by_filter.values():
            paths.extend(file_list)
    return paths


def _ensure_input_files_exist(paths: list[Path]) -> None:
    """Raise a clear error if any configured input path is missing."""
    missing = [path for path in paths if not path.exists()]
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(f"Missing input FITS file(s):\n{formatted}")


def _get_pipeline_functions():
    """Import pipeline helpers lazily after config and file validation."""
    global make_master_bias, make_master_flat, load_fits, save_fits
    global calibrate_and_stack, align_stacked_channels, run_pipeline_diagnostics
    if make_master_bias is None or make_master_flat is None:
        from astro_image_lab.calibration import make_master_bias as imported_make_master_bias
        from astro_image_lab.calibration import make_master_flat as imported_make_master_flat

        make_master_bias = imported_make_master_bias
        make_master_flat = imported_make_master_flat
    if load_fits is None or save_fits is None:
        from astro_image_lab.io import load_fits as imported_load_fits
        from astro_image_lab.io import save_fits as imported_save_fits

        load_fits = imported_load_fits
        save_fits = imported_save_fits
    if calibrate_and_stack is None:
        from astro_image_lab.stacking import calibrate_and_stack as imported_calibrate_and_stack

        calibrate_and_stack = imported_calibrate_and_stack
    if align_stacked_channels is None:
        from astro_image_lab.channel_alignment import (
            align_stacked_channels as imported_align_stacked_channels,
        )

        align_stacked_channels = imported_align_stacked_channels
    if run_pipeline_diagnostics is None:
        from astro_image_lab.diagnostics import (
            run_pipeline_diagnostics as imported_run_pipeline_diagnostics,
        )

        run_pipeline_diagnostics = imported_run_pipeline_diagnostics
    return (
        make_master_bias,
        make_master_flat,
        load_fits,
        save_fits,
        calibrate_and_stack,
        align_stacked_channels,
        run_pipeline_diagnostics,
    )


def _write_csv_report(records: list[dict[str, Any]], output_path: Path, fieldnames: list[str]) -> None:
    """Write report records to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fieldnames})


def _write_alignment_report(records: list[dict[str, Any]], output_path: Path) -> None:
    """Write collected frame-alignment report records to CSV."""
    _write_csv_report(
        records,
        output_path,
        ["filter", "file_path", "index", "status", "error", "method", "min_area"],
    )


def _write_channel_alignment_report(records: list[dict[str, Any]], output_path: Path) -> None:
    """Write collected channel-alignment report records to CSV."""
    _write_csv_report(
        records,
        output_path,
        [
            "filter",
            "input_path",
            "output_path",
            "status",
            "reference_filter",
            "method",
            "min_area",
            "error",
        ],
    )


def run_pipeline(config_path: Path) -> list[Path]:
    """Run calibration and stacking from ``config_path`` and return written files."""
    raw_config = _load_yaml_config(config_path)
    config = _validate_config(raw_config)
    _ensure_input_files_exist(_input_paths(config))
    (
        make_bias,
        make_flat,
        fits_loader,
        fits_saver,
        stack_science,
        align_channels,
        diagnose_pipeline,
    ) = _get_pipeline_functions()

    output_dirs = config["output_dirs"]
    for output_dir in output_dirs.values():
        output_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[Path] = []
    alignment_report_records: list[dict[str, Any]] = []
    stacked_paths: dict[str, Path] = {}
    master_flats: dict[str, Any] = {}
    master_flat_paths: dict[str, Path] = {}
    stacked_images: dict[str, Any] = {}

    master_bias = make_bias(config["bias_files"])
    _bias_data, bias_header = fits_loader(config["bias_files"][0])
    master_bias_path = output_dirs["calibrated"] / "master_bias.fits"
    fits_saver(master_bias, bias_header, master_bias_path)
    written_files.append(master_bias_path)
    print(f"Wrote {master_bias_path}")

    for filter_name in sorted(config["science_files"]):
        master_flat = make_flat(config["flat_files"][filter_name], master_bias)
        _flat_data, flat_header = fits_loader(config["flat_files"][filter_name][0])
        master_flat_path = output_dirs["calibrated"] / f"master_flat_{filter_name}.fits"
        fits_saver(master_flat, flat_header, master_flat_path)
        written_files.append(master_flat_path)
        master_flats[filter_name] = master_flat
        master_flat_paths[filter_name] = master_flat_path
        print(f"Wrote {master_flat_path}")

        alignment = config["alignment"]
        stacked_image, filter_report_records = stack_science(
            config["science_files"][filter_name],
            master_bias,
            master_flat,
            align=alignment["enabled"],
            min_area=alignment["min_area"],
            sigma=config["sigma"],
            maxiters=config["maxiters"],
            return_alignment_report=True,
            filter_name=filter_name,
            fail_policy=alignment["fail_policy"],
            alignment_method=alignment["method"],
            detection_sigma=alignment["detection_sigma"],
            normalize_before_stack=config["stacking"]["normalize_before_stack"],
        )
        alignment_report_records.extend(filter_report_records)
        _science_data, science_header = fits_loader(config["science_files"][filter_name][0])
        stacked_path = output_dirs["stacked"] / f"stacked_{filter_name}.fits"
        fits_saver(stacked_image, science_header, stacked_path)
        written_files.append(stacked_path)
        stacked_paths[filter_name] = stacked_path
        stacked_images[filter_name] = stacked_image
        print(f"Wrote {stacked_path}")

    diagnostics = config["diagnostics"]
    if diagnostics["enabled"]:
        diagnostics_dir = output_dirs["analysis"] / "diagnostics"
        diagnostic_files = diagnose_pipeline(
            bias_files=config["bias_files"],
            flat_files=config["flat_files"],
            science_files=config["science_files"],
            master_bias=master_bias,
            master_bias_path=master_bias_path,
            master_flats=master_flats,
            master_flat_paths=master_flat_paths,
            stacked_images=stacked_images,
            stacked_paths=stacked_paths,
            output_dir=diagnostics_dir,
            config=diagnostics,
            normalize_before_stack=config["stacking"]["normalize_before_stack"],
        )
        written_files.extend(diagnostic_files)
        for diagnostic_file in diagnostic_files:
            print(f"Wrote {diagnostic_file}")

    channel_alignment = config["channel_alignment"]
    if channel_alignment["enabled"]:
        aligned_channel_dir = output_dirs["stacked"] / "aligned_channels"
        channel_report_records = align_channels(
            stacked_paths,
            aligned_channel_dir,
            reference_filter=channel_alignment["reference_filter"],
            method=channel_alignment["method"],
            min_area=channel_alignment["min_area"],
            fail_policy=channel_alignment["fail_policy"],
        )
        for record in channel_report_records:
            if record["status"] in {"reference", "aligned"}:
                written_files.append(Path(record["output_path"]))
                print(f"Wrote {record['output_path']}")
        channel_report_path = output_dirs["analysis"] / "channel_alignment_report.csv"
        _write_channel_alignment_report(channel_report_records, channel_report_path)
        written_files.append(channel_report_path)
        print(f"Wrote {channel_report_path}")

    alignment_report_path = output_dirs["analysis"] / "alignment_report.csv"
    _write_alignment_report(alignment_report_records, alignment_report_path)
    written_files.append(alignment_report_path)
    print(f"Wrote {alignment_report_path}")

    return written_files


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run FITS calibration and stacking from a YAML config."
    )
    parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Path to the YAML pipeline config.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    try:
        written_files = run_pipeline(args.config)
    except (ConfigError, FileNotFoundError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Pipeline complete. Wrote {len(written_files)} file(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
