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

    def test_clears_multi_sweep_hover_state(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 10)
        viewer.plot_sweeps(
            time,
            [np.zeros(10), np.ones(10)],
            labels=["Sweep 1", "Sweep 2"],
            ylabel="pA",
        )

        viewer.plot_single(time, np.zeros(10), ylabel="mV")

        readout = viewer.ax.format_coord(0.5, 0.0)
        assert "Sweep" not in readout
        assert readout.endswith("mV")


class TestPlotAbf:
    def test_loads_and_plots_real_abf(self, qtbot, abf_ap_fine):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)

        viewer.plot_abf(abf_ap_fine, max_sweeps=3)

        # max_sweeps caps at 3, so up to 3 lines drawn.
        assert 1 <= len(viewer.ax.lines) <= 3

    def test_uses_recorded_response_units_for_epsc(self, qtbot, abf_epsc):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)

        viewer.plot_abf(abf_epsc)

        assert viewer.ax.get_ylabel() == "pA"

    def test_uses_one_based_sweep_labels(self, qtbot, abf_ap_fine):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)

        viewer.plot_abf(abf_ap_fine, max_sweeps=2)

        assert viewer._hover_labels == ["Sweep 1", "Sweep 2"]


class TestHoverReadout:
    """Cursor in the trace plot shows `Sweep N  x=...  y=...` in the
    nav toolbar (via matplotlib's format_coord hook), so the legend
    can stay off the plot even when 20 sweeps are drawn.
    """

    def test_format_coord_identifies_nearest_sweep(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 100)
        # Three flat sweeps at distinct levels.
        sweeps = [np.full(100, -70.0), np.full(100, -50.0), np.full(100, 0.0)]

        viewer.plot_sweeps(time, sweeps, labels=["Sweep 0", "Sweep 1", "Sweep 2"])
        readout = viewer.ax.format_coord(0.5, -49.0)

        assert "Sweep 1" in readout

    def test_format_coord_includes_x_and_y(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 10)

        viewer.plot_sweeps(time, [np.zeros(10)], labels=["Sweep 0"])
        readout = viewer.ax.format_coord(0.5, 0.0)

        assert "0.500" in readout
        assert "0.00" in readout

    def test_format_coord_uses_default_labels_when_none_given(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 100)
        sweeps = [np.full(100, -65.0), np.full(100, -30.0)]

        viewer.plot_sweeps(time, sweeps)
        readout = viewer.ax.format_coord(0.5, -30.0)

        assert "Sweep 2" in readout

    def test_no_legend_artist_is_drawn(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 10)

        viewer.plot_sweeps(time, [np.zeros(10), np.ones(10)],
                           labels=["Sweep 0", "Sweep 1"])

        assert viewer.ax.get_legend() is None

    def test_format_coord_drops_label_when_cursor_far_from_any_sweep(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 100)
        # Sweeps at -70 and -60. Cursor at -20 is ~40 mV from the nearest
        # — far outside the 3% threshold, so no sweep label should appear.
        sweeps = [np.full(100, -70.0), np.full(100, -60.0)]

        viewer.plot_sweeps(time, sweeps, labels=["Sweep 0", "Sweep 1"])
        viewer.ax.set_ylim(-80, 0)
        readout = viewer.ax.format_coord(0.5, -20.0)

        assert "Sweep" not in readout

    def test_format_coord_drops_label_when_cursor_outside_time_range(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 100)
        sweeps = [np.full(100, -70.0)]

        viewer.plot_sweeps(time, sweeps, labels=["Sweep 0"])
        readout = viewer.ax.format_coord(2.0, -70.0)

        assert "Sweep" not in readout

    def test_hover_ignores_hidden_sweeps_and_restores_visible_ones(self, qtbot):
        viewer = TraceViewer()
        qtbot.addWidget(viewer)
        time = np.linspace(0, 1, 10)
        viewer.plot_sweeps(time, [np.zeros(10), np.zeros(10)])
        viewer.ax.axhline(2.0)

        viewer.ax.lines[0].set_visible(False)
        assert viewer.ax.format_coord(0.5, 0.0).startswith("Sweep 2 ")

        viewer.ax.lines[1].set_visible(False)
        assert "Sweep" not in viewer.ax.format_coord(0.5, 0.0)

        viewer.ax.lines[0].set_visible(True)
        assert viewer.ax.format_coord(0.5, 0.0).startswith("Sweep 1 ")
