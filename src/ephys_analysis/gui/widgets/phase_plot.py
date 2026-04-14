import numpy as np
from ephys_analysis.core.types import DVDT_CRITERION_MV_MS
from ephys_analysis.gui.widgets.plot_canvas import PlotCanvas


class PhasePlot(PlotCanvas):
    """Widget for dV/dt vs mV phase plot with voltage threshold marker."""

    def plot_phase(self, v: np.ndarray | list, dvdt: np.ndarray | list,
                   vthresh: float | None = None, title: str = "Phase Plot"):
        self.ax.clear()
        v_arr = np.asarray(v)
        dvdt_arr = np.asarray(dvdt)
        self.ax.plot(v_arr, dvdt_arr, linewidth=0.8, color="black", marker="o",
                     markersize=2.5, markerfacecolor="black")
        self.ax.axhline(DVDT_CRITERION_MV_MS, color="orange", linestyle="--",
                        linewidth=1.2, label=f"Criterion = {DVDT_CRITERION_MV_MS:.0f} mV/ms")
        if vthresh is not None:
            self.ax.axvline(vthresh, color="red", linestyle="--",
                            linewidth=1.2, label=f"VThresh = {vthresh:.1f} mV")
            # Highlight the exact sample chosen as the criterion crossing.
            crossings = np.where(dvdt_arr > DVDT_CRITERION_MV_MS)[0]
            if len(crossings):
                idx = crossings[0]
                self.ax.plot(v_arr[idx], dvdt_arr[idx], "o", color="red",
                             markersize=8, markerfacecolor="none",
                             markeredgewidth=1.5,
                             label=f"Crossing: {dvdt_arr[idx]:.1f} mV/ms")
        self.ax.legend(fontsize=8, loc="upper left")
        self.ax.set_xlabel("Membrane Potential (mV)")
        self.ax.set_ylabel("dV/dt (mV/ms)")
        self.ax.set_title(title)
        self.refresh()
