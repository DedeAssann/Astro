from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astro_image_lab import channel_alignment


def test_choose_reference_filter_prefers_green_then_first_available():
    assert channel_alignment.choose_reference_filter(["red", "green", "blue"], None) == "green"
    assert channel_alignment.choose_reference_filter(["red", "blue"], None) == "blue"
    assert channel_alignment.choose_reference_filter(["red", "blue"], "red") == "red"


def test_align_stacked_channels_writes_reference_and_aligned_outputs(monkeypatch, tmp_path):
    stacked_paths = {
        "blue": tmp_path / "stacked_blue.fits",
        "green": tmp_path / "stacked_green.fits",
        "red": tmp_path / "stacked_red.fits",
    }
    frames = {
        path: np.full((2, 2), value, dtype=float)
        for value, path in enumerate(stacked_paths.values(), start=1)
    }
    saved = []
    register_calls = []

    class FakeAstroalign:
        @staticmethod
        def register(image, reference, **kwargs):
            register_calls.append(kwargs)
            return image + reference, np.zeros_like(image, dtype=bool)

    monkeypatch.setitem(sys.modules, "astroalign", FakeAstroalign)
    monkeypatch.setattr(channel_alignment, "load_fits", lambda path: (frames[Path(path)], {"SRC": str(path)}))
    monkeypatch.setattr(
        channel_alignment,
        "save_fits",
        lambda data, header, path, overwrite=True: saved.append((data, header, Path(path), overwrite)),
    )

    records = channel_alignment.align_stacked_channels(
        stacked_paths,
        tmp_path / "aligned_channels",
        reference_filter="green",
        min_area=21,
    )

    assert [record["status"] for record in records] == ["aligned", "reference", "aligned"]
    assert [item[2] for item in saved] == [
        tmp_path / "aligned_channels" / "stacked_blue_aligned.fits",
        tmp_path / "aligned_channels" / "stacked_green_aligned.fits",
        tmp_path / "aligned_channels" / "stacked_red_aligned.fits",
    ]
    assert register_calls == [{"min_area": 21}, {"min_area": 21}]
    assert all(record["reference_filter"] == "green" for record in records)


def test_align_stacked_channels_failure_skip_records_failed_and_continues(monkeypatch, tmp_path):
    stacked_paths = {
        "blue": tmp_path / "stacked_blue.fits",
        "green": tmp_path / "stacked_green.fits",
        "red": tmp_path / "stacked_red.fits",
    }
    frames = {path: np.ones((2, 2), dtype=float) for path in stacked_paths.values()}
    saved = []
    calls = []

    class FakeAstroalign:
        @staticmethod
        def register(image, reference, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("channel mismatch")
            return image, np.zeros_like(image, dtype=bool)

    monkeypatch.setitem(sys.modules, "astroalign", FakeAstroalign)
    monkeypatch.setattr(channel_alignment, "load_fits", lambda path: (frames[Path(path)], {}))
    monkeypatch.setattr(
        channel_alignment,
        "save_fits",
        lambda data, header, path, overwrite=True: saved.append(Path(path)),
    )

    records = channel_alignment.align_stacked_channels(
        stacked_paths,
        tmp_path / "aligned_channels",
        reference_filter="green",
        fail_policy="skip",
    )

    assert [record["status"] for record in records] == ["failed", "reference", "aligned"]
    assert "channel mismatch" in records[0]["error"]
    assert saved == [
        tmp_path / "aligned_channels" / "stacked_green_aligned.fits",
        tmp_path / "aligned_channels" / "stacked_red_aligned.fits",
    ]


def test_align_stacked_channels_failure_raise_raises(monkeypatch, tmp_path):
    stacked_paths = {
        "blue": tmp_path / "stacked_blue.fits",
        "green": tmp_path / "stacked_green.fits",
    }
    frames = {path: np.ones((2, 2), dtype=float) for path in stacked_paths.values()}

    class FakeAstroalign:
        @staticmethod
        def register(image, reference, **kwargs):
            raise RuntimeError("channel mismatch")

    monkeypatch.setitem(sys.modules, "astroalign", FakeAstroalign)
    monkeypatch.setattr(channel_alignment, "load_fits", lambda path: (frames[Path(path)], {}))
    monkeypatch.setattr(channel_alignment, "save_fits", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="channel mismatch"):
        channel_alignment.align_stacked_channels(
            stacked_paths,
            tmp_path / "aligned_channels",
            reference_filter="green",
            fail_policy="raise",
        )
