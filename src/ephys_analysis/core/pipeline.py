"""Analysis pipeline — pure business logic, no GUI dependencies.

Processes samples in spec order: RMP → AP fine → QC gate → Ri/Ih → Ramp → 1s AP → AHPs.
The QC review step is handled via a callback so the GUI can prompt the user.
"""
import logging
from typing import Callable

from ephys_analysis.core.abf_io import load_abf
from ephys_analysis.core.qc import apply_qc_gate
from ephys_analysis.core.types import SampleResult, QCStatus, APFineResult, AnalysisCancelled
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

# Callback type: receives (sample_id, ap_path, ap_result) → True=accept, False=reject
QCReviewer = Callable[[str, str, APFineResult], bool]


def analyze_sample(  # noqa: C901
    info: SampleInfo,
    nominal_data: dict[str, dict[str, str]],
    qc_reviewer: QCReviewer | None = None,
) -> SampleResult:
    """Run the full analysis pipeline on a single sample.

    Args:
        info: Sample metadata and protocol file paths.
        nominal_data: {sample_id: {var_name: var_value}} from user-loaded Excel.
        qc_reviewer: Optional callback for QC visual review. If None, auto-accepts.

    Returns:
        Populated SampleResult with all protocol results and QC status.
    """
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
    ap_path = None
    if PROTO_AP_FINE in protocols:
        ap_path = protocols[PROTO_AP_FINE]
        abf = load_abf(ap_path)
        result.ap_fine = analyze_ap_fine(abf)
    elif PROTO_AP_COARSE in protocols:
        ap_path = protocols[PROTO_AP_COARSE]
        abf = load_abf(ap_path)
        result.ap_fine = analyze_ap_coarse(abf)

    # 3. QC gate
    if result.rmp and result.ap_fine:
        qc_status = apply_qc_gate(result.rmp.rmp_mv, result.ap_fine.voltage_threshold_mv)

        if qc_status == QCStatus.PASSED:
            if qc_reviewer:
                accepted = qc_reviewer(info.sample_id, str(ap_path), result.ap_fine)
            else:
                accepted = True

            if accepted:
                result.qc_status = QCStatus.PASSED
            else:
                result.qc_status = QCStatus.USER_REJECTED_VTHRESH
                result.file_path = str(ap_path) if ap_path else ""
                result.reject_sweep_num = result.ap_fine.sweep_num
        else:
            result.qc_status = QCStatus.RMP_GT_VTHRESH
            result.file_path = str(ap_path) if ap_path else ""
    elif not result.ap_fine:
        result.qc_status = QCStatus.RMP_GT_VTHRESH

    # 4. If passed, continue with remaining protocols
    if result.qc_status == QCStatus.PASSED:
        if PROTO_RI_IH in protocols:
            abf = load_abf(protocols[PROTO_RI_IH])
            result.ri_ih = analyze_ri_ih(abf)

        if PROTO_RAMP in protocols:
            abf = load_abf(protocols[PROTO_RAMP])
            result.ramp = analyze_ramp(abf)

        if PROTO_1S_AP in protocols:
            abf = load_abf(protocols[PROTO_1S_AP])
            ithresh = result.ap_fine.current_threshold_pa if result.ap_fine else 0.0
            rheobase = result.ramp.rheobase_pa if result.ramp else 0.0
            result.one_s_ap = analyze_one_s_ap(abf, ithresh, rheobase)

        if PROTO_AHP_5 in protocols:
            abf = load_abf(protocols[PROTO_AHP_5])
            result.ahp_5 = analyze_ahp(abf, AHP_5)

        if PROTO_AHP_25 in protocols:
            abf = load_abf(protocols[PROTO_AHP_25])
            result.ahp_25 = analyze_ahp(abf, AHP_25)

        if PROTO_AHP_50 in protocols:
            abf = load_abf(protocols[PROTO_AHP_50])
            result.ahp_50 = analyze_ahp(abf, AHP_50)

    return result


def analyze_all(
    samples: dict[tuple[str, str], SampleInfo],
    nominal_data: dict[str, dict[str, str]],
    qc_reviewer: QCReviewer | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[SampleResult]:
    """Run analysis on all samples with per-sample error handling.

    Args:
        samples: {(animal_id, sample_id): SampleInfo} from scan result.
        nominal_data: Nominal variables dict.
        qc_reviewer: Optional QC review callback.
        progress_callback: Optional (index, message) callback for progress.
        cancel_check: Optional callable returning True if analysis should stop.

    Returns:
        List of SampleResult (one per sample, even on error).
    """
    results = []
    items = list(samples.items())

    for idx, ((animal_id, sample_id), info) in enumerate(items):
        if cancel_check and cancel_check():
            break

        if progress_callback:
            progress_callback(idx, f"Analyzing sample {sample_id}...")

        try:
            result = analyze_sample(info, nominal_data, qc_reviewer)
        except AnalysisCancelled:
            raise
        except Exception as e:
            logger.error("Analysis failed for sample %s: %s", sample_id, e, exc_info=True)
            result = SampleResult(
                sample_id=sample_id,
                animal_id=animal_id,
                collection_date=info.collection_date,
                experimenter=info.experimenter,
                qc_status=QCStatus.RMP_GT_VTHRESH,
            )
        results.append(result)

    return results
