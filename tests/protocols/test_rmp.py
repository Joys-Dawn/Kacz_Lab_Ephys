import pytest
import numpy as np

from ephys_analysis.core.abf_io import get_sweep_data, load_abf
from ephys_analysis.protocols.rmp import analyze_rmp


class TestAnalyzeRMP:
    def test_rmp_in_physiological_range(self, abf_rmp):
        abf = load_abf(abf_rmp)

        result = analyze_rmp(abf)

        assert -80.0 < result.rmp_mv < -40.0, f"RMP {result.rmp_mv} mV outside physiological range"

    def test_rmp_matches_reference_for_sample_1666(self, abf_rmp):
        """First-200-ms RMP for sample 1666 is -57.933 mV."""
        abf = load_abf(abf_rmp)

        result = analyze_rmp(abf)

        assert result.rmp_mv == pytest.approx(-57.933, abs=0.01)

    def test_rmp_averages_only_first_200_ms(self, abf_rmp):
        abf = load_abf(abf_rmp)
        data = get_sweep_data(abf, sweep=0, channel=0)
        window_samples = round(0.2 * abf.sampleRate)
        expected = float(np.mean(data[:window_samples]))

        result = analyze_rmp(abf)

        assert result.rmp_mv == pytest.approx(expected, abs=1e-6)

    def test_rmp_ignores_data_at_and_after_200_ms(self, abf_rmp):
        abf = load_abf(abf_rmp)
        window_samples = round(0.2 * abf.sampleRate)
        abf.data[0, :] = 20.0
        abf.data[0, :window_samples // 2] = -80.0
        abf.data[0, window_samples // 2:window_samples] = -60.0

        result = analyze_rmp(abf)

        assert result.rmp_mv == -70.0

    @pytest.mark.parametrize("sample_count", [1999, 2000])
    def test_rmp_preserves_original_short_recording_behavior(self, monkeypatch, sample_count):
        from ephys_analysis.protocols import rmp

        monkeypatch.setattr(
            rmp, "get_sweep_data",
            lambda abf, sweep, channel: np.full(sample_count, -65.0),
        )
        monkeypatch.setattr(rmp, "get_sampling_rate", lambda abf: 10000)

        assert analyze_rmp(None).rmp_mv == -65.0
