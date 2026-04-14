import pytest
from ephys_analysis.core.abf_io import load_abf
from ephys_analysis.protocols.rmp import analyze_rmp


class TestAnalyzeRMP:
    def test_rmp_in_physiological_range(self, abf_rmp):
        abf = load_abf(abf_rmp)

        result = analyze_rmp(abf)

        assert -80.0 < result.rmp_mv < -40.0, f"RMP {result.rmp_mv} mV outside physiological range"

    def test_rmp_matches_reference_for_sample_1666(self, abf_rmp):
        """Sample 1666 reference RMP is -57.933 mV."""
        abf = load_abf(abf_rmp)

        result = analyze_rmp(abf)

        assert result.rmp_mv == pytest.approx(-57.933, abs=0.01)
