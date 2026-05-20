"""Zoomed AP-waveform widget for QC review.

Plots the membrane-potential trace within the threshold-detection window
as clickable sample markers. The user clicks on a marker to override the
auto-detected voltage threshold. dV/dt is overlaid on a secondary y-axis
with the criterion line (28 mV/ms) so the user can visually confirm that
the clicked sample is the first one above the criterion.
"""
import numpy as np
from PySide6.QtCore import Signal

from ephys_analysis.core.types import DVDT_CRITERION_MV_MS
from ephys_analysis.gui.widgets.plot_canvas import PlotCanvas, MiniNavToolbar


class APThresholdPicker(PlotCanvas):
    """Widget for picking a voltage-threshold sample on an AP rise.

    Emits ``threshold_picked(index)`` when the user clicks a marker. ``index``
    is into the ``v``/``dvdt`` arrays passed to ``plot_ap``.
    """

    threshold_picked = Signal(int)

    def __init__(self, parent=None, figsize=(5, 4)):
        super().__init__(parent, figsize=figsize)
        self._v: np.ndarray | None = None
        self._t_ms: np.ndarray | None = None
        self._dvdt: np.ndarray | None = None
        self._auto_idx: int = 0
        self._selected_idx: int = 0
        self._line_v = None
        self._line_dvdt = None
        self._auto_marker = None
        self._selected_marker = None
        self._ax_dvdt = None
        # Home + Pan + Zoom — criterion-crossing samples pile up visually and
        # need zoom for precise picking; Home returns to the default zoomed
        # view from plot_ap.
        self.toolbar = MiniNavToolbar(self.canvas, self)
        self.layout().insertWidget(0, self.toolbar)
        self.canvas.mpl_connect("pick_event", self._on_pick)

    def plot_ap(
        self,
        t_ms: np.ndarray,
        v: np.ndarray,
        dvdt: np.ndarray,
        auto_idx: int,
        zoom_ms: float = 5.0,
    ) -> None:
        """Render the AP trace and let the user click sample markers.

        Args:
            t_ms: time (ms) for each sample. Same length as v and dvdt.
            v: membrane potential (mV) at each sample.
            dvdt: dV/dt (mV/ms) at each sample. Same time-alignment as v.
            auto_idx: index of the auto-detected threshold sample.
            zoom_ms: width of the x-axis view, centered on auto_idx.
        """
        self._t_ms = np.asarray(t_ms, dtype=float)
        self._v = np.asarray(v, dtype=float)
        self._dvdt = np.asarray(dvdt, dtype=float)
        self._auto_idx = int(auto_idx)
        self._selected_idx = int(auto_idx)

        self.ax.clear()
        if self._ax_dvdt is not None:
            self._ax_dvdt.remove()

        # Primary axis: V vs t with clickable markers (one per sample).
        # picker=5 means clicks within 5 pixels of a marker register as a pick.
        (self._line_v,) = self.ax.plot(
            self._t_ms, self._v, "-",
            color="black", linewidth=0.8, marker="o",
            markersize=4, markerfacecolor="white",
            markeredgecolor="black", picker=5,
        )

        # Markers for auto-detected and current selection.
        self._auto_marker = self.ax.plot(
            self._t_ms[self._auto_idx], self._v[self._auto_idx],
            "o", color="orange", markersize=10, markerfacecolor="none",
            markeredgewidth=2.0, label="Auto-detected", zorder=5,
        )[0]
        self._selected_marker = self.ax.plot(
            self._t_ms[self._selected_idx], self._v[self._selected_idx],
            "o", color="red", markersize=12, markerfacecolor="none",
            markeredgewidth=2.0, label="Selected", zorder=6,
        )[0]

        self.ax.set_xlabel("Time (ms)")
        self.ax.set_ylabel("V (mV)")
        self.ax.set_title("AP — click a marker to override VThresh")

        # Secondary axis: dV/dt with criterion line.
        self._ax_dvdt = self.ax.twinx()
        (self._line_dvdt,) = self._ax_dvdt.plot(
            self._t_ms, self._dvdt, "-",
            color="steelblue", linewidth=0.8, alpha=0.6,
            label="dV/dt",
        )
        self._ax_dvdt.axhline(
            DVDT_CRITERION_MV_MS, color="steelblue", linestyle="--",
            linewidth=0.8, alpha=0.6,
            label=f"Criterion = {DVDT_CRITERION_MV_MS:.0f} mV/ms",
        )
        self._ax_dvdt.set_ylabel("dV/dt (mV/ms)", color="steelblue")
        self._ax_dvdt.tick_params(axis="y", labelcolor="steelblue")

        # twinx places the new axis in front, which intercepts pick events on
        # self.ax's line. Lift self.ax above _ax_dvdt and make its patch
        # transparent so dV/dt remains visible underneath but the picker line
        # receives the click.
        self.ax.set_zorder(self._ax_dvdt.get_zorder() + 1)
        self.ax.patch.set_visible(False)

        # Zoom: ±zoom_ms/2 around auto_idx.
        t_center = self._t_ms[self._auto_idx]
        self.ax.set_xlim(t_center - zoom_ms / 2.0, t_center + zoom_ms / 2.0)

        # Combine legends from both axes.
        lines, labels = self.ax.get_legend_handles_labels()
        lines2, labels2 = self._ax_dvdt.get_legend_handles_labels()
        self.ax.legend(lines + lines2, labels + labels2, fontsize=8, loc="upper left")
        self.refresh()

    @property
    def selected_idx(self) -> int:
        return self._selected_idx

    @property
    def auto_idx(self) -> int:
        return self._auto_idx

    def selected_voltage_mv(self) -> float:
        if self._v is None:
            return float("nan")
        return float(self._v[self._selected_idx])

    def selected_dvdt_mv_ms(self) -> float:
        if self._dvdt is None:
            return float("nan")
        return float(self._dvdt[self._selected_idx])

    def selected_time_ms(self) -> float:
        if self._t_ms is None:
            return float("nan")
        return float(self._t_ms[self._selected_idx])

    def select_index(self, idx: int) -> None:
        """Programmatically move the selection. Useful for tests."""
        if self._v is None or self._t_ms is None:
            return
        idx = int(idx)
        if idx < 0 or idx >= len(self._v):
            return
        self._selected_idx = idx
        self._selected_marker.set_data([self._t_ms[idx]], [self._v[idx]])
        self.refresh()
        self.threshold_picked.emit(idx)

    def _on_pick(self, event):
        if self._line_v is None or event.artist is not self._line_v:
            return
        ind = getattr(event, "ind", None)
        if ind is None or len(ind) == 0:
            return
        # If the click was near multiple markers, pick the one whose x is
        # closest to the click's xdata.
        mouse = getattr(event, "mouseevent", None)
        if mouse is not None and mouse.xdata is not None and self._t_ms is not None:
            click_t = float(mouse.xdata)
            idx = min(ind, key=lambda i: abs(self._t_ms[i] - click_t))
        else:
            idx = int(ind[0])
        self.select_index(int(idx))
