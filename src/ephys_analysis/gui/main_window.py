import logging
import re
import threading
from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QLabel, QProgressBar,
    QPlainTextEdit, QStatusBar, QToolBar, QMessageBox, QSplitter,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QThread, Signal

from ephys_analysis.core.pipeline import (
    analyze_all, exclude_protocol_paths, format_sample_notes,
)
from ephys_analysis.core.types import (
    SampleResult, QCStatus, APFineResult, AnalysisCancelled, QCReview,
    OneSAPResult, OneSAPReview, BaselineFlag, BaselineReview,
)
from ephys_analysis.io.scanner import scan_project_folder, ScanResult, SampleInfo
from ephys_analysis.io.excel_export import (
    create_export_timestamp, export_passed, export_rejected,
    export_fully_compiled,
    export_ri_ih_contaminated_sweeps, export_trimming_analysis,
)
from ephys_analysis.gui.widgets.trace_viewer import TraceViewer
from ephys_analysis.gui.dialogs.baseline_flags import BaselineReviewDialog
from ephys_analysis.gui.dialogs.qc_review import QCReviewDialog
from ephys_analysis.gui.dialogs.one_s_ap_review import OneSAPReviewDialog
from ephys_analysis.gui.dialogs.duplicate_resolver import DuplicateResolverDialog
from ephys_analysis.gui.dialogs.nominal_vars import NominalVarsDialog
from ephys_analysis.protocols import (
    PROTO_RMP, PROTO_RI_IH, PROTO_AP_COARSE, PROTO_AP_FINE, PROTO_RAMP,
    PROTO_1S_AP, PROTO_AHP_5, PROTO_AHP_25, PROTO_AHP_50,
)

logger = logging.getLogger(__name__)


_PROTOCOL_PREFIX_RE = re.compile(r"^(\d+)([a-z]?)\.", re.IGNORECASE)
_ANALYZED_PROTOCOLS = {
    PROTO_RMP,
    PROTO_RI_IH,
    PROTO_AP_COARSE,
    PROTO_AP_FINE,
    PROTO_RAMP,
    PROTO_1S_AP,
    PROTO_AHP_5,
    PROTO_AHP_25,
    PROTO_AHP_50,
}


def _protocol_sort_key(name: str) -> tuple[int, str, str]:
    """Sort protocols by their leading number (and optional letter), so
    `11.` lands at the end of the list rather than between `1.` and `2.`
    under default lexicographic sort. Letter is lowercased so `5A` and `5a`
    cluster together.
    """
    m = _PROTOCOL_PREFIX_RE.match(name)
    if m:
        return (int(m.group(1)), m.group(2).lower(), name)
    # No recognized prefix → sort to the end.
    return (10**9, "", name)


class AnalysisWorker(QThread):
    """Worker thread that runs the analysis pipeline off the GUI thread."""

    progress = Signal(int, str)
    # sample_id, ap_path, APFineResult, rmp_mv, all protocol paths
    qc_needed = Signal(str, str, object, float, object)
    # sample_id, all protocol paths, OneSAPResult
    one_s_ap_review_needed = Signal(str, object, object)
    # list of (sample_id, BaselineFlag)
    baseline_flags_found = Signal(object)
    finished = Signal(list)
    cancelled = Signal()
    error = Signal(str)

    def __init__(
        self,
        samples: dict[tuple[str, str], SampleInfo],
        nominal_data: dict[str, dict[str, str]],
        file_notes: dict[str, str] | None = None,
        skip_qc: bool = False,
    ):
        super().__init__()
        self._samples = samples
        self._nominal_data = nominal_data
        self._file_notes = file_notes if file_notes is not None else {}
        self._skip_qc = skip_qc
        self._review_event = threading.Event()
        self._qc_result: QCReview = QCReview(accepted=False)
        self._one_s_ap_result: OneSAPReview = OneSAPReview(accepted=False)
        self._baseline_result = BaselineReview()
        self._cancelled = False

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        try:
            results = analyze_all(
                self._samples,
                self._nominal_data,
                qc_reviewer=None if self._skip_qc else self._qc_review,
                one_s_ap_reviewer=(
                    None if self._skip_qc else self._one_s_ap_review
                ),
                file_notes=self._file_notes,
                baseline_reviewer=(
                    None if self._skip_qc else self._review_baseline_flags
                ),
                skip_qc=self._skip_qc,
                progress_callback=self._on_progress,
                cancel_check=lambda: self._cancelled,
            )
            self.finished.emit(results)
        except AnalysisCancelled:
            self.cancelled.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, index: int, message: str):
        self.progress.emit(index, message)

    def _qc_review(
        self, sample_id: str, ap_path: str, ap_result: APFineResult, rmp_mv: float,
    ) -> QCReview:
        """Called from worker thread — emits signal and blocks until main thread responds."""
        self._review_event.clear()
        protocol_paths = self._protocol_paths_for(ap_path)
        self.qc_needed.emit(
            sample_id, ap_path, ap_result, rmp_mv, protocol_paths
        )
        self._review_event.wait()
        if self._cancelled:
            raise AnalysisCancelled()
        return self._qc_result

    def _one_s_ap_review(
        self,
        sample_id: str,
        protocol_paths: dict[str, str],
        result: OneSAPResult,
    ) -> OneSAPReview:
        self._review_event.clear()
        self.one_s_ap_review_needed.emit(sample_id, protocol_paths, result)
        self._review_event.wait()
        if self._cancelled:
            raise AnalysisCancelled()
        return self._one_s_ap_result

    def _review_baseline_flags(
        self, flags: list[tuple[str, BaselineFlag]],
    ) -> BaselineReview:
        self._review_event.clear()
        self.baseline_flags_found.emit(flags)
        self._review_event.wait()
        if self._cancelled:
            raise AnalysisCancelled()
        return self._baseline_result

    def _protocol_paths_for(self, source_path: str) -> dict[str, str]:
        for info in self._samples.values():
            if any(str(path) == source_path for path in info.protocols.values()):
                return {
                    protocol: str(path)
                    for protocol, path in sorted(
                        info.protocols.items(),
                        key=lambda item: _protocol_sort_key(item[0]),
                    )
                }
        return {}

    def set_qc_result(self, review: QCReview):
        """Called from main thread to unblock the worker."""
        self._qc_result = review
        self._review_event.set()

    def set_one_s_ap_result(self, review: OneSAPReview):
        self._one_s_ap_result = review
        self._review_event.set()

    def set_baseline_result(self, review: BaselineReview):
        self._baseline_result = review
        rejected_paths = {
            path for path, accepted in review.decisions.items() if not accepted
        }
        self._samples = exclude_protocol_paths(
            self._samples, rejected_paths
        )
        self._review_event.set()

    def cancel(self):
        """Request cancellation — unblocks any pending QC wait."""
        self._cancelled = True
        self._review_event.set()



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ephys Analysis")
        self.setMinimumSize(1200, 700)

        self.project_path: Path | None = None
        self.scan_result: ScanResult | None = None
        self.nominal_data: dict[str, dict[str, str]] = {}
        self.results: list[SampleResult] = []
        self.file_notes: dict[str, str] = {}
        self._active_note_path: str | None = None
        self._worker: AnalysisWorker | None = None
        self._analysis_samples: dict[tuple[str, str], SampleInfo] = {}
        self._analysis_is_quick = False

        self._setup_toolbar()
        self._setup_ui()
        self._setup_statusbar()

    def _setup_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._open_btn = QPushButton("Open Project Folder")
        self._open_btn.clicked.connect(self._open_project)
        toolbar.addWidget(self._open_btn)

        self._nominal_btn = QPushButton("Load Nominal Variables")
        self._nominal_btn.clicked.connect(self._load_nominal)
        toolbar.addWidget(self._nominal_btn)

        self._run_btn = QPushButton("Run Analysis")
        self._run_btn.setStyleSheet("font-weight: bold;")
        self._run_btn.clicked.connect(self._run_analysis)
        toolbar.addWidget(self._run_btn)

        self._quick_run_btn = QPushButton("Quick Analysis")
        self._quick_run_btn.clicked.connect(self._run_quick_analysis)
        toolbar.addWidget(self._quick_run_btn)

        self._export_btn = QPushButton("Export Results")
        self._export_btn.clicked.connect(self._export_results)
        toolbar.addWidget(self._export_btn)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)

        # Left: file tree
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Project Files"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Protocol"])
        self.tree.setColumnWidth(0, 200)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemClicked.connect(self._on_tree_click)
        left_layout.addWidget(self.tree)
        notes_label = QLabel("File Notes")
        self.notes_editor = QPlainTextEdit()
        notes_label.setBuddy(self.notes_editor)
        self.notes_editor.setMaximumHeight(100)
        self.notes_editor.setEnabled(False)
        self.notes_editor.textChanged.connect(self._save_active_note)
        left_layout.addWidget(notes_label)
        left_layout.addWidget(self.notes_editor)
        splitter.addWidget(left)

        # Right: trace preview
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Trace Preview"))
        self.trace_viewer = TraceViewer(right, figsize=(8, 5))
        right_layout.addWidget(self.trace_viewer)
        splitter.addWidget(right)

        splitter.setSizes([350, 850])
        layout.addWidget(splitter)

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(300)
        self.progress.setVisible(False)
        self.statusbar.addPermanentWidget(self.progress)

    def _set_toolbar_enabled(self, enabled: bool):
        """Enable/disable toolbar buttons during analysis."""
        self._open_btn.setEnabled(enabled)
        self._nominal_btn.setEnabled(enabled)
        self._run_btn.setEnabled(enabled)
        self._quick_run_btn.setEnabled(enabled)
        self._export_btn.setEnabled(enabled)
        self.notes_editor.setEnabled(enabled and self._active_note_path is not None)

    def _open_project(self):
        path = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if not path:
            return
        self.project_path = Path(path)
        self.results.clear()
        self._analysis_samples = {}
        self.file_notes.clear()
        self._active_note_path = None
        self.notes_editor.clear()
        self.notes_editor.setEnabled(False)
        self.statusbar.showMessage(f"Scanning {self.project_path}...")
        self.scan_result = scan_project_folder(self.project_path)

        # Handle duplicates
        if self.scan_result.duplicates:
            dlg = DuplicateResolverDialog(self.scan_result.duplicates, self)
            if dlg.exec():
                for key, selected_path in dlg.selections.items():
                    animal_id, sample_id, protocol = key
                    self.scan_result.samples[(animal_id, sample_id)].protocols[protocol] = selected_path
            self.scan_result.duplicates.clear()

        self._populate_tree()
        self.statusbar.showMessage(
            f"Loaded {len(self.scan_result.samples)} samples from {self.project_path.name}"
        )

    def _populate_tree(self):
        self.tree.clear()
        if not self.scan_result:
            return

        # Group by animal ID
        animals: dict[str, list] = {}
        for (animal_id, sample_id), info in self.scan_result.samples.items():
            animals.setdefault(animal_id, []).append(info)

        for animal_id, infos in sorted(animals.items()):
            animal_item = QTreeWidgetItem([animal_id])
            self.tree.addTopLevelItem(animal_item)
            for info in sorted(infos, key=lambda i: i.sample_id):
                sample_item = QTreeWidgetItem([info.sample_id])
                animal_item.addChild(sample_item)
                for protocol, path in sorted(
                    info.protocols.items(),
                    key=lambda kv: _protocol_sort_key(kv[0]),
                ):
                    file_item = QTreeWidgetItem([path.name, protocol])
                    file_item.setData(0, Qt.UserRole, str(path))
                    sample_item.addChild(file_item)

        self.tree.expandAll()

    def _on_tree_click(self, item: QTreeWidgetItem, column: int):
        path_str = item.data(0, Qt.UserRole)
        if not path_str:
            self._active_note_path = None
            self.notes_editor.blockSignals(True)
            self.notes_editor.clear()
            self.notes_editor.blockSignals(False)
            self.notes_editor.setEnabled(False)
            return
        path = Path(path_str)
        if path.suffix.lower() == ".abf":
            self._active_note_path = path_str
            self.notes_editor.blockSignals(True)
            self.notes_editor.setPlainText(self.file_notes.get(path_str, ""))
            self.notes_editor.blockSignals(False)
            self.notes_editor.setEnabled(self._worker is None)
            self.trace_viewer.plot_abf(path)

    def _save_active_note(self):
        if self._active_note_path is None:
            return
        note = self.notes_editor.toPlainText().strip()
        if note:
            self.file_notes[self._active_note_path] = note
        else:
            self.file_notes.pop(self._active_note_path, None)

    def _load_nominal(self):
        dlg = NominalVarsDialog(self)
        if dlg.exec():
            self.nominal_data = dlg.nominal_data
            self.statusbar.showMessage(
                f"Loaded nominal variables for {len(self.nominal_data)} samples"
            )

    def _run_analysis(self):
        if not self.scan_result:
            QMessageBox.warning(self, "No Data", "Open a project folder first.")
            return

        self._start_analysis(self.scan_result.samples, skip_qc=False)

    def _run_quick_analysis(self):
        if not self.scan_result:
            QMessageBox.warning(self, "No Data", "Open a project folder first.")
            return

        selected_paths = {
            str(path)
            for item in self.tree.selectedItems()
            if (path := item.data(0, Qt.UserRole))
        }
        if not selected_paths:
            QMessageBox.warning(
                self,
                "No Files Selected",
                "Select one or more ABF files in Project Files first.",
            )
            return

        selected_samples = {}
        unsupported_protocols = set()
        for key, info in self.scan_result.samples.items():
            selected_protocols = {}
            for protocol, path in info.protocols.items():
                if str(path) not in selected_paths:
                    continue
                if protocol in _ANALYZED_PROTOCOLS:
                    selected_protocols[protocol] = path
                else:
                    unsupported_protocols.add(protocol)
            if selected_protocols:
                selected_samples[key] = replace(
                    info,
                    protocols=selected_protocols,
                )

        if unsupported_protocols:
            QMessageBox.information(
                self,
                "Files Without Analyzers",
                "These selected protocols do not have analysis metrics and "
                "will not be included:\n\n"
                + "\n".join(sorted(unsupported_protocols)),
            )
        if not selected_samples:
            QMessageBox.warning(
                self,
                "No Analyzable Files",
                "None of the selected files has an implemented analyzer.",
            )
            return

        self._start_analysis(selected_samples, skip_qc=True)

    def _start_analysis(
        self,
        samples: dict[tuple[str, str], SampleInfo],
        *,
        skip_qc: bool,
    ):
        self.results.clear()
        self._analysis_samples = samples
        self._analysis_is_quick = skip_qc
        sample_count = len(samples)
        self.progress.setVisible(True)
        self.progress.setMaximum(sample_count)
        self._set_toolbar_enabled(False)

        self._save_active_note()
        self._worker = AnalysisWorker(
            samples,
            self.nominal_data,
            self.file_notes,
            skip_qc=skip_qc,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.qc_needed.connect(self._on_qc_needed)
        self._worker.one_s_ap_review_needed.connect(
            self._on_one_s_ap_review_needed
        )
        self._worker.baseline_flags_found.connect(
            self._on_baseline_flags_found
        )
        self._worker.finished.connect(self._on_analysis_finished)
        self._worker.cancelled.connect(self._on_analysis_cancelled)
        self._worker.error.connect(self._on_analysis_error)
        self._worker.start()

    def _on_progress(self, index: int, message: str):
        self.progress.setValue(index)
        self.statusbar.showMessage(message)

    def _on_baseline_flags_found(
        self, flags: list[tuple[str, BaselineFlag]],
    ):
        dialog = BaselineReviewDialog(flags, self)
        accepted = dialog.exec()
        if not self._worker:
            return
        if accepted:
            review = BaselineReview(decisions=dialog.decisions)
            rejected_paths = {
                path
                for path, keep in review.decisions.items()
                if not keep
            }
            self._analysis_samples = exclude_protocol_paths(
                self._analysis_samples, rejected_paths
            )
            self._worker.set_baseline_result(review)
        else:
            self._worker.cancel()

    def _on_qc_needed(
        self,
        sample_id: str,
        ap_path: str,
        ap_result: APFineResult,
        rmp_mv: float,
        protocol_paths: dict[str, str],
    ):
        """Show QC review dialog on main thread, then unblock worker."""
        dlg = QCReviewDialog(
            sample_id,
            ap_path,
            ap_result,
            rmp_mv,
            self,
            protocol_paths=protocol_paths,
            initial_note=self.file_notes.get(ap_path, ""),
            auto_rejected=rmp_mv >= ap_result.voltage_threshold_mv,
        )
        dlg.exec()
        self._store_file_note(ap_path, dlg.notes)
        if dlg.accepted_result == "cancel":
            self._worker.cancel()
        else:
            review = QCReview(
                accepted=dlg.accepted_result is True,
                override_vthresh_mv=dlg.override_vthresh_mv,
                notes=dlg.notes,
                override_auto_reject=dlg.override_auto_reject,
            )
            self._worker.set_qc_result(review)

    def _on_one_s_ap_review_needed(
        self,
        sample_id: str,
        protocol_paths: dict[str, str],
        result: OneSAPResult,
    ):
        one_s_path = protocol_paths[PROTO_1S_AP]
        dlg = OneSAPReviewDialog(
            sample_id,
            protocol_paths,
            result,
            self,
            initial_note=self.file_notes.get(one_s_path, ""),
        )
        dlg.exec()
        self._store_file_note(one_s_path, dlg.notes)
        if dlg.accepted_result == "cancel":
            self._worker.cancel()
        else:
            self._worker.set_one_s_ap_result(OneSAPReview(
                accepted=dlg.accepted_result is True,
                notes=dlg.notes,
            ))

    def _store_file_note(self, path: str, note: str):
        cleaned = note.strip()
        if cleaned:
            self.file_notes[path] = cleaned
        else:
            self.file_notes.pop(path, None)
        if self._active_note_path == path:
            self.notes_editor.blockSignals(True)
            self.notes_editor.setPlainText(cleaned)
            self.notes_editor.blockSignals(False)

    def _on_analysis_finished(self, results: list[SampleResult]):
        self.results = results
        self.progress.setValue(len(results))
        self.progress.setVisible(False)
        self._set_toolbar_enabled(True)
        self._worker = None
        analysis_failures = [
            result
            for result in results
            if result.qc_status == QCStatus.ANALYSIS_FAILED
        ]

        if self._analysis_is_quick:
            selected_file_count = sum(
                len(info.protocols)
                for info in self._analysis_samples.values()
            )
            self.statusbar.showMessage(
                f"Quick analysis complete: {selected_file_count} file(s), "
                f"{len(results)} sample(s), "
                f"{len(analysis_failures)} failed to analyze, QC skipped"
            )
            self._show_analysis_failures(analysis_failures)
            if self._confirm_quick_analysis_export():
                self._export_results()
            return

        passed = sum(1 for r in results if r.qc_status == QCStatus.PASSED)
        rejected = sum(
            1 for r in results
            if r.qc_status in (
                QCStatus.USER_REJECTED_VTHRESH,
                QCStatus.USER_REJECTED_1S_AP,
            )
        )
        failed = sum(1 for r in results if r.qc_status == QCStatus.RMP_GT_VTHRESH)
        fallback_samples = [r.sample_id for r in results if r.ap_used_coarse_fallback]
        message = (
            f"Analysis complete: {passed} passed, {rejected} user rejected, "
            f"{failed} RMP>VThresh, "
            f"{len(analysis_failures)} failed to analyze"
        )
        if fallback_samples:
            message += f", {len(fallback_samples)} used AP coarse fallback"
        self.statusbar.showMessage(message)

        # Modal popup so the user can't miss that AP fine returned no spike
        # for one or more samples and the analyzer silently used coarse —
        # they may want to re-check the AP duplicate-resolver selection.
        if fallback_samples:
            QMessageBox.information(
                self, "AP Coarse Fallback Used",
                "The AP fine analyzer found no spike for the following "
                f"sample{'s' if len(fallback_samples) != 1 else ''}, so the "
                "AP coarse file was used for AP metrics instead:\n\n"
                + ", ".join(fallback_samples)
                + "\n\nReview the AP files for these samples — you may want "
                "to re-pick the AP fine duplicate."
            )

        self._show_analysis_failures(analysis_failures)

    def _show_analysis_failures(self, failures: list[SampleResult]):
        if not failures:
            return
        lines = []
        for result in failures:
            source = (
                f" | {Path(result.file_path).name}"
                if result.file_path
                else ""
            )
            lines.append(
                f"{result.sample_id}{source}: {result.analysis_error}"
            )
        QMessageBox.warning(
            self,
            "Failed to Analyze",
            "The following selection(s) failed to analyze:\n\n"
            + "\n".join(lines),
        )

    def _on_analysis_cancelled(self):
        self.progress.setVisible(False)
        self._set_toolbar_enabled(True)
        self._worker = None
        self.statusbar.showMessage("Analysis cancelled")

    def _on_analysis_error(self, error_msg: str):
        self.progress.setVisible(False)
        self._set_toolbar_enabled(True)
        self._worker = None
        QMessageBox.critical(self, "Analysis Error", f"Fatal error during analysis:\n{error_msg}")

    def _confirm_quick_analysis_export(self) -> bool:
        prompt = QMessageBox(self)
        prompt.setIcon(QMessageBox.Information)
        prompt.setWindowTitle("Quick Analysis Complete")
        prompt.setText("Quick analysis is complete.")
        prompt.setInformativeText("Export results now?")
        export_button = prompt.addButton(
            "Export Results", QMessageBox.AcceptRole,
        )
        prompt.addButton("Later", QMessageBox.RejectRole)
        prompt.setDefaultButton(export_button)
        prompt.exec()
        return prompt.clickedButton() is export_button

    def _export_results(self):
        if not self.results:
            QMessageBox.warning(self, "No Results", "Run analysis first.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not output_dir:
            return

        output_path = Path(output_dir)
        self._save_active_note()
        analysis_samples = self._analysis_samples
        if not analysis_samples and self.scan_result:
            analysis_samples = self.scan_result.samples
        if analysis_samples:
            for result in self.results:
                info = analysis_samples.get(
                    (result.animal_id, result.sample_id)
                )
                if info:
                    result.notes = format_sample_notes(info, self.file_notes)
        timestamp = create_export_timestamp()
        export_passed(self.results, output_path, timestamp)
        export_rejected(self.results, output_path, timestamp)
        export_fully_compiled(self.results, output_path, timestamp)
        export_ri_ih_contaminated_sweeps(
            self.results, output_path, timestamp
        )
        export_trimming_analysis(self.results, output_path, timestamp)

        self.statusbar.showMessage(f"Results exported to {output_path}")
        QMessageBox.information(self, "Export Complete",
                                f"Results exported to:\n{output_path}")
