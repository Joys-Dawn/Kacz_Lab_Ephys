import logging
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QLabel, QProgressBar,
    QStatusBar, QToolBar, QMessageBox, QSplitter,
)
from PySide6.QtCore import Qt, QThread, Signal

from ephys_analysis.core.pipeline import analyze_all
from ephys_analysis.core.types import SampleResult, QCStatus, APFineResult, AnalysisCancelled
from ephys_analysis.io.scanner import scan_project_folder, ScanResult, SampleInfo
from ephys_analysis.io.excel_export import (
    export_passed, export_rejected_vthresh,
    export_rmp_gt_vthresh, export_hyperfiring_sweeps,
    export_ri_ih_contaminated_sweeps, export_trimming_analysis,
)
from ephys_analysis.gui.widgets.trace_viewer import TraceViewer
from ephys_analysis.gui.dialogs.qc_review import QCReviewDialog
from ephys_analysis.gui.dialogs.duplicate_resolver import DuplicateResolverDialog
from ephys_analysis.gui.dialogs.nominal_vars import NominalVarsDialog

logger = logging.getLogger(__name__)


class AnalysisWorker(QThread):
    """Worker thread that runs the analysis pipeline off the GUI thread."""

    progress = Signal(int, str)
    qc_needed = Signal(str, str, object)  # sample_id, ap_path, APFineResult
    finished = Signal(list)
    error = Signal(str)

    def __init__(
        self,
        samples: dict[tuple[str, str], SampleInfo],
        nominal_data: dict[str, dict[str, str]],
    ):
        super().__init__()
        self._samples = samples
        self._nominal_data = nominal_data
        self._qc_event = threading.Event()
        self._qc_result: bool = False
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        try:
            results = analyze_all(
                self._samples,
                self._nominal_data,
                qc_reviewer=self._qc_review,
                progress_callback=self._on_progress,
                cancel_check=lambda: self._cancelled,
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

    def _on_progress(self, index: int, message: str):
        self.progress.emit(index, message)

    def _qc_review(self, sample_id: str, ap_path: str, ap_result: APFineResult) -> bool:
        """Called from worker thread — emits signal and blocks until main thread responds."""
        self._qc_event.clear()
        self.qc_needed.emit(sample_id, ap_path, ap_result)
        self._qc_event.wait()
        if self._cancelled:
            raise AnalysisCancelled()
        return self._qc_result

    def set_qc_result(self, accepted: bool):
        """Called from main thread to unblock the worker."""
        self._qc_result = accepted
        self._qc_event.set()

    def cancel(self):
        """Request cancellation — unblocks any pending QC wait."""
        self._cancelled = True
        self._qc_event.set()



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ephys Analysis")
        self.setMinimumSize(1200, 700)

        self.project_path: Path | None = None
        self.scan_result: ScanResult | None = None
        self.nominal_data: dict[str, dict[str, str]] = {}
        self.results: list[SampleResult] = []
        self._worker: AnalysisWorker | None = None

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
        self.tree.itemClicked.connect(self._on_tree_click)
        left_layout.addWidget(self.tree)
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
        self._export_btn.setEnabled(enabled)

    def _open_project(self):
        path = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if not path:
            return
        self.project_path = Path(path)
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
                for protocol, path in sorted(info.protocols.items()):
                    file_item = QTreeWidgetItem([path.name, protocol])
                    file_item.setData(0, Qt.UserRole, str(path))
                    sample_item.addChild(file_item)

        self.tree.expandAll()

    def _on_tree_click(self, item: QTreeWidgetItem, column: int):
        path_str = item.data(0, Qt.UserRole)
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() == ".abf":
            self.trace_viewer.plot_abf(path)

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

        self.results.clear()
        sample_count = len(self.scan_result.samples)
        self.progress.setVisible(True)
        self.progress.setMaximum(sample_count)
        self._set_toolbar_enabled(False)

        self._worker = AnalysisWorker(self.scan_result.samples, self.nominal_data)
        self._worker.progress.connect(self._on_progress)
        self._worker.qc_needed.connect(self._on_qc_needed)
        self._worker.finished.connect(self._on_analysis_finished)
        self._worker.error.connect(self._on_analysis_error)
        self._worker.start()

    def _on_progress(self, index: int, message: str):
        self.progress.setValue(index)
        self.statusbar.showMessage(message)

    def _on_qc_needed(self, sample_id: str, ap_path: str, ap_result: APFineResult):
        """Show QC review dialog on main thread, then unblock worker."""
        dlg = QCReviewDialog(sample_id, ap_path, ap_result, self)
        dlg.exec()
        if dlg.accepted_result == "cancel":
            self._worker.cancel()
        else:
            self._worker.set_qc_result(dlg.accepted_result is True)

    def _on_analysis_finished(self, results: list[SampleResult]):
        self.results = results
        self.progress.setValue(len(results))
        self.progress.setVisible(False)
        self._set_toolbar_enabled(True)
        self._worker = None

        passed = sum(1 for r in results if r.qc_status == QCStatus.PASSED)
        rejected = sum(1 for r in results if r.qc_status == QCStatus.USER_REJECTED_VTHRESH)
        failed = sum(1 for r in results if r.qc_status == QCStatus.RMP_GT_VTHRESH)
        self.statusbar.showMessage(
            f"Analysis complete: {passed} passed, {rejected} user rejected, {failed} RMP>VThresh"
        )

    def _on_analysis_error(self, error_msg: str):
        self.progress.setVisible(False)
        self._set_toolbar_enabled(True)
        self._worker = None
        QMessageBox.critical(self, "Analysis Error", f"Fatal error during analysis:\n{error_msg}")

    def _export_results(self):
        if not self.results:
            QMessageBox.warning(self, "No Results", "Run analysis first.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not output_dir:
            return

        output_path = Path(output_dir)
        export_passed(self.results, output_path)
        export_rejected_vthresh(self.results, output_path)
        export_rmp_gt_vthresh(self.results, output_path)
        export_hyperfiring_sweeps(self.results, output_path)
        export_ri_ih_contaminated_sweeps(self.results, output_path)
        export_trimming_analysis(self.results, output_path)

        self.statusbar.showMessage(f"Results exported to {output_path}")
        QMessageBox.information(self, "Export Complete",
                                f"Results exported to:\n{output_path}")
