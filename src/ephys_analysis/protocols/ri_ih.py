import numpy as np
import pyabf
from scipy import stats

from ephys_analysis.core.abf_io import (
    get_sweep_data,
    get_sampling_rate,
    reconstruct_currents,
)
from ephys_analysis.core.signal import windowed_mean, windowed_antipeak, time_to_index
from ephys_analysis.core.spike import count_spikes_voltage
from ephys_analysis.core.types import RiIhResult, RiIhContaminatedSweep

# Per protocol docx: a Ri/Ih sweep is contaminated if an AP fires inside
# the baseline window (cursors 1–2) or the steady-state window (cursors 5–6).
# Such sweeps must be excluded from Ri and Sag calculations. Use a generous
# prominence threshold — spontaneous APs are ≥ 40 mV peaks; 15 mV rejects
# baseline noise while admitting any real spike.
CONTAMINATION_PROMINENCE_MV = 15.0


def analyze_ri_ih(abf: pyabf.ABF) -> RiIhResult:
    """Analyze Ri/Ih protocol for input resistance, sag amplitude, and sag ratio.

    Measurements per sweep:
    - BASELINE: mean 0–0.2s (mV)
    - PEAK: antipeak 0.3–0.5s (mV)
    - STEADY STATE: mean 1.0–1.2s (mV)
    """
    rate = get_sampling_rate(abf)
    # Nominal currents (from User List) are used to *filter* which sweeps
    # enter the Ri regression. The regression itself runs on the *measured*
    # stimulus signal — this is what Clampfit does and matches the customer's
    # reference values exactly.
    currents = reconstruct_currents(abf, epoch_index=1)

    baselines = []
    peaks = []
    steady_states = []
    stim_measured_ss_sub = []  # baseline-subtracted measured stimulus (pA)
    contaminated_sweeps: list[RiIhContaminatedSweep] = []

    bl_i0, bl_i1 = time_to_index(0.0, rate), time_to_index(0.2, rate)
    ss_i0, ss_i1 = time_to_index(1.0, rate), time_to_index(1.2, rate)

    for sweep_idx in range(abf.sweepCount):
        response = get_sweep_data(abf, sweep_idx, channel=0)
        bl = windowed_mean(response, 0.0, 0.2, rate)
        pk = windowed_antipeak(response, 0.3, 0.5, rate)
        ss = windowed_mean(response, 1.0, 1.2, rate)
        baselines.append(bl)
        peaks.append(pk)
        steady_states.append(ss)

        stimulus = get_sweep_data(abf, sweep_idx, channel=1)
        stim_bl = windowed_mean(stimulus, 0.0, 0.2, rate)
        stim_ss = windowed_mean(stimulus, 1.0, 1.2, rate)
        stim_measured_ss_sub.append(stim_ss - stim_bl)

        # Detect APs in baseline and steady-state windows — contamination.
        ap_in_bl = count_spikes_voltage(
            response[bl_i0:bl_i1], rate, threshold_mv=0.0,
            min_prominence_mv=CONTAMINATION_PROMINENCE_MV,
        )[0] > 0
        ap_in_ss = count_spikes_voltage(
            response[ss_i0:ss_i1], rate, threshold_mv=0.0,
            min_prominence_mv=CONTAMINATION_PROMINENCE_MV,
        )[0] > 0
        if ap_in_bl or ap_in_ss:
            contaminated_sweeps.append(RiIhContaminatedSweep(
                sweep_num=sweep_idx + 1,
                current_pa=currents[sweep_idx],
                ap_in_baseline=ap_in_bl,
                ap_in_steady_state=ap_in_ss,
            ))

    contaminated_idx = {c.sweep_num - 1 for c in contaminated_sweeps}

    # Baseline-subtracted values
    peak_sub = [pk - bl for pk, bl in zip(peaks, baselines, strict=True)]
    ss_sub = [ss - bl for ss, bl in zip(steady_states, baselines, strict=True)]

    # Input Resistance: slope of steady_state_mv vs measured_current_pa
    # for sweeps where |nominal_current| <= 50 pA. Filtering by nominal
    # ensures we pick the right sweeps even when the measured signal is
    # noisy; the regression uses measured stimulus to match Clampfit.
    # Contaminated sweeps are excluded per protocol docx.
    ri_currents = []
    ri_ss = []
    for i, current in enumerate(currents):
        if i in contaminated_idx:
            continue
        if abs(current) <= 50.0:
            ri_currents.append(stim_measured_ss_sub[i])
            ri_ss.append(ss_sub[i])

    slope, _, _, _, _ = stats.linregress(ri_currents, ri_ss)
    input_resistance_mohm = slope * 1000.0  # mV/pA → MOhm

    # Sag Amplitude: average peak - baseline across most negative current
    # sweeps (excluding contaminated).
    clean_currents = {i: c for i, c in enumerate(currents) if i not in contaminated_idx}
    most_neg_current = min(clean_currents.values())
    sag_indices = [
        i for i, c in clean_currents.items() if abs(c - most_neg_current) < 1.0
    ]
    sag_amp_mv = float(np.mean([peak_sub[i] for i in sag_indices]))

    # Sag Ratio: (steady_state - baseline) / (peak - baseline), excluding
    # contaminated sweeps.
    def _avg_sag_ratio_by_current(target_pa: float, tol: float = 10.0) -> float:
        ratios = [
            ss_sub[i] / peak_sub[i]
            for i, current in enumerate(currents)
            if i not in contaminated_idx and abs(current - target_pa) < tol
        ]
        return float(np.mean(ratios))

    sag_ratio_200pa = _avg_sag_ratio_by_current(-200.0)
    sag_ratio_100pa = _avg_sag_ratio_by_current(-100.0)

    return RiIhResult(
        input_resistance_mohm=input_resistance_mohm,
        sag_amp_mv=sag_amp_mv,
        sag_ratio_200pa=sag_ratio_200pa,
        sag_ratio_100pa=sag_ratio_100pa,
        contaminated_sweeps=contaminated_sweeps,
    )
