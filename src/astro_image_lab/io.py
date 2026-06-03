"""FITS input/output helpers for the astronomy image lab package."""

from pathlib import Path


SUPPORTED_FITS_EXTENSIONS = {".fits", ".fit", ".fts"}


def is_fits_file(path):
    """Return True when ``path`` has a supported FITS file extension.

    Supported extensions are matched case-insensitively and include
    ``.fits``, ``.fit``, and ``.fts``.
    """
    return Path(path).suffix.lower() in SUPPORTED_FITS_EXTENSIONS


def discover_fits_files(directory):
    """Return sorted FITS files directly inside ``directory``.

    The search is non-recursive and accepts all extensions listed in
    :data:`SUPPORTED_FITS_EXTENSIONS`, case-insensitively. Non-files and
    non-FITS paths are ignored.
    """
    return sorted(
        path
        for path in Path(directory).iterdir()
        if path.is_file() and is_fits_file(path)
    )


def load_fits(path):
    """Load the primary image data and header from a FITS file.

    Parameters
    ----------
    path : str or pathlib.Path
        FITS file to open.

    Returns
    -------
    tuple
        ``(data, header)`` from the primary HDU.
    """
    from astropy.io import fits

    with fits.open(Path(path)) as hdul:
        data = hdul[0].data
        if data is not None:
            data = data.copy()
        header = hdul[0].header.copy()
    return data, header


def save_fits(data, header, path, overwrite=True):
    """Save image data and a FITS header to a primary HDU."""
    from astropy.io import fits

    hdu = fits.PrimaryHDU(data=data, header=header)
    hdu.writeto(Path(path), overwrite=overwrite)
