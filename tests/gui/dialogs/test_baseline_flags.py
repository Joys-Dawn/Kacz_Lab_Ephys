import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from ephys_analysis.core.abf_io import load_abf, get_sweep_data
from ephys_analysis.core.types import BaselineFlag
from ephys_analysis.gui.dialogs.baseline_flags import BaselineReviewDialog


def _flag(path):
    abf = load_abf(path)
    return BaselineFlag(
        abf.protocol, str(path), -67,
        baseline_means_mv=[-50.0] * abf.sweepCount,
        out_of_range_sweeps=list(range(1, abf.sweepCount + 1)),
        changed_sweep_pairs=[(1, 2), (2, 3), (3, 4)],
    )


def test_shows_each_sweep_with_its_baseline_and_reason(qtbot, abf_ri_ih):
    flag = _flag(abf_ri_ih)
    dialog = BaselineReviewDialog([("1666", flag)])
    qtbot.addWidget(dialog)
    assert "1666" in dialog.heading.text()
    assert abf_ri_ih.name in dialog.heading.text()
    assert dialog.table.topLevelItemCount() == len(flag.baseline_means_mv)
    assert len(dialog.viewer.ax.lines) == len(flag.baseline_means_mv)
    row = dialog.table.topLevelItem(1)
    assert row.text(0) == "2"
    assert row.text(1) == "-50.00"
    assert "-77 to -57" in row.text(2)
    assert "1-2, 2-3" in row.text(3)
    assert row.checkState(0) == Qt.Checked
    assert dialog.decisions == {}


def test_selection_hides_sweeps_and_preserves_original_numbers(qtbot, abf_ri_ih):
    flag = _flag(abf_ri_ih)
    dialog = BaselineReviewDialog([("1666", flag)])
    qtbot.addWidget(dialog)
    dialog.table.topLevelItem(2).setCheckState(0, Qt.Unchecked)
    assert not dialog.viewer.ax.lines[2].get_visible()
    dialog.table.topLevelItem(2).setCheckState(0, Qt.Checked)
    assert dialog.viewer.ax.lines[2].get_visible()
    dialog.table.topLevelItem(5).setCheckState(0, Qt.Unchecked)
    dialog.keep_button.click()
    assert dialog.decisions == {flag.file_path: True}
    assert dialog.excluded_sweeps == {flag.file_path: {6}}
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_each_file_requires_decision_before_next_file(qtbot, abf_ri_ih, abf_ap_fine):
    first, second = _flag(abf_ri_ih), _flag(abf_ap_fine)
    dialog = BaselineReviewDialog([("1666", first), ("1666", second)])
    qtbot.addWidget(dialog)
    dialog.keep_button.click()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "File 2 of 2" in dialog.review_status.text()
    assert abf_ap_fine.name in dialog.heading.text()
    dialog.reject_button.click()
    assert dialog.decisions == {first.file_path: True, second.file_path: False}
    assert dialog.excluded_sweeps[second.file_path] == set(range(1, len(second.baseline_means_mv) + 1))
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_no_selected_sweeps_requires_explicit_file_rejection(qtbot, abf_ap_fine):
    dialog = BaselineReviewDialog([("1666", _flag(abf_ap_fine))])
    qtbot.addWidget(dialog)
    for row in range(dialog.table.topLevelItemCount()):
        dialog.table.topLevelItem(row).setCheckState(0, Qt.Unchecked)
    assert not dialog.keep_button.isEnabled()
    assert dialog.reject_button.isEnabled()
    assert dialog.decisions == {}
    dialog.cancel_button.click()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.decisions == {}


def test_preview_uses_corrected_voltages(qtbot, abf_ri_ih):
    dialog = BaselineReviewDialog([("1666", _flag(abf_ri_ih))], voltage_offset_mv=-10)
    qtbot.addWidget(dialog)
    original = get_sweep_data(load_abf(abf_ri_ih), 0)
    np.testing.assert_array_equal(dialog.viewer.ax.lines[0].get_ydata(), original - 10)
    assert "-10 mV" in dialog.review_status.text()


def test_sweep_list_scrolls_and_actions_remain_visible(qtbot, abf_ri_ih):
    dialog = BaselineReviewDialog([("1666", _flag(abf_ri_ih))])
    qtbot.addWidget(dialog)
    dialog.show()
    for width in (740, 1100, 900):
        dialog.resize(width, 650)
        qtbot.wait(30)
        assert dialog.table.verticalScrollBar().maximum() > 0
        for button in (dialog.keep_button, dialog.reject_button, dialog.cancel_button):
            assert dialog.rect().contains(button.geometry())
        for row in range(dialog.table.topLevelItemCount() - 1):
            first = dialog.table.visualItemRect(dialog.table.topLevelItem(row))
            second = dialog.table.visualItemRect(dialog.table.topLevelItem(row + 1))
            assert first.bottom() < second.top()
