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
        """Three-window RMP for sample 1666 is -65.807 mV."""
        abf = load_abf(abf_rmp)

        result = analyze_rmp(abf)

        assert result.rmp_mv == pytest.approx(-65.807, abs=0.01)

    def test_rmp_averages_start_middle_and_end_windows(self, abf_rmp):
        abf = load_abf(abf_rmp)
        data = get_sweep_data(abf, sweep=0, channel=0)
        window_samples = round(0.2 * abf.sampleRate)
        middle = len(data) // 2
        half_window = window_samples // 2
        expected = float(np.mean([
            float(np.mean(data[:window_samples])),
            float(np.mean(data[middle - half_window:middle + half_window])),
            float(np.mean(data[-window_samples:])),
        ]))

        result = analyze_rmp(abf)

        assert result.rmp_mv == pytest.approx(expected, abs=1e-6)
