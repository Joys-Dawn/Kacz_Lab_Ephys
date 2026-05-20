import pytest
from ephys_analysis.core.abf_io import (
    load_abf,
    get_protocol_name,
    get_sampling_rate,
    get_sweep_data,
    get_sweep_time,
    get_epoch_info,
    get_holding_level,
    reconstruct_currents,
    get_step_onset_sec,
    get_step_duration_sec,
)


class _FakeEpochSection:
    """Minimal stand-in for pyabf's ``_epochPerDacSection``."""
    def __init__(
        self,
        fEpochInitLevel=(),
        fEpochLevelInc=(),
        lEpochInitDuration=(),
        nEpochType=(),
    ):
        self.fEpochInitLevel = list(fEpochInitLevel)
        self.fEpochLevelInc = list(fEpochLevelInc)
        self.lEpochInitDuration = list(lEpochInitDuration)
        self.nEpochType = list(nEpochType)


class _FakeStringsSection:
    def __init__(self, strings):
        self.strings = strings


class _FakeAbf:
    """Stand-in pyabf.ABF with only the attributes our io helpers touch."""
    def __init__(
        self,
        *,
        sweepCount=4,
        sampleRate=20000.0,
        sweepLengthSec=1.0,
        holdingCommand=(0.0,),
        userListEnable=None,
        userList=None,
        strings=None,
        epoch_section=None,
        abfFilePath="fake.abf",
    ):
        self.sweepCount = sweepCount
        self.sampleRate = sampleRate
        self.sweepLengthSec = sweepLengthSec
        self.holdingCommand = list(holdingCommand)
        self.userListEnable = userListEnable
        self.userList = userList
        self._stringsSection = (
            _FakeStringsSection(strings) if strings is not None else None
        )
        self._epochPerDacSection = epoch_section or _FakeEpochSection()
        self.abfFilePath = abfFilePath


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


class TestGetSweepTime:
    def test_returns_array_matching_sweep_length(self, abf_rmp):
        abf = load_abf(abf_rmp)

        t = get_sweep_time(abf, sweep=0)

        expected_pts = int(abf.sweepLengthSec * abf.sampleRate)
        assert len(t) == expected_pts

    def test_starts_at_zero(self, abf_rmp):
        abf = load_abf(abf_rmp)

        t = get_sweep_time(abf, sweep=0)

        assert t[0] == pytest.approx(0.0, abs=1e-9)


class TestReconstructCurrentsUserList:
    """Behaviour around the ``userListEnable`` branch in reconstruct_currents."""

    def test_returns_parsed_userlist_when_available(self):
        abf = _FakeAbf(
            sweepCount=4,
            userListEnable=[1],
            userList=[0.0, 50.0, 100.0, 150.0],
        )

        result = reconstruct_currents(abf)

        assert result == [0.0, 50.0, 100.0, 150.0]

    def test_truncates_userlist_when_longer_than_sweep_count(self):
        # Recording stopped before the protocol finished — Clampex stored the
        # full list but only the first N sweeps were captured.
        abf = _FakeAbf(
            sweepCount=3,
            userListEnable=[1],
            userList=[0.0, 50.0, 100.0, 150.0, 200.0],
        )

        result = reconstruct_currents(abf)

        assert result == [0.0, 50.0, 100.0]

    def test_returns_short_userlist_when_shorter_than_sweep_count(self):
        # When the recording has more sweeps than the User List defines, the
        # caller-side analyzer truncates its sweep loop to len(currents).
        # Verified against customer Clampfit numbers on samples 1542, 1546,
        # 1566 — the trailing sweeps past the UL are not part of the analysis.
        abf = _FakeAbf(
            sweepCount=5,
            userListEnable=[1],
            userList=[0.0, 50.0, 100.0],
        )

        result = reconstruct_currents(abf)

        assert result == [0.0, 50.0, 100.0]

    def test_falls_back_to_strings_section_when_pyabf_parse_fails(self):
        # pyabf's parser is strict about commas; a stored list of "500 600"
        # (whitespace instead of comma) makes abf.userList None. The strings
        # section still contains the raw bytes, so we recover from there.
        raw = b"100,200,300,400,500 600,700,800,900,1000\x00"
        abf = _FakeAbf(
            sweepCount=10,
            userListEnable=[1],
            userList=None,
            strings=[raw],
        )

        result = reconstruct_currents(abf)

        assert result == [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

    def test_strings_section_truncates_when_list_longer_than_sweep_count(self):
        # Whitespace-separator + recording-stopped-early: both fallbacks
        # interact. The strings scan returns the full list; the caller
        # truncates to sweepCount.
        raw = b"100,200,300,400,500 600,700,800\x00"
        abf = _FakeAbf(
            sweepCount=5,
            userListEnable=[1],
            userList=None,
            strings=[raw],
        )

        result = reconstruct_currents(abf)

        assert result == [100, 200, 300, 400, 500]

    def test_raises_when_userlist_enabled_but_unparseable(self):
        abf = _FakeAbf(
            sweepCount=4,
            userListEnable=[1],
            userList=None,
            strings=[b"nothing,parseable,here\x00"],
            abfFilePath="bad.abf",
        )

        with pytest.raises(ValueError, match="User List"):
            reconstruct_currents(abf)

    def test_userlist_disabled_falls_back_to_epoch_metadata(self):
        epoch = _FakeEpochSection(
            fEpochInitLevel=[0.0, 50.0],
            fEpochLevelInc=[0.0, 25.0],
            lEpochInitDuration=[200, 20000],
            nEpochType=[1, 1],
        )
        abf = _FakeAbf(
            sweepCount=4,
            userListEnable=[0],
            epoch_section=epoch,
        )

        result = reconstruct_currents(abf, epoch_index=1)

        assert result == [50.0, 75.0, 100.0, 125.0]


class TestRaisesOnBadMetadata:
    """Bad-data path: malformed/short epoch metadata must crash loudly so the
    per-sample handler in ``analyze_all`` can disqualify and notify, rather
    than silently substituting zeros.
    """

    def test_reconstruct_currents_raises_when_init_level_empty(self):
        abf = _FakeAbf(
            sweepCount=4,
            userListEnable=None,
            epoch_section=_FakeEpochSection(),
            abfFilePath="no_epochs.abf",
        )

        with pytest.raises(ValueError, match="no epoch metadata"):
            reconstruct_currents(abf)

    def test_reconstruct_currents_raises_when_epoch_index_out_of_range(self):
        epoch = _FakeEpochSection(
            fEpochInitLevel=[0.0],
            fEpochLevelInc=[0.0],
            lEpochInitDuration=[200],
            nEpochType=[1],
        )
        abf = _FakeAbf(
            sweepCount=4,
            userListEnable=None,
            epoch_section=epoch,
        )

        with pytest.raises(ValueError, match="defines only 1 epoch"):
            reconstruct_currents(abf, epoch_index=5)

    def test_get_step_onset_raises_when_init_duration_empty(self):
        abf = _FakeAbf(epoch_section=_FakeEpochSection())

        with pytest.raises(ValueError, match="no epoch metadata"):
            get_step_onset_sec(abf, epoch_index=1)

    def test_get_step_onset_raises_when_epoch_index_past_end(self):
        # epoch_index == len() is allowed (end-of-protocol); > len() raises.
        epoch = _FakeEpochSection(
            fEpochInitLevel=[0.0, 0.0],
            fEpochLevelInc=[0.0, 0.0],
            lEpochInitDuration=[200, 200],
            nEpochType=[1, 1],
        )
        abf = _FakeAbf(epoch_section=epoch)

        with pytest.raises(ValueError, match="defines only 2 epoch"):
            get_step_onset_sec(abf, epoch_index=5)

    def test_get_step_onset_allows_epoch_index_equal_to_length(self):
        epoch = _FakeEpochSection(
            fEpochInitLevel=[0.0, 0.0],
            fEpochLevelInc=[0.0, 0.0],
            lEpochInitDuration=[200, 400],
            nEpochType=[1, 1],
        )
        abf = _FakeAbf(sampleRate=20000.0, sweepLengthSec=1.0, epoch_section=epoch)

        # pre_epoch (1/64 of 20000 = 312) + 200 + 400 = 912 samples at 20kHz.
        onset = get_step_onset_sec(abf, epoch_index=2)

        assert onset == pytest.approx(912 / 20000.0)

    def test_get_step_duration_raises_when_init_duration_empty(self):
        abf = _FakeAbf(epoch_section=_FakeEpochSection())

        with pytest.raises(ValueError, match="no epoch metadata"):
            get_step_duration_sec(abf, epoch_index=1)

    def test_get_step_duration_raises_when_epoch_index_out_of_range(self):
        epoch = _FakeEpochSection(
            fEpochInitLevel=[0.0],
            fEpochLevelInc=[0.0],
            lEpochInitDuration=[200],
            nEpochType=[1],
        )
        abf = _FakeAbf(epoch_section=epoch)

        with pytest.raises(ValueError, match="defines only 1 epoch"):
            get_step_duration_sec(abf, epoch_index=1)

    def test_get_holding_level_raises_when_dac_channel_out_of_range(self):
        abf = _FakeAbf(holdingCommand=[0.0])

        with pytest.raises(ValueError, match="only 1 DAC channel"):
            get_holding_level(abf, dac_channel=3)
