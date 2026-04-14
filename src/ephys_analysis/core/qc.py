from ephys_analysis.core.types import QCStatus


def apply_qc_gate(rmp_mv: float, voltage_threshold_mv: float) -> QCStatus:
    """Apply RMP < VThresh quality control gate.

    Returns PASSED if voltage threshold is strictly greater than RMP,
    otherwise RMP_GT_VTHRESH.
    """
    if voltage_threshold_mv > rmp_mv:
        return QCStatus.PASSED
    return QCStatus.RMP_GT_VTHRESH
