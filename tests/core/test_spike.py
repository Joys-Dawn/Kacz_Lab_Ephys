import numpy as np
import pytest
from ephys_analysis.core.abf_io import load_abf, get_sweep_data, get_sampling_rate
from ephys_analysis.core.spike import find_voltage_threshold, count_spikes_voltage


class TestFindVoltageThreshold:
    def test_real_ap_fine_threshold_in_physiological_range(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)
        rate = get_sampling_rate(abf)

        # Find first sweep with a threshold crossing
        result = None
        for sweep in range(abf.sweepCount):
            data = get_sweep_data(abf, sweep, channel=0)
            result = find_voltage_threshold(data, rate, 0.2975, 0.3015)
            if result is not None:
                break

        assert result is not None, "No sweep in AP fine had a detectable spike"
        vthresh, _, v, dvdt = result
        assert -60.0 < vthresh < -20.0, f"VThresh {vthresh} outside expected range"
        assert len(v) == len(dvdt)
        assert len(v) > 0

    def test_slow_ramp_below_criterion_returns_none(self):
        """20 mV/ms ramp (below 28 criterion) should not trigger threshold."""
        rate = 20000.0
        t = np.arange(0, 0.01, 1.0 / rate)
        signal = np.full_like(t, -60.0)
        ramp_start = int(0.002 * rate)
        ramp_end = int(0.007 * rate)
        signal[ramp_start:ramp_end] = np.linspace(-60, 40, ramp_end - ramp_start)
        signal[ramp_end:] = 40.0

        result = find_voltage_threshold(signal, rate, 0.0, 0.01, dvdt_criterion=28.0)

        assert result is None

    def test_steep_ramp_above_criterion_returns_threshold(self):
        """50 mV/ms ramp (above 28 criterion) should trigger threshold near ramp start."""
        rate = 20000.0
        t = np.arange(0, 0.01, 1.0 / rate)
        signal = np.full_like(t, -60.0)
        ramp_start = int(0.002 * rate)
        ramp_end = int(0.004 * rate)  # 2ms → 50 mV/ms
        signal[ramp_start:ramp_end] = np.linspace(-60, 40, ramp_end - ramp_start)
        signal[ramp_end:] = 40.0

        result = find_voltage_threshold(signal, rate, 0.0, 0.01, dvdt_criterion=28.0)

        assert result is not None
        vthresh, _, v, dvdt = result
        assert -65.0 < vthresh < -40.0

    def test_flat_signal_returns_none(self):
        rate = 20000.0
        signal = np.full(200, -65.0)

        result = find_voltage_threshold(signal, rate, 0.0, 0.01)

        assert result is None


class TestCountSpikesVoltage:
    def test_high_current_sweep_has_spikes(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        rate = get_sampling_rate(abf)
        data = get_sweep_data(abf, abf.sweepCount - 1, channel=0)

        count, times, isi = count_spikes_voltage(data, rate, threshold_mv=0.0)

        assert count > 0
        assert len(times) == count
        assert len(isi) == count - 1

    def test_zero_current_sweep_has_no_spikes(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)
        rate = get_sampling_rate(abf)
        data = get_sweep_data(abf, 0, channel=0)

        count, times, isi = count_spikes_voltage(data, rate, threshold_mv=0.0)

        assert count == 0
        assert times == []
        assert isi == []

    def test_synthetic_three_spikes_with_correct_isi(self):
        rate = 20000.0
        n = int(rate * 1.0)
        signal = np.full(n, -65.0)
        spike_times = [0.2, 0.5, 0.8]
        for t in spike_times:
            idx = int(t * rate)
            signal[idx - 10:idx + 10] = np.concatenate([
                np.linspace(-65, 30, 10),
                np.linspace(30, -65, 10),
            ])

        count, times, isi = count_spikes_voltage(signal, rate, threshold_mv=0.0)

        assert count == 3
        assert len(isi) == 2
        assert isi[0] == pytest.approx(300.0, abs=5.0)
        assert isi[1] == pytest.approx(300.0, abs=5.0)
