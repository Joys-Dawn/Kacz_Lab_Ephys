from dataclasses import replace

import pytest
from ephys_analysis.core.pipeline import analyze_sample, analyze_all
from ephys_analysis.core.types import (
    OneSAPResult, OneSAPReview, QCStatus, QCReview,
    BaselineFlag, BaselineReview, SampleResult,
)
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


@pytest.fixture
def sample_1542_info(scan_result):
    for (animal_id, sample_id), info in scan_result.samples.items():
        if sample_id == "1542":
            return info
    pytest.fail("Sample 1542 not found in scan result")


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
            "Behavior", "Sex", "Nucleus?", "Cell Type", "NOTES",
        ]

    def test_file_notes_are_carried_to_sample_result(self, sample_1666_info):
        protocol, path = next(iter(sample_1666_info.protocols.items()))
        note = "Review this recording"

        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            file_notes={str(path): note},
        )

        assert result.notes == f"{path.name}: {note}"

    def test_qc_note_updates_ap_file_note(self, sample_1666_info):
        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            qc_reviewer=lambda sid, path, ap, rmp: QCReview(
                accepted=True,
                notes="Threshold reviewed",
            ),
        )

        assert "Threshold reviewed" in result.notes


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

    def test_auto_rejected_sample_is_sent_to_reviewer(self, sample_1542_info):
        reviewed_samples = []

        def review(sample_id, path, ap, rmp):
            reviewed_samples.append(sample_id)
            return QCReview(accepted=False)

        result = analyze_sample(
            sample_1542_info,
            nominal_data={},
            qc_reviewer=review,
        )

        assert reviewed_samples == ["1542"]
        assert result.qc_status == QCStatus.RMP_GT_VTHRESH

    def test_auto_rejected_sample_can_be_explicitly_overridden(
        self, sample_1542_info,
    ):
        result = analyze_sample(
            sample_1542_info,
            nominal_data={},
            qc_reviewer=lambda sid, path, ap, rmp: QCReview(
                accepted=True,
                override_auto_reject=True,
            ),
        )

        assert result.qc_status == QCStatus.PASSED


class TestQuickAnalysis:
    def test_skips_all_qc_and_passes_auto_rejected_sample(
        self, sample_1542_info,
    ):
        def unexpected_review(*args):
            pytest.fail("Quick Analysis must not invoke a review callback")

        result = analyze_sample(
            sample_1542_info,
            nominal_data={},
            qc_reviewer=unexpected_review,
            one_s_ap_reviewer=unexpected_review,
            ri_ih_reviewer=unexpected_review,
            skip_qc=True,
        )

        assert result.qc_status == QCStatus.PASSED

    def test_single_selected_protocol_passes_without_qc_dependencies(
        self, sample_1666_info,
    ):
        rmp_path = sample_1666_info.protocols[
            "2. Resting Membrane Potential"
        ]
        selected_info = replace(
            sample_1666_info,
            protocols={"2. Resting Membrane Potential": rmp_path},
        )

        result = analyze_sample(
            selected_info,
            nominal_data={},
            skip_qc=True,
        )

        assert result.qc_status == QCStatus.PASSED
        assert result.rmp is not None
        assert result.ap_fine is None

    def test_processing_error_is_failed_to_analyze_not_auto_rejected(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        rmp_path = sample_1666_info.protocols[
            "2. Resting Membrane Potential"
        ]
        selected_info = replace(
            sample_1666_info,
            protocols={"2. Resting Membrane Potential": rmp_path},
        )

        def fail_analysis(*args, **kwargs):
            raise ValueError("cannot parse selected file")

        monkeypatch.setattr(pipeline_mod, "analyze_sample", fail_analysis)

        results = analyze_all(
            {(selected_info.animal_id, selected_info.sample_id): selected_info},
            nominal_data={},
            skip_qc=True,
        )

        assert results[0].qc_status == QCStatus.ANALYSIS_FAILED
        assert results[0].analysis_error == "cannot parse selected file"
        assert results[0].file_path == str(rmp_path)


class TestBaselineReview:
    def test_flags_are_reviewed_before_sample_analysis(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        rmp_path = sample_1666_info.protocols[
            "2. Resting Membrane Potential"
        ]
        selected_info = replace(
            sample_1666_info,
            protocols={"2. Resting Membrane Potential": rmp_path},
        )
        flag = BaselineFlag(
            protocol="2. Resting Membrane Potential",
            file_path=str(rmp_path),
            target_mv=-67.0,
            baseline_means_mv=[-50.0],
            out_of_range_sweeps=[1],
        )
        monkeypatch.setattr(
            pipeline_mod,
            "analyze_baseline_qc",
            lambda *args, **kwargs: flag,
        )

        events = []

        def review(flags):
            events.append(("baseline", flags))
            return BaselineReview(decisions={str(rmp_path): True})

        results = analyze_all(
            {(selected_info.animal_id, selected_info.sample_id): selected_info},
            nominal_data={},
            baseline_reviewer=review,
            progress_callback=lambda idx, message: events.append(
                ("progress", message)
            ),
        )

        assert events[0] == ("baseline", [("1666", flag)])
        assert events[1][0] == "progress"
        assert results[0].rmp is not None

    def test_rejected_file_is_removed_before_analysis_without_mutating_scan(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        protocol = "2. Resting Membrane Potential"
        rmp_path = sample_1666_info.protocols[protocol]
        selected_info = replace(
            sample_1666_info,
            protocols={protocol: rmp_path},
        )
        flag = BaselineFlag(
            protocol=protocol,
            file_path=str(rmp_path),
            target_mv=-67.0,
            baseline_means_mv=[-50.0],
            out_of_range_sweeps=[1],
        )
        monkeypatch.setattr(
            pipeline_mod,
            "analyze_baseline_qc",
            lambda *args, **kwargs: flag,
        )
        analyzed_infos = []

        def capture_info(info, *args, **kwargs):
            analyzed_infos.append(info)
            return SampleResult(
                sample_id=info.sample_id,
                animal_id=info.animal_id,
            )

        monkeypatch.setattr(pipeline_mod, "analyze_sample", capture_info)

        analyze_all(
            {(selected_info.animal_id, selected_info.sample_id): selected_info},
            nominal_data={},
            baseline_reviewer=lambda flags: BaselineReview(
                decisions={str(rmp_path): False}
            ),
        )

        assert analyzed_infos[0].protocols == {}
        assert selected_info.protocols == {protocol: rmp_path}

    def test_review_must_decide_every_flagged_file(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        protocol = "2. Resting Membrane Potential"
        rmp_path = sample_1666_info.protocols[protocol]
        selected_info = replace(
            sample_1666_info,
            protocols={protocol: rmp_path},
        )
        flag = BaselineFlag(
            protocol=protocol,
            file_path=str(rmp_path),
            target_mv=-67.0,
            baseline_means_mv=[-50.0],
            out_of_range_sweeps=[1],
        )
        monkeypatch.setattr(
            pipeline_mod,
            "analyze_baseline_qc",
            lambda *args, **kwargs: flag,
        )

        with pytest.raises(ValueError, match="did not decide every flagged file"):
            analyze_all(
                {
                    (selected_info.animal_id, selected_info.sample_id):
                        selected_info
                },
                nominal_data={},
                baseline_reviewer=lambda flags: BaselineReview(),
            )

    def test_quick_analysis_skips_baseline_scan(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        def unexpected_check(*args, **kwargs):
            pytest.fail("Quick Analysis must not run baseline QC")

        monkeypatch.setattr(
            pipeline_mod, "analyze_baseline_qc", unexpected_check
        )

        analyze_all(
            {
                (sample_1666_info.animal_id, sample_1666_info.sample_id):
                    sample_1666_info
            },
            nominal_data={},
            baseline_reviewer=lambda flags: pytest.fail(
                "Quick Analysis must not review baseline flags"
            ),
            skip_qc=True,
        )


class TestOneSAPFlagReview:
    @staticmethod
    def _flagged_result(*args, **kwargs):
        return OneSAPResult(sudden_drop_sweeps=[2])

    def test_remove_excludes_only_one_s_ap_recording(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        monkeypatch.setattr(
            pipeline_mod, "analyze_one_s_ap", self._flagged_result
        )

        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            one_s_ap_reviewer=lambda sid, paths, one_s: OneSAPReview(
                accepted=False
            ),
        )

        assert result.qc_status == QCStatus.PASSED
        assert result.one_s_ap is None
        assert result.rmp is not None
        assert result.ri_ih is not None
        assert result.file_path == ""

    def test_keep_preserves_passed_status(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        monkeypatch.setattr(
            pipeline_mod, "analyze_one_s_ap", self._flagged_result
        )

        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            one_s_ap_reviewer=lambda sid, paths, one_s: OneSAPReview(
                accepted=True
            ),
        )

        assert result.qc_status == QCStatus.PASSED

    @pytest.mark.parametrize("accepted", [True, False])
    def test_auto_rejected_sample_is_still_reviewed_and_remains_rejected(
        self, sample_1542_info, monkeypatch, accepted,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        monkeypatch.setattr(
            pipeline_mod, "analyze_one_s_ap", self._flagged_result
        )
        reviewed = []

        def review(sample_id, paths, one_s):
            reviewed.append(sample_id)
            return OneSAPReview(accepted=accepted)

        result = analyze_sample(
            sample_1542_info,
            nominal_data={},
            one_s_ap_reviewer=review,
        )

        assert reviewed == ["1542"]
        assert result.qc_status == QCStatus.RMP_GT_VTHRESH

    def test_review_note_is_exportable_sample_note(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        monkeypatch.setattr(
            pipeline_mod, "analyze_one_s_ap", self._flagged_result
        )

        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            one_s_ap_reviewer=lambda sid, paths, one_s: OneSAPReview(
                accepted=True,
                notes="Fast-spiking pattern reviewed",
            ),
        )

        assert "Fast-spiking pattern reviewed" in result.notes


class TestAnalyzeAll:
    def test_processes_all_samples(self, scan_result):
        results = analyze_all(scan_result.samples, nominal_data={})

        assert len(results) == len(scan_result.samples)

    def test_bad_sample_does_not_abort_batch(self, scan_result):
        """Inject a corrupted sample info and verify the batch still produces
        a result for every sample, including a known-good neighbour.
        """
        from ephys_analysis.io.scanner import SampleInfo
        from ephys_analysis.protocols import PROTO_RMP
        from pathlib import Path

        bad_info = SampleInfo(
            animal_id="bad", sample_id="0000",
            protocols={PROTO_RMP: Path("nonexistent.abf")},
        )
        samples = dict(scan_result.samples)
        samples[("bad", "0000")] = bad_info

        results = analyze_all(samples, nominal_data={})

        assert len(results) == len(samples)
        bad_result = next(r for r in results if r.sample_id == "0000")
        assert bad_result.qc_status == QCStatus.ANALYSIS_FAILED
        assert bad_result.analysis_error
        # A known-good sample's RMP must still populate after the bad neighbour.
        known_good = next(r for r in results if r.sample_id == "1666")
        assert known_good.rmp is not None


class TestMissingProtocolQCDefaults:
    """The default qc_status on SampleResult is PASSED — that's wrong for
    samples missing the inputs to the gate. Without a guard, a sample with
    AP fine but no RMP would slip into the PASSED bucket.
    """

    def test_missing_rmp_marks_sample_rejected(self, sample_1666_info):
        from ephys_analysis.protocols import PROTO_RMP

        sample_1666_info.protocols.pop(PROTO_RMP, None)

        result = analyze_sample(sample_1666_info, nominal_data={})

        assert result.rmp is None
        assert result.qc_status == QCStatus.RMP_GT_VTHRESH

    def test_missing_ap_marks_sample_rejected(self, sample_1666_info):
        from ephys_analysis.protocols import PROTO_AP_FINE, PROTO_AP_COARSE

        sample_1666_info.protocols.pop(PROTO_AP_FINE, None)
        sample_1666_info.protocols.pop(PROTO_AP_COARSE, None)

        result = analyze_sample(sample_1666_info, nominal_data={})

        assert result.ap_fine is None
        assert result.qc_status == QCStatus.RMP_GT_VTHRESH


class TestAPCoarseFallback:
    """When AP fine's analyzer returns None (no detectable spike in the
    chosen AP fine file) and an AP coarse file is present, the pipeline
    silently runs analyze_ap_coarse on the coarse file and sets
    ap_used_coarse_fallback=True so the GUI / spreadsheet can surface it.
    """

    def test_flag_false_when_fine_succeeds(self, sample_1666_info):
        result = analyze_sample(sample_1666_info, nominal_data={})

        assert result.ap_fine is not None
        assert result.ap_used_coarse_fallback is False
        assert result.ap_source_is_coarse is False

    def test_falls_back_to_coarse_when_fine_returns_none(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod

        monkeypatch.setattr(pipeline_mod, "analyze_ap_fine", lambda abf: None)

        result = analyze_sample(sample_1666_info, nominal_data={})

        assert result.ap_used_coarse_fallback is True
        assert result.ap_source_is_coarse is True
        assert result.ap_fine is not None

    def test_no_fallback_when_coarse_file_missing(
        self, sample_1666_info, monkeypatch,
    ):
        import ephys_analysis.core.pipeline as pipeline_mod
        from ephys_analysis.protocols import PROTO_AP_COARSE

        monkeypatch.setattr(pipeline_mod, "analyze_ap_fine", lambda abf: None)
        # Strip the coarse protocol from this sample so the fallback path
        # has nothing to fall back to.
        sample_1666_info.protocols.pop(PROTO_AP_COARSE, None)

        result = analyze_sample(sample_1666_info, nominal_data={})

        assert result.ap_fine is None
        assert result.ap_used_coarse_fallback is False
        assert result.ap_source_is_coarse is False

    def test_coarse_only_sample_marks_source_but_not_fallback(
        self, sample_1666_info,
    ):
        """A sample with no AP fine file (only AP coarse) is the expected
        coarse-only case — ap_source_is_coarse must be True so the export
        shows "coarse", but ap_used_coarse_fallback stays False because
        nothing was unexpectedly fallen back from.
        """
        from ephys_analysis.protocols import PROTO_AP_FINE

        sample_1666_info.protocols.pop(PROTO_AP_FINE, None)

        result = analyze_sample(sample_1666_info, nominal_data={})

        assert result.ap_fine is not None
        assert result.ap_source_is_coarse is True
        assert result.ap_used_coarse_fallback is False


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


def test_back_updates_only_prior_qc_without_repeating_protocol_reviews(sample_1666_info, monkeypatch):
    from ephys_analysis.core import pipeline
    samples = {
        ("animal", sid): replace(sample_1666_info, sample_id=sid, animal_id="animal")
        for sid in ("1", "2", "3")
    }
    calls = []
    decisions = iter([
        QCReview(False, override_vthresh_mv=-80.0),
        QCReview(False, go_back=True),
        QCReview(True, notes="Corrected"),
        QCReview(False),
        QCReview(False, go_back=True),
        QCReview(False, go_back=True),
        QCReview(True),
        QCReview(True),
        QCReview(True),
    ])

    def review(sid, path, ap, rmp):
        calls.append(sid)
        assert ap.voltage_threshold_mv != -80.0
        return next(decisions)

    monkeypatch.setattr(pipeline, "analyze_one_s_ap", lambda *a, **kw: OneSAPResult(high_firing_sweeps=[1]))
    one_s_calls = []

    def review_one_s(sid, paths, result):
        one_s_calls.append(sid)
        return OneSAPReview(False)

    results = analyze_all(samples, {}, qc_reviewer=review, one_s_ap_reviewer=review_one_s)
    assert calls == ["1", "2", "1", "2", "3", "2", "1", "2", "3"]
    assert one_s_calls == ["1", "2", "3"]
    assert all(result.qc_status == QCStatus.PASSED for result in results)
    assert all(result.one_s_ap is None for result in results)
    assert all(result.file_path == "" and result.reject_sweep_num is None for result in results)
    assert "Corrected" in results[0].notes


def test_sweep_selection_reaches_analysis_without_rejecting_sample(sample_1666_info, monkeypatch):
    from ephys_analysis.core import pipeline
    from ephys_analysis.core.types import OneSAPSweep
    calls = []

    def analyze(*args, **kwargs):
        calls.append(kwargs.get("excluded_sweeps", set()))
        return OneSAPResult(sweeps=[OneSAPSweep(50, 1, 1), OneSAPSweep(100, 100, 100)], high_firing_sweeps=[2])

    monkeypatch.setattr(pipeline, "analyze_one_s_ap", analyze)
    result = analyze_sample(sample_1666_info, {}, one_s_ap_reviewer=lambda *a: OneSAPReview(True, excluded_sweeps={2}))
    assert calls == [set(), {2}]
    assert result.qc_status == QCStatus.PASSED


def test_rin_removal_preserves_sample_and_contamination_audit(sample_1666_info, monkeypatch):
    from ephys_analysis.core import pipeline
    from ephys_analysis.core.types import RiIhContaminatedSweep
    sweeps = [RiIhContaminatedSweep(i, 0, True, False) for i in range(1, 7)]
    order = []

    def analyze(abf, contamination_reviewer):
        assert contamination_reviewer(sweeps) is False
        return None

    monkeypatch.setattr(pipeline, "analyze_ri_ih", analyze)
    monkeypatch.setattr(pipeline, "analyze_one_s_ap", lambda *a: OneSAPResult(high_firing_sweeps=[1]))
    result = analyze_sample(
        sample_1666_info, {},
        qc_reviewer=lambda *a: order.append("qc") or True,
        ri_ih_reviewer=lambda *a: order.append("rin") or False,
        one_s_ap_reviewer=lambda *a: order.append("1s") or True,
    )
    assert order == ["qc", "rin", "1s"]
    assert result.qc_status == QCStatus.PASSED
    assert result.ri_ih is None
    assert result.ri_ih_contaminated_sweeps == sweeps
    assert result.ramp is not None and result.ahp_5 is not None


def test_removing_all_one_s_sweeps_keeps_other_protocols(sample_1666_info, monkeypatch):
    from ephys_analysis.core import pipeline
    from ephys_analysis.core.types import OneSAPSweep
    monkeypatch.setattr(pipeline, "analyze_one_s_ap", lambda *a: OneSAPResult(
        sweeps=[OneSAPSweep(50, 100, 100)], high_firing_sweeps=[1],
    ))
    result = analyze_sample(sample_1666_info, {}, one_s_ap_reviewer=lambda *a: OneSAPReview(True, excluded_sweeps={1}))
    assert result.one_s_ap is None
    assert result.qc_status == QCStatus.PASSED
    assert result.ap_fine is not None and result.ri_ih is not None
