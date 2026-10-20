from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from ephys_analysis.core.abf_io import load_abf
from ephys_analysis.core.types import BaselineFlag
from ephys_analysis.gui.dialogs.baseline_flags import BaselineReviewDialog
from ephys_analysis.gui.dialogs.one_s_ap_review import OneSAPReviewDialog
from ephys_analysis.gui.dialogs.qc_review import QCReviewDialog
from ephys_analysis.protocols import PROTO_1S_AP
from ephys_analysis.protocols.one_s_ap import analyze_one_s_ap


def test_review_layouts_render_without_clipped_actions(
    qtbot, tmp_path, abf_1s_ap_high_firing, abf_ap_fine, ap_fine_result,
):
    baseline = BaselineReviewDialog([
        (str(1500 + i), BaselineFlag(
            "4. Ih and Input Resistance", f"recording_{i}.abf", -67,
            out_of_range_sweeps=list(range(1, 23)),
            changed_sweep_pairs=[(3, 4), (15, 16), (16, 17)],
        )) for i in range(20)
    ])
    firing = OneSAPReviewDialog(
        "1566", {PROTO_1S_AP: str(abf_1s_ap_high_firing)},
        analyze_one_s_ap(load_abf(abf_1s_ap_high_firing)),
    )
    qc = QCReviewDialog("1666", str(abf_ap_fine), ap_fine_result, -65, can_go_back=True)
    for name, dialog in (("baseline", baseline), ("firing", firing), ("qc", qc)):
        qtbot.addWidget(dialog)
        dialog.resize(1200 if name != "baseline" else 1100, 800 if name != "baseline" else 650)
        dialog.show()
        qtbot.wait(100)
        for button in dialog.findChildren(QPushButton):
            if button.isVisible() and button.parent() is dialog:
                assert dialog.rect().contains(button.geometry()), button.text()
        image_path = tmp_path / f"{name}.png"
        assert dialog.grab().save(str(image_path))
        print(f"Rendered {image_path}")
        dialog.hide()
    baseline.show()
    for width in (900, 1100, 1000):
        baseline.resize(width, 650)
        qtbot.wait(30)
        baseline.table.doItemsLayout()
        for row in range(baseline.table.topLevelItemCount() - 1):
            first = baseline.table.visualItemRect(baseline.table.topLevelItem(row))
            second = baseline.table.visualItemRect(baseline.table.topLevelItem(row + 1))
            assert first.bottom() < second.top()
    baseline.table.topLevelItem(0).setCheckState(0, Qt.Checked)
    baseline._decide_selected(False)
    assert baseline.decisions["recording_0.abf"] is False
