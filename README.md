# TP Astro: FITS Calibration and Galaxy Analysis Pipeline

TP Astro is a compact, test-covered Python project for reducing astronomical FITS images and extracting first-pass science products from galaxy observations. The V1 pipeline turns raw science frames, bias frames, and filter-specific flats into calibrated and stacked FITS images, then supports visualization, RGB compositing, aperture photometry, effective-radius estimates, and physical-scale conversions.


![Pipeline architecture](docs/assets/pipeline_architecture.svg)

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
│   ├── m83_example.yaml
│   └── m83_explicit_example.yaml
├── docs/                    # Project architecture and design documentation
│   └── architecture.md
├── doc/                     # Original teaching notebooks, PDFs, and legacy processing notes
├── Images/                  # Reference figures and example astronomy images
├── notebooks/               # Exploratory notebooks
├── scripts/                 # Command-line entry points
│   ├── run_calibration.py
│   └── make_demo_figures.py
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

Create one YAML config per observed object. The compact example `configs/m83_example.yaml` needs only the object name, data root, and filters; `scripts/run_calibration.py` discovers FITS inputs from the standard object directory layout.

```bash
python scripts/run_calibration.py --config configs/m83_example.yaml
```

Compact config mode looks like this:

```yaml
object_name: M83
data_root: data
filters:
  - red
  - green
  - blue
```

The inferred local data layout is:

```text
data/<OBJECT_NAME>/
├── raw/
│   └── <filter>/
│       └── *.{fits,fit,fts}
├── calibration/
│   ├── bias/
│   │   └── *.{fits,fit,fts}
│   └── flats/
│       └── <filter>/
│           └── *.{fits,fit,fts}
├── calibrated/
├── stacked/
├── figures/
└── analysis/
```

The CLI accepts `.fits`, `.fit`, and `.fts` filenames case-insensitively, sorts discovered lists for reproducibility, and creates output directories when needed. For each configured science filter, it writes:

- `master_bias.fits` to `data/<OBJECT_NAME>/calibrated/`
- `master_flat_<filter>.fits` to `data/<OBJECT_NAME>/calibrated/`
- `stacked_<filter>.fits` to `data/<OBJECT_NAME>/stacked/`
- `alignment_report.csv` to `data/<OBJECT_NAME>/analysis/`
- When channel alignment is enabled, `stacked/aligned_channels/stacked_<filter>_aligned.fits` and `analysis/channel_alignment_report.csv`

Generate PNG demo figures from those stacked FITS products with:

```bash
python scripts/make_demo_figures.py --object M83
```

By default, the demo-figure script discovers supported FITS files in `data/M83/stacked/`, keeps files whose stems start with `stacked_`, creates `data/M83/figures/` if needed, and prints every PNG path it writes. It saves one channel preview and one finite-pixel histogram per discovered filter:

- `stacked_<filter>.png` to `data/<OBJECT_NAME>/figures/`
- `histogram_<filter>.png` to `data/<OBJECT_NAME>/figures/`

When `stacked_red`, `stacked_green`, and `stacked_blue` files with supported FITS extensions are all available in the selected inputs, it also writes `rgb_composite.png` using the package RGB visualization helper. Use `--data-root` for a different object-layout root, or `--filters blue green red` to render a specific filter subset without rerunning calibration.


Alignment remains enabled by default and can still be controlled with the legacy top-level `align: true` or `align: false` flag. New configs can use an `alignment` block for diagnostics and tuning; when `alignment.enabled` is present, it overrides the legacy `align` value. The default settings preserve the previous behavior:

```yaml
alignment:
  enabled: true
  method: astroalign
  min_area: 12
  detection_sigma: null
  reference: first
  fail_policy: raise
```

`min_area` is forwarded to `astroalign.register`. `fail_policy: raise` stops on a registration failure, while `fail_policy: skip` records the failed science frame in the report and stacks the remaining usable frames. The alignment report records one row per science frame with the filter, file path, frame index, status (`reference`, `aligned`, `skipped`, or `failed`), error message, method, and `min_area`.


Channel alignment is a second, optional alignment stage that runs after per-filter stacking. Frame alignment registers science frames within one filter; channel alignment registers the final `stacked_red`, `stacked_green`, and `stacked_blue` products to a common reference before RGB composition. It is disabled when the `channel_alignment` section is absent. Enable it with:

```yaml
channel_alignment:
  enabled: true
  reference_filter: green
  method: astroalign
  min_area: 12
  fail_policy: raise
```

The reference filter defaults to green when green is available, otherwise the first available filter is used. Successful outputs are written under `data/<OBJECT_NAME>/stacked/aligned_channels/` as `stacked_<filter>_aligned.fits`, and `channel_alignment_report.csv` records each channel status (`reference`, `aligned`, or `failed`). `scripts/make_demo_figures.py` still renders per-filter previews from the regular stacked products, but its RGB composite prefers aligned channel files when they exist and falls back to regular `stacked_<filter>.fits` files otherwise; the CLI prints the RGB source paths it used.

Explicit config mode is still supported for custom file selections. Use `configs/m83_explicit_example.yaml` as a template with `bias_files`, `flat_files`, `science_files`, and optional `output_dirs`. For backward compatibility, older configs can omit `output_dirs` and keep using `output_dir`; in that case all generated FITS outputs are written to the single legacy directory.

## Testing

Run the full test suite from the repository root:

```bash
pytest -q
```

## Current V2.4 status

V2.4 is a working, modular baseline for object-based astronomy-image reduction experiments:

- FITS I/O, calibration, stacking/alignment, visualization, photometry, and galaxy-analysis helpers are implemented under `src/astro_image_lab/`.
- The command-line calibration pipeline is driven by YAML configuration, performs input validation before reading FITS data, writes alignment diagnostics for each science frame, and can optionally align final stacked channels for RGB composition.
- The test suite covers the core numerical behavior and CLI validation paths.
- The example M83 configuration documents the object-based `data/M83/` layout, but the raw FITS data are not committed to the repository.
- The pipeline is intentionally lightweight and explicit, favoring readable scientific steps over a large framework.

## Roadmap for V2

- Add packaging metadata (`pyproject.toml`) and an installable console script.
- Expand configuration schemas for dark frames, exposure-time normalization, WCS-aware alignment, and richer output naming.
- Add end-to-end integration tests using small synthetic FITS fixtures.
- Generate automated quality-control reports with image previews, histograms, rejection statistics, and provenance metadata.
- Improve photometry with background annuli, uncertainty propagation, zero-point handling, and optional `photutils` integration.
- Add WCS-aware galaxy analysis, surface-brightness profiles, and calibrated physical measurements.
- Provide reproducible example data download instructions or scripts for public demonstration datasets.
