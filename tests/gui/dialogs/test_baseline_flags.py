from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from ephys_analysis.core.types import BaselineFlag
from ephys_analysis.gui.dialogs.baseline_flags import BaselineReviewDialog


def _flag(
    file_number: int = 1,
    *,
    sweeps: list[int] | None = None,
) -> BaselineFlag:
    return BaselineFlag(
        protocol="4. Ih and Input Resistance",
        file_path=f"C:/data/recording_{file_number:04d}.abf",
        target_mv=-67.0,
        baseline_means_mv=[-50.0],
        out_of_range_sweeps=sweeps or [1],
        changed_sweep_pairs=[(3, 4), (15, 16), (16, 17)],
    )


def test_shows_one_compact_row_per_flag(qtbot):
    dialog = BaselineReviewDialog([("1542", _flag())])
    qtbot.addWidget(dialog)

    assert dialog.table.topLevelItemCount() == 1
    item = dialog.table.topLevelItem(0)
    reason = item.text(3)
    assert item.text(0) == "1542"
    assert item.text(1) == "recording_0001.abf"
    assert item.text(2) == "4. Ih and Input Resistance"
    assert "sweeps 1" in reason
    assert "pairs 3-4, 15-16, 16-17" in reason


def test_consecutive_sweeps_are_collapsed_into_ranges(qtbot):
    dialog = BaselineReviewDialog([
        ("1542", _flag(sweeps=list(range(1, 17)) + list(range(19, 23)))),
    ])
    qtbot.addWidget(dialog)

    reason = dialog.table.topLevelItem(0).text(3)
    assert "sweeps 1-16, 19-22" in reason
    assert "1, 2, 3" not in reason


def test_reason_wraps_and_preview_does_not_take_stretch_width(qtbot):
    dialog = BaselineReviewDialog([("1542", _flag())])
    qtbot.addWidget(dialog)
    dialog.resize(1100, 650)
    dialog.show()
    qtbot.wait(20)

    item = dialog.table.topLevelItem(0)
    assert "\n" in item.text(3)
    assert dialog.table.itemDelegateForColumn(3) is dialog._reason_delegate
    assert dialog.table.visualItemRect(item).height() > 36
    assert dialog.table.header().stretchLastSection() is False
    assert dialog.table.columnWidth(3) > dialog.table.columnWidth(5)
    assert dialog.table.columnWidth(5) == 90


def test_long_list_scrolls_inside_bounded_dialog(qtbot):
    flags = [(str(1500 + i), _flag(i)) for i in range(80)]
    dialog = BaselineReviewDialog(flags)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(20)

    available = dialog.screen().availableGeometry()
    assert dialog.height() <= min(680, available.height() - 40)
    assert dialog.width() <= min(1100, available.width() - 40)
    assert dialog.table.verticalScrollBar().maximum() > 0
    assert dialog.table.horizontalScrollBar().maximum() == 0
    assert dialog.table.wordWrap() is False
    assert dialog.table.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded


def test_each_file_requires_an_explicit_decision(qtbot):
    first = _flag(1)
    second = _flag(2)
    dialog = BaselineReviewDialog([
        ("1542", first),
        ("1543", second),
    ])
    qtbot.addWidget(dialog)

    assert dialog.decisions == {}
    assert dialog.continue_button.isEnabled() is False

    first_accept, _ = dialog._decision_radios[first.file_path]
    _, second_reject = dialog._decision_radios[second.file_path]
    first_accept.setChecked(True)

    assert dialog.continue_button.isEnabled() is False
    assert dialog.review_status.text() == "1 of 2 files reviewed"

    second_reject.setChecked(True)

    assert dialog.decisions == {
        first.file_path: True,
        second.file_path: False,
    }
    assert dialog.continue_button.isEnabled() is True
    assert dialog.review_status.text() == "2 of 2 files reviewed"


def test_dialog_has_continue_cancel_and_preview_actions(qtbot):
    dialog = BaselineReviewDialog([("1542", _flag())])
    qtbot.addWidget(dialog)
    button_text = {
        button.text() for button in dialog.findChildren(QPushButton)
    }

    assert {"Preview", "Continue Analysis", "Cancel Analysis"} <= button_text


def test_preview_plots_every_sweep(qtbot, monkeypatch):
    flag = _flag()
    plotted = []
    monkeypatch.setattr(
        "ephys_analysis.gui.dialogs.baseline_flags.TraceViewer.plot_abf",
        lambda self, path, max_sweeps=None: plotted.append((path, max_sweeps)),
    )
    dialog = BaselineReviewDialog([("1542", flag)])
    qtbot.addWidget(dialog)

    dialog._preview(Path(flag.file_path))

    assert plotted == [(Path(flag.file_path), None)]
