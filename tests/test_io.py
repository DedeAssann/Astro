from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from astro_image_lab.io import discover_fits_files, is_fits_file


def test_is_fits_file_accepts_supported_extensions_case_insensitively():
    supported_names = [
        "image.fits",
        "image.fit",
        "image.fts",
        "image.FITS",
        "image.FIT",
        "image.FTS",
    ]

    assert [is_fits_file(name) for name in supported_names] == [True] * len(supported_names)
    assert not is_fits_file("image.txt")


def test_discover_fits_files_sorts_and_ignores_non_fits_files(tmp_path):
    fits_paths = [
        tmp_path / "science_red_002.FITS",
        tmp_path / "bias_001.fit",
        tmp_path / "flat_red_001.fts",
    ]
    for path in fits_paths:
        path.write_text("placeholder", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not FITS", encoding="utf-8")
    (tmp_path / "nested.fit").mkdir()

    assert discover_fits_files(tmp_path) == sorted(fits_paths)
