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


def _input_files(tmp_path):
    files = {
        "bias": tmp_path / "bias.fits",
        "flat": tmp_path / "flat.fits",
        "science": tmp_path / "science.fits",
    }
    for path in files.values():
        path.write_text("placeholder", encoding="utf-8")
    return files


def _mock_pipeline_helpers(monkeypatch):
    calls = {}
    master_bias = [[1.0, 1.0], [1.0, 1.0]]
    master_flat = [[2.0, 2.0], [2.0, 2.0]]
    stacked = [[3.0, 3.0], [3.0, 3.0]]

    def fake_make_master_bias(paths):
        calls["bias_paths"] = paths
        return master_bias

    def fake_make_master_flat(paths, bias):
        calls["flat_args"] = (paths, bias)
        return master_flat

    def fake_calibrate_and_stack(science_files, bias, flat, align, sigma, maxiters):
        calls["stack_args"] = (science_files, bias, flat, align, sigma, maxiters)
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
    assert calls["flat_args"] == ([files["flat"]], master_bias)
    assert calls["stack_args"] == ([files["science"]], master_bias, _master_flat, False, 3, 5)


def test_run_pipeline_routes_products_to_object_output_dirs(tmp_path, monkeypatch):
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


def test_main_reports_missing_example_files(capsys):
    exit_code = run_calibration.main(["--config", "configs/m83_example.yaml"])

    captured = capsys.readouterr()
    assert exit_code == 1
    normalized_err = captured.err.replace("\\", "/")
    assert "Missing input FITS file(s)" in normalized_err
    assert "data/M83/calibration/bias/example_bias_001.fits" in normalized_err


def test_validate_config_reports_missing_required_field():
    with pytest.raises(run_calibration.ConfigError, match="missing required field"):
        run_calibration._validate_config({"bias_files": ["bias.fits"]})
