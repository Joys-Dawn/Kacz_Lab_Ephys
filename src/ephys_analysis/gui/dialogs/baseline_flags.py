from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QSplitter,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from ephys_analysis.core.types import BaselineFlag
from ephys_analysis.gui.widgets.trace_viewer import TraceViewer


class BaselineReviewDialog(QDialog):
    """Review one flagged recording at a time for the current sample."""

    def __init__(self, flags: list[tuple[str, BaselineFlag]], parent=None, *, voltage_offset_mv=0.0):
        super().__init__(parent)
        self.setWindowTitle("Baseline QC Review")
        self.setModal(True)
        self._flags = flags
        self._index = 0
        self._voltage_offset_mv = voltage_offset_mv
        self.decisions: dict[str, bool] = {}
        self.excluded_sweeps: dict[str, set[int]] = {}

        layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setWordWrap(True)
        self.heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.heading)
        self.review_status = QLabel()
        layout.addWidget(self.review_status)

        splitter = QSplitter(Qt.Vertical)
        self.viewer = TraceViewer(self, figsize=(8, 4))
        splitter.addWidget(self.viewer)
        self.table = QTreeWidget()
        self.table.setHeaderLabels([
            "Include sweep", "Baseline (mV)", "Outside range (mV)", "Change >=4 mV (pairs)",
        ])
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(100)
        self.table.itemChanged.connect(self._update_sweep_visibility)
        splitter.addWidget(self.table)
        splitter.setSizes([400, 180])
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self.keep_button = QPushButton("Keep Selected Sweeps")
        self.keep_button.clicked.connect(lambda: self._decide(True))
        self.reject_button = QPushButton("Reject File")
        self.reject_button.clicked.connect(lambda: self._decide(False))
        self.cancel_button = QPushButton("Cancel Analysis")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addStretch()
        for button in (self.keep_button, self.reject_button, self.cancel_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        available = self.screen().availableGeometry()
        self.resize(min(1100, available.width() - 40), min(750, available.height() - 40))
        self._show_file()

    def _show_file(self):
        sample_id, flag = self._flags[self._index]
        self.heading.setText(f"Sample {sample_id} | {Path(flag.file_path).name}\n{flag.protocol}")
        self.review_status.setText(
            f"File {self._index + 1} of {len(self._flags)} | "
            f"Voltage offset: {self._voltage_offset_mv:+g} mV"
        )
        self.viewer.plot_abf(flag.file_path, voltage_offset_mv=self._voltage_offset_mv)
        self.table.blockSignals(True)
        self.table.clear()
        for number, baseline in enumerate(flag.baseline_means_mv, start=1):
            outside = (
                f"{flag.target_mv - 10:g} to {flag.target_mv + 10:g}"
                if number in flag.out_of_range_sweeps else ""
            )
            pairs = [f"{a}-{b}" for a, b in flag.changed_sweep_pairs if number in (a, b)]
            item = QTreeWidgetItem([str(number), f"{baseline:.2f}", outside, ", ".join(pairs)])
            item.setCheckState(0, Qt.Checked)
            self.table.addTopLevelItem(item)
        self.table.blockSignals(False)
        self.keep_button.setEnabled(self.table.topLevelItemCount() > 0)

    def _update_sweep_visibility(self, item, column):
        row = self.table.indexOfTopLevelItem(item)
        self.viewer.ax.lines[row].set_visible(item.checkState(0) == Qt.Checked)
        self.viewer.refresh()
        self.keep_button.setEnabled(any(
            self.table.topLevelItem(i).checkState(0) == Qt.Checked
            for i in range(self.table.topLevelItemCount())
        ))

    def _decide(self, keep: bool):
        _, flag = self._flags[self._index]
        self.decisions[flag.file_path] = keep
        self.excluded_sweeps[flag.file_path] = {
            row + 1 for row in range(self.table.topLevelItemCount())
            if not keep or self.table.topLevelItem(row).checkState(0) != Qt.Checked
        }
        self._index += 1
        if self._index == len(self._flags):
            self.accept()
        else:
            self._show_file()
