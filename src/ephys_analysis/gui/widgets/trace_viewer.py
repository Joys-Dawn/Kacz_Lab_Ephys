from pathlib import Path

import numpy as np

from ephys_analysis.core.abf_io import load_abf, get_sweep_data, get_sweep_time, get_protocol_name
from ephys_analysis.gui.widgets.plot_canvas import PlotCanvas


class TraceViewer(PlotCanvas):
    """Widget for plotting ABF sweep traces (response + stimulus)."""

    def plot_abf(self, path: str | Path, max_sweeps: int | None = None):
        """Load an ABF file and plot its sweeps.

        max_sweeps=None plots every sweep — needed for Ih (20 sweeps) and 1s
        AP firing (15 sweeps), which used to truncate at 10.
        """
        abf = load_abf(path)
        time = get_sweep_time(abf)
        n = abf.sweepCount if max_sweeps is None else min(abf.sweepCount, max_sweeps)
        sweeps = [get_sweep_data(abf, i, channel=0) for i in range(n)]
        labels = [f"Sweep {i}" for i in range(len(sweeps))]
        protocol = get_protocol_name(abf)
        self.plot_sweeps(
            time, sweeps, labels=labels,
            title=f"{Path(path).name} — {protocol}",
        )

    def plot_sweeps(self, time: np.ndarray, sweeps: list[np.ndarray],
                    labels: list[str] | None = None,
                    title: str = "", ylabel: str = "mV"):
        self.ax.clear()
        for i, sweep in enumerate(sweeps):
            self.ax.plot(time[:len(sweep)], sweep, linewidth=0.8)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel(ylabel)
        if title:
            self.ax.set_title(title)
        # No legend — at 15-20 sweeps it covers a chunk of the plot, and at
        # 1-2 sweeps it tells you nothing the cursor readout can't.
        # Identify the hovered sweep through the toolbar's coord readout.
        self._hover_time = np.asarray(time, dtype=float)
        self._hover_sweeps = [np.asarray(s, dtype=float) for s in sweeps]
        self._hover_labels = labels if labels else [f"Sweep {i}" for i in range(len(sweeps))]
        self._hover_ylabel = ylabel
        self.ax.format_coord = self._format_coord_sweeps
        self.refresh()

    def _format_coord_sweeps(self, x: float, y: float) -> str:
        """Toolbar readout. Names the nearest sweep ONLY when the cursor is
        visually close to a trace — otherwise the readout would invent a
        sweep label for empty space far above/below every line.
        """
        time = getattr(self, "_hover_time", None)
        sweeps = getattr(self, "_hover_sweeps", None)
        plain = f"x={x:.3f} s, y={y:.2f} {self._hover_ylabel}"
        if time is None or sweeps is None or len(time) == 0:
            return plain
        # Cursor must be within the plotted time range, otherwise it's not
        # hovering over any sweep.
        if x < float(time[0]) or x > float(time[-1]):
            return plain
        # Nearest sample index to cursor x — searchsorted gives the right
        # neighbour; back off one if the left neighbour is actually closer.
        idx = int(np.clip(np.searchsorted(time, x), 0, len(time) - 1))
        if idx > 0 and abs(time[idx - 1] - x) < abs(time[idx] - x):
            idx -= 1
        best_label = None
        best_dist = float("inf")
        for label, sweep in zip(self._hover_labels, sweeps, strict=True):
            if idx >= len(sweep):
                continue
            d = abs(float(sweep[idx]) - y)
            if d < best_dist:
                best_dist = d
                best_label = label
        if best_label is None:
            return plain
        # Only label the sweep when the cursor is within ~3% of the y-axis
        # range of that sweep's value at this x — about a line-width visually.
        y0, y1 = self.ax.get_ylim()
        threshold = 0.03 * abs(y1 - y0)
        if best_dist > threshold:
            return plain
        return f"{best_label}  x={x:.3f} s  y={y:.2f} {self._hover_ylabel}"

    def plot_single(self, time: np.ndarray, data: np.ndarray,
                    title: str = "", ylabel: str = "mV",
                    vlines: list[float] | None = None):
        self.ax.clear()
        self.ax.plot(time[:len(data)], data, linewidth=0.8)
        if vlines:
            for x in vlines:
                self.ax.axvline(x, color="red", linestyle="--", linewidth=0.8)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel(ylabel)
        if title:
            self.ax.set_title(title)
        self.refresh()
