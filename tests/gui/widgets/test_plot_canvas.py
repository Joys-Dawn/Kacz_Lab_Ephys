from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from ephys_analysis.gui.widgets.plot_canvas import PlotCanvas


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
