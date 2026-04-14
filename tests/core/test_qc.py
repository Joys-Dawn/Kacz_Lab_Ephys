from ephys_analysis.core.qc import apply_qc_gate
from ephys_analysis.core.types import QCStatus


class TestApplyQCGate:
    def test_passes_when_vthresh_above_rmp(self):
        result = apply_qc_gate(rmp_mv=-65.0, voltage_threshold_mv=-40.0)

        assert result == QCStatus.PASSED

    def test_fails_when_vthresh_below_rmp(self):
        result = apply_qc_gate(rmp_mv=-65.0, voltage_threshold_mv=-70.0)

        assert result == QCStatus.RMP_GT_VTHRESH

    def test_fails_when_vthresh_equals_rmp(self):
        """Spec says 'if Voltage Threshold > RMP' — strictly greater."""
        result = apply_qc_gate(rmp_mv=-65.0, voltage_threshold_mv=-65.0)

        assert result == QCStatus.RMP_GT_VTHRESH
