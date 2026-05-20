import pytest
from ephys_analysis.core.pipeline import analyze_sample, analyze_all
from ephys_analysis.core.types import QCStatus, QCReview
from ephys_analysis.io.scanner import scan_project_folder


@pytest.fixture
def scan_result(sample_data_root):
    return scan_project_folder(sample_data_root)


@pytest.fixture
def sample_1666_info(scan_result):
    for (animal_id, sample_id), info in scan_result.samples.items():
        if sample_id == "1666":
            return info
    pytest.fail("Sample 1666 not found in scan result")


class TestAnalyzeSample:
    def test_returns_all_protocol_results_when_auto_accepted(self, sample_1666_info):
        result = analyze_sample(sample_1666_info, nominal_data={})

        assert result.sample_id == "1666"
        assert result.qc_status == QCStatus.PASSED
        assert result.rmp is not None
        assert result.ap_fine is not None
        assert result.ri_ih is not None
        assert result.ramp is not None
        assert result.one_s_ap is not None
        assert result.ahp_5 is not None
        assert result.ahp_25 is not None
        assert result.ahp_50 is not None

    def test_rejected_sample_still_runs_remaining_protocols(self, sample_1666_info):
        """Per customer's compiled spreadsheet: Ri/Ih, Ramp, 1s AP and AHPs are
        filled for excluded samples too. QC status only gates downstream group
        statistics, not per-sample protocol computation.
        """
        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            qc_reviewer=lambda sid, path, ap, rmp: False,
        )

        assert result.qc_status == QCStatus.USER_REJECTED_VTHRESH
        assert result.ri_ih is not None
        assert result.ramp is not None
        assert result.one_s_ap is not None
        assert result.ahp_5 is not None
        assert result.ahp_25 is not None
        assert result.ahp_50 is not None

    def test_nominal_data_populates_result_fields(self, sample_1666_info):
        nominal = {"1666": {"Behavior": "CFM", "Sex": "M", "Nucleus?": "PL11-B2"}}
        result = analyze_sample(sample_1666_info, nominal_data=nominal)

        assert result.nominal_vars == {"Behavior": "CFM", "Sex": "M", "Nucleus?": "PL11-B2"}
        # The common dict spreads nominal_vars after the identity columns
        common = result.to_common_dict()
        assert list(common.keys()) == [
            "Collection Date", "Experimenter", "Animal ID", "Sample #",
            "Behavior", "Sex", "Nucleus?",
        ]


class TestQCReviewOverride:
    def test_override_above_rmp_mutates_result_and_passes(self, sample_1666_info):
        # Sample 1666 RMP ≈ −57.9; pick an override well above that.
        new_vt = -50.0
        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            qc_reviewer=lambda sid, path, ap, rmp: QCReview(
                accepted=True, override_vthresh_mv=new_vt,
            ),
        )

        assert result.qc_status == QCStatus.PASSED
        assert result.ap_fine.voltage_threshold_mv == new_vt

    def test_override_below_rmp_flips_verdict_to_rmp_gt_vthresh(self, sample_1666_info):
        # Sample 1666 RMP ≈ −57.9; an override below that fails the gate
        # regardless of the user's Accept click.
        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            qc_reviewer=lambda sid, path, ap, rmp: QCReview(
                accepted=True, override_vthresh_mv=-80.0,
            ),
        )

        assert result.qc_status == QCStatus.RMP_GT_VTHRESH
        assert result.ap_fine.voltage_threshold_mv == -80.0

    def test_accept_with_no_override_leaves_vthresh_untouched(self, sample_1666_info):
        original = analyze_sample(sample_1666_info, nominal_data={})

        accepted = analyze_sample(
            sample_1666_info,
            nominal_data={},
            qc_reviewer=lambda sid, path, ap, rmp: QCReview(accepted=True),
        )

        assert accepted.qc_status == QCStatus.PASSED
        assert accepted.ap_fine.voltage_threshold_mv == original.ap_fine.voltage_threshold_mv

    def test_bool_return_value_still_supported(self, sample_1666_info):
        # Backwards-compat: tests and simpler callers may return plain True/False.
        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            qc_reviewer=lambda sid, path, ap, rmp: False,
        )

        assert result.qc_status == QCStatus.USER_REJECTED_VTHRESH


class TestAnalyzeAll:
    def test_processes_all_samples(self, scan_result):
        results = analyze_all(scan_result.samples, nominal_data={})

        assert len(results) == len(scan_result.samples)

    def test_bad_sample_does_not_abort_batch(self, scan_result):
        """Inject a corrupted sample info and verify the batch still produces
        a result for every sample, including a known-good neighbour.
        """
        from ephys_analysis.io.scanner import SampleInfo
        from pathlib import Path

        bad_info = SampleInfo(
            animal_id="bad", sample_id="0000",
            protocols={"fake": Path("nonexistent.abf")},
        )
        samples = dict(scan_result.samples)
        samples[("bad", "0000")] = bad_info

        results = analyze_all(samples, nominal_data={})

        assert len(results) == len(samples)
        # A known-good sample's RMP must still populate after the bad neighbour.
        known_good = next(r for r in results if r.sample_id == "1666")
        assert known_good.rmp is not None


class TestCancelCheck:
    def test_immediate_cancel_returns_empty_list(self, scan_result):
        results = analyze_all(
            scan_result.samples,
            nominal_data={},
            cancel_check=lambda: True,
        )

        assert results == []

    def test_cancel_check_invoked_before_each_sample(self, scan_result):
        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return False

        analyze_all(
            scan_result.samples,
            nominal_data={},
            cancel_check=cancel,
        )

        assert calls["n"] == len(scan_result.samples)


class TestProgressCallback:
    @pytest.fixture
    def one_sample(self, scan_result):
        return {
            k: v for k, v in scan_result.samples.items() if v.sample_id == "1666"
        }

    def test_callback_invoked_once_per_sample(self, one_sample):
        calls = []

        analyze_all(
            one_sample,
            nominal_data={},
            progress_callback=lambda idx, msg: calls.append((idx, msg)),
        )

        assert len(calls) == 1

    def test_callback_receives_zero_based_index(self, one_sample):
        calls = []

        analyze_all(
            one_sample,
            nominal_data={},
            progress_callback=lambda idx, msg: calls.append((idx, msg)),
        )

        assert calls[0][0] == 0

    def test_callback_message_mentions_sample_id(self, one_sample):
        calls = []

        analyze_all(
            one_sample,
            nominal_data={},
            progress_callback=lambda idx, msg: calls.append((idx, msg)),
        )

        assert "1666" in calls[0][1]
