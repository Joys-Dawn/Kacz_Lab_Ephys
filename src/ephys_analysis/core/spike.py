import numpy as np
from scipy.signal import find_peaks

from ephys_analysis.core.signal import time_to_index
from ephys_analysis.core.types import DVDT_CRITERION_MV_MS


def find_voltage_threshold(
    response_data: np.ndarray,
    sample_rate: float,
    t_start: float,
    t_end: float,
    dvdt_criterion: float = DVDT_CRITERION_MV_MS,
) -> tuple[float, float, np.ndarray, np.ndarray] | None:
    """Find voltage threshold from dV/dt phase plot.

    Args:
        response_data: Full sweep response signal (mV).
        sample_rate: Sampling rate in Hz.
        t_start: Start of analysis window in seconds.
        t_end: End of analysis window in seconds.
        dvdt_criterion: dV/dt threshold in mV/ms.

    Returns:
        (voltage_threshold_mv, threshold_time_sec, phase_plot_v, phase_plot_dvdt)
        or None if no threshold found.
    """
    i0 = time_to_index(t_start, sample_rate)
    i1 = time_to_index(t_end, sample_rate)
    segment = response_data[i0:i1]

    if len(segment) < 3:
        return None

    dt_ms = 1000.0 / sample_rate  # time step in ms

    # Forward difference: dvdt[i] = (V[i+1] - V[i]) / dt
    # Matches Clampfit's diff() function. Threshold voltage is V[i+1]
    # (the voltage at the END of the interval where dV/dt first exceeds
    # criterion), which is the voltage being transitioned to.
    dvdt = np.diff(segment) / dt_ms
    v = segment[1:]  # voltage at the end of each dV/dt interval

    # Phase plot arrays for display: same forward diff used for threshold
    # detection, so the criterion crossing visually lands on the trace.
    dvdt_plot = dvdt
    v_plot = v

    # Find first point where dV/dt exceeds criterion
    threshold_indices = np.where(dvdt > dvdt_criterion)[0]
    if len(threshold_indices) == 0:
        return None

    idx = threshold_indices[0]
    voltage_threshold_mv = float(v[idx])
    # v[idx] = segment[idx+1]; time at segment[idx+1]
    threshold_time_sec = t_start + (idx + 1) / sample_rate

    return voltage_threshold_mv, threshold_time_sec, v_plot, dvdt_plot


def count_spikes_voltage(
    response_data: np.ndarray,
    sample_rate: float,
    threshold_mv: float = 0.0,
    min_spike_distance_ms: float = 2.0,
    min_prominence_mv: float | None = None,
) -> tuple[int, list[float], list[float]]:
    """Count spikes exceeding a voltage threshold.

    Uses scipy.signal.find_peaks to find local maxima above threshold
    with minimum distance between peaks, optionally filtered by prominence.

    Args:
        response_data: Response signal (mV) for the analysis window.
        sample_rate: Sampling rate in Hz.
        threshold_mv: Voltage threshold for spike detection (mV).
        min_spike_distance_ms: Minimum distance between spikes in ms.
        min_prominence_mv: Minimum peak prominence in mV. Used for the 1s AP
            protocol to reject the small oscillations of depolarization block
            (where V sits above threshold with tiny wiggles). None means no
            prominence filter — use for AP fine single-spike detection where
            there's only one clean AP per window.

    Returns:
        (spike_count, spike_times_sec, isi_ms)
    """
    min_distance_pts = max(1, int(min_spike_distance_ms * sample_rate / 1000.0))

    peaks, props = find_peaks(
        response_data,
        height=threshold_mv,
        distance=min_distance_pts,
        prominence=min_prominence_mv,
    )
    # find_peaks uses >= for height; restore strict-greater semantics
    mask = props["peak_heights"] > threshold_mv
    peaks = peaks[mask]

    if len(peaks) == 0:
        return 0, [], []

    spike_times_sec = [float(p / sample_rate) for p in peaks]
    isi_ms = [
        (spike_times_sec[i] - spike_times_sec[i - 1]) * 1000.0
        for i in range(1, len(spike_times_sec))
    ]

    return len(peaks), spike_times_sec, isi_ms
