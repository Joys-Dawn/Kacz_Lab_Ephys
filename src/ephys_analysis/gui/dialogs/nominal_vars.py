from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTableWidget, QTableWidgetItem,
)

from ephys_analysis.io.nominal import load_nominal_variables


class NominalVarsDialog(QDialog):
    """Dialog for loading and previewing nominal variables from Excel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Load Nominal Variables")
        self.setMinimumSize(600, 400)
        self.nominal_data: dict[str, dict[str, str]] = {}

        layout = QVBoxLayout(self)

        # File selection
        file_layout = QHBoxLayout()
        self.path_label = QLabel("No file selected")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        file_layout.addWidget(self.path_label, stretch=1)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)

        # Preview table
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        # OK / Cancel
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Nominal Variables Excel",
            "", "Excel Files (*.xlsx *.xls)"
        )
        if path:
            self.path_label.setText(path)
            self.nominal_data = load_nominal_variables(path)
            self._populate_table()

    def _populate_table(self):
        if not self.nominal_data:
            self.table.clear()
            return

        sample_ids = sorted(self.nominal_data.keys())
        if not sample_ids:
            return
        first = self.nominal_data[sample_ids[0]]
        var_names = list(first.keys())

        self.table.setRowCount(len(sample_ids))
        self.table.setColumnCount(1 + len(var_names))
        self.table.setHorizontalHeaderLabels(["Sample #"] + var_names)

        for row, sid in enumerate(sample_ids):
            self.table.setItem(row, 0, QTableWidgetItem(sid))
            for col, var in enumerate(var_names):
                val = self.nominal_data[sid].get(var, "")
                self.table.setItem(row, col + 1, QTableWidgetItem(val))

        self.table.resizeColumnsToContents()
