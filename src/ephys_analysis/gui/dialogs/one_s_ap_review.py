from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from ephys_analysis.core.types import OneSAPResult
from ephys_analysis.gui.widgets.trace_viewer import TraceViewer
from ephys_analysis.protocols import PROTO_1S_AP, PROTO_RI_IH


def _sweep_text(sweeps: list[int]) -> str:
    return ", ".join(str(sweep) for sweep in sweeps)


def _ap_count_text(count: int) -> str:
    return f"{count} AP" if count == 1 else f"{count} APs"


def _ap_drop_text(result: OneSAPResult) -> list[str]:
    lines = []
    for sweep_num in result.sudden_drop_sweeps:
        previous_count = result.sweeps[sweep_num - 2].raw_spike_count
        dropped_count = result.sweeps[sweep_num - 1].raw_spike_count
        lines.append(
            f"AP drop: sweep {sweep_num - 1} had "
            f"{_ap_count_text(previous_count)}; sweep {sweep_num} had "
            f"{_ap_count_text(dropped_count)}"
        )
    return lines


class OneSAPReviewDialog(QDialog):
    """Review a 1-second AP recording that triggered one or more flags."""

    def __init__(
        self,
        sample_id: str,
        protocol_paths: dict[str, str],
        result: OneSAPResult,
        parent=None,
        initial_note: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle(f"1s AP Review - Sample {sample_id}")
        self.setMinimumSize(900, 600)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        self.accepted_result = None  # True / False / "cancel"
        self._protocol_paths = protocol_paths

        one_s_path = protocol_paths.get(PROTO_1S_AP)
        if not one_s_path:
            raise ValueError("Flagged 1s AP review requires a 1s AP file")

        layout = QVBoxLayout(self)

        header = QLabel(f"Sample {sample_id}")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        flags = []
        if result.sudden_drop_sweeps:
            flags.extend(_ap_drop_text(result))
        if result.baseline_at_or_above_zero_sweeps:
            flags.append(
                "Stimulus baseline >= 0 mV at sweep(s): "
                + _sweep_text(result.baseline_at_or_above_zero_sweeps)
            )
        if result.high_firing_sweeps:
            flags.append(
                "At least 100 APs at sweep(s): "
                + _sweep_text(result.high_firing_sweeps)
            )
        self.flag_label = QLabel("\n".join(flags))
        self.flag_label.setWordWrap(True)
        layout.addWidget(self.flag_label)

        plots = QHBoxLayout()
        self.one_s_viewer = TraceViewer(self, figsize=(7, 4))
        self.one_s_viewer.plot_abf(one_s_path)
        plots.addWidget(self.one_s_viewer)

        self.rin_viewer: TraceViewer | None = None
        rin_path = protocol_paths.get(PROTO_RI_IH)
        if result.high_firing_sweeps and rin_path:
            self.rin_viewer = TraceViewer(self, figsize=(7, 4))
            self.rin_viewer.plot_abf(rin_path)
            plots.addWidget(self.rin_viewer)
            self.setMinimumWidth(1200)
        layout.addLayout(plots)

        self.sweep_table = QTreeWidget()
        self.sweep_table.setHeaderLabels(["Include sweep", "Current (pA)", "APs", "FF (Hz)"])
        self.sweep_table.setRootIsDecorated(False)
        self.sweep_table.setMaximumHeight(180)
        for number, sweep in enumerate(result.sweeps, start=1):
            item = QTreeWidgetItem([
                str(number), f"{sweep.current_pa:g}", str(sweep.spike_count),
                f"{sweep.firing_freq_hz:g}",
            ])
            item.setCheckState(0, Qt.Unchecked if sweep.excluded else Qt.Checked)
            self.sweep_table.addTopLevelItem(item)
        self.sweep_table.itemChanged.connect(self._update_sweep_visibility)
        layout.addWidget(self.sweep_table)

        notes_label = QLabel("Notes")
        self.notes_editor = QPlainTextEdit()
        notes_label.setBuddy(self.notes_editor)
        self.notes_editor.setPlainText(initial_note)
        self.notes_editor.setMaximumHeight(90)
        layout.addWidget(notes_label)
        layout.addWidget(self.notes_editor)

        buttons = QHBoxLayout()
        keep_btn = QPushButton("Keep Selected Sweeps")
        keep_btn.clicked.connect(self._keep)
        remove_btn = QPushButton("Remove 1s AP Recording")
        remove_btn.clicked.connect(self._remove)
        cancel_btn = QPushButton("Cancel Analysis")
        cancel_btn.clicked.connect(self._cancel)
        buttons.addStretch()
        buttons.addWidget(keep_btn)
        buttons.addWidget(remove_btn)
        buttons.addWidget(cancel_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

    @property
    def notes(self) -> str:
        return self.notes_editor.toPlainText().strip()

    @property
    def excluded_sweeps(self) -> set[int]:
        return {
            row + 1 for row in range(self.sweep_table.topLevelItemCount())
            if self.sweep_table.topLevelItem(row).checkState(0) != Qt.Checked
        }

    def _update_sweep_visibility(self, item, column):
        row = self.sweep_table.indexOfTopLevelItem(item)
        self.one_s_viewer.ax.lines[row].set_visible(item.checkState(0) == Qt.Checked)
        self.one_s_viewer.refresh()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            return
        super().keyPressEvent(event)

    def _keep(self):
        self.accepted_result = True
        self.accept()

    def _remove(self):
        self.accepted_result = False
        self.reject()

    def _cancel(self):
        self.accepted_result = "cancel"
        self.reject()
