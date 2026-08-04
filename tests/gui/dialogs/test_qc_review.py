from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLabel, QPushButton

from ephys_analysis.gui.dialogs.qc_review import QCReviewDialog


class TestQCReviewDialog:
    def test_constructs_with_real_abf(self, qtbot, abf_ap_fine, ap_fine_result):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)

        assert dlg.windowTitle() == "QC Review — Sample 1666"

    def test_accepted_result_is_none_before_user_acts(self, qtbot, abf_ap_fine, ap_fine_result):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)

        assert dlg.accepted_result is None

    def test_accept_sets_accepted_result_true(self, qtbot, abf_ap_fine, ap_fine_result):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)

        with qtbot.waitSignal(dlg.accepted, timeout=200):
            dlg._accept()

        assert dlg.accepted_result is True

    def test_reject_sets_accepted_result_false(self, qtbot, abf_ap_fine, ap_fine_result):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)

        with qtbot.waitSignal(dlg.rejected, timeout=200):
            dlg._reject()

        assert dlg.accepted_result is False

    def test_cancel_sets_accepted_result_cancel_string(self, qtbot, abf_ap_fine, ap_fine_result):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)

        with qtbot.waitSignal(dlg.rejected, timeout=200):
            dlg._cancel()

        assert dlg.accepted_result == "cancel"

    def test_escape_key_is_swallowed(self, qtbot, abf_ap_fine, ap_fine_result):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)
        event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)

        dlg.keyPressEvent(event)

        assert dlg.accepted_result is None

    def test_picker_default_selection_is_auto_detected(
        self, qtbot, abf_ap_fine, ap_fine_result,
    ):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)

        assert dlg.picker.selected_idx == dlg.picker.auto_idx

    def test_no_override_recorded_when_user_does_not_pick(
        self, qtbot, abf_ap_fine, ap_fine_result,
    ):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)

        dlg._accept()

        assert dlg.override_vthresh_mv is None

    def test_override_recorded_when_user_picks_different_sample(
        self, qtbot, abf_ap_fine, ap_fine_result,
    ):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)
        # Move selection one sample to the left of the auto pick.
        new_idx = max(0, dlg.picker.auto_idx - 1)
        dlg.picker.select_index(new_idx)

        dlg._accept()

        assert dlg.override_vthresh_mv == dlg.picker.selected_voltage_mv()

    def test_reset_restores_auto_detected_selection(
        self, qtbot, abf_ap_fine, ap_fine_result,
    ):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)
        dlg.picker.select_index(dlg.picker.auto_idx + 1)

        dlg._reset()

        assert dlg.picker.selected_idx == dlg.picker.auto_idx

    def test_clicking_accept_button_triggers_accept(self, qtbot, abf_ap_fine, ap_fine_result):
        dlg = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, rmp_mv=-65.0)
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitExposed(dlg)
        accept_btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Accept")

        qtbot.mouseClick(accept_btn, Qt.LeftButton)

        assert dlg.accepted_result is True

    def test_protocol_selector_switches_trace_without_closing(
        self, qtbot, abf_ap_fine, abf_epsc, ap_fine_result,
    ):
        paths = {
            "1. Spontaneous EPSCs": str(abf_epsc),
            "5b. Single AP fine": str(abf_ap_fine),
        }
        dlg = QCReviewDialog(
            "1666",
            str(abf_ap_fine),
            ap_fine_result,
            rmp_mv=-65.0,
            protocol_paths=paths,
        )
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitExposed(dlg)
        epsc_index = dlg.protocol_selector.findData(str(abf_epsc))

        dlg.protocol_selector.setCurrentIndex(epsc_index)

        assert dlg.isVisible() is True
        assert dlg.trace_viewer.ax.get_ylabel() == "pA"
        assert "Spontaneous EPSCs" in dlg.trace_viewer.ax.get_title()

    def test_initial_note_is_editable(self, qtbot, abf_ap_fine, ap_fine_result):
        dlg = QCReviewDialog(
            "1666",
            str(abf_ap_fine),
            ap_fine_result,
            rmp_mv=-65.0,
            initial_note="Initial note",
        )
        qtbot.addWidget(dlg)

        dlg.notes_editor.appendPlainText("Follow-up")

        assert dlg.notes == "Initial note\nFollow-up"

    def test_auto_rejected_dialog_shows_automatic_verdict(
        self, qtbot, abf_ap_fine, ap_fine_result,
    ):
        dlg = QCReviewDialog(
            "1666",
            str(abf_ap_fine),
            ap_fine_result,
            rmp_mv=-40.0,
            auto_rejected=True,
        )
        qtbot.addWidget(dlg)

        labels = [label.text() for label in dlg.findChildren(QLabel)]
        buttons = [button.text() for button in dlg.findChildren(QPushButton)]
        assert "Automatic QC: REJECTED - RMP>Threshold" in labels
        assert "Override Auto-Reject" in buttons
        assert "Keep Rejected" in buttons

    def test_auto_reject_override_action_is_explicit(
        self, qtbot, abf_ap_fine, ap_fine_result,
    ):
        dlg = QCReviewDialog(
            "1666",
            str(abf_ap_fine),
            ap_fine_result,
            rmp_mv=-40.0,
            auto_rejected=True,
        )
        qtbot.addWidget(dlg)

        dlg._accept()

        assert dlg.accepted_result is True
        assert dlg.override_auto_reject is True
