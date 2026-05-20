import pandas as pd
import pytest
from PySide6.QtWidgets import QFileDialog, QTableWidgetItem

from ephys_analysis.gui.dialogs.nominal_vars import NominalVarsDialog


@pytest.fixture
def nominal_excel(tmp_path):
    path = tmp_path / "nominal.xlsx"
    df = pd.DataFrame({
        "Sample #": ["1666", "1667"],
        "Sex": ["M", "F"],
        "Behavior": ["CFM", "CFM"],
    })
    df.to_excel(path, index=False)
    return path


class TestInitialState:
    def test_starts_with_empty_nominal_data(self, qtbot):
        dlg = NominalVarsDialog()
        qtbot.addWidget(dlg)

        assert dlg.nominal_data == {}

    def test_table_initially_empty(self, qtbot):
        dlg = NominalVarsDialog()
        qtbot.addWidget(dlg)

        assert dlg.table.rowCount() == 0

    def test_path_label_starts_unset(self, qtbot):
        dlg = NominalVarsDialog()
        qtbot.addWidget(dlg)

        assert dlg.path_label.text() == "No file selected"


class TestBrowse:
    def test_browse_populates_nominal_data(self, qtbot, monkeypatch, nominal_excel):
        dlg = NominalVarsDialog()
        qtbot.addWidget(dlg)
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            lambda *args, **kwargs: (str(nominal_excel), ""),
        )

        dlg._browse()

        assert set(dlg.nominal_data.keys()) == {"1666", "1667"}

    def test_browse_populates_table_with_one_row_per_sample(self, qtbot, monkeypatch, nominal_excel):
        dlg = NominalVarsDialog()
        qtbot.addWidget(dlg)
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            lambda *args, **kwargs: (str(nominal_excel), ""),
        )

        dlg._browse()

        assert dlg.table.rowCount() == 2

    def test_browse_table_columns_include_sample_and_vars(self, qtbot, monkeypatch, nominal_excel):
        dlg = NominalVarsDialog()
        qtbot.addWidget(dlg)
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            lambda *args, **kwargs: (str(nominal_excel), ""),
        )

        dlg._browse()

        # Sample # + Sex + Behavior = 3 columns
        assert dlg.table.columnCount() == 3

    def test_browse_updates_path_label(self, qtbot, monkeypatch, nominal_excel):
        dlg = NominalVarsDialog()
        qtbot.addWidget(dlg)
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            lambda *args, **kwargs: (str(nominal_excel), ""),
        )

        dlg._browse()

        assert dlg.path_label.text() == str(nominal_excel)

    def test_browse_cancel_leaves_state_unchanged(self, qtbot, monkeypatch):
        dlg = NominalVarsDialog()
        qtbot.addWidget(dlg)
        monkeypatch.setattr(
            QFileDialog, "getOpenFileName",
            lambda *args, **kwargs: ("", ""),  # User cancelled
        )

        dlg._browse()

        assert dlg.nominal_data == {}


class TestPopulateTable:
    def test_empty_data_clears_existing_items(self, qtbot):
        dlg = NominalVarsDialog()
        qtbot.addWidget(dlg)
        dlg.table.setRowCount(2)
        dlg.table.setColumnCount(3)
        dlg.table.setItem(0, 0, QTableWidgetItem("stale"))

        dlg.nominal_data = {}
        dlg._populate_table()

        assert dlg.table.item(0, 0) is None
