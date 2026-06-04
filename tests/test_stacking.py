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


def test_calibrate_and_stack_align_false_preserves_calibrated_scale_by_default(monkeypatch):
    frames = {
        "science_1.fits": np.array([[12, 22], [32, 42]], dtype=float),
        "science_2.fits": np.array([[14, 24], [34, 44]], dtype=float),
    }
    master_bias = np.full((2, 2), 2.0)
    master_flat = np.array([[1, 2], [5, 8]], dtype=float)
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {"PATH": path}))

    stacked = stacking.calibrate_and_stack(list(frames), master_bias, master_flat, align=False)

    expected_images = [(frame - master_bias) / master_flat for frame in frames.values()]
    expected = np.nanmean(np.asarray(expected_images, dtype=float), axis=0).astype(np.float32)

    np.testing.assert_allclose(stacked, expected)
    assert stacked.dtype == np.float32


def test_calibrate_and_stack_align_false_can_normalize_before_stack(monkeypatch):
    frames = {
        "science_1.fits": np.array([[10, 20], [30, 40]], dtype=float),
        "science_2.fits": np.array([[20, 40], [60, 80]], dtype=float),
    }
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    stacked = stacking.calibrate_and_stack(
        list(frames),
        np.zeros((2, 2)),
        np.ones((2, 2)),
        align=False,
        normalize_before_stack=True,
    )

    expected = frames["science_1.fits"] / np.median(frames["science_1.fits"])
    np.testing.assert_allclose(stacked, expected.astype(np.float32))
    assert np.isclose(np.median(stacked), 1.0)


def test_calibrate_and_stack_align_false_includes_first_image(monkeypatch):
    frames = {
        "first.fits": np.array([[10, 20], [30, 40]], dtype=float),
        "second.fits": np.array([[20, 40], [60, 80]], dtype=float),
        "third.fits": np.array([[30, 60], [90, 120]], dtype=float),
    }
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    stacked = stacking.calibrate_and_stack(frames.keys(), np.zeros((2, 2)), np.ones((2, 2)), align=False)

    expected = np.nanmean(np.asarray(list(frames.values()), dtype=float), axis=0).astype(np.float32)
    # If the first image were skipped and left as zeros, the mean would be lower.
    np.testing.assert_allclose(stacked, expected)


def test_calibrate_and_stack_align_false_does_not_import_astroalign(monkeypatch):
    frames = {"science.fits": np.array([[1, 2], [3, 4]], dtype=float)}
    monkeypatch.setitem(sys.modules, "astroalign", None)
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    stacked = stacking.calibrate_and_stack(frames.keys(), np.zeros((2, 2)), np.ones((2, 2)), align=False)

    np.testing.assert_allclose(stacked, frames["science.fits"].astype(np.float32))


def test_calibrate_and_stack_default_returns_only_stacked_image(monkeypatch):
    frames = {"science.fits": np.array([[1, 2], [3, 4]], dtype=float)}
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    stacked = stacking.calibrate_and_stack(frames.keys(), np.zeros((2, 2)), np.ones((2, 2)), align=False)

    assert isinstance(stacked, np.ndarray)
    assert stacked.shape == (2, 2)


def test_calibrate_and_stack_returns_alignment_report_records(monkeypatch):
    frames = {
        "first.fits": np.array([[1, 2], [3, 4]], dtype=float),
        "second.fits": np.array([[2, 4], [6, 8]], dtype=float),
    }
    calls = []

    class FakeAstroalign:
        @staticmethod
        def register(image, reference, **kwargs):
            calls.append(kwargs)
            return image, np.zeros_like(image, dtype=bool)

    monkeypatch.setitem(sys.modules, "astroalign", FakeAstroalign)
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    stacked, report = stacking.calibrate_and_stack(
        frames.keys(),
        np.zeros((2, 2)),
        np.ones((2, 2)),
        min_area=19,
        return_alignment_report=True,
        filter_name="red",
        normalize_before_stack=True,
    )

    assert isinstance(stacked, np.ndarray)
    assert calls == [{"min_area": 19}]
    assert report[0]["status"] == "reference"
    assert report[0]["filter"] == "red"
    assert report[0]["method"] == "astroalign"
    assert report[0]["min_area"] == 19
    assert report[1]["status"] == "aligned"
    assert report[1]["file_path"] == "second.fits"


def test_calibrate_and_stack_align_false_report_records_skipped(monkeypatch):
    frames = {
        "first.fits": np.array([[1, 2], [3, 4]], dtype=float),
        "second.fits": np.array([[2, 4], [6, 8]], dtype=float),
    }
    monkeypatch.setitem(sys.modules, "astroalign", None)
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    _stacked, report = stacking.calibrate_and_stack(
        frames.keys(),
        np.zeros((2, 2)),
        np.ones((2, 2)),
        align=False,
        return_alignment_report=True,
    )

    assert [record["status"] for record in report] == ["skipped", "skipped"]
    assert [record["method"] for record in report] == ["", ""]


def test_calibrate_and_stack_alignment_failure_skip_records_failed_and_continues(monkeypatch):
    frames = {
        "first.fits": np.array([[1, 2], [3, 4]], dtype=float),
        "bad.fits": np.array([[2, 4], [6, 8]], dtype=float),
        "good.fits": np.array([[3, 6], [9, 12]], dtype=float),
    }
    calls = []

    class FakeAstroalign:
        @staticmethod
        def register(image, reference, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("no stars matched")
            return image, np.zeros_like(image, dtype=bool)

    monkeypatch.setitem(sys.modules, "astroalign", FakeAstroalign)
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    stacked, report = stacking.calibrate_and_stack(
        frames.keys(),
        np.zeros((2, 2)),
        np.ones((2, 2)),
        fail_policy="skip",
        return_alignment_report=True,
        normalize_before_stack=True,
    )

    assert isinstance(stacked, np.ndarray)
    assert [record["status"] for record in report] == ["reference", "failed", "aligned"]
    assert "no stars matched" in report[1]["error"]
    assert calls == [{"min_area": 12}, {"min_area": 12}]


def test_calibrate_and_stack_alignment_failure_raise_records_then_raises(monkeypatch):
    frames = {
        "first.fits": np.array([[1, 2], [3, 4]], dtype=float),
        "bad.fits": np.array([[2, 4], [6, 8]], dtype=float),
    }

    class FakeAstroalign:
        @staticmethod
        def register(image, reference, **kwargs):
            raise RuntimeError("registration exploded")

    monkeypatch.setitem(sys.modules, "astroalign", FakeAstroalign)
    monkeypatch.setattr(stacking, "load_fits", lambda path: (frames[path], {}))

    with pytest.raises(RuntimeError, match="registration exploded"):
        stacking.calibrate_and_stack(
            frames.keys(),
            np.zeros((2, 2)),
            np.ones((2, 2)),
            fail_policy="raise",
            return_alignment_report=True,
            normalize_before_stack=True,
        )
