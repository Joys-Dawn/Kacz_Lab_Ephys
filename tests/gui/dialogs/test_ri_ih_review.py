import pytest
from PySide6.QtWidgets import QPushButton

from ephys_analysis.core.types import RiIhContaminatedSweep
from ephys_analysis.gui.dialogs.ri_ih_review import RiIhReviewDialog


@pytest.mark.parametrize("label,expected", [
    ("Keep Recording", True), ("Remove Recording", False),
    ("Cancel Analysis", "cancel"),
])
def test_recording_review_actions(qtbot, abf_ri_ih, label, expected):
    sweeps = [RiIhContaminatedSweep(i, 0, True, False) for i in range(1, 7)]
    dialog = RiIhReviewDialog("1666", str(abf_ri_ih), sweeps)
    qtbot.addWidget(dialog)
    assert len(dialog.viewer.ax.lines) > 5
    next(button for button in dialog.findChildren(QPushButton) if button.text() == label).click()
    assert dialog.accepted_result == expected


def test_closing_review_cancels_analysis(qtbot, abf_ri_ih):
    dialog = RiIhReviewDialog("1666", str(abf_ri_ih), [])
    qtbot.addWidget(dialog)
    dialog.close()
    assert dialog.accepted_result == "cancel"
