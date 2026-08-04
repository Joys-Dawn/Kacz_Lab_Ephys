import numpy as np
import pyabf

from ephys_analysis.core.abf_io import get_sampling_rate, get_sweep_data
from ephys_analysis.core.signal import time_to_index
from ephys_analysis.core.types import BaselineFlag
from ephys_analysis.protocols import PROTO_AHP_5, PROTO_AHP_25


BASELINE_DURATION_SEC = 0.2
DEFAULT_TARGET_MV = -67.0
AHP_TARGET_MV = -60.0
TARGET_TOLERANCE_MV = 10.0
SUCCESSIVE_CHANGE_MV = 4.0
SUCCESSIVE_PAIR_COUNT = 3
_EXCLUDED_PROTOCOL_MARKERS = ("epsc", "membrane test")


def analyze_baseline_qc(
    abf: pyabf.ABF,
    protocol: str,
    file_path: str,
) -> BaselineFlag | None:
    """Return a flag when an applicable voltage file violates baseline QC.

    Applicability is data-driven: the recorded response must be in mV and
    each sweep must contain the requested 200 ms baseline. EPSC and membrane
    test protocols are excluded explicitly per the customer clarification.
    """
    units = (getattr(abf, "sweepUnitsY", "") or "").strip().casefold()
    protocol_text = protocol.casefold()
    if units != "mv" or any(
        marker in protocol_text for marker in _EXCLUDED_PROTOCOL_MARKERS
    ):
        return None

    rate = get_sampling_rate(abf)
    baseline_samples = time_to_index(BASELINE_DURATION_SEC, rate)
    if baseline_samples <= 0 or abf.sweepCount <= 0:
        return None

    baseline_means = []
    for sweep_idx in range(abf.sweepCount):
        response = get_sweep_data(abf, sweep_idx, channel=0)
        if len(response) < baseline_samples:
            return None
        baseline_means.append(float(np.mean(response[:baseline_samples])))

    target_mv = (
        AHP_TARGET_MV
        if protocol in (PROTO_AHP_5, PROTO_AHP_25)
        else DEFAULT_TARGET_MV
    )
    out_of_range_sweeps = [
        sweep_idx + 1
        for sweep_idx, baseline_mv in enumerate(baseline_means)
        if abs(baseline_mv - target_mv) > TARGET_TOLERANCE_MV
    ]
    changed_sweep_pairs = [
        (sweep_idx + 1, sweep_idx + 2)
        for sweep_idx, (current, following) in enumerate(
            zip(baseline_means, baseline_means[1:])
        )
        if abs(following - current) >= SUCCESSIVE_CHANGE_MV
    ]

    if (
        not out_of_range_sweeps
        and len(changed_sweep_pairs) < SUCCESSIVE_PAIR_COUNT
    ):
        return None

    return BaselineFlag(
        protocol=protocol,
        file_path=file_path,
        target_mv=target_mv,
        baseline_means_mv=baseline_means,
        out_of_range_sweeps=out_of_range_sweeps,
        changed_sweep_pairs=changed_sweep_pairs,
    )
