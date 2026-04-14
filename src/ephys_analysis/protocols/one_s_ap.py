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


def analyze_one_s_ap(
    abf: pyabf.ABF,
    ithresh_pa: float = 0.0,
    rheobase_pa: float = 0.0,
) -> OneSAPResult:
    """Analyze 1s AP firing protocol.

    Args:
        abf: Loaded ABF file.
        ithresh_pa: Current threshold from AP fine (for Ithresh FF).
        rheobase_pa: Rheobase from Ramp (for Rheobase SU FF).
    """
    rate = get_sampling_rate(abf)
    currents = reconstruct_currents(abf, epoch_index=1)
    step_onset = get_step_onset_sec(abf, epoch_index=1)
    step_duration = get_step_duration_sec(abf, epoch_index=1)

    i_start = time_to_index(step_onset, rate)
    i_end = time_to_index(step_onset + step_duration, rate)

    sweeps = []
    first_ff = 0.0
    max_ff = 0.0
    first_sweep = -1
    rheobase_su_ff = 0.0
    rheobase_su_found = False

    for sweep_idx in range(abf.sweepCount):
        response = get_sweep_data(abf, sweep_idx, channel=0)
        step_data = response[i_start:i_end]

        raw_spike_count, spike_times, isi_ms = count_spikes_voltage(
            step_data, rate, threshold_mv=0.0,
            min_prominence_mv=SPIKE_PROMINENCE_MV,
        )

        # Spec rule: reject sweeps with > 50 spikes (genuinely hyper-firing
        # cells flagged for user review). Zero the count/ISI but preserve
        # raw_spike_count and set rejected=True for the hyper-firing export.
        rejected = raw_spike_count > 50
        spike_count = 0 if rejected else raw_spike_count
        if rejected:
            isi_ms = []

        ff = spike_count / step_duration if step_duration > 0 else 0.0

        sweeps.append(OneSAPSweep(
            current_pa=currents[sweep_idx],
            spike_count=spike_count,
            firing_freq_hz=ff,
            isi_ms=isi_ms,
            rejected=rejected,
            raw_spike_count=raw_spike_count,
        ))

        if spike_count > 0 and first_sweep == -1:
            first_sweep = sweep_idx
            first_ff = ff

        if ff > max_ff:
            max_ff = ff

        # Rheobase SU FF: FF at first sweep with current > rheobase
        if rheobase_pa > 0 and currents[sweep_idx] > rheobase_pa and not rheobase_su_found:
            rheobase_su_ff = ff
            rheobase_su_found = True

    # Ithresh FF: FF at the 1s AP sweep whose nominal current is closest to
    # AP fine's Ithresh, within half a step size. AP fine's Ithresh is
    # measured (R2S1 − R1S1), so it rarely lands exactly on a 1s AP step.
    # None = no step is close enough — leave blank rather than reporting 0
    # (which would falsely imply "no firing at Ithresh").
    ithresh_ff: float | None = None
    if ithresh_pa > 0 and len(currents) >= 2:
        step_size = abs(currents[1] - currents[0])
        tolerance = step_size / 2.0
        diffs = [abs(c - ithresh_pa) for c in currents]
        nearest_idx = min(range(len(currents)), key=lambda i: diffs[i])
        if diffs[nearest_idx] <= tolerance:
            ithresh_ff = sweeps[nearest_idx].firing_freq_hz

    return OneSAPResult(
        sweeps=sweeps,
        first_ff_hz=first_ff,
        max_ff_hz=max_ff,
        ithresh_pa=ithresh_pa,
        ithresh_ff_hz=ithresh_ff,
        rheobase_su_ff_hz=rheobase_su_ff,
        first_sweep=first_sweep,
    )
