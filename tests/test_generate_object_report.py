from pathlib import Path
import importlib.util
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_object_report.py"
spec = importlib.util.spec_from_file_location("generate_object_report", SCRIPT_PATH)
generate_object_report = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = generate_object_report
spec.loader.exec_module(generate_object_report)


def test_generate_object_report_writes_report_md(tmp_path):
    data_root = tmp_path / "data"
    object_dir = data_root / "M83"
    stacked_dir = object_dir / "stacked"
    aligned_dir = stacked_dir / "aligned_channels"
    figures_dir = object_dir / "figures"
    analysis_dir = object_dir / "analysis"
    diagnostics_dir = analysis_dir / "diagnostics"
    aligned_dir.mkdir(parents=True)
    figures_dir.mkdir(parents=True)
    diagnostics_dir.mkdir(parents=True)

    (stacked_dir / "stacked_red.fits").write_text("placeholder\n", encoding="utf-8")
    (stacked_dir / "stacked_green.fit").write_text("placeholder\n", encoding="utf-8")
    (aligned_dir / "stacked_red_aligned.fits").write_text("placeholder\n", encoding="utf-8")
    (figures_dir / "rgb_composite.png").write_text("png placeholder\n", encoding="utf-8")
    (figures_dir / "rgb_composite_deep_sky.png").write_text("png placeholder\n", encoding="utf-8")
    (diagnostics_dir / "flat_red_linearity_curve.png").write_text("png placeholder\n", encoding="utf-8")

    report_path = generate_object_report.generate_object_report("M83", data_root=data_root)

    assert report_path == analysis_dir / "report.md"
    text = report_path.read_text(encoding="utf-8")
    assert "# M83 Object Report" in text
    assert "`M83/stacked/stacked_red.fits`" in text
    assert "`M83/stacked/aligned_channels/stacked_red_aligned.fits`" in text
    assert "`M83/figures/rgb_composite_deep_sky.png`" in text
    assert "`M83/analysis/diagnostics/flat_red_linearity_curve.png`" in text
    assert "Suggested next manual checks" in text


def test_generate_object_report_summarizes_warnings_and_alignment_counts(tmp_path):
    data_root = tmp_path / "data"
    analysis_dir = data_root / "M83" / "analysis"
    (data_root / "M83" / "stacked").mkdir(parents=True)
    analysis_dir.mkdir(parents=True)
    diagnostics_dir = analysis_dir / "diagnostics"
    diagnostics_dir.mkdir()
    (diagnostics_dir / "bias_frame_statistics.csv").write_text("file,mean\nbias.fit,100\n", encoding="utf-8")
    (diagnostics_dir / "flat_frame_statistics.csv").write_text("file,filter,mean\nflat.fit,red,1000\n", encoding="utf-8")
    (diagnostics_dir / "calibration_qc_warnings.txt").write_text(
        "bias mean range exceeds tolerance\nflat red missing EXPTIME\n",
        encoding="utf-8",
    )
    (analysis_dir / "alignment_report.csv").write_text(
        "filter,path,frame_index,status\nred,a.fits,0,reference\nred,b.fits,1,aligned\nblue,c.fits,0,failed\n",
        encoding="utf-8",
    )
    (analysis_dir / "channel_alignment_report.csv").write_text(
        "filter,path,status\ngreen,g.fits,reference\nred,r.fits,aligned\nblue,b.fits,failed\n",
        encoding="utf-8",
    )

    report_path = generate_object_report.generate_object_report("M83", data_root=data_root)
    text = report_path.read_text(encoding="utf-8")

    assert "bias mean range exceeds tolerance" in text
    assert "flat red missing EXPTIME" in text
    assert "`M83/analysis/diagnostics/bias_frame_statistics.csv`" in text
    assert "`M83/analysis/diagnostics/flat_frame_statistics.csv`" in text
    assert "Alignment status counts: aligned: 1, failed: 1, reference: 1" in text
    assert "Channel alignment status counts: aligned: 1, failed: 1, reference: 1" in text


def test_generate_object_report_errors_for_missing_object(tmp_path):
    with pytest.raises(generate_object_report.ObjectReportError, match="Object directory does not exist"):
        generate_object_report.generate_object_report("M83", data_root=tmp_path / "data")
