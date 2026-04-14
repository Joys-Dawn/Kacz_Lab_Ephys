import pyabf

from ephys_analysis.core.abf_io import (
    get_sweep_data,
    get_sampling_rate,
    get_step_onset_sec,
    get_step_duration_sec,
)
from ephys_analysis.core.spike import find_voltage_threshold
from ephys_analysis.core.types import RampResult, DVDT_CRITERION_MV_MS


def analyze_ramp(abf: pyabf.ABF) -> RampResult | None:
    """Analyze ramp protocol for rheobase.

    Per spec: Rheobase = positive peak − negative peak of the stimulus
    signal (pA) within a window from t=0 s to the first AP threshold.
    """
    rate = get_sampling_rate(abf)
    response = get_sweep_data(abf, sweep=0, channel=0)

    ramp_onset = get_step_onset_sec(abf, epoch_index=0)
    ramp_duration = get_step_duration_sec(abf, epoch_index=0)

    if ramp_duration <= 0:
        return None

    # Find first spike — returns threshold time directly
    ramp_end = ramp_onset + ramp_duration
    result = find_voltage_threshold(
        response, rate, ramp_onset, ramp_end, dvdt_criterion=DVDT_CRITERION_MV_MS
    )
    if result is None:
        return None

    _, spike_time, _, _ = result

    # Rheobase: peak-to-peak of the measured stimulus signal from t=0
    # to first AP threshold crossing.
    stimulus = get_sweep_data(abf, sweep=0, channel=1)
    spike_idx = int(round(spike_time * rate))
    stim_window = stimulus[0:spike_idx]
    rheobase = float(stim_window.max() - stim_window.min())

    return RampResult(rheobase_pa=rheobase)
