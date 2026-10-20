import numpy as np
import pyabf

from ephys_analysis.core.abf_io import (
    get_sweep_data,
    get_sampling_rate,
    reconstruct_currents,
    get_step_onset_sec,
    get_step_duration_sec,
)
from ephys_analysis.core.signal import time_to_index
from ephys_analysis.core.spike import count_spikes_voltage
from ephys_analysis.core.types import OneSAPResult, OneSAPSweep

# Minimum peak prominence (mV) to count as a spike. Rejects the small
# oscillations of depolarization block (where V sits above 0 mV with
# ~5–15 mV wiggles) while admitting genuine APs (prominence ≫ 20 mV).
# Validated at 15 mV against customer reference: 62/64 per-sweep spike counts
# match exactly across 4 samples × 16 sweeps; 2 off by one.
SPIKE_PROMINENCE_MV = 15.0

# Review rules requested for 1-second AP recordings.
HIGH_FIRING_REVIEW_THRESHOLD = 100
STIMULUS_BASELINE_DURATION_SEC = 0.2


def analyze_one_s_ap(
    abf: pyabf.ABF,
    ithresh_pa: float = 0.0,
    rheobase_pa: float = 0.0,
    excluded_sweeps: set[int] | None = None,
) -> OneSAPResult:
    """Analyze 1s AP firing protocol.

    Args:
        abf: Loaded ABF file.
        ithresh_pa: Current threshold from AP fine (for Ithresh FF).
        rheobase_pa: Rheobase from Ramp (for Rheobase SU FF).
    """
    rate = get_sampling_rate(abf)
    # If the User List is shorter than sweepCount, only the first
    # len(currents) sweeps are analyzed; trailing sweeps without a defined
    # nominal current are dropped.
    currents = reconstruct_currents(abf, epoch_index=1)
    step_onset = get_step_onset_sec(abf, epoch_index=1)
    step_duration = get_step_duration_sec(abf, epoch_index=1)

    i_start = time_to_index(step_onset, rate)
    i_end = time_to_index(step_onset + step_duration, rate)

    excluded_sweeps = excluded_sweeps or set()
    sweeps = []
    first_ff = 0.0
    max_ff = 0.0
    first_sweep = -1
    rheobase_su_ff = 0.0
    rheobase_su_found = False
    sudden_drop_sweeps = []
    baseline_at_or_above_zero_sweeps = []
    high_firing_sweeps = []
    previous_spike_count: int | None = None
    baseline_samples = max(
        1,
        min(
            i_end - i_start,
            time_to_index(STIMULUS_BASELINE_DURATION_SEC, rate),
        ),
    )

    for sweep_idx in range(len(currents)):
        response = get_sweep_data(abf, sweep_idx, channel=0)
        step_data = response[i_start:i_end]

        raw_spike_count, spike_times, isi_ms = count_spikes_voltage(
            step_data, rate, threshold_mv=0.0,
            min_prominence_mv=SPIKE_PROMINENCE_MV,
        )

        spike_count = raw_spike_count
        ff = (raw_spike_count / step_duration) if step_duration > 0 else 0.0
        stimulus_baseline_mv = float(np.mean(step_data[:baseline_samples]))
        sudden_drop = (
            previous_spike_count is not None
            and previous_spike_count >= 5
            and raw_spike_count == 1
        )
        flagged_high_firing = raw_spike_count >= HIGH_FIRING_REVIEW_THRESHOLD

        sweeps.append(OneSAPSweep(
            current_pa=currents[sweep_idx],
            spike_count=spike_count,
            firing_freq_hz=ff,
            isi_ms=isi_ms,
            raw_spike_count=raw_spike_count,
            stimulus_baseline_mv=stimulus_baseline_mv,
            sudden_drop=sudden_drop,
            flagged_high_firing=flagged_high_firing,
            excluded=sweep_idx + 1 in excluded_sweeps,
        ))

        sweep_num = sweep_idx + 1
        if sudden_drop:
            sudden_drop_sweeps.append(sweep_num)
        if stimulus_baseline_mv >= 0.0:
            baseline_at_or_above_zero_sweeps.append(sweep_num)
        if flagged_high_firing:
            high_firing_sweeps.append(sweep_num)

        previous_spike_count = raw_spike_count
        if sweep_num in excluded_sweeps:
            continue

        if spike_count and first_sweep == -1:
            first_sweep = sweep_idx
            first_ff = ff

        if ff > max_ff:
            max_ff = ff

        if rheobase_pa > 0 and currents[sweep_idx] > rheobase_pa and not rheobase_su_found:
            rheobase_su_ff = ff
            rheobase_su_found = True

    # Ithresh FF: FF at the first 1s AP sweep whose nominal current is at or
    # above AP fine's measured Ithresh. None leaves the export blank when no
    # nominal current reaches Ithresh.
    ithresh_ff: float | None = None
    if ithresh_pa > 0:
        threshold_idx = next(
            (i for i, current in enumerate(currents)
             if current >= ithresh_pa and i + 1 not in excluded_sweeps),
            None,
        )
        if threshold_idx is not None:
            ithresh_ff = sweeps[threshold_idx].firing_freq_hz

    return OneSAPResult(
        sweeps=sweeps,
        first_ff_hz=first_ff,
        max_ff_hz=max_ff,
        ithresh_pa=ithresh_pa,
        ithresh_ff_hz=ithresh_ff,
        rheobase_su_ff_hz=rheobase_su_ff,
        first_sweep=first_sweep,
        sudden_drop_sweeps=sudden_drop_sweeps,
        baseline_at_or_above_zero_sweeps=baseline_at_or_above_zero_sweeps,
        high_firing_sweeps=high_firing_sweeps,
    )
