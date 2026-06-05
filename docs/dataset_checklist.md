# Dataset Validation Checklist

Use this checklist after each acquisition session and before final processing.

## Folder layout

- [ ] Object directory exists at `data/<OBJECT>/`.
- [ ] Raw science frames are stored in `raw/<filter>/`, or precalibrated science frames are stored in `calibrated/<filter>/`.
- [ ] Bias frames are stored in `calibration/bias/` when using raw mode.
- [ ] Flat frames are stored in `calibration/flats/<filter>/` when using raw mode.
- [ ] Output directories `stacked/`, `figures/`, and `analysis/` are present or can be created by the pipeline.

## Frame counts

- [ ] Bias frames: 30–50 recommended, 15 minimum.
- [ ] Flat frames: 20–30 per filter recommended, 10 per filter minimum.
- [ ] Science frames: 15–30 per filter recommended, 5 per filter minimum.
- [ ] Every configured filter has matching input folders and filenames.

## Acquisition consistency

- [ ] Bias and science frames use the same camera gain, offset, readout mode, bit depth, binning, and temperature.
- [ ] Flats use the same optical train, focus position, camera rotation, and filter as the science frames.
- [ ] Flats are in the detector linear regime and are not saturated.
- [ ] Image dimensions and binning are consistent within the object dataset.
- [ ] Filter names match the pipeline config exactly: `red`, `green`, and `blue`.

## Post-run QC

- [ ] `calibration_qc_warnings.txt` has no unresolved warnings.
- [ ] `bias_frame_statistics.csv` shows one stable bias regime.
- [ ] Flat linearity curves are acceptable for each filter.
- [ ] `alignment_report.csv` shows successful science-frame alignment or expected skip behavior.
- [ ] `channel_alignment_report.csv` is acceptable when channel alignment is enabled.
- [ ] Deep-sky figures have been generated and inspected.
- [ ] Galaxy-detail figures have been generated with verified crop coordinates.
- [ ] `report.md` has been generated and reviewed.
