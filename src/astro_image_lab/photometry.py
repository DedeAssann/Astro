"""Minimal photometry and galaxy-analysis helpers.

The functions in this module intentionally depend only on NumPy so they can be
used in lightweight teaching notebooks and command-line workflows without
requiring a dedicated photometry package such as ``photutils``.
"""

import numpy as np


def aperture_flux(image, center, radius, background=0.0):
    """Return the background-subtracted flux inside a circular aperture.

    Parameters
    ----------
    image : array-like
        Two-dimensional image data.
    center : tuple of float
        Aperture center as ``(y, x)`` in pixel coordinates.
    radius : float
        Aperture radius in pixels. Pixels whose centers are at or within this
        radius are included.
    background : float, optional
        Scalar sky background value to subtract from each finite pixel included
        in the aperture.

    Returns
    -------
    float
        Sum of finite aperture pixels after subtracting ``background`` per
        included pixel. Non-finite image pixels are ignored.
    """
    image = np.asarray(image, dtype=float)
    if image.ndim != 2:
        raise ValueError("image must be a two-dimensional array")

    y_center, x_center = center
    radius = float(radius)
    if radius < 0:
        raise ValueError("radius must be non-negative")

    background = float(background)
    yy, xx = np.indices(image.shape, dtype=float)
    aperture = (yy - y_center) ** 2 + (xx - x_center) ** 2 <= radius**2
    finite_aperture = aperture & np.isfinite(image)

    return float(np.sum(image[finite_aperture] - background))


def aperture_growth_curve(image, center, radii, background=0.0):
    """Measure aperture fluxes for a sequence of circular radii.

    Parameters are the same as :func:`aperture_flux`, except ``radii`` is an
    iterable of aperture radii in pixels.

    Returns
    -------
    tuple of numpy.ndarray
        ``(radii, fluxes)`` as floating-point arrays. The radii are returned in
        the same order they were provided.
    """
    radii = np.asarray(radii, dtype=float)
    fluxes = np.asarray(
        [aperture_flux(image, center, radius, background=background) for radius in radii],
        dtype=float,
    )
    return radii, fluxes


def estimate_effective_radius(radii, fluxes):
    """Estimate the half-light/effective radius from a growth curve.

    The effective radius is the radius containing half of the final total flux,
    where the final flux is the flux at the largest supplied radius. Linear
    interpolation is used between the two sampled radii that bracket this
    half-flux value.
    """
    radii = np.asarray(radii, dtype=float)
    fluxes = np.asarray(fluxes, dtype=float)

    if radii.shape != fluxes.shape:
        raise ValueError("radii and fluxes must have the same shape")
    if radii.size == 0:
        raise ValueError("radii and fluxes must not be empty")
    if not np.all(np.isfinite(radii)) or not np.all(np.isfinite(fluxes)):
        raise ValueError("radii and fluxes must contain only finite values")

    order = np.argsort(radii)
    sorted_radii = radii[order]
    sorted_fluxes = fluxes[order]
    half_flux = sorted_fluxes[-1] / 2.0

    if sorted_fluxes[0] >= half_flux:
        return float(sorted_radii[0])

    for index in range(1, sorted_fluxes.size):
        previous_flux = sorted_fluxes[index - 1]
        current_flux = sorted_fluxes[index]
        if current_flux >= half_flux:
            previous_radius = sorted_radii[index - 1]
            current_radius = sorted_radii[index]
            if current_flux == previous_flux:
                return float(current_radius)
            fraction = (half_flux - previous_flux) / (current_flux - previous_flux)
            return float(previous_radius + fraction * (current_radius - previous_radius))

    return float(sorted_radii[-1])


def distance_modulus(distance_pc):
    """Return the distance modulus for a distance in parsecs.

    The distance modulus is ``5 * log10(distance_pc / 10)``.
    """
    distance_pc = float(distance_pc)
    if distance_pc <= 0:
        raise ValueError("distance_pc must be positive")
    return float(5.0 * np.log10(distance_pc / 10.0))


def apparent_to_absolute_magnitude(m_app, distance_pc):
    """Convert apparent magnitude to absolute magnitude."""
    return float(m_app) - distance_modulus(distance_pc)


def arcsec_to_kpc(theta_arcsec, distance_pc):
    """Convert an angular size in arcseconds to kpc using the small-angle approximation.

    ``physical_size_kpc = distance_pc * theta_arcsec / 206265 / 1000``.
    """
    distance_pc = float(distance_pc)
    if distance_pc <= 0:
        raise ValueError("distance_pc must be positive")
    return float(distance_pc * float(theta_arcsec) / 206265.0 / 1000.0)


def pixel_radius_to_kpc(radius_pixels, pixel_scale_arcsec, distance_pc):
    """Convert a radius in pixels to kpc through an arcsecond pixel scale."""
    theta_arcsec = float(radius_pixels) * float(pixel_scale_arcsec)
    return arcsec_to_kpc(theta_arcsec, distance_pc)
