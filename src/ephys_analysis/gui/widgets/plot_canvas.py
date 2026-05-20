from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget


class MiniNavToolbar(NavigationToolbar2QT):
    """matplotlib nav toolbar trimmed to Home + Pan + Zoom."""
    toolitems = [
        ti for ti in NavigationToolbar2QT.toolitems
        if ti[0] in ("Home", "Pan", "Zoom")
    ]


class PlotCanvas(QWidget):
    """Base widget wrapping a matplotlib FigureCanvasQTAgg."""

    def __init__(self, parent=None, figsize=(6, 4)):
        super().__init__(parent)
        self.figure = Figure(figsize=figsize, tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

    def clear(self):
        self.ax.clear()
        self.canvas.draw()

    def refresh(self):
        self.canvas.draw()
