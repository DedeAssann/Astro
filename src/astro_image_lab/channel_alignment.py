"""Alignment helpers for final stacked filter/channel images."""

from __future__ import annotations

from pathlib import Path

from .io import load_fits, save_fits


def choose_reference_filter(filters, reference_filter="green"):
    """Choose the channel-alignment reference filter.

    ``green`` is preferred by default when present. If no explicit reference is
    available, the first sorted filter is used for deterministic behavior.
    """
    available_filters = sorted(filters)
    if not available_filters:
        raise ValueError("at least one stacked filter is required for channel alignment")
    if reference_filter is None:
        return "green" if "green" in available_filters else available_filters[0]
    if reference_filter in available_filters:
        return reference_filter
    raise ValueError(f"reference_filter {reference_filter!r} is not available in stacked filters")


def _channel_report_record(
    *,
    filter_name,
    input_path,
    output_path,
    status,
    reference_filter,
    method,
    min_area,
    error="",
):
    """Build one serializable channel-alignment report record."""
    return {
        "filter": filter_name,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "status": status,
        "reference_filter": reference_filter,
        "method": method,
        "min_area": min_area,
        "error": error,
    }


def align_stacked_channels(
    stacked_paths,
    output_dir,
    reference_filter="green",
    method="astroalign",
    min_area=12,
    fail_policy="raise",
):
    """Align final stacked filter images to a common reference filter.

    Parameters
    ----------
    stacked_paths : Mapping[str, pathlib.Path]
        Mapping from filter name to the corresponding ``stacked_<filter>.fits``
        path.
    output_dir : pathlib.Path or str
        Directory where ``stacked_<filter>_aligned.fits`` files are written.
    reference_filter : str or None, optional
        Reference filter to align channels to. When ``None``, green is selected
        if present, otherwise the first available filter is selected.
    method : {"astroalign"}, optional
        Channel alignment implementation. Only ``astroalign`` is supported.
    min_area : int, optional
        Forwarded to ``astroalign.register``.
    fail_policy : {"raise", "skip"}, optional
        ``raise`` stops on the first non-reference alignment failure. ``skip``
        records the failure and continues with remaining channels.

    Returns
    -------
    list[dict]
        CSV-ready channel alignment report records.
    """
    if method != "astroalign":
        raise ValueError("method must be 'astroalign'")
    if fail_policy not in {"raise", "skip"}:
        raise ValueError("fail_policy must be 'raise' or 'skip'")
    if not isinstance(min_area, int) or min_area <= 0:
        raise ValueError("min_area must be a positive integer")

    stacked_paths = {filter_name: Path(path) for filter_name, path in stacked_paths.items()}
    resolved_reference_filter = choose_reference_filter(stacked_paths, reference_filter)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    import astroalign

    reference_path = stacked_paths[resolved_reference_filter]
    reference_data, reference_header = load_fits(reference_path)
    records = []

    for filter_name in sorted(stacked_paths):
        input_path = stacked_paths[filter_name]
        output_path = output_dir / f"stacked_{filter_name}_aligned.fits"

        if filter_name == resolved_reference_filter:
            save_fits(reference_data, reference_header, output_path)
            records.append(
                _channel_report_record(
                    filter_name=filter_name,
                    input_path=input_path,
                    output_path=output_path,
                    status="reference",
                    reference_filter=resolved_reference_filter,
                    method=method,
                    min_area=min_area,
                )
            )
            continue

        channel_data, channel_header = load_fits(input_path)
        try:
            aligned_data, _footprint = astroalign.register(
                channel_data, reference_data, min_area=min_area
            )
        except Exception as exc:
            records.append(
                _channel_report_record(
                    filter_name=filter_name,
                    input_path=input_path,
                    output_path=output_path,
                    status="failed",
                    reference_filter=resolved_reference_filter,
                    method=method,
                    min_area=min_area,
                    error=str(exc),
                )
            )
            if fail_policy == "raise":
                raise
            continue

        save_fits(aligned_data, channel_header, output_path)
        records.append(
            _channel_report_record(
                filter_name=filter_name,
                input_path=input_path,
                output_path=output_path,
                status="aligned",
                reference_filter=resolved_reference_filter,
                method=method,
                min_area=min_area,
            )
        )

    return records
