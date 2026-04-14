from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
)
from PySide6.QtCore import Qt

from ephys_analysis.core.abf_io import load_abf, get_sweep_data, get_sweep_time
from ephys_analysis.core.types import APFineResult
from ephys_analysis.gui.widgets.phase_plot import PhasePlot
from ephys_analysis.gui.widgets.trace_viewer import TraceViewer


class QCReviewDialog(QDialog):
    """Dialog for reviewing voltage threshold QC on a single sample.

    Shows phase plot (left) and response signal (right) side by side,
    both with VThresh marked as a vertical dotted line.
    User accepts or rejects.
    """

    def __init__(self, sample_id: str, abf_path: str,
                 ap_result: APFineResult, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"QC Review — Sample {sample_id}")
        self.setMinimumSize(1000, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)
        self.accepted_result = None  # True = accept, False = reject, "cancel" = abort batch

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            f"Sample: {sample_id}  |  Sweep: {ap_result.sweep_num}  |  "
            f"VThresh: {ap_result.voltage_threshold_mv:.1f} mV  |  "
            f"Current: {ap_result.current_threshold_pa:.0f} pA"
        )
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Side-by-side plots
        plot_layout = QHBoxLayout()

        # Left: phase plot
        self.phase_plot = PhasePlot(self, figsize=(5, 4))
        self.phase_plot.plot_phase(
            ap_result.phase_plot_v,
            ap_result.phase_plot_dvdt,
            vthresh=ap_result.voltage_threshold_mv,
            title="Phase Plot (dV/dt vs mV)",
        )
        plot_layout.addWidget(self.phase_plot)

        # Right: response signal with VThresh line
        self.trace_viewer = TraceViewer(self, figsize=(5, 4))
        abf = load_abf(abf_path)
        # sweep_num is 1-indexed (customer convention); pyabf is 0-indexed.
        sweep_idx = ap_result.sweep_num - 1
        time = get_sweep_time(abf, sweep_idx)
        response = get_sweep_data(abf, sweep_idx, channel=0)
        self.trace_viewer.plot_single(
            time, response,
            title="Response Signal",
            ylabel="mV",
        )
        # Add a horizontal line at VThresh on the response plot
        self.trace_viewer.ax.axhline(
            ap_result.voltage_threshold_mv, color="red", linestyle="--",
            linewidth=1.0, label=f"VThresh = {ap_result.voltage_threshold_mv:.1f} mV",
        )
        self.trace_viewer.ax.legend(fontsize=8)
        self.trace_viewer.refresh()
        plot_layout.addWidget(self.trace_viewer)

        layout.addLayout(plot_layout)

        # Accept / Reject buttons
        btn_layout = QHBoxLayout()
        accept_btn = QPushButton("Accept")
        accept_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px 24px;")
        accept_btn.clicked.connect(self._accept)
        reject_btn = QPushButton("Reject")
        reject_btn.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 8px 24px;")
        reject_btn.clicked.connect(self._reject)
        cancel_btn = QPushButton("Cancel Analysis")
        cancel_btn.setStyleSheet("padding: 8px 24px;")
        cancel_btn.clicked.connect(self._cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(accept_btn)
        btn_layout.addWidget(reject_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            return  # ignore — user must click Accept or Reject
        super().keyPressEvent(event)

    def _accept(self):
        self.accepted_result = True
        self.accept()

    def _reject(self):
        self.accepted_result = False
        self.reject()

    def _cancel(self):
        self.accepted_result = "cancel"
        self.reject()
