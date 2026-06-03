from pathlib import Path
import csv
import importlib.util
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_calibration.py"
spec = importlib.util.spec_from_file_location("run_calibration", SCRIPT_PATH)
run_calibration = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run_calibration
spec.loader.exec_module(run_calibration)


def _write_legacy_config(path, output_dir, files):
    path.write_text(
        f"""
bias_files:
  - {files['bias']}

flat_files:
  red:
    - {files['flat']}

science_files:
  red:
    - {files['science']}

output_dir: {output_dir}
align: false
sigma: 3
maxiters: 5
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_object_config(path, output_dirs, files):
    path.write_text(
        f"""
object_name: M83

bias_files:
  - {files['bias']}

flat_files:
  red:
    - {files['flat']}

science_files:
  red:
    - {files['science']}

output_dirs:
  calibrated: {output_dirs['calibrated']}
  stacked: {output_dirs['stacked']}
  figures: {output_dirs['figures']}
  analysis: {output_dirs['analysis']}
align: false
sigma: 3
maxiters: 5
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _write_compact_config(path, data_root, filters=("red", "green"), object_name="M83"):
    filter_lines = "\n".join(f"  - {filter_name}" for filter_name in filters)
    path.write_text(
        f"""
object_name: {object_name}
data_root: {data_root}
filters:
{filter_lines}
align: false
sigma: 3
maxiters: 5
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("placeholder", encoding="utf-8")
    return path


def _create_compact_tree(tmp_path, filters=("red", "green")):
    data_root = tmp_path / "data"
    object_dir = data_root / "M83"
    files = {
        "bias": [
            _touch(object_dir / "calibration" / "bias" / "bias_002.FIT"),
            _touch(object_dir / "calibration" / "bias" / "bias_001.fit"),
        ],
        "flat": {},
        "science": {},
    }
    _touch(object_dir / "calibration" / "bias" / "bias_notes.txt")
    for filter_name in filters:
        files["flat"][filter_name] = [
            _touch(object_dir / "calibration" / "flats" / filter_name / f"flat_{filter_name}_002.fits"),
            _touch(object_dir / "calibration" / "flats" / filter_name / f"flat_{filter_name}_001.fts"),
        ]
        files["science"][filter_name] = [
            _touch(object_dir / "raw" / filter_name / f"science_{filter_name}_002.fit"),
            _touch(object_dir / "raw" / filter_name / f"science_{filter_name}_001.FITS"),
        ]
        _touch(object_dir / "calibration" / "flats" / filter_name / f"flat_{filter_name}_notes.txt")
        _touch(object_dir / "raw" / filter_name / f"science_{filter_name}_notes.txt")
    return data_root, object_dir, files


def _input_files(tmp_path):
    return {
        "bias": _touch(tmp_path / "bias.fits"),
        "flat": _touch(tmp_path / "flat.fits"),
        "science": _touch(tmp_path / "science.fits"),
    }


def _mock_pipeline_helpers(monkeypatch):
    calls = {}
    master_bias = [[1.0, 1.0], [1.0, 1.0]]
    master_flat = [[2.0, 2.0], [2.0, 2.0]]
    stacked = [[3.0, 3.0], [3.0, 3.0]]

    def fake_make_master_bias(paths):
        calls["bias_paths"] = paths
        return master_bias

    def fake_make_master_flat(paths, bias):
        calls.setdefault("flat_args", {})[Path(paths[0]).parent.name] = (paths, bias)
        return master_flat

    def fake_calibrate_and_stack(
        science_files,
        bias,
        flat,
        align,
        min_area,
        sigma,
        maxiters,
        return_alignment_report=False,
        filter_name=None,
        fail_policy="raise",
        alignment_method="astroalign",
        detection_sigma=None,
    ):
        calls.setdefault("stack_args", {})[Path(science_files[0]).parent.name] = (
            science_files,
            bias,
            flat,
            align,
            min_area,
            sigma,
            maxiters,
            return_alignment_report,
            filter_name,
            fail_policy,
            alignment_method,
            detection_sigma,
        )
        records = [
            {
                "filter": filter_name or "",
                "file_path": str(science_files[0]),
                "index": 0,
                "status": "skipped" if not align else "reference",
                "error": "",
                "method": alignment_method if align else "",
                "min_area": min_area,
            }
        ]
        if return_alignment_report:
            return stacked, records
        return stacked

    saved = []

    def fake_save_fits(data, header, path, overwrite=True):
        saved.append((data, header, path, overwrite))
        path.write_text("written", encoding="utf-8")

    monkeypatch.setattr(run_calibration, "make_master_bias", fake_make_master_bias)
    monkeypatch.setattr(run_calibration, "make_master_flat", fake_make_master_flat)
    monkeypatch.setattr(run_calibration, "calibrate_and_stack", fake_calibrate_and_stack)
    monkeypatch.setattr(
        run_calibration,
        "load_fits",
        lambda path: ([[0.0, 0.0], [0.0, 0.0]], {"SRC": str(path)}),
    )
    monkeypatch.setattr(run_calibration, "save_fits", fake_save_fits)
    return calls, saved, master_bias, master_flat


def test_run_pipeline_discovers_compact_object_layout(tmp_path, monkeypatch):
    data_root, object_dir, files = _create_compact_tree(tmp_path)
    config_path = tmp_path / "config.yaml"
    _write_compact_config(config_path, data_root)
    calls, saved, master_bias, master_flat = _mock_pipeline_helpers(monkeypatch)

    written = run_calibration.run_pipeline(config_path)

    assert calls["bias_paths"] == sorted(files["bias"])
    for filter_name in ("red", "green"):
        assert calls["flat_args"][filter_name] == (sorted(files["flat"][filter_name]), master_bias)
        assert calls["stack_args"][filter_name] == (
            sorted(files["science"][filter_name]),
            master_bias,
            master_flat,
            False,
            12,
            3,
            5,
            True,
            filter_name,
            "raise",
            "astroalign",
            None,
        )
    assert written == [
        object_dir / "calibrated" / "master_bias.fits",
        object_dir / "calibrated" / "master_flat_green.fits",
        object_dir / "stacked" / "stacked_green.fits",
        object_dir / "calibrated" / "master_flat_red.fits",
        object_dir / "stacked" / "stacked_red.fits",
        object_dir / "analysis" / "alignment_report.csv",
    ]
    assert [item[2] for item in saved] == written[:-1]
    assert all((object_dir / dirname).exists() for dirname in ("calibrated", "stacked", "figures", "analysis"))


def test_validate_config_reports_missing_bias_directory(tmp_path):
    config_path = tmp_path / "config.yaml"
    _write_compact_config(config_path, tmp_path / "data", filters=("red",))

    with pytest.raises(run_calibration.ConfigError, match="Required bias directory does not exist"):
        run_calibration._validate_config(run_calibration._load_yaml_config(config_path))


def test_validate_config_reports_missing_flat_directory_for_filter(tmp_path):
    data_root, object_dir, _files = _create_compact_tree(tmp_path, filters=("red",))
    config_path = tmp_path / "config.yaml"
    _write_compact_config(config_path, data_root, filters=("red", "blue"))
    (object_dir / "raw" / "blue").mkdir(parents=True)
    _touch(object_dir / "raw" / "blue" / "science_blue.fits")

    with pytest.raises(
        run_calibration.ConfigError,
        match="Required flat for filter 'blue' directory does not exist",
    ):
        run_calibration._validate_config(run_calibration._load_yaml_config(config_path))


def test_validate_config_reports_missing_science_directory_for_filter(tmp_path):
    data_root, object_dir, _files = _create_compact_tree(tmp_path, filters=("red",))
    config_path = tmp_path / "config.yaml"
    _write_compact_config(config_path, data_root, filters=("red", "blue"))
    _touch(object_dir / "calibration" / "flats" / "blue" / "flat_blue.fits")

    with pytest.raises(
        run_calibration.ConfigError,
        match="Required science for filter 'blue' directory does not exist",
    ):
        run_calibration._validate_config(run_calibration._load_yaml_config(config_path))


def test_run_pipeline_writes_expected_outputs_with_legacy_output_dir(tmp_path, monkeypatch):
    files = _input_files(tmp_path)
    output_dir = tmp_path / "results"
    config_path = tmp_path / "config.yaml"
    _write_legacy_config(config_path, output_dir, files)
    calls, saved, master_bias, _master_flat = _mock_pipeline_helpers(monkeypatch)

    written = run_calibration.run_pipeline(config_path)

    assert written == [
        output_dir / "master_bias.fits",
        output_dir / "master_flat_red.fits",
        output_dir / "stacked_red.fits",
        output_dir / "alignment_report.csv",
    ]
    assert [item[2] for item in saved] == written[:-1]
    assert calls["bias_paths"] == [files["bias"]]
    assert calls["flat_args"][tmp_path.name] == ([files["flat"]], master_bias)
    assert calls["stack_args"][tmp_path.name] == (
        [files["science"]],
        master_bias,
        _master_flat,
        False,
        12,
        3,
        5,
        True,
        "red",
        "raise",
        "astroalign",
        None,
    )


def test_run_pipeline_routes_explicit_file_lists_to_explicit_output_dirs(tmp_path, monkeypatch):
    files = _input_files(tmp_path)
    output_dirs = {
        "calibrated": tmp_path / "data" / "M83" / "calibrated",
        "stacked": tmp_path / "data" / "M83" / "stacked",
        "figures": tmp_path / "data" / "M83" / "figures",
        "analysis": tmp_path / "data" / "M83" / "analysis",
    }
    config_path = tmp_path / "config.yaml"
    _write_object_config(config_path, output_dirs, files)
    _calls, saved, _master_bias, _master_flat = _mock_pipeline_helpers(monkeypatch)

    written = run_calibration.run_pipeline(config_path)

    assert written == [
        output_dirs["calibrated"] / "master_bias.fits",
        output_dirs["calibrated"] / "master_flat_red.fits",
        output_dirs["stacked"] / "stacked_red.fits",
        output_dirs["analysis"] / "alignment_report.csv",
    ]
    assert [item[2] for item in saved] == written[:-1]
    assert all(path.exists() for path in output_dirs.values())


def test_validate_config_alignment_enabled_overrides_legacy_align(tmp_path):
    files = _input_files(tmp_path)
    config = {
        "bias_files": [str(files["bias"])],
        "flat_files": {"red": [str(files["flat"])]},
        "science_files": {"red": [str(files["science"])]},
        "output_dir": str(tmp_path / "out"),
        "align": False,
        "alignment": {"enabled": True, "min_area": 21, "fail_policy": "skip"},
    }

    validated = run_calibration._validate_config(config)

    assert validated["align"] is True
    assert validated["alignment"]["enabled"] is True
    assert validated["alignment"]["min_area"] == 21
    assert validated["alignment"]["fail_policy"] == "skip"


def test_run_pipeline_writes_alignment_report_csv(tmp_path, monkeypatch):
    files = _input_files(tmp_path)
    output_dir = tmp_path / "results"
    config_path = tmp_path / "config.yaml"
    _write_legacy_config(config_path, output_dir, files)
    _mock_pipeline_helpers(monkeypatch)

    written = run_calibration.run_pipeline(config_path)

    report_path = output_dir / "alignment_report.csv"
    assert report_path in written
    with report_path.open("r", encoding="utf-8", newline="") as report_file:
        rows = list(csv.DictReader(report_file))
    assert rows == [
        {
            "filter": "red",
            "file_path": str(files["science"]),
            "index": "0",
            "status": "skipped",
            "error": "",
            "method": "",
            "min_area": "12",
        }
    ]


def test_validate_config_channel_alignment_defaults_disabled(tmp_path):
    files = _input_files(tmp_path)
    validated = run_calibration._validate_config(
        {
            "bias_files": [str(files["bias"])],
            "flat_files": {"red": [str(files["flat"])]},
            "science_files": {"red": [str(files["science"])]},
            "output_dir": str(tmp_path / "out"),
        }
    )

    assert validated["channel_alignment"] == {
        "enabled": False,
        "reference_filter": None,
        "method": "astroalign",
        "min_area": 12,
        "fail_policy": "raise",
    }


def test_run_pipeline_writes_aligned_channel_outputs_when_enabled(tmp_path, monkeypatch):
    data_root, object_dir, _files = _create_compact_tree(tmp_path, filters=("red", "green"))
    config_path = tmp_path / "config.yaml"
    _write_compact_config(config_path, data_root, filters=("red", "green"))
    with config_path.open("a", encoding="utf-8") as config_file:
        config_file.write(
            "channel_alignment:\n"
            "  enabled: true\n"
            "  reference_filter: green\n"
            "  method: astroalign\n"
            "  min_area: 17\n"
            "  fail_policy: skip\n"
        )
    _mock_pipeline_helpers(monkeypatch)
    calls = {}

    def fake_align_stacked_channels(stacked_paths, output_dir, reference_filter, method, min_area, fail_policy):
        calls["channel_alignment"] = (
            stacked_paths,
            output_dir,
            reference_filter,
            method,
            min_area,
            fail_policy,
        )
        return [
            {
                "filter": "green",
                "input_path": str(stacked_paths["green"]),
                "output_path": str(output_dir / "stacked_green_aligned.fits"),
                "status": "reference",
                "reference_filter": "green",
                "method": method,
                "min_area": min_area,
                "error": "",
            },
            {
                "filter": "red",
                "input_path": str(stacked_paths["red"]),
                "output_path": str(output_dir / "stacked_red_aligned.fits"),
                "status": "aligned",
                "reference_filter": "green",
                "method": method,
                "min_area": min_area,
                "error": "",
            },
        ]

    monkeypatch.setattr(run_calibration, "align_stacked_channels", fake_align_stacked_channels)

    written = run_calibration.run_pipeline(config_path)

    aligned_dir = object_dir / "stacked" / "aligned_channels"
    assert calls["channel_alignment"] == (
        {
            "green": object_dir / "stacked" / "stacked_green.fits",
            "red": object_dir / "stacked" / "stacked_red.fits",
        },
        aligned_dir,
        "green",
        "astroalign",
        17,
        "skip",
    )
    assert aligned_dir / "stacked_green_aligned.fits" in written
    assert aligned_dir / "stacked_red_aligned.fits" in written
    report_path = object_dir / "analysis" / "channel_alignment_report.csv"
    assert report_path in written
    with report_path.open("r", encoding="utf-8", newline="") as report_file:
        rows = list(csv.DictReader(report_file))
    assert [row["status"] for row in rows] == ["reference", "aligned"]
    assert all(row["reference_filter"] == "green" for row in rows)


def test_main_reports_missing_bias_directory_from_temp_config(tmp_path, capsys, monkeypatch):
    data_root = tmp_path / "data"
    object_name = "MissingBiasObject"
    object_dir = data_root / object_name
    filter_name = "blue"
    _touch(object_dir / "calibration" / "flats" / filter_name / "flat_blue.fits")
    _touch(object_dir / "raw" / filter_name / "science_blue.fits")
    config_path = tmp_path / "missing_bias_config.yaml"
    _write_compact_config(config_path, data_root, filters=(filter_name,), object_name=object_name)

    def fail_if_pipeline_imports_are_reached():
        raise AssertionError("main() should stop during config validation for missing bias data")

    monkeypatch.setattr(
        run_calibration, "_get_pipeline_functions", fail_if_pipeline_imports_are_reached
    )

    exit_code = run_calibration.main(["--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    normalized_err = captured.err.replace("\\", "/")
    expected_bias_dir = object_dir / "calibration" / "bias"
    assert "Required bias directory does not exist" in normalized_err
    assert str(expected_bias_dir).replace("\\", "/") in normalized_err


def test_validate_config_reports_missing_required_input_mode():
    with pytest.raises(run_calibration.ConfigError, match="all explicit input fields"):
        run_calibration._validate_config({"bias_files": ["bias.fits"]})
