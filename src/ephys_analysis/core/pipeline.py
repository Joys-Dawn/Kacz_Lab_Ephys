"""Analysis pipeline — pure business logic, no GUI dependencies.

Detailed analysis reviews baseline flags before processing samples, then runs
RMP → AP fine → QC review/gate → Ri/Ih → Ramp → 1s AP → flagged-file
review → AHPs. Quick Analysis runs selected protocols with every QC path
disabled. Review steps use callbacks so the business logic remains independent
of the GUI.
"""
import logging
from dataclasses import replace
from pathlib import Path
from typing import Callable

from ephys_analysis.core.abf_io import load_abf
from ephys_analysis.core.baseline_qc import analyze_baseline_qc
from ephys_analysis.core.qc import apply_qc_gate
from ephys_analysis.core.types import (
    SampleResult, QCStatus, APFineResult, AnalysisCancelled, QCReview,
    OneSAPResult, OneSAPReview, BaselineFlag, BaselineReview,
    RiIhContaminatedSweep,
)
from ephys_analysis.io.scanner import SampleInfo
from ephys_analysis.protocols import (
    PROTO_RMP, PROTO_AP_FINE, PROTO_AP_COARSE, PROTO_RI_IH,
    PROTO_RAMP, PROTO_1S_AP, PROTO_AHP_5, PROTO_AHP_25, PROTO_AHP_50,
)
from ephys_analysis.protocols.rmp import analyze_rmp
from ephys_analysis.protocols.ap import analyze_ap_fine, analyze_ap_coarse
from ephys_analysis.protocols.ri_ih import analyze_ri_ih
from ephys_analysis.protocols.ramp import analyze_ramp
from ephys_analysis.protocols.one_s_ap import analyze_one_s_ap
from ephys_analysis.protocols.ahp import analyze_ahp, AHP_5, AHP_25, AHP_50

logger = logging.getLogger(__name__)

# Callback type: receives (sample_id, ap_path, ap_result, rmp_mv) → QCReview.
# Tests can pass simpler callables that return a bool; the pipeline normalizes
# both forms via _normalize_review below.
QCReviewer = Callable[[str, str, APFineResult, float], "QCReview | bool"]
OneSAPReviewer = Callable[
    [str, dict[str, str], OneSAPResult], "OneSAPReview | bool"
]
BaselineReviewer = Callable[
    [list[tuple[str, BaselineFlag]]], "BaselineReview | dict[str, bool]"
]
RiIhReviewer = Callable[[str, str, list[RiIhContaminatedSweep]], bool]


def _normalize_review(value) -> QCReview:
    if isinstance(value, QCReview):
        return value
    return QCReview(accepted=bool(value))


def _normalize_one_s_ap_review(value) -> OneSAPReview:
    if isinstance(value, OneSAPReview):
        return value
    return OneSAPReview(accepted=bool(value))


def _normalize_baseline_review(value) -> BaselineReview:
    if isinstance(value, BaselineReview):
        return value
    return BaselineReview(decisions=dict(value))


def _set_file_note(file_notes: dict[str, str], path: str, note: str) -> None:
    cleaned = note.strip()
    if cleaned:
        file_notes[path] = cleaned
    else:
        file_notes.pop(path, None)


def format_sample_notes(
    info: SampleInfo, file_notes: dict[str, str]
) -> str:
    entries = []
    for path in info.protocols.values():
        note = file_notes.get(str(path), "").strip()
        if note:
            entries.append(f"{Path(path).name}: {note}")
    return "\n".join(entries)


def exclude_protocol_paths(
    samples: dict[tuple[str, str], SampleInfo],
    rejected_paths: set[str],
) -> dict[tuple[str, str], SampleInfo]:
    """Copy a sample map without user-rejected protocol recordings."""
    if not rejected_paths:
        return samples
    return {
        key: replace(
            info,
            protocols={
                protocol: path
                for protocol, path in info.protocols.items()
                if str(path) not in rejected_paths
            },
        )
        for key, info in samples.items()
    }


def apply_qc_review(result: SampleResult, ap_path: str, review: QCReview) -> None:
    """Apply a decision to the original automatic threshold, including on undo."""
    initial_status = apply_qc_gate(result.rmp.rmp_mv, result.ap_fine.voltage_threshold_mv)
    if review.override_vthresh_mv is not None:
        result.ap_fine.voltage_threshold_mv = review.override_vthresh_mv
    status = apply_qc_gate(result.rmp.rmp_mv, result.ap_fine.voltage_threshold_mv)
    result.file_path = ""
    result.reject_sweep_num = None
    if review.override_auto_reject:
        result.qc_status = QCStatus.PASSED
    elif initial_status != QCStatus.PASSED or status != QCStatus.PASSED:
        result.qc_status = QCStatus.RMP_GT_VTHRESH
        result.file_path = ap_path
    elif review.accepted:
        result.qc_status = QCStatus.PASSED
    else:
        result.qc_status = QCStatus.USER_REJECTED_VTHRESH
        result.file_path = ap_path
        result.reject_sweep_num = result.ap_fine.sweep_num


def analyze_sample(  # noqa: C901
    info: SampleInfo,
    nominal_data: dict[str, dict[str, str]],
    qc_reviewer: QCReviewer | None = None,
    one_s_ap_reviewer: OneSAPReviewer | None = None,
    file_notes: dict[str, str] | None = None,
    skip_qc: bool = False,
    ri_ih_reviewer: RiIhReviewer | None = None,
) -> SampleResult:
    """Run the full analysis pipeline on a single sample.

    Args:
        info: Sample metadata and protocol file paths.
        nominal_data: {sample_id: {var_name: var_value}} from user-loaded Excel.
        qc_reviewer: Optional callback for QC visual review. If None, auto-accepts.
        one_s_ap_reviewer: Optional callback for flagged 1-second AP review.
        file_notes: Notes keyed by source ABF path.
        skip_qc: Bypass automatic and manual QC for Quick Analysis.

    Returns:
        Populated SampleResult with all protocol results and QC status.
    """
    notes_by_path = file_notes if file_notes is not None else {}
    result = SampleResult(
        sample_id=info.sample_id,
        animal_id=info.animal_id,
        collection_date=info.collection_date,
        experimenter=info.experimenter,
        nominal_vars=nominal_data.get(info.sample_id, {}),
    )

    protocols = info.protocols

    # 1. RMP
    if PROTO_RMP in protocols:
        abf = load_abf(protocols[PROTO_RMP])
        result.rmp = analyze_rmp(abf)

    # 2. AP fine (or coarse fallback)
    # Three possibilities: (a) fine file present and has a spike → use fine;
    # (b) fine present but analyzer returns None → try coarse and flag the
    # fallback so reviewers know; (c) fine missing entirely → coarse is the
    # only option and no flag is needed.
    ap_path = None
    if PROTO_AP_FINE in protocols:
        ap_path = protocols[PROTO_AP_FINE]
        abf = load_abf(ap_path)
        result.ap_fine = analyze_ap_fine(abf)
        if result.ap_fine is None and PROTO_AP_COARSE in protocols:
            coarse_path = protocols[PROTO_AP_COARSE]
            coarse_abf = load_abf(coarse_path)
            coarse_result = analyze_ap_coarse(coarse_abf)
            if coarse_result is not None:
                result.ap_fine = coarse_result
                ap_path = coarse_path
                result.ap_source_is_coarse = True
                result.ap_used_coarse_fallback = True
    elif PROTO_AP_COARSE in protocols:
        ap_path = protocols[PROTO_AP_COARSE]
        abf = load_abf(ap_path)
        result.ap_fine = analyze_ap_coarse(abf)
        result.ap_source_is_coarse = True

    # 3. QC gate
    if skip_qc:
        result.qc_status = QCStatus.PASSED
    elif result.rmp and result.ap_fine:
        review = QCReview(accepted=True)
        if qc_reviewer:
            raw = qc_reviewer(
                info.sample_id, str(ap_path), result.ap_fine, result.rmp.rmp_mv,
            )
            review = _normalize_review(raw)
        if review.notes is not None:
            _set_file_note(notes_by_path, str(ap_path), review.notes)
        apply_qc_review(result, str(ap_path), review)
    else:
        result.qc_status = QCStatus.RMP_GT_VTHRESH
        result.file_path = str(ap_path) if ap_path else ""

    # 4. Remaining protocols — run for every sample, not just PASSED ones.
    # The customer's compiled spreadsheet fills these columns for excluded
    # samples too; QC status only gates downstream group statistics, not
    # whether the per-sample number is computed.
    if PROTO_RI_IH in protocols:
        abf = load_abf(protocols[PROTO_RI_IH])

        def review_contamination(sweeps):
            result.ri_ih_contaminated_sweeps = sweeps
            return ri_ih_reviewer(
                info.sample_id, str(protocols[PROTO_RI_IH]), sweeps
            )

        if ri_ih_reviewer and not skip_qc:
            result.ri_ih = analyze_ri_ih(abf, contamination_reviewer=review_contamination)
        else:
            result.ri_ih = analyze_ri_ih(abf)

    if PROTO_RAMP in protocols:
        abf = load_abf(protocols[PROTO_RAMP])
        result.ramp = analyze_ramp(abf)

    if PROTO_1S_AP in protocols:
        abf = load_abf(protocols[PROTO_1S_AP])
        ithresh = result.ap_fine.current_threshold_pa if result.ap_fine else 0.0
        rheobase = result.ramp.rheobase_pa if result.ramp else 0.0
        result.one_s_ap = analyze_one_s_ap(abf, ithresh, rheobase)

        if (
            result.one_s_ap.requires_review
            and one_s_ap_reviewer
            and not skip_qc
        ):
            protocol_paths = {
                protocol: str(path) for protocol, path in protocols.items()
            }
            raw = one_s_ap_reviewer(
                info.sample_id, protocol_paths, result.one_s_ap
            )
            review = _normalize_one_s_ap_review(raw)
            one_s_path = str(protocols[PROTO_1S_AP])
            if review.notes is not None:
                _set_file_note(notes_by_path, one_s_path, review.notes)
            if not review.accepted or (
                result.one_s_ap.sweeps
                and review.excluded_sweeps == set(range(1, len(result.one_s_ap.sweeps) + 1))
            ):
                result.one_s_ap = None
            elif review.excluded_sweeps:
                result.one_s_ap = analyze_one_s_ap(
                    abf, ithresh, rheobase,
                    excluded_sweeps=review.excluded_sweeps,
                )

    if PROTO_AHP_5 in protocols:
        abf = load_abf(protocols[PROTO_AHP_5])
        result.ahp_5 = analyze_ahp(abf, AHP_5)

    if PROTO_AHP_25 in protocols:
        abf = load_abf(protocols[PROTO_AHP_25])
        result.ahp_25 = analyze_ahp(abf, AHP_25)

    if PROTO_AHP_50 in protocols:
        abf = load_abf(protocols[PROTO_AHP_50])
        result.ahp_50 = analyze_ahp(abf, AHP_50)

    result.notes = format_sample_notes(info, notes_by_path)
    return result


def analyze_all(
    samples: dict[tuple[str, str], SampleInfo],
    nominal_data: dict[str, dict[str, str]],
    qc_reviewer: QCReviewer | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    one_s_ap_reviewer: OneSAPReviewer | None = None,
    file_notes: dict[str, str] | None = None,
    baseline_reviewer: BaselineReviewer | None = None,
    skip_qc: bool = False,
    ri_ih_reviewer: RiIhReviewer | None = None,
) -> list[SampleResult]:
    """Run analysis on all samples with per-sample error handling.

    Args:
        samples: {(animal_id, sample_id): SampleInfo} from scan result.
        nominal_data: Nominal variables dict.
        qc_reviewer: Optional QC review callback.
        progress_callback: Optional (index, message) callback for progress.
        cancel_check: Optional callable returning True if analysis should stop.
        one_s_ap_reviewer: Optional flagged 1-second AP review callback.
        file_notes: Notes keyed by source ABF path.
        baseline_reviewer: Optional callback that reviews applicable baseline
            flags and returns an Accept/Reject decision for every flagged file.
        skip_qc: Bypass automatic and manual QC for Quick Analysis.

    Returns:
        List of SampleResult (one per sample, even on error).
    """
    results = []
    items = list(samples.items())

    if not skip_qc and baseline_reviewer:
        baseline_flags = []
        for (_, sample_id), info in items:
            for protocol, path in info.protocols.items():
                try:
                    flag = analyze_baseline_qc(
                        load_abf(path),
                        protocol=protocol,
                        file_path=str(path),
                    )
                except Exception as e:
                    logger.error(
                        "Baseline check failed for %s (%s): %s",
                        sample_id,
                        path,
                        e,
                        exc_info=True,
                    )
                    continue
                if flag is not None:
                    baseline_flags.append((sample_id, flag))
        if baseline_flags:
            review = _normalize_baseline_review(
                baseline_reviewer(baseline_flags)
            )
            flagged_paths = {flag.file_path for _, flag in baseline_flags}
            missing_decisions = flagged_paths - review.decisions.keys()
            if missing_decisions:
                missing = ", ".join(sorted(missing_decisions))
                raise ValueError(
                    f"Baseline review did not decide every flagged file: {missing}"
                )
            rejected_paths = {
                path
                for path in flagged_paths
                if not review.decisions[path]
            }
            if rejected_paths:
                items = list(
                    exclude_protocol_paths(
                        dict(items), rejected_paths
                    ).items()
                )

    # Keep automatic inputs so Back changes QC without repeating protocol reviews.
    qc_history: list[tuple[int, str, str, APFineResult, float]] = []
    notes_by_path = file_notes if file_notes is not None else {}

    def review_qc(sample_id, path, ap, rmp):
        qc_history.append((idx, sample_id, path, replace(ap), rmp))
        cursor = len(qc_history) - 1
        while True:
            sample_index, sid, source, automatic_ap, resting = qc_history[cursor]
            review = _normalize_review(
                qc_reviewer(sid, source, replace(automatic_ap), resting)
            )
            if review.go_back:
                if cursor == 0:
                    raise ValueError("No previous QC review is available")
                cursor -= 1
                continue
            if cursor == len(qc_history) - 1:
                return review
            previous = results[sample_index]
            if previous.qc_status != QCStatus.ANALYSIS_FAILED:
                previous.ap_fine.voltage_threshold_mv = automatic_ap.voltage_threshold_mv
                apply_qc_review(previous, source, review)
            if review.notes is not None:
                _set_file_note(notes_by_path, source, review.notes)
                previous.notes = format_sample_notes(items[sample_index][1], notes_by_path)
            cursor += 1

    for idx, ((animal_id, sample_id), info) in enumerate(items):
        if cancel_check and cancel_check():
            break

        if progress_callback:
            progress_callback(idx, f"Analyzing sample {sample_id}...")

        try:
            result = analyze_sample(
                info,
                nominal_data,
                qc_reviewer=review_qc if qc_reviewer else None,
                one_s_ap_reviewer=one_s_ap_reviewer,
                file_notes=notes_by_path,
                skip_qc=skip_qc,
                ri_ih_reviewer=ri_ih_reviewer,
            )
        except AnalysisCancelled:
            raise
        except Exception as e:
            logger.error("Analysis failed for sample %s: %s", sample_id, e, exc_info=True)
            source_paths = [str(path) for path in info.protocols.values()]
            result = SampleResult(
                sample_id=sample_id,
                animal_id=animal_id,
                collection_date=info.collection_date,
                experimenter=info.experimenter,
                qc_status=QCStatus.ANALYSIS_FAILED,
                analysis_error=str(e),
                file_path=source_paths[0] if len(source_paths) == 1 else "",
                notes=format_sample_notes(info, file_notes or {}),
            )
        results.append(result)

    return results
