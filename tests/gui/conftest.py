"""Shared fixtures and matplotlib config for GUI tests.

Forces matplotlib's non-interactive Agg backend so plot widgets can render
without a real display, and exposes a fixture-builder for synthetic
APFineResult objects (used by QCReviewDialog and main_window tests).
"""
import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest

from ephys_analysis.core.types import (
    APFineResult, RMPResult, RiIhResult, RampResult, OneSAPResult,
    AHPResult, SampleResult, QCStatus,
)
from ephys_analysis.io.scanner import SampleInfo, ScanResult


@pytest.fixture
def ap_fine_result(abf_ap_fine):
    """Real APFineResult from the analyzer on sample 1666's AP-fine recording.

    Using the real analyzer's output (not a synthetic fixture) is important
    here: the QC review dialog re-reads the ABF and re-finds the threshold
    in the named sweep, so the fixture's sweep_num must actually contain a
    detectable AP. Synthesizing values is fine for fields the dialog doesn't
    re-compute (peak_amp_mv etc.) but sweep_num must be real.
    """
    from ephys_analysis.protocols.ap import analyze_ap_fine
    from ephys_analysis.core.abf_io import load_abf

    return analyze_ap_fine(load_abf(abf_ap_fine))


@pytest.fixture
def fake_scan_result(tmp_path):
    """ScanResult with two synthetic samples and zero duplicates."""
    info1 = SampleInfo(
        animal_id="animalA", sample_id="1666",
        collection_date="2026_01_01", experimenter="JCA",
        protocols={"2. Resting Membrane Potential": tmp_path / "rmp_1666.abf"},
    )
    info2 = SampleInfo(
        animal_id="animalA", sample_id="1667",
        collection_date="2026_01_01", experimenter="JCA",
        protocols={"2. Resting Membrane Potential": tmp_path / "rmp_1667.abf"},
    )
    sr = ScanResult()
    sr.samples = {
        ("animalA", "1666"): info1,
        ("animalA", "1667"): info2,
    }
    return sr


@pytest.fixture
def passed_sample_result():
    return SampleResult(
        sample_id="1666", animal_id="animalA",
        collection_date="2026_01_01", experimenter="JCA",
        qc_status=QCStatus.PASSED,
        rmp=RMPResult(rmp_mv=-65.0),
        ap_fine=APFineResult(
            peak_amp_mv=80.0, half_width_ms=1.2,
            max_rise_slope_mv_ms=300.0, max_decay_slope_mv_ms=-100.0,
            sweep_num=1, current_threshold_pa=500.0,
            stim_baseline_pa=-50.0, stim_step_pa=450.0,
            voltage_threshold_mv=-45.0, spike_num=1,
        ),
        ri_ih=RiIhResult(
            input_resistance_mohm=150.0, sag_amp_mv=-10.0,
            sag_ratio_200pa=0.8, sag_ratio_100pa=0.9,
        ),
        ramp=RampResult(rheobase_pa=200.0),
        ahp_5=AHPResult(peak_mv=-5.0, ms200_mv=-2.0, ms1000_mv=-0.5),
        ahp_25=AHPResult(peak_mv=-8.0, ms200_mv=-3.0, ms1000_mv=-1.0),
        ahp_50=AHPResult(peak_mv=-10.0, ms200_mv=-4.0, ms1000_mv=-1.5),
        one_s_ap=OneSAPResult(
            first_ff_hz=3.0, max_ff_hz=3.0,
            ithresh_pa=500.0, ithresh_ff_hz=3.0,
            rheobase_su_ff_hz=3.0, first_sweep=1,
        ),
    )
