from ephys_analysis.core.abf_io import load_abf
from ephys_analysis.protocols.ahp import analyze_ahp, AHP_5, AHP_25, AHP_50


class TestAnalyzeAHP:
    def test_5_ahp_peak_is_negative(self, abf_ahp_5):
        abf = load_abf(abf_ahp_5)

        result = analyze_ahp(abf, AHP_5)

        assert result.peak_mv < 0

    def test_25_ahp_peak_is_negative(self, abf_ahp_25):
        abf = load_abf(abf_ahp_25)

        result = analyze_ahp(abf, AHP_25)

        assert result.peak_mv < 0

    def test_50_ahp_returns_result(self, abf_ahp_50):
        """50 AHP may have weak signal but should still produce a result."""
        abf = load_abf(abf_ahp_50)

        result = analyze_ahp(abf, AHP_50)

        assert result is not None

    def test_different_cursors_produce_different_results(self, abf_ahp_5):
        """Using 25 AHP cursors on a 5 AHP file should give different (wrong) peak values."""
        abf = load_abf(abf_ahp_5)

        result_5 = analyze_ahp(abf, AHP_5)
        result_25 = analyze_ahp(abf, AHP_25)

        assert result_5.peak_mv != result_25.peak_mv
