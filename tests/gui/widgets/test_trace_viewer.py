import numpy as np

from ephys_analysis.gui.widgets.trace_viewer import TraceViewer


class TestPlotSweeps:
    def test_plots_one_line_per_sweep(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 100)
        sweeps = [np.sin(time), np.cos(time), np.sin(time) * 2]

        viewer.plot_sweeps(time, sweeps, labels=["a", "b", "c"])

        assert len(viewer.ax.lines) == 3

    def test_sets_axis_labels(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 10)

        viewer.plot_sweeps(time, [np.zeros(10)], labels=["a"], ylabel="pA")

        assert viewer.ax.get_xlabel() == "Time (s)"
        assert viewer.ax.get_ylabel() == "pA"

    def test_sets_title_when_provided(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 10)

        viewer.plot_sweeps(time, [np.zeros(10)], title="My Title")

        assert viewer.ax.get_title() == "My Title"

    def test_replots_clears_previous_lines(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 10)
        viewer.plot_sweeps(time, [np.zeros(10), np.ones(10)])

        viewer.plot_sweeps(time, [np.zeros(10)])

        assert len(viewer.ax.lines) == 1


class TestPlotSingle:
    def test_plots_one_line(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 100)

        viewer.plot_single(time, np.sin(time))

        assert len(viewer.ax.lines) == 1

    def test_adds_vline_when_requested(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 100)

        viewer.plot_single(time, np.zeros(100), vlines=[0.5])

        # The data line + one axvline produces 2 lines on the axis.
        assert len(viewer.ax.lines) == 2


class TestPlotAbf:
    def test_loads_and_plots_real_abf(self, qtbot, abf_ap_fine):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)

        viewer.plot_abf(abf_ap_fine, max_sweeps=3)

        # max_sweeps caps at 3, so up to 3 lines drawn.
        assert 1 <= len(viewer.ax.lines) <= 3
