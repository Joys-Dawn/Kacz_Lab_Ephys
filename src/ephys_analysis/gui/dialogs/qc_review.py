import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import Qt

from ephys_analysis.core.abf_io import (
    load_abf, get_sweep_data, get_sweep_time, get_sampling_rate,
)
from ephys_analysis.core.types import APFineResult, DVDT_CRITERION_MV_MS
from ephys_analysis.gui.widgets.ap_threshold_picker import APThresholdPicker
from ephys_analysis.gui.widgets.plot_canvas import MiniNavToolbar
from ephys_analysis.gui.widgets.trace_viewer import TraceViewer

# VThresh detection window (must match the analyzer in protocols/ap.py).
VTHRESH_WINDOW_START_SEC = 0.2975
VTHRESH_WINDOW_END_SEC = 0.3015


class QCReviewDialog(QDialog):
    """Dialog for reviewing — and optionally overriding — the voltage threshold.

    The left pane shows the AP rise as clickable sample markers with a dV/dt
    overlay. The user clicks the sample they consider the true threshold; we
    update the displayed VThresh, the live QC verdict, and (on Accept) record
    the override so the pipeline mutates the result and re-applies the gate.
    """

    def __init__(self, sample_id: str, abf_path: str,
                 ap_result: APFineResult, rmp_mv: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"QC Review — Sample {sample_id}")
        self.setMinimumSize(1000, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

        self._rmp_mv = rmp_mv
        self._auto_vthresh_mv = ap_result.voltage_threshold_mv
        self.accepted_result = None  # True / False / "cancel"
        self.override_vthresh_mv: float | None = None  # set on Accept if changed

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            f"Sample: {sample_id}  |  Sweep: {ap_result.sweep_num}  |  "
            f"RMP: {rmp_mv:.1f} mV  |  Current: {ap_result.current_threshold_pa:.0f} pA"
        )
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        # Plots side-by-side
        plot_layout = QHBoxLayout()
        self.picker = APThresholdPicker(self, figsize=(5, 4))
        plot_layout.addWidget(self.picker)

        self.trace_viewer = TraceViewer(self, figsize=(5, 4))
        # Matching toolbar so the canvas tops align with the picker's, and so
        # the user can also zoom into the AP within the full-sweep view.
        self._trace_toolbar = MiniNavToolbar(self.trace_viewer.canvas, self.trace_viewer)
        self.trace_viewer.layout().insertWidget(0, self._trace_toolbar)
        abf = load_abf(abf_path)
        rate = get_sampling_rate(abf)
        sweep_idx = ap_result.sweep_num - 1  # sweep_num is 1-indexed
        time = get_sweep_time(abf, sweep_idx)
        response = get_sweep_data(abf, sweep_idx, channel=0)
        self.trace_viewer.plot_single(
            time, response, title="Full Sweep", ylabel="mV",
        )
        self._vthresh_line = self.trace_viewer.ax.axhline(
            ap_result.voltage_threshold_mv, color="red", linestyle="--",
            linewidth=1.0,
        )
        self.trace_viewer.refresh()
        plot_layout.addWidget(self.trace_viewer)
        layout.addLayout(plot_layout)

        # Build the picker's data from the same forward-diff convention used
        # by the analyzer (spike.find_voltage_threshold), so the auto-detected
        # sample lands at the exact index the analyzer chose.
        i0 = int(round(VTHRESH_WINDOW_START_SEC * rate))
        i1 = int(round(VTHRESH_WINDOW_END_SEC * rate))
        segment = response[i0:i1]
        dt_ms = 1000.0 / rate
        dvdt = np.diff(segment) / dt_ms
        v = segment[1:]
        # t for each sample: position of segment[i+1] within the sweep, in ms.
        t_ms = (i0 + 1 + np.arange(len(v))) * dt_ms
        crossings = np.where(dvdt > DVDT_CRITERION_MV_MS)[0]
        auto_idx = int(crossings[0]) if len(crossings) else 0

        self.picker.plot_ap(t_ms, v, dvdt, auto_idx=auto_idx, zoom_ms=5.0)
        self.picker.threshold_picked.connect(self._on_pick)

        # Readout panel
        readout = QFrame()
        readout.setFrameShape(QFrame.StyledPanel)
        readout_layout = QHBoxLayout(readout)
        self._readout_label = QLabel()
        self._readout_label.setStyleSheet("font-family: monospace;")
        self._qc_label = QLabel()
        self._qc_label.setStyleSheet("font-weight: bold;")
        readout_layout.addWidget(self._readout_label)
        readout_layout.addStretch()
        readout_layout.addWidget(self._qc_label)
        layout.addWidget(readout)
        self._refresh_readout()

        # Buttons
        btn_layout = QHBoxLayout()
        self._accept_btn = QPushButton("Accept")
        self._accept_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; "
            "padding: 8px 24px;"
        )
        self._accept_btn.clicked.connect(self._accept)
        reject_btn = QPushButton("Reject")
        reject_btn.setStyleSheet(
            "background-color: #f44336; color: white; font-weight: bold; "
            "padding: 8px 24px;"
        )
        reject_btn.clicked.connect(self._reject)
        reset_btn = QPushButton("Reset to auto-detected")
        reset_btn.setStyleSheet("padding: 8px 16px;")
        reset_btn.clicked.connect(self._reset)
        cancel_btn = QPushButton("Cancel Analysis")
        cancel_btn.setStyleSheet("padding: 8px 24px;")
        cancel_btn.clicked.connect(self._cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self._accept_btn)
        btn_layout.addWidget(reject_btn)
        btn_layout.addWidget(reset_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            return  # ignore — user must click Accept or Reject
        super().keyPressEvent(event)

    def _current_vthresh_mv(self) -> float:
        return self.picker.selected_voltage_mv()

    def _refresh_readout(self):
        v = self.picker.selected_voltage_mv()
        dvdt = self.picker.selected_dvdt_mv_ms()
        is_override = self.picker.selected_idx != self.picker.auto_idx
        delta = v - self._auto_vthresh_mv
        tag = " (user override)" if is_override else " (auto)"
        self._readout_label.setText(
            f"VThresh = {v:.2f} mV{tag}   "
            f"dV/dt at point = {dvdt:.1f} mV/ms   "
            f"Δvs auto = {delta:+.2f} mV"
        )
        if v > self._rmp_mv:
            self._qc_label.setText("QC: PASS")
            self._qc_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
        else:
            self._qc_label.setText("QC: FAIL (VThresh ≤ RMP)")
            self._qc_label.setStyleSheet("color: #c62828; font-weight: bold;")
        # Move the horizontal VThresh line on the right-side trace.
        self._vthresh_line.set_ydata([v, v])
        self.trace_viewer.refresh()

    def _on_pick(self, _idx: int):
        self._refresh_readout()

    def _reset(self):
        self.picker.select_index(self.picker.auto_idx)

    def _accept(self):
        self.accepted_result = True
        if self.picker.selected_idx != self.picker.auto_idx:
            self.override_vthresh_mv = self._current_vthresh_mv()
        self.accept()

    def _reject(self):
        self.accepted_result = False
        self.reject()

    def _cancel(self):
        self.accepted_result = "cancel"
        self.reject()
