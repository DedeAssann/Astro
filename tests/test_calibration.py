from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astro_image_lab import calibration


def test_make_master_bias_matches_nanmedian_stack(monkeypatch):
    frames = {
        "bias_1.fits": np.array([[1, np.nan], [3, 4]], dtype=float),
        "bias_2.fits": np.array([[3, 4], [5, 6]], dtype=float),
        "bias_3.fits": np.array([[5, 6], [7, 8]], dtype=float),
    }
    monkeypatch.setattr(calibration, "load_fits", lambda path: (frames[path], {}))

    master_bias = calibration.make_master_bias(list(frames))

    expected = np.nanmedian(np.asarray(list(frames.values()), dtype=float), axis=0)
    assert master_bias.shape == (2, 2)
    np.testing.assert_array_equal(master_bias, expected)


def test_make_master_flat_matches_processing_py_logic(monkeypatch):
    frames = {
        "flat_1.fits": np.array([[12, 22], [32, 42]], dtype=float),
        "flat_2.fits": np.array([[22, 32], [42, 52]], dtype=float),
    }
    master_bias = np.array([[2, 2], [2, 2]], dtype=float)
    monkeypatch.setattr(calibration, "load_fits", lambda path: (frames[path], {}))

    master_flat = calibration.make_master_flat(list(frames), master_bias)

    expected = np.zeros((2, 2), dtype=float)
    for flat in frames.values():
        tmp = flat - master_bias
        expected += tmp / np.median(tmp) / len(frames)
    expected /= np.median(expected)

    assert master_flat.shape == (2, 2)
    assert np.isclose(np.median(master_flat), 1.0)
    np.testing.assert_allclose(master_flat, expected)


def test_calibrate_science_image_applies_formula_on_valid_pixels():
    science_data = np.array([[12, 22], [32, 42]], dtype=float)
    master_bias = np.array([[2, 2], [2, 2]], dtype=float)
    master_flat = np.array([[1, 2], [5, 8]], dtype=float)

    calibrated = calibration.calibrate_science_image(science_data, master_bias, master_flat)

    expected = (science_data - master_bias) / master_flat
    np.testing.assert_allclose(calibrated, expected)


def test_calibrate_science_image_sets_nan_only_for_invalid_flat_pixels():
    science_data = np.array([[12, 22], [32, 42]], dtype=float)
    master_bias = np.array([[2, 2], [2, 2]], dtype=float)
    master_flat = np.array([[1, 0], [np.inf, np.nan]], dtype=float)

    calibrated = calibration.calibrate_science_image(science_data, master_bias, master_flat)

    assert calibrated[0, 0] == 10
    assert np.isnan(calibrated[0, 1])
    assert np.isnan(calibrated[1, 0])
    assert np.isnan(calibrated[1, 1])
