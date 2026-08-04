import numpy as np
import pytest
from ephys_analysis.core.abf_io import get_sweep_data, load_abf
from ephys_analysis.protocols.ap import analyze_ap_fine, analyze_ap_coarse


class TestAnalyzeAPFine:
    def test_detects_spike(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result is not None, "AP fine should detect at least one spike"

    def test_peak_amp_positive(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result.peak_amp_mv > 0

    def test_half_width_positive(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result.half_width_ms > 0

    def test_rise_slope_positive_decay_slope_negative(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result.max_rise_slope_mv_ms > 0
        assert result.max_decay_slope_mv_ms < 0

    def test_spike_count_at_least_one(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result.spike_num >= 1

    def test_voltage_threshold_in_physiological_range(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert -60.0 < result.voltage_threshold_mv < -20.0

    def test_current_threshold_is_measured_plateau_minus_baseline(self, abf_ap_fine):
        """Current Threshold = measured stim plateau mean − baseline mean (R2S1 − R1S1)."""
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result.current_threshold_pa == pytest.approx(
            result.stim_step_pa - result.stim_baseline_pa, abs=1e-6
        )

    def test_current_threshold_matches_reference_for_sample_1666(self, abf_ap_fine):
        """Sample 1666 reference Ithresh is 581.370 pA (R2S1 − R1S1)."""
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result.current_threshold_pa == pytest.approx(581.370, abs=0.01)

    def test_current_threshold_uses_inclusive_protocol_cursors(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)
        stimulus = get_sweep_data(abf, result.sweep_num - 1, channel=1)
        rate = abf.sampleRate
        expected_baseline = float(np.mean(stimulus[0:round(0.2 * rate) + 1]))
        expected_step = float(
            np.mean(
                stimulus[
                    round(0.29695 * rate):round(0.29885 * rate) + 1
                ]
            )
        )

        assert result.stim_baseline_pa == pytest.approx(expected_baseline, abs=1e-6)
        assert result.stim_step_pa == pytest.approx(expected_step, abs=1e-6)

    def test_negative_stimulus_pulse_uses_fixed_protocol_cursor(
        self, abf_ap_fine_negative_pulse
    ):
        abf = load_abf(abf_ap_fine_negative_pulse)

        result = analyze_ap_fine(abf)

        assert result is not None
        assert result.stim_step_pa < 0
        assert result.current_threshold_pa == pytest.approx(1207.31885, abs=0.001)

    def test_sweep_num_within_valid_range(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert 1 <= result.sweep_num <= abf.sweepCount

    def test_peak_amp_matches_reference_for_sample_1666(self, abf_ap_fine):
        """Sample 1666 reference Peak Amplitude is 118.870 mV."""
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result.peak_amp_mv == pytest.approx(118.870, abs=0.01)

    def test_half_width_matches_reference_for_sample_1666(self, abf_ap_fine):
        """Sample 1666 reference Half-Width is 0.5873 ms."""
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result.half_width_ms == pytest.approx(0.5873, abs=0.001)


class TestAnalyzeAPCoarse:
    def test_detects_spike(self, abf_ap_coarse):
        abf = load_abf(abf_ap_coarse)

        result = analyze_ap_coarse(abf)

        assert result is not None, "AP coarse should detect at least one spike"
        assert result.peak_amp_mv > 0


class TestMaxRiseAboveZeroMask:
    """Customer's Max Rise = max(dV/dt) restricted to samples where V[i+1] > 0.

    On clean APs the unmasked max happens during the overshoot anyway, so the
    mask has no effect (raw forward-diff already matches). On weak / noisy APs
    a pre-overshoot dV/dt spike would otherwise be picked up; the mask
    suppresses it and matches Clampfit's Max Slope of Rise.
    """

    def test_max_rise_matches_reference_for_sample_1666(self, abf_ap_fine):
        """Sample 1666 reference Max Rise is 549.316 mV/ms (clean AP)."""
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert result.max_rise_slope_mv_ms == pytest.approx(549.316, abs=0.01)

    def test_pre_overshoot_noise_does_not_inflate_max_rise(self, abf_ap_fine):
        """Inject a spurious +50 mV/ms transient at V ≈ -40 mV in the AP
        window. The transient has high dV/dt but lands well below 0 mV, so the
        above-zero mask must exclude it and leave Max Rise unchanged.
        """
        abf = load_abf(abf_ap_fine)
        rate = abf.sampleRate
        baseline_result = analyze_ap_fine(abf)

        # Two adjacent samples giving dV/dt ≈ +50 mV/ms in the pre-rise window.
        # At 20 kHz, 50 mV/ms = 2.5 mV per sample.
        i = int(0.298 * rate)
        abf.data[0, i] = -42.5
        abf.data[0, i + 1] = -40.0

        result = analyze_ap_fine(abf)

        assert result.max_rise_slope_mv_ms == pytest.approx(
            baseline_result.max_rise_slope_mv_ms, abs=0.01
        )


class TestSubthresholdEventIsSkipped:
    """A sweep where dV/dt crosses the 28 mV/ms criterion but voltage never
    rises above 0 mV is not a real AP — the analyzer must skip it and keep
    searching later sweeps. Without that guard, sub-threshold depolarizations
    would corrupt Peak Amplitude / Half-Width.
    """

    def test_steep_subthreshold_ramp_does_not_get_reported_as_ap(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)
        rate = abf.sampleRate
        baseline_result = analyze_ap_fine(abf)

        # Inject a 50 mV/ms ramp into sweep 0 at the VThresh window peaking at -10 mV.
        # dV/dt over 28 mV/ms but peak below 0 mV → analyzer must skip sweep 0.
        i_start = int(0.296 * rate)
        i_end = int(0.300 * rate)
        n = i_end - i_start
        abf.data[0, i_start:i_end] = np.linspace(-60.0, -10.0, n)

        result = analyze_ap_fine(abf)

        # peak_amp_mv stays positive — analyzer skipped the sub-threshold event
        # and found the real AP at the original sweep, unchanged.
        assert result.peak_amp_mv > 0
        assert result.sweep_num == baseline_result.sweep_num
