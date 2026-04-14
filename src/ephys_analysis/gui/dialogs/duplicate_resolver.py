from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QScrollArea, QWidget, QGroupBox,
)
from PySide6.QtCore import Qt

from ephys_analysis.gui.widgets.trace_viewer import TraceViewer


class DuplicateResolverDialog(QDialog):
    """Dialog for resolving duplicate ABF files sharing the same protocol.

    Shows trace plots for each duplicate and lets the user pick which to keep.
    """

    def __init__(self, duplicates: dict[tuple[str, str, str], list[Path]], parent=None):
        """
        Args:
            duplicates: {(animal_id, sample_id, protocol_name): [path1, path2, ...]}
        """
        super().__init__(parent)
        self.setWindowTitle("Duplicate Protocol Files")
        self.setMinimumSize(800, 600)
        self.selections: dict[tuple[str, str, str], Path] = {}
        self._checkboxes: dict[tuple[str, str, str], list[tuple[QCheckBox, Path]]] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Multiple files found with the same protocol. Select which to keep:"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        for key, paths in duplicates.items():
            animal_id, sample_id, protocol = key
            group = QGroupBox(f"Sample {sample_id} — {protocol} ({len(paths)} files)")
            group_layout = QVBoxLayout(group)

            self._checkboxes[key] = []
            for path in paths:
                row = QHBoxLayout()
                cb = QCheckBox(path.name)
                cb.setChecked(paths.index(path) == 0)  # Default: first file selected
                self._checkboxes[key].append((cb, path))
                row.addWidget(cb)

                # Preview button
                preview_btn = QPushButton("Preview")
                preview_btn.clicked.connect(lambda checked, p=path, pr=protocol: self._preview(p, pr))
                row.addWidget(preview_btn)
                row.addStretch()
                group_layout.addLayout(row)

            scroll_layout.addWidget(group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Continue button
        continue_btn = QPushButton("Continue with Selected")
        continue_btn.setStyleSheet("font-weight: bold; padding: 8px 24px;")
        continue_btn.clicked.connect(self._continue)
        layout.addWidget(continue_btn, alignment=Qt.AlignCenter)

    def _preview(self, path: Path, protocol: str):
        """Show a trace plot preview in a popup."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Preview: {path.name}")
        dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout(dialog)
        viewer = TraceViewer(dialog, figsize=(6, 4))
        viewer.plot_abf(path, max_sweeps=5)
        layout.addWidget(viewer)
        dialog.exec()

    def _continue(self):
        for key, cb_list in self._checkboxes.items():
            for cb, path in cb_list:
                if cb.isChecked():
                    self.selections[key] = path
                    break  # Take first checked
        self.accept()
