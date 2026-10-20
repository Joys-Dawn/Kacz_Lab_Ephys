from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QScrollArea, QWidget, QGroupBox,
)
from PySide6.QtCore import Qt

from ephys_analysis.gui.widgets.trace_viewer import TraceViewer


class DuplicateResolverDialog(QDialog):
    """Dialog for resolving duplicate ABF files sharing the same protocol.

    Shows trace plots for each duplicate and lets the user pick which to keep.
    Exactly one file must be selected per protocol — enforced via QRadioButton.
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
        self._radios: dict[tuple[str, str, str], list[tuple[QRadioButton, Path]]] = {}
        self._button_groups: list[QButtonGroup] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Multiple files found with the same protocol. Select which to keep:"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        for key, paths in duplicates.items():
            _, sample_id, protocol = key
            group = QGroupBox(f"Sample {sample_id} — {protocol} ({len(paths)} files)")
            group_layout = QVBoxLayout(group)

            button_group = QButtonGroup(self)
            button_group.setExclusive(True)
            self._button_groups.append(button_group)
            self._radios[key] = []

            for i, path in enumerate(paths):
                row = QHBoxLayout()
                rb = QRadioButton(path.name)
                if i == 0:
                    rb.setChecked(True)
                button_group.addButton(rb)
                self._radios[key].append((rb, path))
                row.addWidget(rb)

                preview_btn = QPushButton("Preview")
                preview_btn.clicked.connect(lambda checked, p=path: self._preview(p))
                row.addWidget(preview_btn)
                row.addStretch()
                group_layout.addLayout(row)

            scroll_layout.addWidget(group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        continue_btn = QPushButton("Continue with Selected")
        continue_btn.setStyleSheet("font-weight: bold; padding: 8px 24px;")
        continue_btn.clicked.connect(self._continue)
        layout.addWidget(continue_btn, alignment=Qt.AlignCenter)

    def _preview(self, path: Path):
        """Open a modeless trace preview. Multiple previews can be open at once."""
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.setWindowTitle(f"Preview: {path.name}")
        dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout(dialog)
        viewer = TraceViewer(dialog, figsize=(6, 4))
        viewer.plot_abf(path)
        layout.addWidget(viewer)
        dialog.show()

    def _continue(self):
        for key, rb_list in self._radios.items():
            for rb, path in rb_list:
                if rb.isChecked():
                    self.selections[key] = path
                    break
        self.accept()
