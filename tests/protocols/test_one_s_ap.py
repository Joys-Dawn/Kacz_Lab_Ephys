import pytest
from ephys_analysis.core.abf_io import load_abf
from ephys_analysis.protocols.one_s_ap import analyze_one_s_ap


class TestAnalyzeOneSAP:
    def test_returns_sweep_for_every_abf_sweep(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf)

        assert len(result.sweeps) == abf.sweepCount

    def test_last_nonzero_ff_gte_first_nonzero_ff(self, abf_1s_ap):
        """Firing frequency should generally increase with current."""
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf)
        non_zero = [s for s in result.sweeps if s.firing_freq_hz > 0]

        assert len(non_zero) >= 2, "Expected at least 2 sweeps with spikes"
        assert non_zero[-1].firing_freq_hz >= non_zero[0].firing_freq_hz

    def test_first_ff_equals_ff_of_first_sweep_with_spikes(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf)

        assert result.first_sweep >= 0, "Expected at least one sweep with spikes"
        assert result.first_ff_hz == result.sweeps[result.first_sweep].firing_freq_hz

    def test_zero_current_sweep_has_no_spikes(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf)

        assert result.sweeps[0].current_pa == pytest.approx(0.0)
        assert result.sweeps[0].spike_count == 0

    def test_ithresh_pa_passed_through(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf, ithresh_pa=500.0, rheobase_pa=200.0)

        assert result.ithresh_pa == pytest.approx(500.0)
