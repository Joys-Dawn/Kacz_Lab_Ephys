from pathlib import Path

import numpy as np

from ephys_analysis.core.abf_io import load_abf, get_sweep_data, get_sweep_time, get_protocol_name
from ephys_analysis.gui.widgets.plot_canvas import PlotCanvas


class TraceViewer(PlotCanvas):
    """Widget for plotting ABF sweep traces (response + stimulus)."""

    def plot_abf(self, path: str | Path, max_sweeps: int = 10):
        """Load an ABF file and plot its sweeps."""
        abf = load_abf(path)
        time = get_sweep_time(abf)
        sweeps = [get_sweep_data(abf, i, channel=0)
                  for i in range(min(abf.sweepCount, max_sweeps))]
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
            label = labels[i] if labels else f"Sweep {i}"
            self.ax.plot(time[:len(sweep)], sweep, label=label, linewidth=0.8)
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel(ylabel)
        if title:
            self.ax.set_title(title)
        if labels and len(labels) <= 10:
            self.ax.legend(fontsize=7)
        self.refresh()

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
