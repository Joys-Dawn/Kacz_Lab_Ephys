from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtCore import Qt

from ephys_analysis.core.abf_io import load_abf, get_sweep_data
from ephys_analysis.core.types import BaselineFlag, QCReview
from ephys_analysis.gui import main_window as window_module
from ephys_analysis.gui.main_window import MainWindow
from ephys_analysis.gui.dialogs.qc_review import QCReviewDialog
from ephys_analysis.gui.dialogs.one_s_ap_review import OneSAPReviewDialog
from ephys_analysis.io.scanner import ScanResult, scan_project_folder
from ephys_analysis.protocols import PROTO_AP_FINE, PROTO_RI_IH, PROTO_1S_AP
from ephys_analysis.protocols.ap import analyze_ap_fine
from ephys_analysis.protocols.one_s_ap import analyze_one_s_ap


@pytest.mark.parametrize("offset", [-10, 7.25, 0])
def test_offset_control_updates_selected_sample_only_and_invalidates_results(qtbot, monkeypatch, sample_data_root, offset):
    window = MainWindow()
    qtbot.addWidget(window)
    samples = scan_project_folder(sample_data_root).samples
    info = next(info for info in samples.values() if info.sample_id == "1666")
    info.voltage_offset_mv = 1
    window.scan_result = ScanResult(samples=samples)
    window._populate_tree()
    animal = next(window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount()) if window.tree.topLevelItem(i).text(0) == info.animal_id)
    item = next(animal.child(i) for i in range(animal.childCount()) if animal.child(i).text(0) == "1666")
    file_item = next(item.child(i) for i in range(item.childCount()) if item.child(i).text(1) == PROTO_AP_FINE)
    file_item.setSelected(True)
    window._on_tree_click(file_item, 0)
    window.results = [object()]
    window._qc_reviews = {"previous": QCReview(True)}
    window._qc_contexts = {"previous": object()}
    monkeypatch.setattr(window_module.QInputDialog, "getDouble", lambda *a: (offset, True))
    window._set_voltage_offset()
    assert info.voltage_offset_mv == offset
    assert all(other.voltage_offset_mv == 0 for other in samples.values() if other is not info)
    assert window.results == []
    assert window._qc_contexts == {}
    assert window._qc_reviews == {}
    assert not window._undo_qc_btn.isEnabled()
    y = get_sweep_data(load_abf(info.protocols[PROTO_AP_FINE]), 0)
    np.testing.assert_array_equal(window.trace_viewer.ax.lines[0].get_ydata(), y + offset)
    assert item.text(1) == (f"Offset: {offset:+g} mV" if offset else "")


def test_cancel_voltage_input_preserves_results(qtbot, monkeypatch, fake_scan_result):
    window = MainWindow()
    qtbot.addWidget(window)
    window.scan_result = fake_scan_result
    window._populate_tree()
    window.tree.topLevelItem(0).child(0).setSelected(True)
    result = object()
    window.results = [result]
    monkeypatch.setattr(window_module.QInputDialog, "getDouble", lambda *a: (-10, False))
    window._set_voltage_offset()
    assert window.results == [result]
    assert all(info.voltage_offset_mv == 0 for info in fake_scan_result.samples.values())


def test_qc_and_other_protocol_preview_use_same_correction(qtbot, abf_ap_fine, abf_ri_ih, abf_epsc):
    offset = -10
    ap = analyze_ap_fine(load_abf(abf_ap_fine, voltage_offset_mv=offset))
    paths = {PROTO_AP_FINE: str(abf_ap_fine), PROTO_RI_IH: str(abf_ri_ih), "1. Spontaneous EPSCs": str(abf_epsc)}
    dialog = QCReviewDialog("1666", str(abf_ap_fine), ap, -68, protocol_paths=paths,
                            voltage_offset_mv=offset, excluded_sweeps_by_path={str(abf_ri_ih): {2}})
    qtbot.addWidget(dialog)
    np.testing.assert_array_equal(dialog._ap_response, get_sweep_data(load_abf(abf_ap_fine), ap.sweep_num - 1) + offset)
    assert dialog.picker.selected_voltage_mv() == ap.voltage_threshold_mv
    dialog.protocol_selector.setCurrentIndex(dialog.protocol_selector.findData(str(abf_ri_ih)))
    np.testing.assert_array_equal(dialog.trace_viewer.ax.lines[0].get_ydata(), get_sweep_data(load_abf(abf_ri_ih), 0) + offset)
    assert not dialog.trace_viewer.ax.lines[1].get_visible()
    dialog.protocol_selector.setCurrentIndex(dialog.protocol_selector.findData(str(abf_epsc)))
    np.testing.assert_array_equal(dialog.trace_viewer.ax.lines[0].get_ydata(), get_sweep_data(load_abf(abf_epsc), 0))
    assert dialog.trace_viewer.ax.get_ylabel() == "pA"


def test_baseline_exclusions_and_offset_reach_worker_and_later_qc(qtbot, monkeypatch, abf_ap_fine):
    from ephys_analysis.io.scanner import SampleInfo
    window = MainWindow()
    qtbot.addWidget(window)
    path = str(abf_ap_fine)
    info = SampleInfo("animal", "1666", protocols={PROTO_AP_FINE: abf_ap_fine}, voltage_offset_mv=-5)
    window._analysis_samples = {("animal", "1666"): info}
    reviews = []
    window._worker = SimpleNamespace(set_baseline_result=reviews.append)
    captured = {}

    def dialog(flags, parent, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(exec=lambda: 1, decisions={path: True}, excluded_sweeps={path: {1, 2}})

    monkeypatch.setattr(window_module, "BaselineReviewDialog", dialog)
    window._on_baseline_flags_found([("1666", BaselineFlag(PROTO_AP_FINE, path, -67, [-50] * 4, [1]))])
    assert captured["voltage_offset_mv"] == -5
    assert reviews[0].excluded_sweeps == {path: {1, 2}}
    assert window._sample_for_path(path).excluded_sweeps == {path: {1, 2}}
    assert info.excluded_sweeps == {}


def test_one_s_review_disables_baseline_excluded_sweeps_and_corrects_both_plots(qtbot, abf_1s_ap_high_firing, abf_ri_ih):
    offset = -5
    abf = load_abf(abf_1s_ap_high_firing, voltage_offset_mv=offset)
    result = analyze_one_s_ap(abf, excluded_sweeps={2})
    paths = {PROTO_1S_AP: str(abf_1s_ap_high_firing), PROTO_RI_IH: str(abf_ri_ih)}
    dialog = OneSAPReviewDialog("1566", paths, result, voltage_offset_mv=offset)
    qtbot.addWidget(dialog)
    assert dialog.excluded_sweeps == {2}
    assert not dialog.sweep_table.topLevelItem(1).flags() & Qt.ItemIsEnabled
    assert not dialog.one_s_viewer.ax.lines[1].get_visible()
    np.testing.assert_array_equal(dialog.one_s_viewer.ax.lines[0].get_ydata(), get_sweep_data(abf, 0))
    np.testing.assert_array_equal(dialog.rin_viewer.ax.lines[0].get_ydata(), get_sweep_data(load_abf(abf_ri_ih), 0) + offset)


def test_quick_and_detailed_runs_receive_selected_sample_correction(qtbot, monkeypatch, fake_scan_result):
    window = MainWindow()
    qtbot.addWidget(window)
    key, info = next(iter(fake_scan_result.samples.items()))
    fake_scan_result.samples[key] = replace(info, voltage_offset_mv=-10)
    window.scan_result = fake_scan_result
    window._populate_tree()
    window.tree.topLevelItem(0).child(0).child(0).setSelected(True)
    calls = []
    monkeypatch.setattr(window, "_start_analysis", lambda samples, **kw: calls.append((samples, kw)))
    window._run_quick_analysis()
    window._run_analysis()
    assert [call[1]["skip_qc"] for call in calls] == [True, False]
    assert all(samples[key].voltage_offset_mv == -10 for samples, _ in calls)
