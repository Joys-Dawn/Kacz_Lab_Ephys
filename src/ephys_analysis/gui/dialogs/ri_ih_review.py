from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ephys_analysis.core.types import RiIhContaminatedSweep
from ephys_analysis.gui.widgets.trace_viewer import TraceViewer


class RiIhReviewDialog(QDialog):
    def __init__(
        self, sample_id: str, path: str,
        sweeps: list[RiIhContaminatedSweep], parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Rin Review - Sample {sample_id}")
        self.resize(900, 600)
        self.accepted_result = "cancel"
        layout = QVBoxLayout(self)
        summary = QLabel(
            f"{len(sweeps)} contaminated sweeps: "
            + ", ".join(str(sweep.sweep_num) for sweep in sweeps)
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        self.viewer = TraceViewer(self)
        self.viewer.plot_abf(path)
        layout.addWidget(self.viewer)
        buttons = QHBoxLayout()
        for label, result in (
            ("Keep Recording", True), ("Remove Recording", False),
            ("Cancel Analysis", "cancel"),
        ):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, value=result: self._finish(value))
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _finish(self, result):
        self.accepted_result = result
        self.accept()

    def keyPressEvent(self, event):
        if event.key() != Qt.Key_Escape:
            super().keyPressEvent(event)
