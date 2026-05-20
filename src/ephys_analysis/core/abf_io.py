"""ABF file I/O.

Epoch metadata (init levels, increments, durations) is read directly from
the ABF header section. These are static template values — per-sweep levels
are computed as init + inc * sweep_number, which is the same formula pyabf
uses internally (waveform.py:458). This avoids calling setSweep for metadata
that doesn't depend on sweep state.

The header sections (_epochPerDacSection, _dacSection) map 1:1 to the ABF2
binary format, which is a frozen spec from Molecular Devices.
"""
import re

import pyabf
import numpy as np
from pathlib import Path


def load_abf(path: str | Path, load_data: bool = True) -> pyabf.ABF:
    return pyabf.ABF(str(path), loadData=load_data)


def get_protocol_name(abf: pyabf.ABF) -> str:
    return abf.protocol


def _abf_label(abf: pyabf.ABF) -> str:
    """Best-effort human-readable identifier for an ABF used in error messages."""
    name = getattr(abf, "protocol", "") or ""
    return name if name else "<unnamed protocol>"


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


def _scan_userlist_from_strings(abf: pyabf.ABF) -> list[float] | None:
    """Scan the ABF StringsSection for a User List of numeric values.

    Used when a User List is enabled but pyabf's strict parser fails — e.g. a
    Clampex protocol with a missing comma (``700 800`` instead of ``700,800``).
    The list string lives verbatim in the strings section, so splitting on
    whitespace OR commas recovers the intended values.

    Returns the first list that is at least ``sweepCount`` long; the caller
    is responsible for truncating to the number of sweeps actually recorded.
    """
    n_sweeps = abf.sweepCount
    if n_sweeps < 2:
        return None
    strings = getattr(getattr(abf, "_stringsSection", None), "strings", None)
    if not strings:
        return None
    for raw in strings:
        text = raw.decode("latin-1", errors="replace") if isinstance(raw, bytes) else raw
        for piece in text.split("\x00"):
            piece = piece.strip()
            if not piece or "," not in piece:
                continue
            tokens = [t for t in re.split(r"[\s,]+", piece) if t]
            try:
                vals = [float(t) for t in tokens]
            except ValueError:
                continue
            if len(vals) >= n_sweeps:
                return vals
    return None


def reconstruct_currents(abf: pyabf.ABF, epoch_index: int = 1) -> list[float]:
    """Reconstruct nominal current for each sweep.

    Always uses the ABF User List when enabled — the authoritative record of
    what Clampex actually injected per sweep. The returned list has length
    ``min(sweepCount, len(UserList))``:

      - If the User List is longer than ``sweepCount`` (the experimenter
        stopped the recording before the protocol finished), the list is
        truncated to the first ``sweepCount`` values.
      - If the User List is shorter than ``sweepCount`` (sweeps beyond the
        end of the list have no defined nominal current — confirmed by
        customer analysis on samples 1531/1542/1546/1566), the recording is
        effectively truncated to the length of the User List and the
        trailing sweeps are dropped by the analyzers.

    Falls back to the epoch's linear ``init + inc * sweep_number`` only when
    no User List is enabled for this protocol.
    """
    ul_enable = getattr(abf, "userListEnable", None)
    if ul_enable and ul_enable[0] == 1:
        n = abf.sweepCount
        parsed = getattr(abf, "userList", None)
        if parsed is not None:
            return list(parsed[:n])
        scanned = _scan_userlist_from_strings(abf)
        if scanned is not None:
            return list(scanned[:n])
        raise ValueError(
            f"Protocol '{_abf_label(abf)}' has a User List enabled but no "
            f"per-sweep values could be read from the file. "
            f"Check the User List definition in the Clampex protocol. "
            f"File: {abf.abfFilePath}"
        )

    epoch = get_epoch_info(abf)
    if not epoch["init_level"]:
        raise ValueError(
            f"Protocol '{_abf_label(abf)}' has no epoch metadata, so per-sweep "
            f"currents cannot be reconstructed. Expected a stimulus protocol "
            f"with at least {epoch_index + 1} epoch(s) defined. "
            f"File: {abf.abfFilePath}"
        )
    if epoch_index >= len(epoch["init_level"]):
        raise ValueError(
            f"Protocol '{_abf_label(abf)}' defines only {len(epoch['init_level'])} "
            f"epoch(s); the analyzer needs epoch #{epoch_index + 1} (1-indexed) "
            f"to reconstruct currents. File: {abf.abfFilePath}"
        )

    init = epoch["init_level"][epoch_index]
    inc = epoch["level_inc"][epoch_index]
    return [init + inc * i for i in range(abf.sweepCount)]


def get_step_onset_sec(abf: pyabf.ABF, epoch_index: int = 1) -> float:
    """Get the onset time in seconds of the given epoch.

    Sums durations of all preceding epochs and the pre-epoch holding period.
    The pre-epoch holding period is 1/64 of the sweep length.
    """
    epoch = get_epoch_info(abf)
    if not epoch["init_duration"]:
        raise ValueError(
            f"Protocol '{_abf_label(abf)}' has no epoch metadata, so the step "
            f"onset time cannot be computed. File: {abf.abfFilePath}"
        )
    # epoch_index == len() is allowed: returns the onset of the (hypothetical)
    # epoch after the last one — i.e. end-of-protocol time.
    if epoch_index > len(epoch["init_duration"]):
        raise ValueError(
            f"Protocol '{_abf_label(abf)}' defines only "
            f"{len(epoch['init_duration'])} epoch(s); the analyzer needs the "
            f"onset of epoch #{epoch_index + 1} (1-indexed). "
            f"File: {abf.abfFilePath}"
        )

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
    if not epoch["init_duration"]:
        raise ValueError(
            f"Protocol '{_abf_label(abf)}' has no epoch metadata, so the step "
            f"duration cannot be read. File: {abf.abfFilePath}"
        )
    if epoch_index >= len(epoch["init_duration"]):
        raise ValueError(
            f"Protocol '{_abf_label(abf)}' defines only "
            f"{len(epoch['init_duration'])} epoch(s); the analyzer needs the "
            f"duration of epoch #{epoch_index + 1} (1-indexed). "
            f"File: {abf.abfFilePath}"
        )
    return epoch["init_duration"][epoch_index] / get_sampling_rate(abf)


def get_holding_level(abf: pyabf.ABF, dac_channel: int = 0) -> float:
    """Get the DAC holding level in pA (or mV for voltage clamp)."""
    if dac_channel >= len(abf.holdingCommand):
        raise ValueError(
            f"ABF has only {len(abf.holdingCommand)} DAC channel(s); the "
            f"analyzer asked for DAC #{dac_channel + 1} (1-indexed). "
            f"File: {abf.abfFilePath}"
        )
    return float(abf.holdingCommand[dac_channel])
