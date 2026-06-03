from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astro_image_lab import stacking


def test_normalize_by_median_divides_by_image_median():
    image = np.array([[2, 4], [6, 8]], dtype=float)

    normalized = stacking.normalize_by_median(image)

    np.testing.assert_allclose(normalized, image / np.median(image))
    assert np.isclose(np.median(normalized), 1.0)


def test_normalize_by_median_rejects_zero_or_invalid_median():
    with pytest.raises(ValueError, match="invalid median"):
        stacking.normalize_by_median(np.array([[-1, 1], [-1, 1]], dtype=float))

    with pytest.raises(ValueError, match="invalid median"):
        stacking.normalize_by_median(np.array([[np.nan, 1], [2, 3]], dtype=float))


def test_stack_images_sigma_clips_and_nanmeans_axis_zero():
    image_stack = np.array(
        [
            [[1, 1], [1, 1]],
            [[1, 1], [1, 1]],
            [[100, 1], [1, 1]],
        ],
        dtype=float,
    )

    stacked = stacking.stack_images(image_stack, sigma=2, maxiters=10)

    np.testing.assert_allclose(stacked, np.ones((2, 2), dtype=np.float32))
    assert stacked.dtype == np.float32


def test_calibrate_and_stack_align_false_loads_calibrates_normalizes_all_images(monkeypatch):
    frames = {
        "science_1.fits": np.array([[12, 22], [32, 42]], dtype=float),
        "science_2.fits": np.array([[14, 24], [34, 44]], dtype=float),
    }
    master_bias = np.full((2, 2), 2.0)
    master_flat = np.array([[1, 2], [5, 8]], dtype=float)
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {"PATH": path}))

    stacked = stacking.calibrate_and_stack(list(frames), master_bias, master_flat, align=False)

    expected_images = []
    for frame in frames.values():
        calibrated = (frame - master_bias) / master_flat
        expected_images.append(calibrated / np.median(calibrated))
    expected = np.nanmean(np.asarray(expected_images, dtype=float), axis=0).astype(np.float32)

    np.testing.assert_allclose(stacked, expected)
    assert stacked.dtype == np.float32


def test_calibrate_and_stack_align_false_includes_first_image(monkeypatch):
    frames = {
        "first.fits": np.array([[10, 20], [30, 40]], dtype=float),
        "second.fits": np.array([[20, 40], [60, 80]], dtype=float),
        "third.fits": np.array([[30, 60], [90, 120]], dtype=float),
    }
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    stacked = stacking.calibrate_and_stack(frames.keys(), np.zeros((2, 2)), np.ones((2, 2)), align=False)

    expected_first_normalized = frames["first.fits"] / np.median(frames["first.fits"])
    # All three images have the same normalized values. If the first image were
    # skipped and left as zeros, the old processing.py bug would lower the mean.
    np.testing.assert_allclose(stacked, expected_first_normalized.astype(np.float32))


def test_calibrate_and_stack_align_false_does_not_import_astroalign(monkeypatch):
    frames = {"science.fits": np.array([[1, 2], [3, 4]], dtype=float)}
    monkeypatch.setitem(sys.modules, "astroalign", None)
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    stacked = stacking.calibrate_and_stack(frames.keys(), np.zeros((2, 2)), np.ones((2, 2)), align=False)

    expected = frames["science.fits"] / np.median(frames["science.fits"])
    np.testing.assert_allclose(stacked, expected.astype(np.float32))
