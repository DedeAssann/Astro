from pathlib import Path
import importlib.util
import sys

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "make_demo_figures.py"
spec = importlib.util.spec_from_file_location("make_demo_figures", SCRIPT_PATH)
make_demo_figures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = make_demo_figures
spec.loader.exec_module(make_demo_figures)


def _touch_stacked(data_root, object_name="M83", filters=("red",), extensions=None):
    stacked_dir = data_root / object_name / "stacked"
    stacked_dir.mkdir(parents=True, exist_ok=True)
    extensions = extensions or {}
    for filter_name in filters:
        extension = extensions.get(filter_name, ".fits")
        (stacked_dir / f"stacked_{filter_name}{extension}").write_text(
            "synthetic placeholder; tests mock FITS loading\n",
            encoding="utf-8",
        )
    return stacked_dir


def _mock_load_fits(monkeypatch):
    loaded = []

    def fake_load_fits(path):
        loaded.append(Path(path))
        value_by_filter = {"blue": 1.0, "green": 2.0, "red": 3.0}
        filter_name = Path(path).stem.removeprefix("stacked_").removesuffix("_aligned")
        return np.full((4, 4), value_by_filter.get(filter_name, 4.0)), {"FILTER": filter_name}

    monkeypatch.setattr(make_demo_figures, "load_fits", fake_load_fits)
    return loaded


def test_object_argument_discovers_stacked_fits_and_writes_channel_outputs(
    tmp_path,
    monkeypatch,
    capsys,
):
    data_root = tmp_path / "data"
    _touch_stacked(
        data_root,
        filters=("red", "green"),
        extensions={"red": ".fit", "green": ".fts"},
    )
    loaded = _mock_load_fits(monkeypatch)

    written = make_demo_figures.make_demo_figures("M83", data_root=data_root)

    expected = [
        data_root / "M83" / "figures" / "stacked_green.png",
        data_root / "M83" / "figures" / "histogram_green.png",
        data_root / "M83" / "figures" / "stacked_red.png",
        data_root / "M83" / "figures" / "histogram_red.png",
    ]
    assert written == expected
    assert loaded == [
        data_root / "M83" / "stacked" / "stacked_green.fts",
        data_root / "M83" / "stacked" / "stacked_red.fit",
    ]
    assert all(path.is_file() for path in expected)
    assert capsys.readouterr().out.splitlines() == [str(path) for path in expected]


def test_discovers_and_processes_stacked_images_with_mixed_fits_extensions(
    tmp_path,
    monkeypatch,
):
    data_root = tmp_path / "data"
    stacked_dir = _touch_stacked(
        data_root,
        filters=("red", "green", "blue"),
        extensions={"red": ".fit", "green": ".fts", "blue": ".FITS"},
    )
    (stacked_dir / "stacked_notes.txt").write_text("ignore me", encoding="utf-8")
    (stacked_dir / "unstacked_red.fits").write_text("ignore me", encoding="utf-8")
    loaded = _mock_load_fits(monkeypatch)

    written = make_demo_figures.make_demo_figures("M83", data_root=data_root)

    assert loaded == [
        data_root / "M83" / "stacked" / "stacked_blue.FITS",
        data_root / "M83" / "stacked" / "stacked_green.fts",
        data_root / "M83" / "stacked" / "stacked_red.fit",
        data_root / "M83" / "stacked" / "stacked_red.fit",
        data_root / "M83" / "stacked" / "stacked_green.fts",
        data_root / "M83" / "stacked" / "stacked_blue.FITS",
    ]
    assert data_root / "M83" / "figures" / "rgb_composite.png" in written


def test_rgb_composite_prefers_aligned_channel_files(tmp_path, monkeypatch, capsys):
    data_root = tmp_path / "data"
    stacked_dir = _touch_stacked(data_root, filters=("blue", "green", "red"))
    aligned_dir = stacked_dir / "aligned_channels"
    aligned_dir.mkdir()
    for filter_name in ("blue", "green", "red"):
        (aligned_dir / f"stacked_{filter_name}_aligned.fits").write_text(
            "aligned placeholder; tests mock FITS loading\n",
            encoding="utf-8",
        )
    loaded = _mock_load_fits(monkeypatch)

    make_demo_figures.make_demo_figures("M83", data_root=data_root)

    assert loaded[-3:] == [
        aligned_dir / "stacked_red_aligned.fits",
        aligned_dir / "stacked_green_aligned.fits",
        aligned_dir / "stacked_blue_aligned.fits",
    ]
    stdout = capsys.readouterr().out
    assert "RGB composite sources:" in stdout
    assert "stacked_red_aligned.fits" in stdout


def test_missing_stacked_directory_gives_clear_error(tmp_path):
    with pytest.raises(
        make_demo_figures.DemoFigureError,
        match="Stacked directory does not exist",
    ):
        make_demo_figures.make_demo_figures("M83", data_root=tmp_path / "data")


def test_empty_stacked_directory_gives_clear_error(tmp_path):
    data_root = tmp_path / "data"
    (data_root / "M83" / "stacked").mkdir(parents=True)

    with pytest.raises(
        make_demo_figures.DemoFigureError,
        match="No stacked FITS files found",
    ):
        make_demo_figures.make_demo_figures("M83", data_root=data_root)


def test_requested_missing_filter_gives_clear_error(tmp_path):
    data_root = tmp_path / "data"
    _touch_stacked(data_root, filters=("red",))

    with pytest.raises(
        make_demo_figures.DemoFigureError,
        match=r"Stacked FITS file\(s\) not found",
    ):
        make_demo_figures.make_demo_figures("M83", data_root=data_root, filters=["blue"])


def test_rgb_composite_is_generated_only_when_red_green_and_blue_exist(
    tmp_path,
    monkeypatch,
):
    data_root = tmp_path / "data"
    _touch_stacked(data_root, filters=("red", "green"))
    _mock_load_fits(monkeypatch)

    written_without_blue = make_demo_figures.make_demo_figures("M83", data_root=data_root)

    assert (data_root / "M83" / "figures" / "rgb_composite.png") not in written_without_blue
    assert not (data_root / "M83" / "figures" / "rgb_composite.png").exists()

    _touch_stacked(data_root, filters=("blue",))

    written_with_rgb = make_demo_figures.make_demo_figures("M83", data_root=data_root)

    rgb_path = data_root / "M83" / "figures" / "rgb_composite.png"
    assert rgb_path in written_with_rgb
    assert rgb_path.is_file()


def test_cli_filters_limit_generated_outputs(tmp_path, monkeypatch, capsys):
    data_root = tmp_path / "data"
    _touch_stacked(
        data_root,
        filters=("blue", "green", "red"),
        extensions={"blue": ".FIT", "green": ".fts", "red": ".fits"},
    )
    _mock_load_fits(monkeypatch)

    exit_code = make_demo_figures.main(
        ["--object", "M83", "--data-root", str(data_root), "--filters", "blue"]
    )

    assert exit_code == 0
    expected = [
        data_root / "M83" / "figures" / "stacked_blue.png",
        data_root / "M83" / "figures" / "histogram_blue.png",
    ]
    assert capsys.readouterr().out.splitlines() == [str(path) for path in expected]
    assert all(path.is_file() for path in expected)
    assert not (data_root / "M83" / "figures" / "rgb_composite.png").exists()


def test_enhance_rgb_writes_enhanced_composite_when_enabled(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    _touch_stacked(data_root, filters=("blue", "green", "red"))
    _mock_load_fits(monkeypatch)

    written = make_demo_figures.make_demo_figures(
        "M83",
        data_root=data_root,
        enhance_rgb=True,
        stretch=4.0,
        gamma=1.2,
        background_percentile=5,
        lower=0,
        upper=100,
    )

    enhanced_path = data_root / "M83" / "figures" / "rgb_composite_enhanced.png"
    assert enhanced_path in written
    assert enhanced_path.is_file()


def test_cli_enhance_rgb_writes_enhanced_composite(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    _touch_stacked(data_root, filters=("blue", "green", "red"))
    _mock_load_fits(monkeypatch)

    exit_code = make_demo_figures.main(
        [
            "--object",
            "M83",
            "--data-root",
            str(data_root),
            "--enhance-rgb",
            "--stretch",
            "4.0",
            "--gamma",
            "1.2",
            "--background-percentile",
            "5",
            "--lower",
            "0",
            "--upper",
            "100",
        ]
    )

    assert exit_code == 0
    assert (data_root / "M83" / "figures" / "rgb_composite.png").is_file()
    assert (data_root / "M83" / "figures" / "rgb_composite_enhanced.png").is_file()
