import numpy as np
import pytest

from ephys_analysis.core.abf_io import load_abf
from ephys_analysis.protocols.ri_ih import analyze_ri_ih


class TestAnalyzeRiIh:
    def test_input_resistance_positive(self, abf_ri_ih):
        abf = load_abf(abf_ri_ih)

        result = analyze_ri_ih(abf)

        assert result.input_resistance_mohm > 0

    def test_sag_ratio_200pa_between_zero_and_one(self, abf_ri_ih):
        abf = load_abf(abf_ri_ih)

        result = analyze_ri_ih(abf)

        assert 0.0 < result.sag_ratio_200pa <= 1.0, (
            f"200pA sag ratio {result.sag_ratio_200pa} out of range"
        )

    def test_sag_ratio_100pa_between_zero_and_one(self, abf_ri_ih):
        abf = load_abf(abf_ri_ih)

        result = analyze_ri_ih(abf)

        assert 0.0 < result.sag_ratio_100pa <= 1.0, (
            f"100pA sag ratio {result.sag_ratio_100pa} out of range"
        )

    def test_sag_amplitude_negative(self, abf_ri_ih):
        """Sag amplitude should be negative (hyperpolarizing deflection)."""
        abf = load_abf(abf_ri_ih)

        result = analyze_ri_ih(abf)

        assert result.sag_amp_mv < 0

    def test_no_contamination_in_clean_sample(self, abf_ri_ih):
        """Sample data has no APs in baseline/steady state, so no contamination."""
        abf = load_abf(abf_ri_ih)

        result = analyze_ri_ih(abf)

        assert result.contaminated_sweeps == []


class TestContaminationDetection:
    """Inject a synthetic AP into baseline or steady state and verify detection."""

    def _inject_ap(self, abf, sweep_idx: int, time_sec: float):
        """Overwrite a short chunk of sweep data with a gaussian-ish AP.

        pyabf stores all sweeps concatenated in abf.data[channel, :]; setSweep
        just slices into that buffer, so mutating it is sufficient.
        """
        rate = abf.sampleRate
        i = int(time_sec * rate)
        t = np.arange(-20, 21) / rate * 1000.0  # ms
        spike = (80.0 * np.exp(-(t ** 2) / 0.3)).astype(abf.data.dtype)
        start = sweep_idx * abf.sweepPointCount + (i - 20)
        end = sweep_idx * abf.sweepPointCount + (i + 21)
        abf.data[0, start:end] += spike

    def test_ap_in_baseline_flags_sweep(self, abf_ri_ih):
        abf = load_abf(abf_ri_ih)
        # Inject AP at t=0.1s (inside baseline 0-0.2s) on sweep 0
        self._inject_ap(abf, sweep_idx=0, time_sec=0.1)

        result = analyze_ri_ih(abf)

        assert len(result.contaminated_sweeps) == 1
        assert result.contaminated_sweeps[0].sweep_num == 1
        assert result.contaminated_sweeps[0].ap_in_baseline is True
        assert result.contaminated_sweeps[0].ap_in_steady_state is False

    def test_ap_in_steady_state_flags_sweep(self, abf_ri_ih):
        abf = load_abf(abf_ri_ih)
        # Inject AP at t=1.1s (inside steady state 1.0-1.2s) on sweep 1
        self._inject_ap(abf, sweep_idx=1, time_sec=1.1)

        result = analyze_ri_ih(abf)

        assert len(result.contaminated_sweeps) == 1
        assert result.contaminated_sweeps[0].sweep_num == 2
        assert result.contaminated_sweeps[0].ap_in_steady_state is True

    def test_contaminated_sweep_excluded_from_ri(self, abf_ri_ih):
        """An injected AP in a Ri-eligible sweep must be excluded from the regression.

        Without exclusion, the spike would corrupt steady-state for that sweep
        and skew Ri far more than simply dropping one regression point does.
        """
        abf_clean = load_abf(abf_ri_ih)
        ri_clean = analyze_ri_ih(abf_clean).input_resistance_mohm

        abf_dirty = load_abf(abf_ri_ih)
        from ephys_analysis.core.abf_io import reconstruct_currents
        currents = reconstruct_currents(abf_dirty, epoch_index=1)
        target_sweep = next(i for i, c in enumerate(currents) if abs(c) <= 50.0)
        # Large, wide pulse — dominates the 0.2 s ss window mean if not excluded
        rate = abf_dirty.sampleRate
        pollution_start = int(1.05 * rate)
        pollution_end = int(1.15 * rate)
        offset = target_sweep * abf_dirty.sweepPointCount
        abf_dirty.data[0, offset + pollution_start: offset + pollution_end] += 200.0
        # And inject an AP to trip the detector
        self._inject_ap(abf_dirty, sweep_idx=target_sweep, time_sec=1.1)

        result = analyze_ri_ih(abf_dirty)

        assert len(result.contaminated_sweeps) == 1
        # With exclusion, Ri should stay close to clean (same regression minus
        # one point). Without exclusion, the +200 mV pollution on that sweep's
        # ss_sub would skew Ri by tens of MOhm.
        assert abs(result.input_resistance_mohm - ri_clean) < 10.0


@pytest.mark.parametrize("count,keep", [(5, True), (6, True), (6, False)])
def test_contamination_review_threshold_and_decision(abf_ri_ih, count, keep):
    abf = load_abf(abf_ri_ih)
    for sweep in range(count):
        TestContaminationDetection()._inject_ap(abf, sweep, 0.1)
    calls = []

    def review(sweeps):
        calls.append(sweeps)
        return keep

    result = analyze_ri_ih(abf, contamination_reviewer=review)
    assert len(calls) == (1 if count > 5 else 0)
    if keep:
        assert len(result.contaminated_sweeps) == count
        clean_result = analyze_ri_ih(abf)
        assert result == clean_result
    else:
        assert result is None


def test_all_contaminated_sweeps_leave_metrics_unavailable(abf_ri_ih):
    abf = load_abf(abf_ri_ih)
    for sweep in range(abf.sweepCount):
        TestContaminationDetection()._inject_ap(abf, sweep, 0.1)
    result = analyze_ri_ih(abf, contamination_reviewer=lambda sweeps: True)
    assert len(result.contaminated_sweeps) == abf.sweepCount
    assert result.input_resistance_mohm is None
    assert result.sag_amp_mv is None
    assert result.sag_ratio_100pa is None
    assert result.sag_ratio_200pa is None


def test_insufficient_rin_points_do_not_discard_available_sag(abf_ri_ih):
    from ephys_analysis.core.abf_io import reconstruct_currents
    abf = load_abf(abf_ri_ih)
    for sweep, current in enumerate(reconstruct_currents(abf, epoch_index=1)):
        if abs(current) <= 50:
            TestContaminationDetection()._inject_ap(abf, sweep, 0.1)
    result = analyze_ri_ih(abf)
    assert result.input_resistance_mohm is None
    assert result.sag_amp_mv is not None
    assert result.sag_ratio_100pa is not None
    assert result.sag_ratio_200pa is not None


def test_undefined_sag_ratio_is_blank_without_substituting_sweeps(abf_ri_ih):
    from ephys_analysis.core.abf_io import reconstruct_currents
    abf = load_abf(abf_ri_ih)
    for sweep, current in enumerate(reconstruct_currents(abf, epoch_index=1)):
        if abs(current + 100) < 10:
            start = sweep * abf.sweepPointCount
            abf.data[0, start:start + abf.sweepPointCount] = -65
    result = analyze_ri_ih(abf)
    assert result.sag_ratio_100pa is None
    assert result.sag_ratio_200pa is not None
