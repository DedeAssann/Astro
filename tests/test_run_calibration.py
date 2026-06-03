from pathlib import Path
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
            _touch(object_dir / "calibration" / "bias" / "bias_001.fits"),
        ],
        "flat": {},
        "science": {},
    }
    for filter_name in filters:
        files["flat"][filter_name] = [
            _touch(object_dir / "calibration" / "flats" / filter_name / f"flat_b_{filter_name}.fts"),
            _touch(object_dir / "calibration" / "flats" / filter_name / f"flat_a_{filter_name}.fits"),
        ]
        files["science"][filter_name] = [
            _touch(object_dir / "raw" / filter_name / f"science_b_{filter_name}.FIT"),
            _touch(object_dir / "raw" / filter_name / f"science_a_{filter_name}.fits"),
        ]
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

    def fake_calibrate_and_stack(science_files, bias, flat, align, sigma, maxiters):
        calls.setdefault("stack_args", {})[Path(science_files[0]).parent.name] = (
            science_files,
            bias,
            flat,
            align,
            sigma,
            maxiters,
        )
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
            3,
            5,
        )
    assert written == [
        object_dir / "calibrated" / "master_bias.fits",
        object_dir / "calibrated" / "master_flat_green.fits",
        object_dir / "stacked" / "stacked_green.fits",
        object_dir / "calibrated" / "master_flat_red.fits",
        object_dir / "stacked" / "stacked_red.fits",
    ]
    assert [item[2] for item in saved] == written
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
    ]
    assert [item[2] for item in saved] == written
    assert calls["bias_paths"] == [files["bias"]]
    assert calls["flat_args"][tmp_path.name] == ([files["flat"]], master_bias)
    assert calls["stack_args"][tmp_path.name] == ([files["science"]], master_bias, _master_flat, False, 3, 5)


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
    ]
    assert [item[2] for item in saved] == written
    assert all(path.exists() for path in output_dirs.values())


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
