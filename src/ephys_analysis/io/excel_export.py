from datetime import datetime
from typing import Callable

import pandas as pd
from pathlib import Path

from ephys_analysis.core.types import SampleResult, QCStatus


_REJECTED_STATUSES = {
    QCStatus.USER_REJECTED_VTHRESH,
    QCStatus.USER_REJECTED_1S_AP,
    QCStatus.RMP_GT_VTHRESH,
    QCStatus.ANALYSIS_FAILED,
}


def create_export_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _output_path(
    output_dir: Path, label: str, timestamp: str | None
) -> Path:
    stamp = timestamp or create_export_timestamp()
    name = f"{label}_{stamp}"
    folder = Path(output_dir) / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{name}.xlsx"


def _sort_by_sample(df: pd.DataFrame) -> pd.DataFrame:
    sample_text = df["Sample #"].astype(str)
    sample_number = pd.to_numeric(sample_text, errors="coerce")
    return (
        df.assign(_sample_number=sample_number, _sample_text=sample_text)
        .sort_values(
            ["_sample_number", "_sample_text"],
            na_position="last",
            kind="stable",
        )
        .drop(columns=["_sample_number", "_sample_text"])
        .reset_index(drop=True)
    )


def _write_tab(
    writer: pd.ExcelWriter,
    samples: list[SampleResult],
    sheet_name: str,
    row_builder: Callable[[SampleResult], dict | None],
):
    """Write a single tab to an Excel writer if any rows are produced."""
    rows = []
    for s in samples:
        row = row_builder(s)
        if row is not None:
            rows.append(row)
    if rows:
        _sort_by_sample(pd.DataFrame(rows)).to_excel(
            writer, sheet_name=sheet_name, index=False
        )
    elif sheet_name == "Fully Compiled":
        columns = row_builder(SampleResult(sample_id="", animal_id=""))
        pd.DataFrame(columns=list(columns)).to_excel(
            writer, sheet_name=sheet_name, index=False
        )


# ---- Shared row builders ---------------------------------------------------
# Each builder takes a SampleResult and returns a dict for one row of the
# named tab, or None if the sample has no data for that protocol. Builders
# are pure functions of the sample so they can be reused between the PASSED
# and REJECTED composites (rejected rows get FLAG/File Path spliced in by
# _rejected_row).

def _rmp_row(s: SampleResult) -> dict | None:
    if not s.rmp:
        return None
    row = s.to_common_dict()
    row["Starting RMP (mV)"] = s.rmp.rmp_mv
    return row


def _rheobase_row(s: SampleResult) -> dict | None:
    if not s.ramp:
        return None
    row = s.to_common_dict()
    row["Rheobase (pA)"] = s.ramp.rheobase_pa
    return row


def _sag_row(s: SampleResult) -> dict | None:
    if not s.ri_ih:
        return None
    row = s.to_common_dict()
    row["200 pA Avg"] = s.ri_ih.sag_ratio_200pa
    row["100 pA Avg"] = s.ri_ih.sag_ratio_100pa
    row["Sag Amplitude (mV)"] = s.ri_ih.sag_amp_mv
    return row


def _rin_row(s: SampleResult) -> dict | None:
    if not s.ri_ih:
        return None
    row = s.to_common_dict()
    ri = s.ri_ih.input_resistance_mohm
    row["Slope"] = ri / 1000.0 if ri is not None else None
    row["Ri"] = s.ri_ih.input_resistance_mohm
    return row


def _ap_source(s: SampleResult) -> str:
    """Which AP protocol the metrics came from — "coarse" whenever
    analyze_ap_coarse produced the metrics, either because there was no fine
    recording or because fine returned None and the pipeline fell back."""
    return "coarse" if s.ap_source_is_coarse else "fine"


def _current_threshold_row(s: SampleResult) -> dict | None:
    if not s.ap_fine:
        return None
    row = s.to_common_dict()
    row["AP Source"] = _ap_source(s)
    row["Sweep"] = s.ap_fine.sweep_num
    row["R1S1 Mean"] = s.ap_fine.stim_baseline_pa
    row["R2S1 Mean"] = s.ap_fine.stim_step_pa
    row["Ithresh"] = s.ap_fine.current_threshold_pa
    row["Spike #"] = s.ap_fine.spike_num
    return row


def _ap_properties_row(s: SampleResult) -> dict | None:
    if not s.ap_fine:
        return None
    row = s.to_common_dict()
    row["AP Source"] = _ap_source(s)
    row["Sweep"] = s.ap_fine.sweep_num
    row["Half-Width (ms)"] = s.ap_fine.half_width_ms
    row["Max Rise (mV/ms)"] = s.ap_fine.max_rise_slope_mv_ms
    row["Max Decay (mV/ms)"] = s.ap_fine.max_decay_slope_mv_ms
    row["Peak Amplitude (mV)"] = s.ap_fine.peak_amp_mv
    row["Threshold (mV)"] = s.ap_fine.voltage_threshold_mv
    return row


def _firing_row(s: SampleResult) -> dict | None:
    if not s.one_s_ap or not s.one_s_ap.sweeps:
        return None
    row = s.to_common_dict()
    row["First Sweep"] = (
        s.one_s_ap.first_sweep + 1 if s.one_s_ap.first_sweep >= 0 else None
    )
    row["First FF (Hz)"] = s.one_s_ap.first_ff_hz
    row["Max FF (Hz)"] = s.one_s_ap.max_ff_hz
    row["Ithresh (pA)"] = s.one_s_ap.ithresh_pa
    row["Ithresh FF (Hz)"] = s.one_s_ap.ithresh_ff_hz
    row["Rheobase SU FF (Hz)"] = s.one_s_ap.rheobase_su_ff_hz
    for sw in s.one_s_ap.sweeps:
        row[f"FF {sw.current_pa:.0f}pA"] = None if sw.excluded else sw.firing_freq_hz
    for sw in s.one_s_ap.sweeps:
        valid = not sw.excluded and sw.spike_count >= 3 and len(sw.isi_ms) >= 2
        row[f"First ISI {sw.current_pa:.0f}pA (ms)"] = sw.isi_ms[0] if valid else None
        row[f"Last ISI {sw.current_pa:.0f}pA (ms)"] = sw.isi_ms[-1] if valid else None
        row[f"ISI Ratio {sw.current_pa:.0f}pA (first/last)"] = (
            sw.isi_ms[0] / sw.isi_ms[-1] if valid else None
        )
    return row


def _ahp_row_builder(attr: str) -> Callable[[SampleResult], dict | None]:
    def _build(s: SampleResult) -> dict | None:
        ahp_result = getattr(s, attr)
        if not ahp_result:
            return None
        row = s.to_common_dict()
        row["Peak (mV)"] = ahp_result.peak_mv
        row["200ms (mV)"] = ahp_result.ms200_mv
        row["1000ms (mV)"] = ahp_result.ms1000_mv
        return row
    return _build


def _fully_compiled_row(s: SampleResult) -> dict:
    """Master row per sample — every metric in column order matching the
    customer's compiled spreadsheet (identity prefix, RMP, Rheobase, Ri/Sag,
    Current Threshold, AHP blocks, per-sweep FF, summary FF, AP properties).
    """
    one_s = s.one_s_ap if (s.one_s_ap and s.one_s_ap.sweeps) else None
    row = s.to_common_dict()
    row["Starting RMP (mV)"] = s.rmp.rmp_mv if s.rmp else None
    row["Rheobase pA"] = s.ramp.rheobase_pa if s.ramp else None
    row["Rheobase SU FF"] = one_s.rheobase_su_ff_hz if one_s else None
    row["200 pA Avg"] = s.ri_ih.sag_ratio_200pa if s.ri_ih else None
    row["100 pA Avg"] = s.ri_ih.sag_ratio_100pa if s.ri_ih else None
    ri = s.ri_ih.input_resistance_mohm if s.ri_ih else None
    row["Ri Slope"] = ri / 1000.0 if ri is not None else None
    row["Ri"] = s.ri_ih.input_resistance_mohm if s.ri_ih else None
    row["AP Source"] = _ap_source(s) if s.ap_fine else None
    row["Sweep"] = s.ap_fine.sweep_num if s.ap_fine else None
    row["R1S1 Mean"] = s.ap_fine.stim_baseline_pa if s.ap_fine else None
    row["R2S1 Mean"] = s.ap_fine.stim_step_pa if s.ap_fine else None
    row["Ithresh"] = s.ap_fine.current_threshold_pa if s.ap_fine else None
    row["Spike #"] = s.ap_fine.spike_num if s.ap_fine else None
    for attr, prefix in (("ahp_5", "5 spike"), ("ahp_25", "25 spike"), ("ahp_50", "50 spike")):
        ahp = getattr(s, attr)
        row[f"{prefix} peakAHP"] = ahp.peak_mv if ahp else None
        row[f"{prefix} 200ms AHP"] = ahp.ms200_mv if ahp else None
        row[f"{prefix} sAHP"] = ahp.ms1000_mv if ahp else None
    if one_s:
        for sw in one_s.sweeps:
            row[f"FF {sw.current_pa:.0f}pA"] = None if sw.excluded else sw.firing_freq_hz
    row["First FF"] = one_s.first_ff_hz if one_s else None
    row["Max FF"] = one_s.max_ff_hz if one_s else None
    row["Half-Width (ms)"] = s.ap_fine.half_width_ms if s.ap_fine else None
    row["Max Rise (mV/ms)"] = s.ap_fine.max_rise_slope_mv_ms if s.ap_fine else None
    row["Max Decay (mV/ms)"] = s.ap_fine.max_decay_slope_mv_ms if s.ap_fine else None
    row["Peak Amplitude (mV)"] = s.ap_fine.peak_amp_mv if s.ap_fine else None
    row["Threshold (mV)"] = s.ap_fine.voltage_threshold_mv if s.ap_fine else None
    return row


# ---- Reject-row wrapper ---------------------------------------------------

def _flag_for(s: SampleResult) -> str:
    """Describe why a result was not included with passed samples."""
    if s.qc_status == QCStatus.ANALYSIS_FAILED:
        return "FAILED TO ANALYZE"
    if s.qc_status in (
        QCStatus.USER_REJECTED_VTHRESH,
        QCStatus.USER_REJECTED_1S_AP,
    ):
        return "USER"
    return "AUTO"  # QCStatus.RMP_GT_VTHRESH


def _rejected_row(builder: Callable[[SampleResult], dict | None]):
    """Wrap a shared row builder so the rejected composite gets FLAG and
    File Path columns spliced in right after the identity prefix.
    """
    def _build(s: SampleResult) -> dict | None:
        base = builder(s)
        if base is None:
            return None
        common = s.to_common_dict()
        metrics = {k: v for k, v in base.items() if k not in common}
        return {
            **common,
            "FLAG": _flag_for(s),
            "File Path": s.file_path,
            "Analysis Error": s.analysis_error,
            **metrics,
        }
    return _build


def _merged_row(builder: Callable[[SampleResult], dict | None]):
    """Add the reject metadata columns used when PASSED and REJECTED merge."""
    def _build(s: SampleResult) -> dict | None:
        base = builder(s)
        if base is None:
            return None
        common = s.to_common_dict()
        metrics = {k: v for k, v in base.items() if k not in common}
        rejected = s.qc_status in _REJECTED_STATUSES
        return {
            **common,
            "FLAG": _flag_for(s) if rejected else "",
            "File Path": s.file_path if rejected else "",
            "Analysis Error": s.analysis_error,
            **metrics,
        }
    return _build


# ---- Composites -----------------------------------------------------------

# Tab name → row builder. Used by both PASSED and REJECTED composites so the
# two workbooks have identical tab structure (the customer toggles edge-case
# cells between them, so the column layouts must line up).
_COMPOSITE_TABS: list[tuple[str, Callable[[SampleResult], dict | None]]] = [
    ("Fully Compiled", _fully_compiled_row),
    ("RMP", _rmp_row),
    ("Rheobase", _rheobase_row),
    ("Sag", _sag_row),
    ("Rin", _rin_row),
    ("Current Threshold", _current_threshold_row),
    ("5 AHP", _ahp_row_builder("ahp_5")),
    ("25 AHP", _ahp_row_builder("ahp_25")),
    ("50 AHP", _ahp_row_builder("ahp_50")),
    ("1s Firing", _firing_row),
    ("Compiled AP Properties", _ap_properties_row),
]


def export_passed(
    results: list[SampleResult],
    output_dir: Path,
    timestamp: str | None = None,
) -> Path | None:
    """Export PASSED samples to a timestamped composite workbook."""
    passed = [r for r in results if r.qc_status == QCStatus.PASSED]
    if not results:
        return None

    path = _output_path(output_dir, "ALL PASSED", timestamp)

    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        for sheet_name, builder in _COMPOSITE_TABS:
            _write_tab(writer, passed, sheet_name, builder)

    return path


def export_rejected(
    results: list[SampleResult],
    output_dir: Path,
    timestamp: str | None = None,
) -> Path | None:
    """Export every rejected sample to a timestamped composite workbook."""
    rejected = [
        r for r in results
        if r.qc_status in _REJECTED_STATUSES
    ]
    if not results:
        return None

    path = _output_path(output_dir, "ALL REJECTED", timestamp)

    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        for sheet_name, builder in _COMPOSITE_TABS:
            _write_tab(writer, rejected, sheet_name, _rejected_row(builder))

    return path


def export_fully_compiled(
    results: list[SampleResult],
    output_dir: Path,
    timestamp: str | None = None,
) -> Path | None:
    """Export the sorted union of PASSED and REJECTED composite workbooks."""
    if not results:
        return None

    path = _output_path(output_dir, "ALL CELLS (COMPILED)", timestamp)
    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        for sheet_name, builder in _COMPOSITE_TABS:
            _write_tab(writer, results, sheet_name, _merged_row(builder))
    return path


def export_cell_types(
    results: list[SampleResult],
    output_dir: Path,
    timestamp: str | None = None,
) -> list[Path]:
    paths = []
    for cell_type, label in (
        ("Regular", "REGULAR SPIKING PASSED"),
        ("Burst", "BURST SPIKING PASSED"),
        ("Interneuron", "INTERNEURONS PASSED"),
    ):
        samples = [
            result for result in results
            if result.qc_status == QCStatus.PASSED and result.cell_type == cell_type
        ]
        path = _output_path(output_dir, label, timestamp)
        with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
            for sheet_name, builder in _COMPOSITE_TABS:
                _write_tab(writer, samples, sheet_name, builder)
        paths.append(path)
    return paths


def export_ri_ih_contaminated_sweeps(
    results: list[SampleResult],
    output_dir: Path,
    timestamp: str | None = None,
) -> Path | None:
    """Export Ri/Ih sweeps with APs in their baseline or steady-state windows.

    Per protocol docx: such sweeps are excluded from the Ri regression and Sag
    calculations. This file preserves them for user review.
    """
    rows = []
    for s in results:
        contaminated = (
            s.ri_ih.contaminated_sweeps if s.ri_ih else s.ri_ih_contaminated_sweeps
        )
        for c in contaminated:
            row = s.to_common_dict()
            row["Sweep #"] = c.sweep_num
            row["Current (pA)"] = c.current_pa
            row["AP in Baseline"] = c.ap_in_baseline
            row["AP in Steady State"] = c.ap_in_steady_state
            rows.append(row)

    if not rows:
        return None

    path = _output_path(output_dir, "Ri-Ih Contaminated Sweeps", timestamp)
    _sort_by_sample(pd.DataFrame(rows)).to_excel(str(path), index=False)
    return path


def export_trimming_analysis(
    results: list[SampleResult],
    output_dir: Path,
    timestamp: str | None = None,
) -> Path:
    """Export QC trimming analysis summary."""
    path = _output_path(output_dir, "Trimming Analysis", timestamp)

    rows = []
    for s in results:
        row = s.to_common_dict()
        row["Starting RMP (mV)"] = s.rmp.rmp_mv if s.rmp else None
        row["VThresh (mV)"] = s.ap_fine.voltage_threshold_mv if s.ap_fine else None
        row["QC Status"] = s.qc_status.value
        row["Analysis Error"] = s.analysis_error
        rows.append(row)

    df = _sort_by_sample(pd.DataFrame(rows)) if rows else pd.DataFrame()
    df.to_excel(str(path), index=False)
    return path
