import numpy as np
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
        non_zero = [
            s for s in result.sweeps
            if s.firing_freq_hz is not None and s.firing_freq_hz > 0
        ]

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


def _inject_spikes(abf, target_sweep: int, n_spikes: int):
    rate = abf.sampleRate
    onset_sample = int(0.297 * rate)
    step_samples = int(1.0 * rate)
    step_start = target_sweep * abf.sweepPointCount + onset_sample
    step_end = step_start + step_samples
    abf.data[0, step_start:step_end] = -65.0
    spacing = step_samples // n_spikes
    for i in range(n_spikes):
        center = step_start + i * spacing + spacing // 2
        if center + 10 >= step_end:
            break
        abf.data[0, center - 10:center] = np.linspace(-65, 30, 10)
        abf.data[0, center:center + 10] = np.linspace(30, -65, 10)


class TestOneSAPReviewFlags:
    def test_sudden_drop_flag_matches_sample_1533(self, abf_1s_ap_sudden_drop):
        abf = load_abf(abf_1s_ap_sudden_drop)

        result = analyze_one_s_ap(abf)

        assert result.sudden_drop_sweeps == [13]
        assert result.sweeps[12].sudden_drop is True

    def test_stimulus_baseline_flag_matches_sample_1669(
        self, abf_1s_ap_baseline_zero
    ):
        abf = load_abf(abf_1s_ap_baseline_zero)

        result = analyze_one_s_ap(abf)

        assert result.baseline_at_or_above_zero_sweeps == [12, 13, 14, 15, 16]
        assert result.sweeps[11].stimulus_baseline_mv >= 0.0

    def test_hundred_spikes_is_review_threshold(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        target = abf.sweepCount - 1
        _inject_spikes(abf, target_sweep=target, n_spikes=100)

        result = analyze_one_s_ap(abf)

        assert result.sweeps[target].flagged_high_firing is True
        assert result.high_firing_sweeps == [target + 1]

    def test_ninety_nine_spikes_is_not_flagged(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        target = abf.sweepCount - 1
        _inject_spikes(abf, target_sweep=target, n_spikes=99)

        result = analyze_one_s_ap(abf)

        assert result.sweeps[target].flagged_high_firing is False
        assert result.high_firing_sweeps == []

    def test_high_firing_sweep_values_are_preserved(self, abf_1s_ap_high_firing):
        abf = load_abf(abf_1s_ap_high_firing)

        result = analyze_one_s_ap(abf)

        sweep = result.sweeps[10]
        assert result.high_firing_sweeps == [11, 12]
        assert sweep.spike_count == 119
        assert sweep.firing_freq_hz == pytest.approx(119.0)
        assert sweep.isi_ms
        assert result.max_ff_hz == pytest.approx(129.0)
        assert result.requires_review is True


class TestIthreshFF:
    """``ithresh_ff_hz`` comes from the first nominal current at or above
    AP fine's measured Ithresh and is blank when no such sweep has an FF.
    """

    def test_returns_none_when_ithresh_pa_is_zero(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf, ithresh_pa=0.0)

        assert result.ithresh_ff_hz is None

    def test_returns_none_when_ithresh_exceeds_highest_current(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf, ithresh_pa=99999.0)

        assert result.ithresh_ff_hz is None

    def test_matches_ff_when_ithresh_exactly_on_a_step(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        # Probe the protocol's actual currents and pick one mid-range step.
        probe = analyze_one_s_ap(abf)
        target = probe.sweeps[probe.first_sweep + 1]

        result = analyze_one_s_ap(abf, ithresh_pa=target.current_pa)

        assert result.ithresh_ff_hz == pytest.approx(target.firing_freq_hz)

    def test_uses_first_current_above_ithresh_between_steps(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        probe = analyze_one_s_ap(abf)
        adjacent = zip(probe.sweeps, probe.sweeps[1:])
        lower, upper = next(
            (lower, upper)
            for lower, upper in adjacent
            if lower.firing_freq_hz is not None
            and upper.firing_freq_hz is not None
            and lower.firing_freq_hz != upper.firing_freq_hz
        )
        ithresh = lower.current_pa + 0.1 * (upper.current_pa - lower.current_pa)

        result = analyze_one_s_ap(abf, ithresh_pa=ithresh)

        assert lower.current_pa < ithresh < upper.current_pa
        assert result.ithresh_ff_hz == pytest.approx(upper.firing_freq_hz)


class TestRheobaseSuFF:
    """``rheobase_su_ff_hz`` is the FF at the first sweep whose nominal current
    exceeds the rheobase value provided by the Ramp protocol.
    """

    def test_matches_ff_of_first_sweep_above_rheobase(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf, rheobase_pa=125.0)

        target = next(s for s in result.sweeps if s.current_pa > 125.0)
        assert result.rheobase_su_ff_hz == pytest.approx(target.firing_freq_hz)

    def test_zero_when_no_sweep_exceeds_rheobase(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf, rheobase_pa=99999.0)

        assert result.rheobase_su_ff_hz == pytest.approx(0.0)

    def test_zero_when_rheobase_not_provided(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf)

        assert result.rheobase_su_ff_hz == pytest.approx(0.0)


class TestFlaggedSweepsRemainInSummaryMetrics:
    def test_high_firing_sweep_can_supply_max_ff(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        target = abf.sweepCount - 1
        _inject_spikes(abf, target_sweep=target, n_spikes=100)

        result = analyze_one_s_ap(abf)

        assert result.sweeps[target].flagged_high_firing is True
        assert result.max_ff_hz == pytest.approx(100.0)

    def test_high_firing_sweep_can_supply_rheobase_su_ff(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        _inject_spikes(abf, target_sweep=2, n_spikes=100)

        result = analyze_one_s_ap(abf, rheobase_pa=75.0)

        assert result.sweeps[2].flagged_high_firing is True
        assert result.rheobase_su_ff_hz == pytest.approx(100.0)

    def test_high_firing_sweep_can_supply_ithresh_ff(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        _inject_spikes(abf, target_sweep=6, n_spikes=100)

        result = analyze_one_s_ap(abf, ithresh_pa=300.0)

        assert result.sweeps[6].flagged_high_firing is True
        assert result.ithresh_ff_hz == pytest.approx(100.0)
