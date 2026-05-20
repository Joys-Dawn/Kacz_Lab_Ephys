from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from ephys_analysis.gui.dialogs.duplicate_resolver import DuplicateResolverDialog


@pytest.fixture
def two_duplicate_groups():
    """Two protocols each with two candidate files."""
    return {
        ("animalA", "1666", "PROTO_X"): [Path("x_1.abf"), Path("x_2.abf")],
        ("animalA", "1666", "PROTO_Y"): [Path("y_1.abf"), Path("y_2.abf")],
    }


class TestInitialState:
    def test_first_file_pre_checked_in_each_group(self, qtbot, two_duplicate_groups):
        dlg = DuplicateResolverDialog(two_duplicate_groups)
        qtbot.addWidget(dlg)

        for key, rb_list in dlg._radios.items():
            checked = [rb.isChecked() for rb, _ in rb_list]
            assert checked == [True, False]

    def test_selections_empty_until_continue_clicked(self, qtbot, two_duplicate_groups):
        dlg = DuplicateResolverDialog(two_duplicate_groups)
        qtbot.addWidget(dlg)

        assert dlg.selections == {}

    def test_one_radio_row_per_file(self, qtbot, two_duplicate_groups):
        dlg = DuplicateResolverDialog(two_duplicate_groups)
        qtbot.addWidget(dlg)

        total_rbs = sum(len(rbs) for rbs in dlg._radios.values())
        assert total_rbs == 4


class TestMutualExclusion:
    def test_checking_second_radio_unchecks_first_in_same_group(
        self, qtbot, two_duplicate_groups
    ):
        dlg = DuplicateResolverDialog(two_duplicate_groups)
        qtbot.addWidget(dlg)
        rb_first, _ = dlg._radios[("animalA", "1666", "PROTO_X")][0]
        rb_second, _ = dlg._radios[("animalA", "1666", "PROTO_X")][1]

        rb_second.setChecked(True)

        assert not rb_first.isChecked()
        assert rb_second.isChecked()

    def test_groups_are_independent(self, qtbot, two_duplicate_groups):
        """Selecting in PROTO_X must not affect PROTO_Y's selection."""
        dlg = DuplicateResolverDialog(two_duplicate_groups)
        qtbot.addWidget(dlg)
        x_second, _ = dlg._radios[("animalA", "1666", "PROTO_X")][1]
        y_first, _ = dlg._radios[("animalA", "1666", "PROTO_Y")][0]

        x_second.setChecked(True)

        assert y_first.isChecked()


class TestContinueButton:
    def test_default_selections_keep_first_file(self, qtbot, two_duplicate_groups):
        dlg = DuplicateResolverDialog(two_duplicate_groups)
        qtbot.addWidget(dlg)

        dlg._continue()

        assert dlg.selections[("animalA", "1666", "PROTO_X")] == Path("x_1.abf")
        assert dlg.selections[("animalA", "1666", "PROTO_Y")] == Path("y_1.abf")

    def test_user_can_switch_selection_to_second_file(self, qtbot, two_duplicate_groups):
        dlg = DuplicateResolverDialog(two_duplicate_groups)
        qtbot.addWidget(dlg)
        rb_second, _ = dlg._radios[("animalA", "1666", "PROTO_X")][1]

        rb_second.setChecked(True)
        dlg._continue()

        assert dlg.selections[("animalA", "1666", "PROTO_X")] == Path("x_2.abf")

    def test_continue_accepts_dialog(self, qtbot, two_duplicate_groups):
        dlg = DuplicateResolverDialog(two_duplicate_groups)
        qtbot.addWidget(dlg)

        with qtbot.waitSignal(dlg.accepted, timeout=200):
            dlg._continue()

    def test_clicking_continue_button_finalizes_selections(self, qtbot, two_duplicate_groups):
        dlg = DuplicateResolverDialog(two_duplicate_groups)
        qtbot.addWidget(dlg)
        dlg.show()
        qtbot.waitExposed(dlg)
        continue_btn = next(
            b for b in dlg.findChildren(QPushButton)
            if b.text() == "Continue with Selected"
        )

        qtbot.mouseClick(continue_btn, Qt.LeftButton)

        assert len(dlg.selections) == 2


class TestEmptyDuplicates:
    def test_empty_dict_produces_empty_selections_on_continue(self, qtbot):
        dlg = DuplicateResolverDialog({})
        qtbot.addWidget(dlg)

        dlg._continue()

        assert dlg.selections == {}
