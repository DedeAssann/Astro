from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astro_image_lab import calibration


def test_make_master_bias_preserves_shape_and_uses_median(monkeypatch):
    frames = {
        "bias_1.fits": np.array([[1, 2], [3, 4]], dtype=float),
        "bias_2.fits": np.array([[3, 4], [5, 6]], dtype=float),
        "bias_3.fits": np.array([[5, 6], [7, 8]], dtype=float),
    }
    monkeypatch.setattr(calibration, "load_fits", lambda path: (frames[path], {}))

    master_bias = calibration.make_master_bias(list(frames))

    assert master_bias.shape == (2, 2)
    np.testing.assert_array_equal(master_bias, np.array([[3, 4], [5, 6]], dtype=float))


def test_make_master_flat_subtracts_bias_and_normalizes_around_one(monkeypatch):
    frames = {
        "flat_1.fits": np.array([[12, 22], [32, 42]], dtype=float),
        "flat_2.fits": np.array([[22, 32], [42, 52]], dtype=float),
    }
    master_bias = np.array([[2, 2], [2, 2]], dtype=float)
    monkeypatch.setattr(calibration, "load_fits", lambda path: (frames[path], {}))

    master_flat = calibration.make_master_flat(list(frames), master_bias)

    assert master_flat.shape == (2, 2)
    assert np.isclose(np.nanmedian(master_flat), 1.0)


def test_calibrate_science_image_applies_formula_and_masks_invalid_flat_values():
    science_data = np.array([[12, 22], [32, 42]], dtype=float)
    master_bias = np.array([[2, 2], [2, 2]], dtype=float)
    master_flat = np.array([[1, 2], [0, np.nan]], dtype=float)

    calibrated = calibration.calibrate_science_image(science_data, master_bias, master_flat)

    expected = np.array([[10, 10], [np.nan, np.nan]], dtype=float)
    np.testing.assert_allclose(calibrated, expected, equal_nan=True)
    assert np.isnan(calibrated[1, 0])
    assert np.isnan(calibrated[1, 1])
