from typing import Callable

import pandas as pd
from pathlib import Path

from ephys_analysis.core.types import SampleResult, QCStatus


def _sort_by_sample(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values("Sample #").reset_index(drop=True)


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
    row["Slope"] = s.ri_ih.input_resistance_mohm / 1000.0
    row["Ri"] = s.ri_ih.input_resistance_mohm
    return row


def _current_threshold_row(s: SampleResult) -> dict | None:
    if not s.ap_fine:
        return None
    row = s.to_common_dict()
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
    row["First Sweep"] = s.one_s_ap.first_sweep
    row["First FF (Hz)"] = s.one_s_ap.first_ff_hz
    row["Max FF (Hz)"] = s.one_s_ap.max_ff_hz
    row["Ithresh (pA)"] = s.one_s_ap.ithresh_pa
    row["Ithresh FF (Hz)"] = s.one_s_ap.ithresh_ff_hz
    row["Rheobase SU FF (Hz)"] = s.one_s_ap.rheobase_su_ff_hz
    for sw in s.one_s_ap.sweeps:
        row[f"FF {sw.current_pa:.0f}pA"] = sw.firing_freq_hz
    for sw in s.one_s_ap.sweeps:
        if sw.rejected:
            mean_isi = None
        elif sw.isi_ms:
            mean_isi = sum(sw.isi_ms) / len(sw.isi_ms)
        else:
            mean_isi = 0.0
        row[f"ISI {sw.current_pa:.0f}pA"] = mean_isi
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
    row["Ri Slope"] = (s.ri_ih.input_resistance_mohm / 1000.0) if s.ri_ih else None
    row["Ri"] = s.ri_ih.input_resistance_mohm if s.ri_ih else None
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
            row[f"FF {sw.current_pa:.0f}pA"] = sw.firing_freq_hz
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
    """USER if a human rejected via the QC dialog; AUTO if the automatic
    RMP > VThresh gate failed the cell."""
    if s.qc_status == QCStatus.USER_REJECTED_VTHRESH:
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


def export_passed(results: list[SampleResult], output_dir: Path) -> Path | None:
    """Export PASSED results to PASSED/results.xlsx, one tab per protocol
    plus a Fully Compiled master tab. Only QCStatus.PASSED samples are
    included — per customer Q2: 'separate metrics for PASSED and REJECTED,
    not intermingled'.
    """
    passed = [r for r in results if r.qc_status == QCStatus.PASSED]
    if not passed:
        return None

    output_dir = Path(output_dir) / "PASSED"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "results.xlsx"

    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        for sheet_name, builder in _COMPOSITE_TABS:
            _write_tab(writer, passed, sheet_name, builder)

    return path


def export_rejected(results: list[SampleResult], output_dir: Path) -> Path | None:
    """Export every rejected sample to a single REJECTED/results.xlsx with the
    same tab structure as PASSED. Each row carries a FLAG column ('USER' for
    samples a human rejected via the QC dialog, 'AUTO' for samples the
    automatic RMP > VThresh gate failed) and a File Path column so reviewers
    can find the source ABF when re-classifying an edge case.
    """
    rejected = [
        r for r in results
        if r.qc_status in (QCStatus.USER_REJECTED_VTHRESH, QCStatus.RMP_GT_VTHRESH)
    ]
    if not rejected:
        return None

    output_dir = Path(output_dir) / "REJECTED"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "results.xlsx"

    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        for sheet_name, builder in _COMPOSITE_TABS:
            _write_tab(writer, rejected, sheet_name, _rejected_row(builder))

    return path


def export_hyperfiring_sweeps(results: list[SampleResult], output_dir: Path) -> Path | None:
    """Export 1s AP sweeps with > 50 spikes (spec's hyper-firing rejection).

    One row per rejected sweep. Users review these to decide whether they are
    genuinely hyper-firing cells (keep) or analysis artefacts (discard).
    """
    rows = []
    for s in results:
        if not s.one_s_ap:
            continue
        for sweep_idx, sw in enumerate(s.one_s_ap.sweeps):
            if not sw.rejected:
                continue
            row = s.to_common_dict()
            row["Sweep #"] = sweep_idx + 1
            row["Current (pA)"] = sw.current_pa
            row["Raw Spike Count"] = sw.raw_spike_count
            rows.append(row)

    if not rows:
        return None

    output_dir = Path(output_dir) / "1s AP Rejected Sweeps"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "results.xlsx"
    _sort_by_sample(pd.DataFrame(rows)).to_excel(str(path), index=False)
    return path


def export_ri_ih_contaminated_sweeps(
    results: list[SampleResult], output_dir: Path
) -> Path | None:
    """Export Ri/Ih sweeps with APs in their baseline or steady-state windows.

    Per protocol docx: such sweeps are excluded from the Ri regression and Sag
    calculations. This file preserves them for user review.
    """
    rows = []
    for s in results:
        if not s.ri_ih or not s.ri_ih.contaminated_sweeps:
            continue
        for c in s.ri_ih.contaminated_sweeps:
            row = s.to_common_dict()
            row["Sweep #"] = c.sweep_num
            row["Current (pA)"] = c.current_pa
            row["AP in Baseline"] = c.ap_in_baseline
            row["AP in Steady State"] = c.ap_in_steady_state
            rows.append(row)

    if not rows:
        return None

    output_dir = Path(output_dir) / "Ri-Ih Contaminated Sweeps"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "results.xlsx"
    _sort_by_sample(pd.DataFrame(rows)).to_excel(str(path), index=False)
    return path


def export_trimming_analysis(results: list[SampleResult], output_dir: Path) -> Path:
    """Export QC trimming analysis summary."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "trimming_analysis.xlsx"

    rows = []
    for s in results:
        row = s.to_common_dict()
        row["Starting RMP (mV)"] = s.rmp.rmp_mv if s.rmp else None
        row["VThresh (mV)"] = s.ap_fine.voltage_threshold_mv if s.ap_fine else None
        row["QC Status"] = s.qc_status.value
        rows.append(row)

    df = _sort_by_sample(pd.DataFrame(rows)) if rows else pd.DataFrame()
    df.to_excel(str(path), index=False)
    return path
