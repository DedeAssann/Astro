#!/usr/bin/env python3
"""Run the calibration and stacking pipeline from a YAML configuration file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Allow ``python scripts/run_calibration.py`` from a source checkout without
# requiring an editable install.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

make_master_bias = None
make_master_flat = None
load_fits = None
save_fits = None
calibrate_and_stack = None

REQUIRED_FIELDS = ("bias_files", "flat_files", "science_files", "output_dir")


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


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate config shape and fill optional defaults."""
    missing_fields = [field for field in REQUIRED_FIELDS if field not in config]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ConfigError(f"Config is missing required field(s): {missing}")

    bias_files = _require_non_empty_list(config, "bias_files")
    flat_files = _require_filter_mapping(config, "flat_files")
    science_files = _require_filter_mapping(config, "science_files")

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

    output_dir = config["output_dir"]
    if not isinstance(output_dir, str) or not output_dir:
        raise ConfigError("Config field 'output_dir' must be a non-empty path string")

    align = config.get("align", True)
    if not isinstance(align, bool):
        raise ConfigError("Config field 'align' must be true or false")

    sigma = config.get("sigma", 2)
    if not isinstance(sigma, (int, float)) or sigma <= 0:
        raise ConfigError("Config field 'sigma' must be a positive number")

    maxiters = config.get("maxiters", 10)
    if maxiters is not None and (not isinstance(maxiters, int) or maxiters < 0):
        raise ConfigError("Config field 'maxiters' must be a non-negative integer or null")

    return {
        "bias_files": [Path(path) for path in bias_files],
        "flat_files": {name: [Path(path) for path in paths] for name, paths in flat_files.items()},
        "science_files": {name: [Path(path) for path in paths] for name, paths in science_files.items()},
        "output_dir": Path(output_dir),
        "align": align,
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
    global calibrate_and_stack
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
    return make_master_bias, make_master_flat, load_fits, save_fits, calibrate_and_stack

def run_pipeline(config_path: Path) -> list[Path]:
    """Run calibration and stacking from ``config_path`` and return written files."""
    raw_config = _load_yaml_config(config_path)
    config = _validate_config(raw_config)
    _ensure_input_files_exist(_input_paths(config))
    make_bias, make_flat, fits_loader, fits_saver, stack_science = _get_pipeline_functions()

    output_dir = config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    written_files: list[Path] = []

    master_bias = make_bias(config["bias_files"])
    _bias_data, bias_header = fits_loader(config["bias_files"][0])
    master_bias_path = output_dir / "master_bias.fits"
    fits_saver(master_bias, bias_header, master_bias_path)
    written_files.append(master_bias_path)
    print(f"Wrote {master_bias_path}")

    for filter_name in sorted(config["science_files"]):
        master_flat = make_flat(config["flat_files"][filter_name], master_bias)
        _flat_data, flat_header = fits_loader(config["flat_files"][filter_name][0])
        master_flat_path = output_dir / f"master_flat_{filter_name}.fits"
        fits_saver(master_flat, flat_header, master_flat_path)
        written_files.append(master_flat_path)
        print(f"Wrote {master_flat_path}")

        stacked_image = stack_science(
            config["science_files"][filter_name],
            master_bias,
            master_flat,
            align=config["align"],
            sigma=config["sigma"],
            maxiters=config["maxiters"],
        )
        _science_data, science_header = fits_loader(config["science_files"][filter_name][0])
        stacked_path = output_dir / f"stacked_{filter_name}.fits"
        fits_saver(stacked_image, science_header, stacked_path)
        written_files.append(stacked_path)
        print(f"Wrote {stacked_path}")

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
        f"Pipeline complete. Wrote {len(written_files)} file(s) "
        f"under {written_files[0].parent}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
