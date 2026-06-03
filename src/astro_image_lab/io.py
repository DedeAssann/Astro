"""FITS input/output helpers for the astronomy image lab package."""

from pathlib import Path


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
