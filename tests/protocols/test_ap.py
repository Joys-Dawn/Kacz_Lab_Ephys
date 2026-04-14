import pytest
from ephys_analysis.core.abf_io import load_abf
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

    def test_sweep_num_within_valid_range(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert 1 <= result.sweep_num <= abf.sweepCount

    def test_phase_plot_data_populated(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        result = analyze_ap_fine(abf)

        assert len(result.phase_plot_v) > 0
        assert len(result.phase_plot_v) == len(result.phase_plot_dvdt)

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
