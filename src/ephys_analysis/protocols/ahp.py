import numpy as np
import pyabf
from dataclasses import dataclass

from ephys_analysis.core.abf_io import get_sweep_data, get_sampling_rate
from ephys_analysis.core.signal import windowed_mean, windowed_antipeak
from ephys_analysis.core.types import AHPResult


@dataclass
class AHPCursors:
    baseline: tuple[float, float]
    peak: tuple[float, float]
    ms200: tuple[float, float]
    ms1000: tuple[float, float]


AHP_5 = AHPCursors(
    baseline=(0.0, 0.2),
    peak=(0.38, 0.58),
    ms200=(0.57, 0.59),
    ms1000=(1.37, 1.39),
)

AHP_25 = AHPCursors(
    baseline=(0.0, 0.2),
    peak=(0.66, 0.86),
    ms200=(0.85, 0.87),
    ms1000=(1.65, 1.67),
)

AHP_50 = AHPCursors(
    baseline=(0.0, 0.2),
    peak=(1.41, 1.61),
    ms200=(1.60, 1.62),
    ms1000=(2.40, 2.42),
)


def analyze_ahp(abf: pyabf.ABF, cursors: AHPCursors) -> AHPResult:
    """Analyze AHP protocol (5, 25, or 50 spike) using provided cursor positions.

    Measures baseline, antipeak, 200ms mean, and 1000ms mean per sweep.
    Baseline-subtracts all values, then averages across sweeps.
    """
    rate = get_sampling_rate(abf)

    peaks = []
    ms200s = []
    ms1000s = []

    for sweep_idx in range(abf.sweepCount):
        response = get_sweep_data(abf, sweep_idx, channel=0)

        bl = windowed_mean(response, *cursors.baseline, rate)
        pk = windowed_antipeak(response, *cursors.peak, rate)
        m200 = windowed_mean(response, *cursors.ms200, rate)
        m1000 = windowed_mean(response, *cursors.ms1000, rate)

        peaks.append(pk - bl)
        ms200s.append(m200 - bl)
        ms1000s.append(m1000 - bl)

    return AHPResult(
        peak_mv=float(np.mean(peaks)),
        ms200_mv=float(np.mean(ms200s)),
        ms1000_mv=float(np.mean(ms1000s)),
    )
