import pytest
from ephys_analysis.core.abf_io import (
    load_abf,
    get_protocol_name,
    get_sampling_rate,
    get_sweep_data,
    get_epoch_info,
    get_holding_level,
    reconstruct_currents,
    get_step_onset_sec,
    get_step_duration_sec,
)


class TestLoadAbf:
    def test_returns_abf_with_sweeps(self, abf_rmp):
        abf = load_abf(abf_rmp)

        assert abf.sweepCount > 0


class TestGetProtocolName:
    def test_rmp_protocol_string(self, abf_rmp):
        abf = load_abf(abf_rmp)

        assert get_protocol_name(abf) == "2. Resting Membrane Potential"

    def test_ap_fine_protocol_string(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        assert get_protocol_name(abf) == "5b. Single AP fine"


class TestGetSamplingRate:
    def test_returns_20khz_for_sample_data(self, abf_rmp):
        abf = load_abf(abf_rmp)

        assert get_sampling_rate(abf) == 20000.0


class TestGetSweepData:
    def test_returns_float_array_with_data(self, abf_ri_ih):
        abf = load_abf(abf_ri_ih)

        data = get_sweep_data(abf, 0, channel=0)

        assert len(data) > 0
        assert data.dtype.kind == "f"


class TestReconstructCurrents:
    def test_ri_ih_returns_20_values(self, abf_ri_ih):
        abf = load_abf(abf_ri_ih)

        currents = reconstruct_currents(abf, epoch_index=1)

        assert len(currents) == 20
        assert all(isinstance(c, float) for c in currents)

    def test_ap_fine_has_25pa_steps(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        currents = reconstruct_currents(abf, epoch_index=1)

        assert len(currents) == abf.sweepCount
        step = currents[1] - currents[0]
        assert step == pytest.approx(25.0, abs=0.01)

    def test_1s_ap_starts_at_zero_with_50pa_steps(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        currents = reconstruct_currents(abf, epoch_index=1)

        assert len(currents) == abf.sweepCount
        assert currents[0] == pytest.approx(0.0)
        assert currents[1] - currents[0] == pytest.approx(50.0, abs=0.01)


class TestGetStepOnset:
    def test_1s_ap_onset_near_300ms(self, abf_1s_ap):
        """Step onset should be ~0.297s, not the 3.0s stated in original spec."""
        abf = load_abf(abf_1s_ap)

        onset = get_step_onset_sec(abf, epoch_index=1)

        assert onset == pytest.approx(0.297, abs=0.1)


class TestGetStepDuration:
    def test_1s_ap_duration_is_one_second(self, abf_1s_ap):
        abf = load_abf(abf_1s_ap)

        duration = get_step_duration_sec(abf, epoch_index=1)

        assert duration == pytest.approx(1.0, abs=0.01)


class TestGetEpochInfo:
    def test_returns_all_expected_keys(self, abf_ap_fine):
        abf = load_abf(abf_ap_fine)

        info = get_epoch_info(abf)

        assert "init_level" in info
        assert "level_inc" in info
        assert "init_duration" in info
        assert "epoch_types" in info
        assert len(info["init_level"]) > 0


class TestGetHoldingLevel:
    def test_ramp_holding_is_zero(self, abf_ramp):
        abf = load_abf(abf_ramp)

        holding = get_holding_level(abf)

        assert holding == pytest.approx(0.0)
