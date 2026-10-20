from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.backend_bases import MouseButton, MouseEvent
import pytest

from ephys_analysis.gui.widgets.plot_canvas import PlotCanvas


@pytest.mark.parametrize("axis", ["x", "y", None])
def test_axis_zoom_changes_only_selected_axes(qtbot, axis):
    widget = PlotCanvas()
    qtbot.addWidget(widget)
    widget.toolbar.enable_axis_zoom()
    widget.toolbar.zoom_axis.setCurrentIndex({None: 0, "x": 1, "y": 2}[axis])
    widget.ax.set_xlim(0, 10)
    widget.ax.set_ylim(0, 100)
    widget.refresh()
    widget.toolbar.zoom()
    start = widget.ax.transData.transform((2, 20))
    end = widget.ax.transData.transform((8, 80))
    press = MouseEvent("button_press_event", widget.canvas, *start, button=1)
    motion = MouseEvent(
        "motion_notify_event", widget.canvas, *end, buttons={MouseButton.LEFT}
    )
    release = MouseEvent("button_release_event", widget.canvas, *end, button=1)
    widget.toolbar.press_zoom(press)
    widget.toolbar.drag_zoom(motion)
    widget.toolbar.release_zoom(release)
    assert widget.ax.get_xlim() == pytest.approx((0, 10) if axis == "y" else (2, 8), abs=0.1)
    assert widget.ax.get_ylim() == pytest.approx((0, 100) if axis == "x" else (20, 80), abs=0.5)
    widget.toolbar.home()
    assert widget.ax.get_xlim() == (0, 10)
    assert widget.ax.get_ylim() == (0, 100)


class TestPlotCanvas:
    def test_constructs_with_default_figsize(self, qtbot):
        canvas = PlotCanvas()
        qtbot.addWidget(canvas)

        assert canvas.figure is not None

    def test_wraps_a_qt_agg_canvas(self, qtbot):
        canvas = PlotCanvas()
        qtbot.addWidget(canvas)

        assert isinstance(canvas.canvas, FigureCanvasQTAgg)

    def test_axes_attached_to_figure(self, qtbot):
        canvas = PlotCanvas()
        qtbot.addWidget(canvas)

        assert canvas.ax in canvas.figure.axes

    def test_clear_empties_axes(self, qtbot):
        canvas = PlotCanvas()
        qtbot.addWidget(canvas)
        canvas.ax.plot([0, 1], [0, 1])

        canvas.clear()

        assert len(canvas.ax.lines) == 0

    def test_refresh_does_not_raise(self, qtbot):
        canvas = PlotCanvas()
        qtbot.addWidget(canvas)

        canvas.refresh()
