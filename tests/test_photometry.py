from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astro_image_lab import photometry


def test_aperture_flux_sums_finite_pixels_in_circular_aperture():
    image = np.arange(25, dtype=float).reshape(5, 5)
    image[2, 3] = np.nan

    flux = photometry.aperture_flux(image, center=(2, 2), radius=1)

    # Radius 1 around (y=2, x=2) includes center plus four cardinal neighbors;
    # the NaN right-hand neighbor is ignored.
    expected = image[2, 2] + image[1, 2] + image[3, 2] + image[2, 1]
    assert flux == expected


def test_aperture_flux_subtracts_scalar_background_per_finite_pixel():
    image = np.ones((3, 3), dtype=float) * 10

    flux = photometry.aperture_flux(image, center=(1, 1), radius=1, background=2)

    assert flux == 5 * (10 - 2)


def test_aperture_flux_rejects_non_finite_or_negative_radius():
    image = np.ones((3, 3), dtype=float)

    for radius in [-1, np.nan, np.inf, -np.inf]:
        with pytest.raises(ValueError, match="radius must be finite and non-negative"):
            photometry.aperture_flux(image, center=(1, 1), radius=radius)


def test_aperture_growth_curve_returns_radii_and_flux_arrays():
    image = np.ones((5, 5), dtype=float)

    radii, fluxes = photometry.aperture_growth_curve(
        image, center=(2, 2), radii=[0, 1, 2]
    )

    np.testing.assert_allclose(radii, np.array([0, 1, 2], dtype=float))
    np.testing.assert_allclose(fluxes, np.array([1, 5, 13], dtype=float))


def test_aperture_growth_curve_rejects_non_finite_radii_before_fluxes(monkeypatch):
    image = np.ones((3, 3), dtype=float)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("aperture_flux should not be called for invalid radii")

    monkeypatch.setattr(photometry, "aperture_flux", fail_if_called)

    for radii in ([0, np.nan], [0, np.inf], [0, -np.inf]):
        with pytest.raises(ValueError, match="radii must contain only finite values"):
            photometry.aperture_growth_curve(image, center=(1, 1), radii=radii)


def test_estimate_effective_radius_interpolates_half_total_flux():
    radii = np.array([0, 1, 2, 3], dtype=float)
    fluxes = np.array([0, 4, 8, 10], dtype=float)

    effective_radius = photometry.estimate_effective_radius(radii, fluxes)

    assert effective_radius == pytest.approx(1.25)


def test_estimate_effective_radius_uses_maximum_flux_for_non_monotonic_curve():
    radii = np.array([0, 1, 2, 3], dtype=float)
    fluxes = np.array([0, 100, 110, 10], dtype=float)

    effective_radius = photometry.estimate_effective_radius(radii, fluxes)

    # Half-light should use half of the maximum flux (110 / 2), not half of
    # the final, oversubtracted growth-curve value (10 / 2).
    assert effective_radius == pytest.approx(0.55)


def test_distance_modulus_and_absolute_magnitude():
    distance_pc = 1_000_000

    assert photometry.distance_modulus(distance_pc) == pytest.approx(25.0)
    assert photometry.apparent_to_absolute_magnitude(10.0, distance_pc) == pytest.approx(-15.0)


def test_angular_and_pixel_radius_conversions_to_kpc():
    distance_pc = 206_265_000

    assert photometry.arcsec_to_kpc(1, distance_pc) == pytest.approx(1.0)
    assert photometry.pixel_radius_to_kpc(
        10, pixel_scale_arcsec=0.5, distance_pc=distance_pc
    ) == pytest.approx(5.0)
