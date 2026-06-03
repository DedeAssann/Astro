from pathlib import Path
import importlib.util
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_calibration.py"
spec = importlib.util.spec_from_file_location("run_calibration", SCRIPT_PATH)
run_calibration = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run_calibration
spec.loader.exec_module(run_calibration)


def _write_config(path, output_dir, files):
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


def test_run_pipeline_writes_expected_outputs_with_mocked_helpers(tmp_path, monkeypatch):
    bias_path = tmp_path / "bias.fits"
    flat_path = tmp_path / "flat.fits"
    science_path = tmp_path / "science.fits"
    for path in (bias_path, flat_path, science_path):
        path.write_text("placeholder", encoding="utf-8")

    output_dir = tmp_path / "results"
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        output_dir,
        {"bias": bias_path, "flat": flat_path, "science": science_path},
    )

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

    monkeypatch.setattr(run_calibration, "make_master_bias", fake_make_master_bias)
    monkeypatch.setattr(run_calibration, "make_master_flat", fake_make_master_flat)

    def fake_calibrate_and_stack(science_files, bias, flat, align, sigma, maxiters):
        calls["stack_args"] = (science_files, bias, flat, align, sigma, maxiters)
        return stacked

    saved = []

    def fake_save_fits(data, header, path, overwrite=True):
        saved.append((data, header, path, overwrite))
        path.write_text("written", encoding="utf-8")

    monkeypatch.setattr(run_calibration, "calibrate_and_stack", fake_calibrate_and_stack)
    monkeypatch.setattr(
        run_calibration,
        "load_fits",
        lambda path: ([[0.0, 0.0], [0.0, 0.0]], {"SRC": str(path)}),
    )
    monkeypatch.setattr(run_calibration, "save_fits", fake_save_fits)

    written = run_calibration.run_pipeline(config_path)

    assert written == [
        output_dir / "master_bias.fits",
        output_dir / "master_flat_red.fits",
        output_dir / "stacked_red.fits",
    ]
    assert [item[2] for item in saved] == written
    assert calls["bias_paths"] == [bias_path]
    assert calls["flat_args"] == ([flat_path], master_bias)
    assert calls["stack_args"] == ([science_path], master_bias, master_flat, False, 3, 5)


def test_main_reports_missing_example_files(capsys):
    exit_code = run_calibration.main(["--config", "configs/m83_example.yaml"])

    captured = capsys.readouterr()
    assert exit_code == 1
    normalized_err = captured.err.replace("\\", "/")
    assert "Missing input FITS file(s)" in normalized_err
    assert "data/calibration/bias/example_bias_001.fits" in normalized_err


def test_validate_config_reports_missing_required_field():
    with pytest.raises(run_calibration.ConfigError, match="missing required field"):
        run_calibration._validate_config({"bias_files": ["bias.fits"]})
