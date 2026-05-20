"""GUI tests for MainWindow + AnalysisWorker.

External dependencies (file dialog, project scanner, message boxes, the
analysis pipeline) are monkeypatched at their import site in
`ephys_analysis.gui.main_window` so no real ABFs, displays, or modals are
needed.
"""
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ephys_analysis.core.types import AnalysisCancelled, APFineResult
from ephys_analysis.gui import main_window as mw_module
from ephys_analysis.gui.main_window import AnalysisWorker, MainWindow
from ephys_analysis.io.scanner import SampleInfo


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
            "export_hyperfiring_sweeps", "export_ri_ih_contaminated_sweeps",
            "export_trimming_analysis",
        ]:
            monkeypatch.setattr(mw_module, fn,
                                (lambda name: lambda *a, **kw: called.append(name))(fn))

        win._export_results()

        assert set(called) == {
            "export_passed", "export_rejected",
            "export_hyperfiring_sweeps", "export_ri_ih_contaminated_sweeps",
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
