# Data Acquisition and Dataset Validation Guide

This guide describes how to collect local stellar or galaxy imaging datasets so they can be reduced consistently by the TP Astro calibration, stacking, visualization, and reporting workflow. Use it before and immediately after each observing session to make sure every object has enough raw or precalibrated data for reliable processing.

## Recommended local folder structure

Create one object directory under `data/` and keep the filter names identical to the pipeline configuration names. For RGB datasets, use `red`, `green`, and `blue` consistently in both folder names and YAML config values.

```text
data/<OBJECT>/
├── raw/
│   ├── red/
│   ├── green/
│   └── blue/
├── calibration/
│   ├── bias/
│   └── flats/
│       ├── red/
│       ├── green/
│       └── blue/
├── calibrated/
│   ├── red/
│   ├── green/
│   └── blue/
├── stacked/
├── figures/
└── analysis/
```

Expected usage by pipeline mode:

- **Raw mode** reads raw science frames from `raw/<filter>/`, bias frames from `calibration/bias/`, and flat frames from `calibration/flats/<filter>/`. The pipeline writes master calibration products and calibrated outputs under `calibrated/`, stacked FITS files under `stacked/`, figures under `figures/`, and reports/diagnostics under `analysis/`.
- **Precalibrated mode** reads already bias/flat-corrected science frames from `calibrated/<filter>/` and skips calibration-frame creation and calibration QC.

## Raw-mode acquisition recommendations

Use raw mode when you have access to the original science frames plus calibration frames from the same acquisition setup.

| Frame type | Recommended count | Minimum count | Folder |
| --- | ---: | ---: | --- |
| Bias | 30–50 total | 15 total | `data/<OBJECT>/calibration/bias/` |
| Flats | 20–30 per filter | 10 per filter | `data/<OBJECT>/calibration/flats/<filter>/` |
| Science | 15–30 per filter | 5 per filter | `data/<OBJECT>/raw/<filter>/` |

Raw-mode setup guidance:

- Keep the same camera settings for bias and science frames, including gain, offset, readout mode, bit depth, binning, and sensor temperature.
- Bias frames should be zero-duration or the shortest supported exposure for the camera, with the detector covered and no light leaks.
- Flats should use the same optical train, focus position, camera rotation, and filter as the matching science frames.
- Flats should be in the detector linear regime and must not be saturated. As a practical rule, keep the flat-field histogram well below clipping and avoid frames with saturated stars, panels, or sky gradients.
- Use one flat set per filter and store it under the exact filter folder name.
- Filter names should match config names exactly: `red`, `green`, and `blue`.
- Avoid mixing frames with different image dimensions, binning, crop windows, or camera orientation unless you intentionally update the processing configuration and crop coordinates.

## Precalibrated mode

Use precalibrated mode when only calibrated science images are available, for example after another tool has already applied bias/dark/flat correction.

Expected layout:

```text
data/<OBJECT>/
└── calibrated/
    ├── red/
    ├── green/
    └── blue/
```

Set `input_mode: precalibrated` in the object config:

```yaml
object_name: <OBJECT>
data_root: data
input_mode: precalibrated
filters:
  - red
  - green
  - blue
```

In this mode, the pipeline does not require `calibration/bias/`, `calibration/flats/<filter>/`, `bias_files`, or `flat_files`. It still performs stacking, optional frame alignment, optional channel alignment, figure generation, and report generation.

## QC workflow after acquisition

Run these checks for each object before starting detailed analysis or comparing objects.

1. **Run the calibration pipeline.**

   ```bash
   python scripts/run_calibration.py --config configs/<object_config>.yaml
   ```

2. **Inspect calibration warnings.** Review `data/<OBJECT>/analysis/diagnostics/calibration_qc_warnings.txt` for mixed bias regimes, saturated flats, non-linear flats, missing calibration products, or other run-level warnings.

3. **Inspect bias statistics.** Review `data/<OBJECT>/analysis/diagnostics/bias_frame_statistics.csv` and confirm the bias frame means and medians form a single stable regime unless you intentionally separated acquisition settings.

4. **Inspect flat linearity curves.** Review `data/<OBJECT>/analysis/diagnostics/flat_<filter>_linearity_curve.png` for every filter. Flat means should scale predictably with exposure time over the accepted range and should not approach saturation.

5. **Inspect science-frame alignment.** Review `data/<OBJECT>/analysis/alignment_report.csv` for registration success, failures, star-detection issues, or large transforms.

6. **Inspect channel alignment.** If channel alignment is enabled, review `data/<OBJECT>/analysis/channel_alignment_report.csv` and the aligned channel products under `data/<OBJECT>/stacked/aligned_channels/`.

7. **Generate deep-sky and galaxy-detail figures.**

   ```bash
   python scripts/make_demo_figures.py --object <OBJECT> --preset deep_sky
   python scripts/make_demo_figures.py --object <OBJECT> --preset galaxy_detail --crop-center <x> <y> --crop-size <pixels>
   ```

8. **Generate the object report.**

   ```bash
   python scripts/generate_object_report.py --object <OBJECT>
   ```

9. **Review final outputs.** Confirm the stacked FITS files, RGB/comparison figures, and `data/<OBJECT>/analysis/report.md` are internally consistent before treating the dataset as complete.

## Common acquisition issues

- **Mixed bias regimes:** Bias frames with different gain, offset, temperature, readout mode, or acquisition sessions can produce multiple ADU clusters. Re-acquire a matched bias set or separate datasets by camera setting.
- **Saturated flats:** Saturated or clipped flats create invalid master flats and can imprint artifacts into calibrated science frames. Re-acquire flats in the detector linear regime.
- **Too few stars for alignment:** Sparse fields, short exposures, clouds, poor focus, or aggressive cropping can leave too few sources for reliable registration. Increase exposure time, use a wider field, improve focus/tracking, or adjust alignment settings.
- **Inconsistent filter names:** Folder names and config filter names must match exactly. Prefer `red`, `green`, and `blue` for RGB workflows.
- **Too few frames:** Low frame counts reduce rejection quality and signal-to-noise. Aim for the recommended counts and treat the minimum counts as emergency lower bounds only.
- **Different image shapes:** Mixed camera binning, crop windows, rotations, or exports with different dimensions can break stacking or channel alignment. Keep acquisition geometry fixed per object.
- **Wrong crop coordinates:** Galaxy-detail figures depend on accurate pixel coordinates in the stacked image. Verify the target center after stacking and update `--crop-center` before producing final report figures.

## Dataset readiness summary

Before processing an object for final analysis, confirm that:

- The object folder follows the expected `data/<OBJECT>/` layout.
- Every configured filter has enough science frames.
- Raw-mode datasets include enough matched bias frames and per-filter flats.
- Precalibrated datasets set `input_mode: precalibrated` and place inputs under `calibrated/<filter>/`.
- QC diagnostics and alignment reports have been reviewed.
- Deep-sky, galaxy-detail, and `report.md` outputs have been generated and visually inspected.
