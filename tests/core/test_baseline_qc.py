import numpy as np

from ephys_analysis.core.baseline_qc import analyze_baseline_qc
from ephys_analysis.protocols import PROTO_AHP_5, PROTO_RMP


class FakeABF:
    def __init__(
        self,
        baselines_mv: list[float],
        *,
        units: str = "mV",
        sweep_duration_sec: float = 0.3,
    ):
        self.sampleRate = 1000.0
        self.sweepUnitsY = units
        self.sweepCount = len(baselines_mv)
        sample_count = round(sweep_duration_sec * self.sampleRate)
        self._sweeps = [
            np.full(sample_count, baseline, dtype=float)
            for baseline in baselines_mv
        ]
        self.sweepY = np.array([], dtype=float)

    def setSweep(self, sweep: int, channel: int = 0):
        self.sweepY = self._sweeps[sweep]


def test_stable_baselines_inside_default_range_are_not_flagged():
    abf = FakeABF([-67.0, -66.0, -68.0, -67.0])

    result = analyze_baseline_qc(abf, "4. Ih", "stable.abf")

    assert result is None


def test_baseline_more_than_ten_mv_from_target_is_flagged():
    abf = FakeABF([-67.0, -56.9])

    result = analyze_baseline_qc(abf, "4. Ih", "outside.abf")

    assert result is not None
    assert result.out_of_range_sweeps == [2]


def test_baseline_exactly_ten_mv_from_target_is_not_flagged():
    abf = FakeABF([-77.0, -57.0])

    result = analyze_baseline_qc(abf, "4. Ih", "boundary.abf")

    assert result is None


def test_three_successive_pairs_at_four_mv_are_flagged():
    abf = FakeABF([-67.0, -63.0, -67.0, -63.0])

    result = analyze_baseline_qc(abf, "4. Ih", "changes.abf")

    assert result is not None
    assert result.changed_sweep_pairs == [(1, 2), (2, 3), (3, 4)]


def test_two_successive_changed_pairs_are_not_enough_to_flag():
    abf = FakeABF([-67.0, -63.0, -67.0])

    result = analyze_baseline_qc(abf, "4. Ih", "two-pairs.abf")

    assert result is None


def test_five_spike_ahp_uses_negative_sixty_mv_target():
    abf = FakeABF([-72.0])

    result = analyze_baseline_qc(abf, PROTO_AHP_5, "ahp.abf")

    assert result is not None
    assert result.target_mv == -60.0
    assert result.out_of_range_sweeps == [1]


def test_pa_recording_is_not_applicable():
    abf = FakeABF([-20.0, 20.0, -20.0, 20.0], units="pA")

    result = analyze_baseline_qc(abf, "1. Spontaneous EPSCs", "epsc.abf")

    assert result is None


def test_membrane_test_is_excluded_even_when_recorded_in_mv():
    abf = FakeABF([-20.0, 20.0, -20.0, 20.0])

    result = analyze_baseline_qc(abf, "Membrane Test", "membrane.abf")

    assert result is None


def test_recording_shorter_than_two_hundred_ms_is_not_applicable():
    abf = FakeABF([-20.0], sweep_duration_sec=0.1)

    result = analyze_baseline_qc(abf, "Short voltage protocol", "short.abf")

    assert result is None


def test_rmp_has_no_absolute_baseline_range_flag():
    assert analyze_baseline_qc(FakeABF([-20.0]), PROTO_RMP, "rmp.abf") is None


def test_rmp_still_flags_three_successive_baseline_changes():
    result = analyze_baseline_qc(
        FakeABF([-50.0, -46.0, -50.0, -46.0]), PROTO_RMP, "rmp.abf"
    )
    assert result.out_of_range_sweeps == []
    assert result.changed_sweep_pairs == [(1, 2), (2, 3), (3, 4)]
