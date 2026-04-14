import pyabf

from ephys_analysis.core.abf_io import get_sweep_data, get_sampling_rate
from ephys_analysis.core.signal import windowed_mean
from ephys_analysis.core.types import RMPResult


def analyze_rmp(abf: pyabf.ABF) -> RMPResult:
    """Analyze RMP protocol: mean voltage in 200ms window starting at t=0."""
    data = get_sweep_data(abf, sweep=0, channel=0)
    rate = get_sampling_rate(abf)
    rmp_mv = windowed_mean(data, 0.0, 0.2, rate)
    return RMPResult(rmp_mv=rmp_mv)
