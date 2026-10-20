from copy import copy

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QComboBox, QVBoxLayout, QWidget


class MiniNavToolbar(NavigationToolbar2QT):
    """matplotlib nav toolbar trimmed to Home + Pan + Zoom."""
    toolitems = [
        ti for ti in NavigationToolbar2QT.toolitems
        if ti[0] in ("Home", "Pan", "Zoom")
    ]

    def enable_axis_zoom(self):
        self.zoom_axis = QComboBox(self)
        self.zoom_axis.setToolTip("Zoom axes")
        self.zoom_axis.addItem("Zoom XY", None)
        self.zoom_axis.addItem("Zoom X", "x")
        self.zoom_axis.addItem("Zoom Y", "y")
        self.addWidget(self.zoom_axis)

    def _axis_event(self, event):
        selector = getattr(self, "zoom_axis", None)
        if selector is not None and selector.currentData() is not None:
            event = copy(event)
            event.key = selector.currentData()
        return event

    def drag_zoom(self, event):
        super().drag_zoom(self._axis_event(event))

    def release_zoom(self, event):
        super().release_zoom(self._axis_event(event))


class PlotCanvas(QWidget):
    """Base widget wrapping a matplotlib FigureCanvasQTAgg."""

    def __init__(self, parent=None, figsize=(6, 4), show_toolbar: bool = True):
        super().__init__(parent)
        self.figure = Figure(figsize=figsize, tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if show_toolbar:
            self.toolbar = MiniNavToolbar(self.canvas, self)
            layout.addWidget(self.toolbar)
        else:
            self.toolbar = None
        layout.addWidget(self.canvas)

    def clear(self):
        self.ax.clear()
        self.canvas.draw()

    def refresh(self):
        self.canvas.draw()
