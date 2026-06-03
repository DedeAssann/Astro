# TP Astro: FITS Calibration and Galaxy Analysis Pipeline

TP Astro is a compact, test-covered Python project for reducing astronomical FITS images and extracting first-pass science products from galaxy observations. The V1 pipeline turns raw science frames, bias frames, and filter-specific flats into calibrated and stacked FITS images, then supports visualization, RGB compositing, aperture photometry, effective-radius estimates, and physical-scale conversions.

## Scientific motivation

Deep-sky images contain both astronomical signal and instrument signatures. Bias frames characterize electronic offsets, flat fields characterize pixel-to-pixel and optical-response variations, and multiple science exposures improve signal-to-noise when aligned and stacked. This project packages that workflow into reusable helpers and a YAML-driven command-line interface so the same reduction steps can be inspected, tested, and repeated for targets such as M83.

The scientific goal of V1 is to provide a transparent teaching and portfolio pipeline that connects detector calibration to measurable galaxy properties: cleaned images, stacked filter products, RGB figures, aperture fluxes, effective radii, and angular-to-physical size estimates.

## Features

- **FITS I/O helpers** for loading primary-HDU image data and preserving headers when writing derived products.
- **Calibration helpers** for master-bias creation, normalized master-flat creation, and science-frame calibration.
- **Stacking and alignment helpers** for median normalization, optional `astroalign` registration, sigma clipping, and mean stacking.
- **YAML-driven CLI pipeline** that validates inputs and writes master calibration products plus stacked science images.
- **Visualization helpers** for percentile scaling, single-image plots, histograms, before/after comparisons, and RGB composites.
- **Photometry and galaxy-analysis helpers** for circular aperture fluxes, growth curves, effective radius estimates, distance modulus, absolute magnitude conversion, and pixel-to-kpc conversion.
- **Tests** covering calibration math, stacking behavior, visualization utilities, photometry utilities, and CLI config validation.

## Repository structure

```text
.
├── configs/                 # Example YAML pipeline configurations
│   └── m83_example.yaml
├── docs/                    # Project architecture and design documentation
│   └── architecture.md
├── doc/                     # Original teaching notebooks, PDFs, and legacy processing notes
├── Images/                  # Reference figures and example astronomy images
├── notebooks/               # Exploratory notebooks
├── scripts/                 # Command-line entry points
│   └── run_calibration.py
├── src/astro_image_lab/     # Reusable package modules
│   ├── calibration.py
│   ├── io.py
│   ├── photometry.py
│   ├── stacking.py
│   └── visualization.py
├── tests/                   # Pytest suite
├── environment.yml          # Conda environment definition
├── requirements.txt         # Pip dependency list
└── README.md
```

## Installation

### Option A: pip and virtualenv

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The repository currently uses a source-checkout layout. Scripts add `src/` to `sys.path` when needed, and tests do the same. For interactive notebooks or ad-hoc Python sessions, either run from the repository root or export:

```bash
export PYTHONPATH="$PWD/src:${PYTHONPATH}"
```

### Option B: conda

```bash
conda env create -f environment.yml
conda activate tp-astro
```

## Usage example

Edit `configs/m83_example.yaml` so each path points to local FITS files. The example config expects bias frames, per-filter flat frames, per-filter science frames, and an output directory.

```bash
python scripts/run_calibration.py --config configs/m83_example.yaml
```

For each configured science filter, the CLI writes:

- `master_bias.fits`
- `master_flat_<filter>.fits`
- `stacked_<filter>.fits`

The example configuration writes these outputs under `results/m83/`.

## Testing

Run the full test suite from the repository root:

```bash
pytest -q
```

## Current V1 status

V1 is a working, modular baseline for small astronomy-image reduction experiments:

- FITS I/O, calibration, stacking/alignment, visualization, photometry, and galaxy-analysis helpers are implemented under `src/astro_image_lab/`.
- The command-line calibration pipeline is driven by YAML configuration and performs input validation before reading FITS data.
- The test suite covers the core numerical behavior and CLI validation paths.
- The example M83 configuration documents the expected data layout, but the raw FITS data are not committed to the repository.
- The pipeline is intentionally lightweight and explicit, favoring readable scientific steps over a large framework.

## Roadmap for V2

- Add packaging metadata (`pyproject.toml`) and an installable console script.
- Expand configuration schemas for dark frames, exposure-time normalization, WCS-aware alignment, and richer output naming.
- Add end-to-end integration tests using small synthetic FITS fixtures.
- Generate automated quality-control reports with image previews, histograms, rejection statistics, and provenance metadata.
- Improve photometry with background annuli, uncertainty propagation, zero-point handling, and optional `photutils` integration.
- Add WCS-aware galaxy analysis, surface-brightness profiles, and calibrated physical measurements.
- Provide reproducible example data download instructions or scripts for public demonstration datasets.
