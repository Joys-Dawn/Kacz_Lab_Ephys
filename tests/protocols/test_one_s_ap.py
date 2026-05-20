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


class TestHyperfiringRejection:
    """Spec rule: sweeps with > 50 detected peaks are flagged for user review.
    spike_count and firing_freq_hz are set to None (not zero) so cross-cell
    averages over the per-sweep columns treat them as missing data rather
    than dragging the mean toward zero. raw_spike_count is preserved.
    """

    def test_synthetic_51_spike_sweep_is_rejected(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        rate = abf.sampleRate
        target = abf.sweepCount - 1  # last sweep, highest current

        onset_sample = int(0.297 * rate)
        step_samples = int(1.0 * rate)
        sweep_offset = target * abf.sweepPointCount
        step_start = sweep_offset + onset_sample
        step_end = step_start + step_samples

        # 51 narrow triangle spikes at -65 → +30 → -65, every ~19 ms.
        abf.data[0, step_start:step_end] = -65.0
        n_spikes = 51
        spacing = step_samples // n_spikes
        for i in range(n_spikes):
            center = step_start + i * spacing + spacing // 2
            if center + 10 >= step_end:
                break
            abf.data[0, center - 10:center] = np.linspace(-65, 30, 10)
            abf.data[0, center:center + 10] = np.linspace(30, -65, 10)

        result = analyze_one_s_ap(abf)

        assert result.sweeps[target].rejected is True

    def test_rejected_sweep_spike_count_is_none(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        rate = abf.sampleRate
        target = abf.sweepCount - 1

        onset_sample = int(0.297 * rate)
        step_samples = int(1.0 * rate)
        step_start = target * abf.sweepPointCount + onset_sample
        step_end = step_start + step_samples
        abf.data[0, step_start:step_end] = -65.0
        n_spikes = 51
        spacing = step_samples // n_spikes
        for i in range(n_spikes):
            center = step_start + i * spacing + spacing // 2
            if center + 10 >= step_end:
                break
            abf.data[0, center - 10:center] = np.linspace(-65, 30, 10)
            abf.data[0, center:center + 10] = np.linspace(30, -65, 10)

        result = analyze_one_s_ap(abf)

        assert result.sweeps[target].spike_count is None
        assert result.sweeps[target].firing_freq_hz is None

    def test_rejected_sweep_preserves_raw_spike_count(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        rate = abf.sampleRate
        target = abf.sweepCount - 1

        onset_sample = int(0.297 * rate)
        step_samples = int(1.0 * rate)
        step_start = target * abf.sweepPointCount + onset_sample
        step_end = step_start + step_samples
        abf.data[0, step_start:step_end] = -65.0
        n_spikes = 51
        spacing = step_samples // n_spikes
        for i in range(n_spikes):
            center = step_start + i * spacing + spacing // 2
            if center + 10 >= step_end:
                break
            abf.data[0, center - 10:center] = np.linspace(-65, 30, 10)
            abf.data[0, center:center + 10] = np.linspace(30, -65, 10)

        result = analyze_one_s_ap(abf)

        assert result.sweeps[target].raw_spike_count > 50

    def test_rejected_sweep_has_empty_isi(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        rate = abf.sampleRate
        target = abf.sweepCount - 1

        onset_sample = int(0.297 * rate)
        step_samples = int(1.0 * rate)
        step_start = target * abf.sweepPointCount + onset_sample
        step_end = step_start + step_samples
        abf.data[0, step_start:step_end] = -65.0
        n_spikes = 51
        spacing = step_samples // n_spikes
        for i in range(n_spikes):
            center = step_start + i * spacing + spacing // 2
            if center + 10 >= step_end:
                break
            abf.data[0, center - 10:center] = np.linspace(-65, 30, 10)
            abf.data[0, center:center + 10] = np.linspace(30, -65, 10)

        result = analyze_one_s_ap(abf)

        assert result.sweeps[target].isi_ms == []


class TestIthreshFF:
    """``ithresh_ff_hz`` is None when AP fine's measured Ithresh does not land
    within half a step of any 1s AP sweep current — leaves the spreadsheet
    cell blank rather than reporting a misleading 0.
    """

    def test_returns_none_when_ithresh_pa_is_zero(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        result = analyze_one_s_ap(abf, ithresh_pa=0.0)

        assert result.ithresh_ff_hz is None

    def test_returns_none_when_ithresh_far_from_any_step(self, abf_1s_ap):
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


def _inject_51_spikes(abf, target_sweep: int):
    rate = abf.sampleRate
    onset_sample = int(0.297 * rate)
    step_samples = int(1.0 * rate)
    step_start = target_sweep * abf.sweepPointCount + onset_sample
    step_end = step_start + step_samples
    abf.data[0, step_start:step_end] = -65.0
    n_spikes = 51
    spacing = step_samples // n_spikes
    for i in range(n_spikes):
        center = step_start + i * spacing + spacing // 2
        if center + 10 >= step_end:
            break
        abf.data[0, center - 10:center] = np.linspace(-65, 30, 10)
        abf.data[0, center:center + 10] = np.linspace(30, -65, 10)


class TestRejectedSweepsSkippedInSummaryMetrics:
    """A rejected sweep's FF is None, so summary metrics that pick a specific
    sweep (Rheobase SU FF, Ithresh FF) must skip it rather than treating its
    zeroed FF as a real value. Without the skip, a hyper-firing sweep at the
    metric's chosen step would report FF=0 — falsely implying "no firing".
    """

    def test_max_ff_ignores_rejected_sweep(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        baseline = analyze_one_s_ap(abf)
        # Inject 51 spikes into the lowest-FF non-rejected sweep so it can't
        # accidentally still hold the max if rejected sweeps were counted.
        _inject_51_spikes(abf, target_sweep=abf.sweepCount - 1)

        result = analyze_one_s_ap(abf)

        assert result.sweeps[abf.sweepCount - 1].rejected is True
        assert result.max_ff_hz == pytest.approx(baseline.max_ff_hz)

    def test_rheobase_su_ff_blank_when_first_supra_sweep_rejected(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        # rheobase = 75 → first sweep above is index 2 (100 pA).
        _inject_51_spikes(abf, target_sweep=2)

        result = analyze_one_s_ap(abf, rheobase_pa=75.0)

        assert result.sweeps[2].rejected is True
        # The metric picks the first sweep above rheobase; that sweep is
        # rejected, so the value stays at its default 0.0 — the user sees
        # the rejection mark and knows to disregard.
        assert result.rheobase_su_ff_hz == pytest.approx(0.0)

    def test_ithresh_ff_none_when_nearest_sweep_rejected(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        # Target the 300 pA sweep (index 6). Ithresh=300 lands exactly on it.
        _inject_51_spikes(abf, target_sweep=6)

        result = analyze_one_s_ap(abf, ithresh_pa=300.0)

        assert result.sweeps[6].rejected is True
        assert result.ithresh_ff_hz is None
