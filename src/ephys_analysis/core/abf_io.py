"""ABF file I/O.

Epoch metadata (init levels, increments, durations) is read directly from
the ABF header section. These are static template values — per-sweep levels
are computed as init + inc * sweep_number, which is the same formula pyabf
uses internally (waveform.py:458). This avoids calling setSweep for metadata
that doesn't depend on sweep state.

The header sections (_epochPerDacSection, _dacSection) map 1:1 to the ABF2
binary format, which is a frozen spec from Molecular Devices.
"""
import pyabf
import numpy as np
from pathlib import Path


def load_abf(path: str | Path, load_data: bool = True) -> pyabf.ABF:
    return pyabf.ABF(str(path), loadData=load_data)


def get_protocol_name(abf: pyabf.ABF) -> str:
    return abf.protocol


def get_sampling_rate(abf: pyabf.ABF) -> float:
    return abf.sampleRate


def get_sweep_data(abf: pyabf.ABF, sweep: int, channel: int = 0) -> np.ndarray:
    abf.setSweep(sweep, channel=channel)
    return abf.sweepY.copy()


def get_sweep_time(abf: pyabf.ABF, sweep: int = 0) -> np.ndarray:
    abf.setSweep(sweep)
    return abf.sweepX.copy()


def get_epoch_info(abf: pyabf.ABF) -> dict:
    """Extract epoch template values from ABF header.

    Returns dict with keys: init_level, level_inc, init_duration, epoch_types.
    These are sweep-independent — per-sweep levels are init_level + level_inc * sweep.
    """
    ep = abf._epochPerDacSection
    return {
        "init_level": list(ep.fEpochInitLevel),
        "level_inc": list(ep.fEpochLevelInc),
        "init_duration": [int(x) for x in ep.lEpochInitDuration],
        "epoch_types": [int(x) for x in ep.nEpochType],
    }


def reconstruct_currents(abf: pyabf.ABF, epoch_index: int = 1) -> list[float]:
    """Reconstruct nominal current for each sweep.

    Uses the ABF User List when available (non-linear sweep patterns like
    Ri/Ih and AP coarse). Falls back to init + inc * sweep_number for
    protocols with linear current steps.
    """
    # User List overrides epoch init+inc for non-linear sweep patterns
    if (hasattr(abf, 'userListEnable') and abf.userListEnable
            and abf.userListEnable[0] == 1
            and hasattr(abf, 'userList') and abf.userList is not None
            and len(abf.userList) == abf.sweepCount):
        return list(abf.userList)

    epoch = get_epoch_info(abf)
    if not epoch["init_level"] or epoch_index >= len(epoch["init_level"]):
        return [0.0] * abf.sweepCount

    init = epoch["init_level"][epoch_index]
    inc = epoch["level_inc"][epoch_index]
    return [init + inc * i for i in range(abf.sweepCount)]


def get_step_onset_sec(abf: pyabf.ABF, epoch_index: int = 1) -> float:
    """Get the onset time in seconds of the given epoch.

    Sums durations of all preceding epochs and the pre-epoch holding period.
    The pre-epoch holding period is 1/64 of the sweep length.
    """
    epoch = get_epoch_info(abf)
    if not epoch["init_duration"] or epoch_index > len(epoch["init_duration"]):
        return 0.0

    rate = get_sampling_rate(abf)
    total_points = int(abf.sweepLengthSec * rate)
    pre_epoch_pts = total_points // 64

    pts = pre_epoch_pts
    for i in range(epoch_index):
        pts += epoch["init_duration"][i]
    return pts / rate


def get_step_duration_sec(abf: pyabf.ABF, epoch_index: int = 1) -> float:
    """Get the duration in seconds of the given epoch."""
    epoch = get_epoch_info(abf)
    if not epoch["init_duration"] or epoch_index >= len(epoch["init_duration"]):
        return 0.0
    return epoch["init_duration"][epoch_index] / get_sampling_rate(abf)


def get_holding_level(abf: pyabf.ABF, dac_channel: int = 0) -> float:
    """Get the DAC holding level in pA (or mV for voltage clamp)."""
    if dac_channel < len(abf.holdingCommand):
        return float(abf.holdingCommand[dac_channel])
    return 0.0
