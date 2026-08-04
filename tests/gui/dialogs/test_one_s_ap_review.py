from ephys_analysis.core.abf_io import load_abf
from ephys_analysis.core.types import OneSAPResult, OneSAPSweep
from ephys_analysis.gui.dialogs.one_s_ap_review import OneSAPReviewDialog
from ephys_analysis.protocols import PROTO_1S_AP, PROTO_RI_IH
from ephys_analysis.protocols.one_s_ap import analyze_one_s_ap


def _drop_result() -> OneSAPResult:
    return OneSAPResult(
        sweeps=[
            OneSAPSweep(0.0, 0, 0.0, raw_spike_count=0),
            OneSAPSweep(50.0, 10, 10.0, raw_spike_count=10),
            OneSAPSweep(
                100.0,
                1,
                1.0,
                raw_spike_count=1,
                sudden_drop=True,
            ),
        ],
        sudden_drop_sweeps=[3],
    )


class TestOneSAPReviewDialog:
    def test_high_firing_review_shows_one_s_ap_and_rin(
        self, qtbot, abf_1s_ap_high_firing, abf_ri_ih_high_firing,
    ):
        result = analyze_one_s_ap(load_abf(abf_1s_ap_high_firing))
        paths = {
            PROTO_1S_AP: str(abf_1s_ap_high_firing),
            PROTO_RI_IH: str(abf_ri_ih_high_firing),
        }

        dlg = OneSAPReviewDialog("1566", paths, result)
        qtbot.addWidget(dlg)

        assert dlg.one_s_viewer.ax.get_ylabel() == "mV"
        assert dlg.rin_viewer is not None
        assert dlg.rin_viewer.ax.get_ylabel() == "mV"

    def test_non_high_firing_flag_shows_only_one_s_ap(
        self, qtbot, abf_1s_ap,
    ):
        result = _drop_result()
        paths = {PROTO_1S_AP: str(abf_1s_ap)}

        dlg = OneSAPReviewDialog("1666", paths, result)
        qtbot.addWidget(dlg)

        assert dlg.rin_viewer is None

    def test_ap_drop_flag_shows_both_sweep_counts(
        self, qtbot, abf_1s_ap_sudden_drop,
    ):
        result = analyze_one_s_ap(load_abf(abf_1s_ap_sudden_drop))
        dlg = OneSAPReviewDialog(
            "1533",
            {PROTO_1S_AP: str(abf_1s_ap_sudden_drop)},
            result,
        )
        qtbot.addWidget(dlg)

        assert dlg.flag_label.text() == (
            "AP drop: sweep 12 had 10 APs; sweep 13 had 1 AP"
        )

    def test_keep_records_true(self, qtbot, abf_1s_ap):
        dlg = OneSAPReviewDialog(
            "1666",
            {PROTO_1S_AP: str(abf_1s_ap)},
            _drop_result(),
        )
        qtbot.addWidget(dlg)

        dlg._keep()

        assert dlg.accepted_result is True

    def test_remove_records_false(self, qtbot, abf_1s_ap):
        dlg = OneSAPReviewDialog(
            "1666",
            {PROTO_1S_AP: str(abf_1s_ap)},
            _drop_result(),
        )
        qtbot.addWidget(dlg)

        dlg._remove()

        assert dlg.accepted_result is False

    def test_notes_are_returned(self, qtbot, abf_1s_ap):
        dlg = OneSAPReviewDialog(
            "1666",
            {PROTO_1S_AP: str(abf_1s_ap)},
            _drop_result(),
            initial_note="Review note",
        )
        qtbot.addWidget(dlg)

        assert dlg.notes == "Review note"
