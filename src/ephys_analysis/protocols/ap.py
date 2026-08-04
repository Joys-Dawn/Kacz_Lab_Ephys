import logging

import numpy as np
import pyabf

from ephys_analysis.core.abf_io import (
    get_sweep_data,
    get_sampling_rate,
)
from ephys_analysis.core.signal import (
    windowed_mean,
    windowed_peak,
    time_to_index,
)
from ephys_analysis.core.spike import count_spikes_voltage, find_voltage_threshold
from ephys_analysis.core.types import APFineResult

logger = logging.getLogger(__name__)

# AP window for measurements (seconds)
AP_WINDOW_START = 0.29
AP_WINDOW_END = 0.31

# VThresh phase plot window (seconds)
VTHRESH_WINDOW_START = 0.2975
VTHRESH_WINDOW_END = 0.3015

# Baseline window (seconds)
BASELINE_START = 0.0
BASELINE_END = 0.2

# Current Threshold stimulus cursor (seconds)
ITHRESH_STIM_START = 0.29695
ITHRESH_STIM_END = 0.29885


def _inclusive_window_mean(
    data: np.ndarray, start_sec: float, end_sec: float, sampling_rate: float
) -> float:
    """Return the mean between cursor endpoints, including both endpoints."""
    i0 = time_to_index(start_sec, sampling_rate)
    i1 = time_to_index(end_sec, sampling_rate)
    return float(np.mean(data[i0:i1 + 1]))


def _interpolated_half_width(
    segment: np.ndarray, half_level: float, dt_ms: float
) -> float | None:
    """Compute half width with linear interpolation at crossings.

    Returns None if the half-level crossing cannot be detected.
    """
    above = segment > half_level
    if not np.any(above):
        return None

    # Find first upward crossing (False→True)
    rise_idx = None
    for i in range(1, len(above)):
        if above[i] and not above[i - 1]:
            denom = segment[i] - segment[i - 1]
            if denom == 0:
                rise_idx = float(i)
            else:
                frac = (half_level - segment[i - 1]) / denom
                rise_idx = (i - 1) + frac
            break

    # Find last downward crossing (True→False)
    fall_idx = None
    for i in range(len(above) - 1, 0, -1):
        if above[i - 1] and not above[i]:
            denom = segment[i] - segment[i - 1]
            if denom == 0:
                fall_idx = float(i - 1)
            else:
                frac = (half_level - segment[i - 1]) / denom
                fall_idx = (i - 1) + frac
            break

    if rise_idx is None or fall_idx is None:
        return None

    return (fall_idx - rise_idx) * dt_ms


def _analyze_ap(abf: pyabf.ABF) -> APFineResult | None:
    """Core AP analysis shared by fine and coarse.

    Returns None if no sweep has a detectable spike.
    """
    rate = get_sampling_rate(abf)

    for sweep_idx in range(abf.sweepCount):
        response = get_sweep_data(abf, sweep_idx, channel=0)

        # Check if this sweep has a full action potential:
        # 1) dV/dt must exceed criterion (28 mV/ms)
        # 2) Peak voltage in AP window must exceed 0 mV (sub-threshold
        #    depolarizations can cross the dV/dt criterion without being full APs)
        vthresh_result = find_voltage_threshold(
            response, rate, VTHRESH_WINDOW_START, VTHRESH_WINDOW_END
        )
        if vthresh_result is None:
            continue

        # Gate: require full AP (peak > 0 mV in AP window)
        peak_amp = windowed_peak(response, AP_WINDOW_START, AP_WINDOW_END, rate)
        if peak_amp < 0.0:
            continue

        voltage_threshold_mv, _ = vthresh_result

        # This is the first sweep with a spike — extract all metrics
        baseline = windowed_mean(response, BASELINE_START, BASELINE_END, rate)
        final_peak_amp = peak_amp - baseline

        # dV/dt within AP window for rise/decay slopes
        i0 = time_to_index(AP_WINDOW_START, rate)
        i1 = time_to_index(AP_WINDOW_END, rate)
        ap_segment = response[i0:i1]
        dt_ms = 1000.0 / rate
        dvdt = np.diff(ap_segment) / dt_ms
        # Max Rise / Max Decay are restricted to the AP's above-zero phase to
        # match Clampfit. Forward-diff convention: dvdt[i] = (V[i+1]-V[i])/dt.
        # For Max Rise, the "rising sample" is V[i+1] — keep dvdt[i] when
        # V[i+1] > 0 so we only count slopes that land on the overshoot, not
        # noise spikes earlier in the rise. For Max Decay, the "still-spiking
        # sample" is V[i] — keep dvdt[i] when V[i] > 0 so AHP dynamics after
        # V crosses 0 don't enter the min. Clean APs converge with both
        # conventions; weak/noisy APs only match the customer when these
        # masks are applied.
        v_before = ap_segment[:-1]
        v_after = ap_segment[1:]
        rise_mask = v_after > 0
        decay_mask = v_before > 0
        max_rise_slope = float(np.max(dvdt[rise_mask])) if rise_mask.any() else float(np.max(dvdt))
        max_decay_slope = float(np.min(dvdt[decay_mask])) if decay_mask.any() else float(np.min(dvdt))

        # Half width: width at half of peak absolute voltage
        # Validated against Clampfit reference — exact match on all 4 test samples
        half_level = peak_amp / 2.0
        half_width_ms = _interpolated_half_width(ap_segment, half_level, dt_ms)
        if half_width_ms is None:
            logger.warning("Half width could not be computed for sweep %d", sweep_idx)
            half_width_ms = 0.0

        # Spike count at threshold sweep — count voltage peaks above 0 mV
        spike_count, _, _ = count_spikes_voltage(ap_segment, rate, threshold_mv=0.0)

        # Current Threshold (Ithresh) — measured stimulus means from the
        # protocol's inclusive R1 and R2 cursor windows (R2S1 − R1S1).
        stim = get_sweep_data(abf, sweep_idx, channel=1)
        stim_baseline = _inclusive_window_mean(
            stim, BASELINE_START, BASELINE_END, rate
        )
        stim_step = _inclusive_window_mean(
            stim, ITHRESH_STIM_START, ITHRESH_STIM_END, rate
        )
        current_threshold = stim_step - stim_baseline

        return APFineResult(
            peak_amp_mv=final_peak_amp,
            half_width_ms=half_width_ms,
            max_rise_slope_mv_ms=max_rise_slope,
            max_decay_slope_mv_ms=max_decay_slope,
            sweep_num=sweep_idx + 1,
            current_threshold_pa=current_threshold,
            stim_baseline_pa=stim_baseline,
            stim_step_pa=stim_step,
            voltage_threshold_mv=voltage_threshold_mv,
            spike_num=spike_count,
        )

    return None


def analyze_ap_fine(abf: pyabf.ABF) -> APFineResult | None:
    """Analyze AP fine protocol."""
    return _analyze_ap(abf)


def analyze_ap_coarse(abf: pyabf.ABF) -> APFineResult | None:
    """Analyze AP coarse protocol (fallback when AP fine is missing)."""
    return _analyze_ap(abf)
