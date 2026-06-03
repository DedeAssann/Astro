# TP Astro Architecture

This document describes the V2.2 scientific workflow and software architecture for the TP Astro FITS calibration and galaxy-analysis pipeline.


![Pipeline architecture](assets/pipeline_architecture.svg)

The static SVG above is the main visual overview for portfolio and README use. The Mermaid diagrams below remain as text-based technical references.

## Scientific pipeline

```mermaid
flowchart TD
    A[Raw science FITS images] --> B[Calibration]
    C[Bias frames] --> D[Master bias]
    E[Flat frames per filter] --> F[Master flat per filter]
    D --> B
    F --> B
    B --> G[Calibrated science images]
    G --> H[Median normalization]
    H --> I[Optional alignment]
    I --> J[Sigma-clipped stacking]
    J --> K[Stacked FITS images]
    K --> L[Visualization]
    K --> M[Photometry and galaxy analysis]
    L --> N[PNG figures and RGB composites]
    M --> O[Fluxes, effective radius, physical scales]
```

## Software architecture

```mermaid
flowchart LR
    CFG[configs/*.yaml] --> CLI[scripts/run_calibration.py]
    CLI --> IO[astro_image_lab.io]
    CLI --> CAL[astro_image_lab.calibration]
    CLI --> STACK[astro_image_lab.stacking]
    CAL --> IO
    STACK --> IO
    STACK --> CAL
    STACK -. optional .-> ALIGN[astroalign]
    STACK -. preferred .-> ASTROPY[astropy.stats.sigma_clip]
    IO -. FITS backend .-> FITS[astropy.io.fits]
    FITS --> OUT[(data/<OBJECT_NAME>/{calibrated,stacked})]
    OUT --> VIZ[astro_image_lab.visualization]
    OUT --> PHOTO[astro_image_lab.photometry]
    VIZ --> FIGS[(PNG figures / RGB arrays)]
    PHOTO --> MEAS[(Fluxes / radii / kpc scales)]
    TESTS[tests/] --> CLI
    TESTS --> IO
    TESTS --> CAL
    TESTS --> STACK
    TESTS --> VIZ
    TESTS --> PHOTO
```


## Object-based data layout

V2.2 organizes local data by observed object and uses one YAML config per object. The compact config mode provides `object_name`, `data_root`, and `filters`, then the CLI discovers FITS inputs from this standard structure:

```text
data/M83/
├── raw/
│   ├── red/
│   │   └── *.{fits,fit,fts}
│   ├── green/
│   │   └── *.{fits,fit,fts}
│   └── blue/
│       └── *.{fits,fit,fts}
├── calibration/
│   ├── bias/
│   │   └── *.{fits,fit,fts}
│   └── flats/
│       ├── red/
│       │   └── *.{fits,fit,fts}
│       ├── green/
│       │   └── *.{fits,fit,fts}
│       └── blue/
│           └── *.{fits,fit,fts}
├── calibrated/
├── stacked/
├── figures/
└── analysis/
```

The CLI accepts `.fits`, `.fit`, and `.fts` files case-insensitively and sorts discovered lists for reproducibility. Compact configs infer `output_dirs.calibrated`, `output_dirs.stacked`, `output_dirs.figures`, and `output_dirs.analysis` from `data_root/object_name`. Explicit `output_dirs` override those inferred directories; older V1 configs without `output_dirs` remain supported by setting `output_dir`, which is used for all generated FITS files. `master_bias.fits` and `master_flat_<filter>.fits` are written to the calibrated directory, while `stacked_<filter>.fits` is written to the stacked directory.

## Module responsibility table

| Module or path | Responsibility | Main outputs |
| --- | --- | --- |
| `scripts/run_calibration.py` | Command-line entry point; loads one object YAML config, validates explicit or compact discovery fields, checks inputs, creates output directories, orchestrates master calibration products and stacked outputs. | `master_bias.fits`, `master_flat_<filter>.fits`, `stacked_<filter>.fits` |
| `scripts/make_demo_figures.py` | Post-pipeline demo-figure entry point; reads object-layout stacked FITS outputs, creates the figures directory, writes per-filter previews and histograms, and optionally writes an RGB composite. | `stacked_<filter>.png`, `histogram_<filter>.png`, `rgb_composite.png` |
| `src/astro_image_lab/io.py` | FITS I/O boundary; centralizes supported FITS extension checks and non-recursive file discovery, reads primary-HDU image data and headers, and writes data/header pairs back to FITS. | Sorted FITS path lists, NumPy-like image arrays, FITS headers, FITS files |
| `src/astro_image_lab/calibration.py` | Builds master bias and master flats; applies `(science - master_bias) / master_flat` calibration. | Master calibration arrays and calibrated science arrays |
| `src/astro_image_lab/stacking.py` | Median-normalizes calibrated science images, optionally registers images with `astroalign`, sigma-clips stacks, and averages surviving pixels. | Stacked `float32` science images |
| `src/astro_image_lab/visualization.py` | Percentile scaling and Matplotlib-based inspection plots; RGB array creation from stacked channels. | Figures, PNG files, RGB arrays |
| `src/astro_image_lab/photometry.py` | Lightweight aperture photometry and galaxy-analysis math implemented with NumPy. | Aperture fluxes, growth curves, effective radius, magnitudes, kpc scales |
| `configs/m83_example.yaml` | Example declarative pipeline configuration for M83-style red/green/blue processing. | Runtime parameters and input/output paths |
| `tests/` | Regression tests for numerical helpers, CLI validation, and plotting behavior. | Test confidence for V1 behavior |

## Input/output table

| Stage | Inputs | Outputs | Notes |
| --- | --- | --- | --- |
| Configuration | Compact object YAML with `object_name`, `data_root`, `filters`, and optional legacy `align`, `alignment`, `sigma`, `maxiters`; or explicit YAML with `bias_files`, `flat_files`, `science_files`. Legacy configs may use `output_dir`; explicit `output_dirs` can override inferred outputs. | Validated Python paths and options. | Compact discovery requires standard per-filter raw and flat directories. Explicit mode still requires matching `flat_files` and `science_files` filters. |
| Bias creation | Bias FITS files. | `output_dirs.calibrated/master_bias.fits` and in-memory master-bias array. | Default combine method is per-pixel median. Legacy `output_dir` configs write this file to the single legacy directory. |
| Flat creation | Per-filter flat FITS files and master bias. | `output_dirs.calibrated/master_flat_<filter>.fits` and in-memory normalized master-flat arrays. | Each flat is bias-subtracted and median-normalized before equal-weight averaging. Legacy `output_dir` configs write these files to the single legacy directory. |
| Science calibration | Per-filter raw science FITS files, master bias, matching master flat. | In-memory calibrated science arrays. | Invalid or zero flat pixels become `NaN` downstream. |
| Normalization and alignment | Calibrated science arrays; optional `astroalign` registration. | Normalized and optionally registered stack cube plus CSV-ready alignment records. | The first science image is retained as the alignment reference. Alignment records capture filter, file path, index, status, errors, method, and `min_area`. |
| Sigma-clipped stacking | Stack cube, sigma threshold, maximum iterations. | `output_dirs.stacked/stacked_<filter>.fits` images. | Uses Astropy sigma clipping when available, with a NumPy fallback. Legacy `output_dir` configs write these files to the single legacy directory. |
| Visualization | Stacked FITS data or arrays. | Inspection figures, histograms, comparisons, RGB composites. | Plot helpers can save PNGs when an output path is supplied. `scripts/make_demo_figures.py` provides the object-layout CLI for discovering supported FITS files in `data/<OBJECT_NAME>/stacked/` whose stems start with `stacked_` and rendering them into `data/<OBJECT_NAME>/figures/`. |
| Photometry and galaxy analysis | Stacked image arrays, aperture center/radii, background estimate, distance and pixel scale metadata. | Fluxes, growth curves, effective radius, absolute magnitudes, physical sizes. | V1 provides lightweight NumPy calculations rather than a full photometry framework. |

## Data flow through the system

1. Each observed target has its own YAML file. Compact configs describe the object name, data root, filters, and stacking parameters; explicit configs can still list every bias, flat, and science FITS path.
2. The CLI validates the config before importing heavier scientific helpers. In compact mode it checks required directories, discovers `.fits`, `.fit`, and `.fts` files case-insensitively with the shared FITS I/O helpers, sorts them, and raises clear errors for missing directories or empty required FITS directories. It also creates all configured or inferred output directories when they are missing.
3. Bias frames are loaded through the FITS I/O layer and combined into a master bias. The CLI writes that product with the header from the first bias frame into the inferred or explicit calibrated directory, or the legacy `output_dir`.
4. For each filter, flat frames are loaded, bias-subtracted, normalized by their median response, averaged, renormalized, and written as a filter-specific master flat into the inferred or explicit calibrated directory, or the legacy `output_dir`.
5. For the same filter, each science frame is loaded, calibrated with the master bias and matching master flat, then normalized by its median to place images on a common relative scale.
6. If alignment is enabled, the first normalized science image is used as the reference and later images are registered to it with `astroalign.register(..., min_area=alignment.min_area)`. If alignment is disabled, images are stacked in their original pixel coordinates and report rows are marked `skipped`. `alignment.fail_policy: raise` preserves stop-on-failure behavior, while `skip` records failed registrations and continues with remaining frames.
7. The normalized image cube is sigma-clipped along the exposure axis and averaged into a final stacked image, which is saved as `stacked_<filter>.fits` in `output_dirs.stacked` or the legacy `output_dir`. Collected alignment diagnostics are written to `output_dirs.analysis/alignment_report.csv`, or to `alignment_report.csv` in the legacy `output_dir`.
8. Stacked products can then feed visualization helpers for review figures and RGB composites, or photometry helpers for aperture fluxes, growth curves, effective-radius estimates, and angular-to-physical size conversions. The demo-figure CLI is intentionally post-processing only: it discovers or accepts stacked filters, loads only supported FITS files whose stems are `stacked_<filter>`, writes PNGs under `figures/`, and never requires raw/calibration inputs or reruns reduction.
9. Tests exercise the scientific assumptions and guard against regressions in calibration formulas, stacking behavior, alignment-report behavior, plotting helpers, photometry math, and CLI validation.
