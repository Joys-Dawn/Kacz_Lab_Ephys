"""GUI tests for MainWindow + AnalysisWorker.

External dependencies (file dialog, project scanner, message boxes, the
analysis pipeline) are monkeypatched at their import site in
`ephys_analysis.gui.main_window` so no real ABFs, displays, or modals are
needed.
"""
from pathlib import Path
from types import SimpleNamespace
import pytest

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ephys_analysis.core.types import (
    AnalysisCancelled, APFineResult, OneSAPResult, OneSAPReview,
    BaselineFlag, BaselineReview, SampleResult, QCStatus,
)
from ephys_analysis.gui import main_window as mw_module
from ephys_analysis.gui.main_window import AnalysisWorker, MainWindow
from ephys_analysis.io.scanner import SampleInfo


@pytest.mark.parametrize("decision", [True, False, "cancel"])
def test_rin_review_routes_decision_to_worker(qtbot, monkeypatch, decision):
    win = MainWindow()
    qtbot.addWidget(win)
    calls = []
    win._worker = SimpleNamespace(
        set_ri_ih_result=lambda value: calls.append(value),
        cancel=lambda: calls.append("cancel"),
    )
    monkeypatch.setattr(mw_module, "RiIhReviewDialog", lambda *a: SimpleNamespace(
        exec=lambda: None, accepted_result=decision,
    ))
    win._on_ri_ih_review_needed("1", "rin.abf", [])
    assert calls == [decision]


def test_worker_waits_for_rin_review(qtbot, monkeypatch):
    captured = []

    def analyze(samples, nominal, ri_ih_reviewer, **kwargs):
        captured.append(ri_ih_reviewer("1", "rin.abf", []))
        return []

    monkeypatch.setattr(mw_module, "analyze_all", analyze)
    worker = AnalysisWorker({}, {})
    worker.ri_ih_review_needed.connect(lambda *args: worker.set_ri_ih_result(False))
    with qtbot.waitSignal(worker.finished, timeout=2000):
        worker.start()
    worker.wait(2000)
    assert captured == [False]


def test_qc_back_action_is_forwarded(qtbot, monkeypatch):
    win = MainWindow()
    qtbot.addWidget(win)
    reviews = []
    win._worker = SimpleNamespace(set_qc_result=reviews.append)
    monkeypatch.setattr(mw_module, "QCReviewDialog", lambda *a, **kw: SimpleNamespace(
        exec=lambda: None, notes="", accepted_result="back",
    ))
    win._on_qc_needed("1", "ap.abf", _make_ap_result(), -65, {}, True)
    assert reviews[0].go_back is True
    assert win._qc_reviews == {}


@pytest.mark.parametrize("decision", [True, False, "cancel"])
def test_undo_qc_after_completion_preserves_protocol_results(
    qtbot, monkeypatch, passed_sample_result, decision,
):
    from ephys_analysis.core.types import QCReview
    win = MainWindow()
    qtbot.addWidget(win)
    path = str(Path("C:/data/ap.abf"))
    result = passed_sample_result
    result.qc_status = QCStatus.USER_REJECTED_VTHRESH
    result.file_path = path
    result.reject_sweep_num = 1
    win._analysis_samples = {("animalA", "1666"): SampleInfo(
        "animalA", "1666", protocols={"AP": Path(path)},
    )}
    win._qc_contexts[path] = ("1666", _make_ap_result(), -65, {"AP": path})
    win._qc_reviews[path] = QCReview(False)
    win._on_analysis_finished([result])
    assert win._undo_qc_btn.isEnabled()
    protocol_result = result.one_s_ap
    monkeypatch.setattr(mw_module, "QCReviewDialog", lambda *a, **kw: SimpleNamespace(
        exec=lambda: None, notes="corrected", accepted_result=decision,
        override_vthresh_mv=-40, override_auto_reject=False,
    ))
    win._undo_qc()
    assert result.one_s_ap is protocol_result
    assert result.qc_status == (QCStatus.PASSED if decision is True else QCStatus.USER_REJECTED_VTHRESH)
    if decision != "cancel":
        assert result.ap_fine.voltage_threshold_mv == -40
        assert "corrected" in result.notes
    if decision is True:
        assert result.file_path == "" and result.reject_sweep_num is None


def test_threaded_analysis_can_backtrack_and_finish(qtbot, monkeypatch, sample_data_root):
    from ephys_analysis.io.scanner import scan_project_folder
    all_samples = scan_project_folder(sample_data_root).samples
    samples = {}
    for sid in ("1666", "1542"):
        key = next(key for key in all_samples if key[1] == sid)
        samples[key] = all_samples[key]
    decisions = iter([False, "back", True, True])
    visited = []

    class Review:
        def __init__(self, sid, *args, **kwargs):
            visited.append((sid, kwargs["can_go_back"]))
            self.accepted_result = next(decisions)
            self.notes = "Reviewed"
            self.override_vthresh_mv = None
            self.override_auto_reject = (
                self.accepted_result is True and kwargs["auto_rejected"]
            )

        def exec(self):
            return 1

    monkeypatch.setattr(mw_module, "QCReviewDialog", Review)
    monkeypatch.setattr(mw_module, "BaselineReviewDialog", lambda flags, *a: SimpleNamespace(
        exec=lambda: 1, decisions={flag.file_path: True for _, flag in flags},
    ))
    monkeypatch.setattr(mw_module, "OneSAPReviewDialog", lambda *a, **kw: SimpleNamespace(
        exec=lambda: 1, accepted_result=True, notes="", excluded_sweeps=set(),
    ))
    monkeypatch.setattr(mw_module, "RiIhReviewDialog", lambda *a: SimpleNamespace(
        exec=lambda: 1, accepted_result=True,
    ))
    monkeypatch.setattr(QMessageBox, "information", lambda *a: None)
    win = MainWindow()
    qtbot.addWidget(win)
    win._start_analysis(samples, skip_qc=False)
    worker = win._worker
    try:
        qtbot.waitUntil(lambda: len(win.results) == 2, timeout=15000)
    finally:
        if worker.isRunning():
            worker.cancel()
        worker.wait(2000)
    assert visited == [("1666", False), ("1542", True), ("1666", False), ("1542", True)]
    assert all(result.qc_status == QCStatus.PASSED for result in win.results)
    assert win._undo_qc_btn.isEnabled()


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _FakeDuplicateDialog:
    """Stand-in DuplicateResolverDialog that accepts and keeps paths[0]."""
    def __init__(self, duplicates, parent=None):
        self.selections = {key: paths[0] for key, paths in duplicates.items()}

    def exec(self):
        return 1  # QDialog.Accepted


class _CancellingDuplicateDialog:
    """Dialog stand-in that rejects (user clicked X)."""
    def __init__(self, duplicates, parent=None):
        self.selections = {}

    def exec(self):
        return 0  # QDialog.Rejected


def _make_ap_result(vthresh=-45.0):
    return APFineResult(
        peak_amp_mv=80.0, half_width_ms=1.2,
        max_rise_slope_mv_ms=300.0, max_decay_slope_mv_ms=-100.0,
        sweep_num=1, current_threshold_pa=500.0,
        stim_baseline_pa=-50.0, stim_step_pa=450.0,
        voltage_threshold_mv=vthresh, spike_num=1,
    )


# ---------------------------------------------------------------------------
# MainWindow construction
# ---------------------------------------------------------------------------

class TestMainWindowConstruction:
    def test_title_set(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)

        assert win.windowTitle() == "Ephys Analysis"

    def test_starts_with_no_scan_result(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)

        assert win.scan_result is None

    def test_starts_with_no_results(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)

        assert win.results == []

    def test_starts_with_empty_nominal_data(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)

        assert win.nominal_data == {}

    def test_tree_widget_initially_empty(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)

        assert win.tree.topLevelItemCount() == 0


# ---------------------------------------------------------------------------
# Open Project Folder
# ---------------------------------------------------------------------------

class TestOpenProject:
    def test_cancel_dialog_leaves_state_unchanged(self, qtbot, monkeypatch):
        win = MainWindow()
        qtbot.addWidget(win)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                            lambda *a, **kw: "")

        win._open_project()

        assert win.scan_result is None

    def test_successful_scan_stores_result(self, qtbot, monkeypatch, tmp_path, fake_scan_result):
        win = MainWindow()
        qtbot.addWidget(win)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                            lambda *a, **kw: str(tmp_path))
        monkeypatch.setattr(mw_module, "scan_project_folder",
                            lambda p: fake_scan_result)

        win._open_project()

        assert win.scan_result is fake_scan_result

    def test_successful_scan_populates_tree(self, qtbot, monkeypatch, tmp_path, fake_scan_result):
        win = MainWindow()
        qtbot.addWidget(win)
        monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                            lambda *a, **kw: str(tmp_path))
        monkeypatch.setattr(mw_module, "scan_project_folder",
                            lambda p: fake_scan_result)

        win._open_project()

        # Top-level node is the animal; both samples are children of it.
        assert win.tree.topLevelItemCount() == 1

    def test_duplicate_dialog_invoked_when_duplicates_present(
        self, qtbot, monkeypatch, tmp_path, fake_scan_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        path_a = tmp_path / "dupe_a.abf"
        path_b = tmp_path / "dupe_b.abf"
        path_a.touch()
        path_b.touch()
        fake_scan_result.duplicates = {
            ("animalA", "1666", "PROTO_X"): [path_a, path_b]
        }
        invocations = []

        class _SpyDialog(_FakeDuplicateDialog):
            def __init__(self, dupes, parent=None):
                invocations.append(dupes)
                super().__init__(dupes, parent)

        monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                            lambda *a, **kw: str(tmp_path))
        monkeypatch.setattr(mw_module, "scan_project_folder",
                            lambda p: fake_scan_result)
        monkeypatch.setattr(mw_module, "DuplicateResolverDialog", _SpyDialog)

        win._open_project()

        assert len(invocations) == 1

    def test_duplicate_resolution_applies_user_selection(
        self, qtbot, monkeypatch, tmp_path, fake_scan_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        path_a = tmp_path / "dupe_a.abf"
        path_b = tmp_path / "dupe_b.abf"
        path_a.touch()
        path_b.touch()
        fake_scan_result.duplicates = {
            ("animalA", "1666", "PROTO_X"): [path_a, path_b]
        }
        # Pre-set the active protocol entry to path_a; dialog returns path_b.
        info = fake_scan_result.samples[("animalA", "1666")]
        info.protocols["PROTO_X"] = path_a

        class _PickSecondDialog(_FakeDuplicateDialog):
            def __init__(self, dupes, parent=None):
                super().__init__(dupes, parent)
                self.selections = {
                    ("animalA", "1666", "PROTO_X"): path_b
                }

        monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                            lambda *a, **kw: str(tmp_path))
        monkeypatch.setattr(mw_module, "scan_project_folder",
                            lambda p: fake_scan_result)
        monkeypatch.setattr(mw_module, "DuplicateResolverDialog", _PickSecondDialog)

        win._open_project()

        assert info.protocols["PROTO_X"] == path_b

    def test_no_duplicate_dialog_when_no_duplicates(
        self, qtbot, monkeypatch, tmp_path, fake_scan_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        invocations = []

        class _SpyDialog(_FakeDuplicateDialog):
            def __init__(self, dupes, parent=None):
                invocations.append(dupes)
                super().__init__(dupes, parent)

        monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                            lambda *a, **kw: str(tmp_path))
        monkeypatch.setattr(mw_module, "scan_project_folder",
                            lambda p: fake_scan_result)
        monkeypatch.setattr(mw_module, "DuplicateResolverDialog", _SpyDialog)

        win._open_project()

        assert invocations == []


# ---------------------------------------------------------------------------
# Run Analysis
# ---------------------------------------------------------------------------

class TestRunAnalysis:
    def test_warns_when_no_scan_result(self, qtbot, monkeypatch):
        win = MainWindow()
        qtbot.addWidget(win)
        warning_calls = []
        monkeypatch.setattr(QMessageBox, "warning",
                            lambda *a, **kw: warning_calls.append(a))

        win._run_analysis()

        assert len(warning_calls) == 1

    def test_disables_toolbar_when_analysis_starts(self, qtbot, monkeypatch, fake_scan_result):
        win = MainWindow()
        qtbot.addWidget(win)
        win.scan_result = fake_scan_result

        # Block analyze_all in worker thread so we can observe the disabled state.
        import threading
        gate = threading.Event()
        monkeypatch.setattr(mw_module, "analyze_all",
                            lambda *a, **kw: (gate.wait(), [])[1])

        win._run_analysis()

        assert not win._run_btn.isEnabled()
        # Cleanup: release the worker so the QThread exits.
        gate.set()
        win._worker.wait(2000)


class TestQCReviewSlot:
    def test_auto_reject_flag_and_override_are_forwarded(
        self, qtbot, monkeypatch,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        captured = {}

        class FakeDialog:
            def __init__(self, *args, **kwargs):
                captured["auto_rejected"] = kwargs["auto_rejected"]
                self.notes = "Reviewed"
                self.accepted_result = True
                self.override_vthresh_mv = None
                self.override_auto_reject = True

            def exec(self):
                return 1

        worker = SimpleNamespace(
            set_qc_result=lambda review: captured.update(review=review),
            cancel=lambda: captured.update(cancelled=True),
        )
        win._worker = worker
        monkeypatch.setattr(mw_module, "QCReviewDialog", FakeDialog)

        win._on_qc_needed(
            "1542",
            "C:/data/ap.abf",
            _make_ap_result(vthresh=-45.0),
            -40.0,
            {},
        )

        assert captured["auto_rejected"] is True
        assert captured["review"].override_auto_reject is True


class TestQuickAnalysis:
    def test_warns_when_no_files_are_selected(
        self, qtbot, monkeypatch, fake_scan_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        win.scan_result = fake_scan_result
        win._populate_tree()
        warnings = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *args, **kwargs: warnings.append(args),
        )

        win._run_quick_analysis()

        assert warnings[0][1] == "No Files Selected"

    def test_runs_only_selected_analyzable_file_without_qc(
        self, qtbot, monkeypatch, fake_scan_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        win.scan_result = fake_scan_result
        win._populate_tree()
        first_file = win.tree.topLevelItem(0).child(0).child(0)
        first_file.setSelected(True)
        captured = {}

        def start(samples, *, skip_qc):
            captured["samples"] = samples
            captured["skip_qc"] = skip_qc

        monkeypatch.setattr(win, "_start_analysis", start)

        win._run_quick_analysis()

        assert captured["skip_qc"] is True
        assert list(captured["samples"]) == [("animalA", "1666")]
        selected_info = captured["samples"][("animalA", "1666")]
        assert list(selected_info.protocols) == [
            "2. Resting Membrane Potential"
        ]

    def test_completion_prompt_exports_when_accepted(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        win._analysis_is_quick = True
        exported = []
        monkeypatch.setattr(
            win, "_confirm_quick_analysis_export", lambda: True,
        )
        monkeypatch.setattr(win, "_export_results", lambda: exported.append(True))

        win._on_analysis_finished([passed_sample_result])

        assert exported == [True]

    def test_completion_prompt_can_defer_export(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        win._analysis_is_quick = True
        exported = []
        monkeypatch.setattr(
            win, "_confirm_quick_analysis_export", lambda: False,
        )
        monkeypatch.setattr(win, "_export_results", lambda: exported.append(True))

        win._on_analysis_finished([passed_sample_result])

        assert exported == []

    def test_completion_prompt_has_clear_export_and_later_actions(
        self, qtbot, monkeypatch,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        captured = {}

        def inspect_and_defer(prompt):
            captured["title"] = prompt.windowTitle()
            captured["text"] = prompt.text()
            captured["details"] = prompt.informativeText()
            captured["buttons"] = [button.text() for button in prompt.buttons()]
            next(
                button for button in prompt.buttons()
                if button.text() == "Later"
            ).click()
            return 0

        monkeypatch.setattr(QMessageBox, "exec", inspect_and_defer)

        assert win._confirm_quick_analysis_export() is False
        assert captured == {
            "title": "Quick Analysis Complete",
            "text": "Quick analysis is complete.",
            "details": "Export results now?",
            "buttons": ["Export Results", "Later"],
        }

    def test_completion_prompt_accepts_export_action(
        self, qtbot, monkeypatch,
    ):
        win = MainWindow()
        qtbot.addWidget(win)

        def choose_export(prompt):
            next(
                button for button in prompt.buttons()
                if button.text() == "Export Results"
            ).click()
            return 0

        monkeypatch.setattr(QMessageBox, "exec", choose_export)

        assert win._confirm_quick_analysis_export() is True


# ---------------------------------------------------------------------------
# Export Results
# ---------------------------------------------------------------------------

class TestExportResults:
    def test_warns_when_no_results(self, qtbot, monkeypatch):
        win = MainWindow()
        qtbot.addWidget(win)
        warning_calls = []
        monkeypatch.setattr(QMessageBox, "warning",
                            lambda *a, **kw: warning_calls.append(a))

        win._export_results()

        assert len(warning_calls) == 1

    def test_calls_all_export_functions(
        self, qtbot, monkeypatch, tmp_path, passed_sample_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        win.results = [passed_sample_result]
        monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                            lambda *a, **kw: str(tmp_path))
        monkeypatch.setattr(QMessageBox, "information",
                            lambda *a, **kw: None)
        called = []
        for fn in [
            "export_passed", "export_rejected",
            "export_fully_compiled", "export_cell_types",
            "export_ri_ih_contaminated_sweeps",
            "export_trimming_analysis",
        ]:
            monkeypatch.setattr(mw_module, fn,
                                (lambda name: lambda *a, **kw: called.append(name))(fn))

        win._export_results()

        assert set(called) == {
            "export_passed", "export_rejected",
            "export_fully_compiled", "export_cell_types",
            "export_ri_ih_contaminated_sweeps",
            "export_trimming_analysis",
        }

    def test_cancel_dialog_does_nothing(self, qtbot, monkeypatch, passed_sample_result):
        win = MainWindow()
        qtbot.addWidget(win)
        win.results = [passed_sample_result]
        monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                            lambda *a, **kw: "")
        called = []
        monkeypatch.setattr(mw_module, "export_passed",
                            lambda *a, **kw: called.append("passed"))

        win._export_results()

        assert called == []

    def test_all_exports_receive_one_shared_timestamp(
        self, qtbot, monkeypatch, tmp_path, passed_sample_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        win.results = [passed_sample_result]
        monkeypatch.setattr(
            QFileDialog, "getExistingDirectory", lambda *a, **kw: str(tmp_path)
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
        monkeypatch.setattr(
            mw_module, "create_export_timestamp", lambda: "20260714_153000"
        )
        timestamps = []
        for fn in [
            "export_passed", "export_rejected", "export_fully_compiled",
            "export_cell_types",
            "export_ri_ih_contaminated_sweeps",
            "export_trimming_analysis",
        ]:
            monkeypatch.setattr(
                mw_module,
                fn,
                lambda results, output, timestamp: timestamps.append(timestamp),
            )

        win._export_results()

        assert timestamps == ["20260714_153000"] * 6

    def test_notes_edited_after_analysis_are_refreshed_before_export(
        self, qtbot, monkeypatch, tmp_path, fake_scan_result, passed_sample_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        win.scan_result = fake_scan_result
        win.results = [passed_sample_result]
        rmp_path = str(
            fake_scan_result.samples[("animalA", "1666")].protocols[
                "2. Resting Membrane Potential"
            ]
        )
        win.file_notes[rmp_path] = "Added after analysis"
        monkeypatch.setattr(
            QFileDialog, "getExistingDirectory", lambda *a, **kw: str(tmp_path)
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
        for fn in [
            "export_passed", "export_rejected", "export_fully_compiled",
            "export_cell_types",
            "export_ri_ih_contaminated_sweeps",
            "export_trimming_analysis",
        ]:
            monkeypatch.setattr(mw_module, fn, lambda *a, **kw: None)

        win._export_results()

        assert "Added after analysis" in passed_sample_result.notes


class TestFileNotes:
    def test_editing_selected_file_stores_note(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)
        win._active_note_path = "C:/data/sample.abf"
        win.notes_editor.setEnabled(True)

        win.notes_editor.setPlainText("Inspect this trace")

        assert win.file_notes["C:/data/sample.abf"] == "Inspect this trace"

    def test_clearing_note_removes_it(self, qtbot):
        win = MainWindow()
        qtbot.addWidget(win)
        win._active_note_path = "C:/data/sample.abf"
        win.file_notes["C:/data/sample.abf"] = "Old note"
        win.notes_editor.setEnabled(True)

        win.notes_editor.clear()

        assert "C:/data/sample.abf" not in win.file_notes


# ---------------------------------------------------------------------------
# Analysis-finished slot
# ---------------------------------------------------------------------------

class TestOnAnalysisFinished:
    def test_stores_results(self, qtbot, passed_sample_result):
        win = MainWindow()
        qtbot.addWidget(win)
        win._set_toolbar_enabled(False)
        win.progress.setVisible(True)

        win._on_analysis_finished([passed_sample_result])

        assert win.results == [passed_sample_result]

    def test_reenables_toolbar(self, qtbot, passed_sample_result):
        win = MainWindow()
        qtbot.addWidget(win)
        win._set_toolbar_enabled(False)

        win._on_analysis_finished([passed_sample_result])

        assert win._run_btn.isEnabled()

    def test_status_message_includes_pass_count(self, qtbot, passed_sample_result):
        win = MainWindow()
        qtbot.addWidget(win)

        win._on_analysis_finished([passed_sample_result])

        assert "1 passed" in win.statusbar.currentMessage()

    def test_status_message_omits_fallback_when_none(self, qtbot, passed_sample_result):
        win = MainWindow()
        qtbot.addWidget(win)

        win._on_analysis_finished([passed_sample_result])

        assert "coarse fallback" not in win.statusbar.currentMessage()

    def test_status_message_includes_fallback_count(self, qtbot, monkeypatch, passed_sample_result):
        win = MainWindow()
        qtbot.addWidget(win)
        passed_sample_result.ap_used_coarse_fallback = True
        # Suppress the modal so the test doesn't block.
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)

        win._on_analysis_finished([passed_sample_result])

        assert "1 used AP coarse fallback" in win.statusbar.currentMessage()

    def test_information_popup_shown_when_fallback_used(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        passed_sample_result.ap_used_coarse_fallback = True
        info_calls = []
        monkeypatch.setattr(QMessageBox, "information",
                            lambda *a, **kw: info_calls.append(a))

        win._on_analysis_finished([passed_sample_result])

        assert len(info_calls) == 1

    def test_information_popup_lists_fallback_sample_ids(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        passed_sample_result.ap_used_coarse_fallback = True
        info_calls = []
        monkeypatch.setattr(QMessageBox, "information",
                            lambda *a, **kw: info_calls.append(a))

        win._on_analysis_finished([passed_sample_result])

        # QMessageBox.information(parent, title, text) — text is positional arg 2.
        assert "1666" in info_calls[0][2]

    def test_information_popup_not_shown_when_no_fallback(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        info_calls = []
        monkeypatch.setattr(QMessageBox, "information",
                            lambda *a, **kw: info_calls.append(a))

        win._on_analysis_finished([passed_sample_result])

        assert info_calls == []

    def test_quick_analysis_reports_processing_failure(
        self, qtbot, monkeypatch,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        win._analysis_is_quick = True
        monkeypatch.setattr(
            win, "_confirm_quick_analysis_export", lambda: False,
        )
        failed = SampleResult(
            sample_id="1669",
            animal_id="64280",
            qc_status=QCStatus.ANALYSIS_FAILED,
            file_path="C:/data/unreadable.abf",
            analysis_error="cannot parse selected file",
        )
        warning_calls = []
        monkeypatch.setattr(
            QMessageBox,
            "warning",
            lambda *args, **kwargs: warning_calls.append(args),
        )

        win._on_analysis_finished([failed])

        assert "1 failed to analyze" in win.statusbar.currentMessage()
        assert warning_calls[0][1] == "Failed to Analyze"
        assert "unreadable.abf" in warning_calls[0][2]
        assert "cannot parse selected file" in warning_calls[0][2]


# ---------------------------------------------------------------------------
# AnalysisWorker
# ---------------------------------------------------------------------------

class TestAnalysisWorker:
    def _samples(self):
        return {("animalA", "1666"): SampleInfo(
            animal_id="animalA", sample_id="1666",
        )}

    def test_finished_signal_carries_results(self, qtbot, monkeypatch, passed_sample_result):
        monkeypatch.setattr(mw_module, "analyze_all",
                            lambda *a, **kw: [passed_sample_result])
        worker = AnalysisWorker(self._samples(), {})

        with qtbot.waitSignal(worker.finished, timeout=2000) as blocker:
            worker.start()

        assert blocker.args[0] == [passed_sample_result]

    def test_qc_review_callback_returns_value_set_by_main_thread(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        captured = {}

        def fake_analyze_all(samples, nominal, qc_reviewer, **kwargs):
            captured["qc_result"] = qc_reviewer(
                "1666", "/fake.abf", _make_ap_result(), -65.0,
            )
            return [passed_sample_result]

        monkeypatch.setattr(mw_module, "analyze_all", fake_analyze_all)
        worker = AnalysisWorker(self._samples(), {})
        # Main-thread responder: when qc_needed fires, immediately accept.
        from ephys_analysis.core.types import QCReview
        worker.qc_needed.connect(
            lambda sid, path, ap, rmp: worker.set_qc_result(QCReview(accepted=True))
        )

        with qtbot.waitSignal(worker.finished, timeout=2000):
            worker.start()

        assert captured["qc_result"].accepted is True

    def test_cancel_during_qc_emits_cancelled_signal(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        captured = {}

        def fake_analyze_all(samples, nominal, qc_reviewer, **kwargs):
            try:
                qc_reviewer("1666", "/fake.abf", _make_ap_result(), -65.0)
            except AnalysisCancelled:
                captured["cancelled"] = True
                raise
            return [passed_sample_result]

        monkeypatch.setattr(mw_module, "analyze_all", fake_analyze_all)
        worker = AnalysisWorker(self._samples(), {})
        worker.qc_needed.connect(lambda sid, path, ap, rmp: worker.cancel())

        # AnalysisCancelled is routed to the dedicated `cancelled` signal, not
        # `error` — the user-initiated cancel is not a fatal error.
        with qtbot.waitSignal(worker.cancelled, timeout=2000):
            worker.start()

        assert captured["cancelled"] is True

    def test_error_signal_emitted_on_pipeline_exception(self, qtbot, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("boom")
        monkeypatch.setattr(mw_module, "analyze_all", boom)
        worker = AnalysisWorker(self._samples(), {})

        with qtbot.waitSignal(worker.error, timeout=2000) as blocker:
            worker.start()

        assert "boom" in blocker.args[0]

    def test_cancelled_flag_is_set_by_cancel(self, qtbot):
        worker = AnalysisWorker(self._samples(), {})

        worker.cancel()

        assert worker.is_cancelled is True

    def test_one_s_ap_review_callback_returns_main_thread_verdict(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        captured = {}

        def fake_analyze_all(
            samples, nominal, one_s_ap_reviewer, **kwargs
        ):
            captured["review"] = one_s_ap_reviewer(
                "1666", {}, OneSAPResult(high_firing_sweeps=[11])
            )
            return [passed_sample_result]

        monkeypatch.setattr(mw_module, "analyze_all", fake_analyze_all)
        worker = AnalysisWorker(self._samples(), {})
        worker.one_s_ap_review_needed.connect(
            lambda sid, paths, result: worker.set_one_s_ap_result(
                OneSAPReview(accepted=True)
            )
        )

        with qtbot.waitSignal(worker.finished, timeout=2000):
            worker.start()

        assert captured["review"].accepted is True

    def test_quick_worker_disables_every_qc_callback(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        captured = {}

        def fake_analyze_all(samples, nominal, **kwargs):
            captured.update(kwargs)
            return [passed_sample_result]

        monkeypatch.setattr(mw_module, "analyze_all", fake_analyze_all)
        worker = AnalysisWorker(self._samples(), {}, skip_qc=True)

        with qtbot.waitSignal(worker.finished, timeout=2000):
            worker.start()

        assert captured["skip_qc"] is True
        assert captured["qc_reviewer"] is None
        assert captured["one_s_ap_reviewer"] is None
        assert captured["baseline_reviewer"] is None
        assert captured["ri_ih_reviewer"] is None

    def test_baseline_review_waits_for_main_thread_decisions(
        self, qtbot, monkeypatch, passed_sample_result,
    ):
        captured = {}
        flag = BaselineFlag(
            protocol="2. Resting Membrane Potential",
            file_path="C:/data/rmp.abf",
            target_mv=-67.0,
            baseline_means_mv=[-50.0],
            out_of_range_sweeps=[1],
        )

        def fake_analyze_all(samples, nominal, baseline_reviewer, **kwargs):
            captured["review"] = baseline_reviewer([("1666", flag)])
            return [passed_sample_result]

        monkeypatch.setattr(mw_module, "analyze_all", fake_analyze_all)
        worker = AnalysisWorker(self._samples(), {})
        worker.baseline_flags_found.connect(
            lambda flags: worker.set_baseline_result(
                BaselineReview(decisions={flag.file_path: False})
            )
        )

        with qtbot.waitSignal(worker.finished, timeout=2000):
            worker.start()

        assert captured["review"].decisions == {flag.file_path: False}

    def test_baseline_rejection_is_removed_from_later_protocol_previews(
        self, qtbot,
    ):
        ap_path = Path("C:/data/ap.abf")
        ri_path = Path("C:/data/ri.abf")
        worker = AnalysisWorker(
            {
                ("animalA", "1666"): SampleInfo(
                    animal_id="animalA",
                    sample_id="1666",
                    protocols={"5b. AP fine": ap_path, "4. Ri": ri_path},
                )
            },
            {},
        )

        worker.set_baseline_result(BaselineReview(
            decisions={str(ri_path): False}
        ))

        assert worker._protocol_paths_for(str(ap_path)) == {
            "5b. AP fine": str(ap_path)
        }

    def test_baseline_dialog_returns_decisions_to_worker(
        self, qtbot, monkeypatch,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        reviews = []
        win._worker = SimpleNamespace(
            set_baseline_result=lambda review: reviews.append(review),
            cancel=lambda: None,
        )
        rejected_path = Path("C:/data/rmp.abf")
        accepted_path = Path("C:/data/accepted.abf")
        win._analysis_samples = {
            ("animalA", "1666"): SampleInfo(
                animal_id="animalA",
                sample_id="1666",
                protocols={
                    "2. Resting Membrane Potential": rejected_path,
                    "4. Ih and Input Resistance": accepted_path,
                },
            )
        }
        captured = {}

        class FakeDialog:
            def __init__(self, flags, parent):
                captured["flags"] = flags
                captured["parent"] = parent
                self.decisions = {flags[0][1].file_path: False}

            def exec(self):
                captured["shown"] = True
                return 1

        monkeypatch.setattr(mw_module, "BaselineReviewDialog", FakeDialog)
        flag = BaselineFlag(
            protocol="2. Resting Membrane Potential",
            file_path=str(rejected_path),
            target_mv=-67.0,
            baseline_means_mv=[-50.0, -67.0, -62.0, -67.0],
            out_of_range_sweeps=[1],
            changed_sweep_pairs=[(1, 2), (2, 3), (3, 4)],
        )

        win._on_baseline_flags_found([("1666", flag)])

        assert captured["flags"] == [("1666", flag)]
        assert captured["parent"] is win
        assert captured["shown"] is True
        assert reviews[0].decisions == {flag.file_path: False}
        assert win._analysis_samples[("animalA", "1666")].protocols == {
            "4. Ih and Input Resistance": accepted_path
        }

    def test_closing_baseline_dialog_cancels_analysis(
        self, qtbot, monkeypatch,
    ):
        win = MainWindow()
        qtbot.addWidget(win)
        cancelled = []
        win._worker = SimpleNamespace(
            set_baseline_result=lambda review: None,
            cancel=lambda: cancelled.append(True),
        )

        class FakeDialog:
            decisions = {}

            def __init__(self, flags, parent):
                pass

            def exec(self):
                return 0

        monkeypatch.setattr(mw_module, "BaselineReviewDialog", FakeDialog)
        flag = BaselineFlag(
            protocol="4. Ih and Input Resistance",
            file_path="C:/data/ri.abf",
            target_mv=-67.0,
            out_of_range_sweeps=[1],
        )

        win._on_baseline_flags_found([("1666", flag)])

        assert cancelled == [True]


class TestProtocolSortKey:
    """The file tree sorts protocols by their leading number so `11.` lands
    at the end of the list, not between `1.` and `2.` under lexicographic
    sort.
    """

    def test_protocol_11_sorts_after_9(self):
        from ephys_analysis.gui.main_window import _protocol_sort_key

        names = [
            "1. Spontaneous EPSCs",
            "11. 50 Spike AHP",
            "2. Resting Membrane Potential",
            "9. 1s AP Firing",
        ]
        ordered = sorted(names, key=_protocol_sort_key)

        assert ordered[-1] == "11. 50 Spike AHP"

    def test_letter_suffix_orders_a_before_b(self):
        from ephys_analysis.gui.main_window import _protocol_sort_key

        names = [
            "5b. Single AP fine",
            "5a. Single AP coarse",
            "6. Ramp 6s",
        ]
        ordered = sorted(names, key=_protocol_sort_key)

        assert ordered == [
            "5a. Single AP coarse",
            "5b. Single AP fine",
            "6. Ramp 6s",
        ]

    def test_unprefixed_name_goes_to_end(self):
        from ephys_analysis.gui.main_window import _protocol_sort_key

        names = [
            "Unknown Protocol",
            "1. Spontaneous EPSCs",
            "11. 50 Spike AHP",
        ]
        ordered = sorted(names, key=_protocol_sort_key)

        assert ordered[-1] == "Unknown Protocol"
