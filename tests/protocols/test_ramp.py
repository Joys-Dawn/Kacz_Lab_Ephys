from ephys_analysis.core.abf_io import load_abf
from ephys_analysis.protocols.ramp import analyze_ramp


class TestAnalyzeRamp:
    def test_detects_spike_and_returns_positive_rheobase(self, abf_ramp):
        abf = load_abf(abf_ramp)

        result = analyze_ramp(abf)

        assert result is not None, "Ramp should detect a spike"
        assert result.rheobase_pa > 0

    def test_rheobase_in_physiological_range(self, abf_ramp):
        abf = load_abf(abf_ramp)

        result = analyze_ramp(abf)

        assert 50.0 < result.rheobase_pa < 1000.0, (
            f"Rheobase {result.rheobase_pa} pA outside expected range"
        )
