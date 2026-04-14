import numpy as np
import pytest
from ephys_analysis.core.signal import (
    time_to_index,
    windowed_mean,
    windowed_peak,
    windowed_antipeak,
)


class TestTimeToIndex:
    def test_zero_time_returns_zero(self):
        assert time_to_index(0.0, 20000.0) == 0

    def test_one_second_at_20khz(self):
        assert time_to_index(1.0, 20000.0) == 20000

    def test_half_second_at_20khz(self):
        assert time_to_index(0.5, 20000.0) == 10000

    def test_one_millisecond_at_20khz(self):
        assert time_to_index(0.001, 20000.0) == 20


class TestWindowedMean:
    def test_constant_signal_returns_that_constant(self):
        data = np.full(20000, 5.0)

        result = windowed_mean(data, 0.0, 0.5, 20000.0)

        assert result == pytest.approx(5.0)

    def test_linear_ramp_returns_midpoint(self):
        data = np.arange(100, dtype=float)  # 0..99 at 100 Hz

        result = windowed_mean(data, 0.0, 0.5, 100.0)  # samples 0-49

        assert result == pytest.approx(24.5)


class TestWindowedPeak:
    def test_finds_spike_within_window(self):
        data = np.zeros(20000)
        data[5000] = 42.0  # t=0.25s, inside [0.2, 0.3]

        result = windowed_peak(data, 0.2, 0.3, 20000.0)

        assert result == pytest.approx(42.0)

    def test_ignores_spike_outside_window(self):
        data = np.zeros(20000)
        data[1000] = 42.0  # t=0.05s, outside [0.2, 0.3]

        result = windowed_peak(data, 0.2, 0.3, 20000.0)

        assert result == pytest.approx(0.0)


class TestWindowedAntipeak:
    def test_finds_negative_dip_within_window(self):
        data = np.zeros(20000)
        data[5000] = -15.0  # t=0.25s, inside [0.2, 0.3]

        result = windowed_antipeak(data, 0.2, 0.3, 20000.0)

        assert result == pytest.approx(-15.0)
