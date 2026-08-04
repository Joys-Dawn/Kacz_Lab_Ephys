import numpy as np
import pyabf

from ephys_analysis.core.abf_io import get_sweep_data, get_sampling_rate
from ephys_analysis.core.signal import windowed_mean
from ephys_analysis.core.types import RMPResult

RMP_WINDOW_SEC = 0.2


def analyze_rmp(abf: pyabf.ABF) -> RMPResult:
    """Average 200 ms windows from the start, middle, and end of the signal."""
    data = get_sweep_data(abf, sweep=0, channel=0)
    rate = get_sampling_rate(abf)
    duration_sec = len(data) / rate
    if duration_sec < RMP_WINDOW_SEC:
        raise ValueError(
            f"RMP sweep is {duration_sec:.3f} s; at least "
            f"{RMP_WINDOW_SEC:.3f} s is required"
        )

    middle_start = (duration_sec - RMP_WINDOW_SEC) / 2.0
    final_start = duration_sec - RMP_WINDOW_SEC
    window_means = [
        windowed_mean(data, 0.0, RMP_WINDOW_SEC, rate),
        windowed_mean(
            data, middle_start, middle_start + RMP_WINDOW_SEC, rate
        ),
        windowed_mean(data, final_start, duration_sec, rate),
    ]
    rmp_mv = float(np.mean(window_means))
    return RMPResult(rmp_mv=rmp_mv)
