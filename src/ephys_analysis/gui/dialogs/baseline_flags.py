from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QHeaderView,
    QWidget,
)

from ephys_analysis.core.types import BaselineFlag
from ephys_analysis.gui.widgets.trace_viewer import TraceViewer


class WrappedReasonDelegate(QStyledItemDelegate):
    """Paint and size the Reason column as native wrapped item text."""

    def __init__(self, view: QTreeWidget):
        super().__init__(view)
        self._view = view

    def initStyleOption(self, option: QStyleOptionViewItem, index):
        super().initStyleOption(option, index)
        option.features |= QStyleOptionViewItem.WrapText
        option.textElideMode = Qt.ElideNone

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        text_width = max(80, self._view.columnWidth(index.column()) - 10)
        bounds = styled.fontMetrics.boundingRect(
            QRect(0, 0, text_width, 10_000),
            Qt.TextWordWrap,
            styled.text,
        )
        return QSize(text_width, max(36, bounds.height() + 10))


def _sweep_ranges(sweeps: list[int]) -> str:
    if not sweeps:
        return ""
    values = sorted(set(sweeps))
    ranges = []
    start = previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            previous = value
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value
    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(ranges)


def _reason(flag: BaselineFlag) -> str:
    reasons = []
    if flag.out_of_range_sweeps:
        reasons.append(
            f"Outside {flag.target_mv - 10:g} to {flag.target_mv + 10:g} mV: "
            f"sweeps {_sweep_ranges(flag.out_of_range_sweeps)}"
        )
    if flag.changed_sweep_pairs:
        pairs = ", ".join(
            f"{first}-{second}" for first, second in flag.changed_sweep_pairs
        )
        reasons.append(f">=4 mV successive change: pairs {pairs}")
    return "\n".join(reasons)


class BaselineReviewDialog(QDialog):
    """Review baseline-flagged recordings before protocol analysis."""

    def __init__(
        self,
        flags: list[tuple[str, BaselineFlag]],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Baseline QC Review")
        self.setModal(True)
        self.decisions: dict[str, bool] = {}
        self._decision_radios: dict[
            str, tuple[QRadioButton, QRadioButton]
        ] = {}
        self._button_groups: list[QButtonGroup] = []

        layout = QVBoxLayout(self)

        heading = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(
            self.style().standardIcon(QStyle.SP_MessageBoxWarning).pixmap(24, 24)
        )
        heading.addWidget(icon)
        sample_count = len({sample_id for sample_id, _ in flags})
        summary = QLabel(
            f"Review {len(flags)} flagged file"
            f"{'s' if len(flags) != 1 else ''} across {sample_count} sample"
            f"{'s' if sample_count != 1 else ''} before analysis"
        )
        summary.setStyleSheet("font-weight: bold;")
        heading.addWidget(summary)
        heading.addStretch()
        layout.addLayout(heading)

        instructions = QLabel(
            "Preview each recording as needed, then choose Accept or Reject. "
            "Rejected recordings will be excluded from analysis."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.table = QTreeWidget()
        self.table.setHeaderLabels(
            ["Sample", "File", "Protocol", "Reason", "Decision", ""]
        )
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setUniformRowHeights(False)
        self.table.setSelectionMode(QTreeWidget.NoSelection)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._reason_delegate = WrappedReasonDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self._reason_delegate)

        for sample_id, flag in flags:
            reason = _reason(flag)
            values = [
                sample_id,
                Path(flag.file_path).name,
                flag.protocol,
                reason,
            ]
            item = QTreeWidgetItem(values)
            for column, value in enumerate(values):
                item.setToolTip(column, value)
            item.setToolTip(3, reason)
            self.table.addTopLevelItem(item)

            decision_widget = QWidget(self.table)
            decision_layout = QHBoxLayout(decision_widget)
            decision_layout.setContentsMargins(0, 0, 0, 0)
            decision_layout.setSpacing(8)
            accept_radio = QRadioButton("Accept")
            reject_radio = QRadioButton("Reject")
            group = QButtonGroup(self)
            group.setExclusive(True)
            group.addButton(accept_radio)
            group.addButton(reject_radio)
            self._button_groups.append(group)
            self._decision_radios[flag.file_path] = (
                accept_radio,
                reject_radio,
            )
            accept_radio.toggled.connect(
                lambda checked, path=flag.file_path: self._set_decision(
                    path, True, checked
                )
            )
            reject_radio.toggled.connect(
                lambda checked, path=flag.file_path: self._set_decision(
                    path, False, checked
                )
            )
            decision_layout.addWidget(accept_radio)
            decision_layout.addWidget(reject_radio)
            self.table.setItemWidget(item, 4, decision_widget)

            preview_button = QPushButton("Preview")
            preview_button.clicked.connect(
                lambda checked=False, path=Path(flag.file_path): self._preview(path)
            )
            preview_widget = QWidget(self.table)
            preview_layout = QHBoxLayout(preview_widget)
            preview_layout.setContentsMargins(3, 0, 3, 0)
            preview_button.setFixedHeight(28)
            preview_layout.addWidget(preview_button)
            self.table.setItemWidget(item, 5, preview_widget)

        header = self.table.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 160)
        self.table.setColumnWidth(4, 210)
        self.table.setColumnWidth(5, 90)
        header.sectionResized.connect(self._schedule_row_layout)
        layout.addWidget(self.table, stretch=1)

        self.review_status = QLabel()
        layout.addWidget(self.review_status)

        buttons = QDialogButtonBox()
        self.continue_button = buttons.addButton(
            "Continue Analysis", QDialogButtonBox.AcceptRole
        )
        self.continue_button.setDefault(True)
        self.continue_button.setEnabled(False)
        cancel_button = buttons.addButton(
            "Cancel Analysis", QDialogButtonBox.RejectRole
        )
        cancel_button.clicked.connect(self.reject)
        self.continue_button.clicked.connect(self.accept)
        layout.addWidget(buttons)
        self._update_review_status()

        available = self.screen().availableGeometry()
        width = min(1100, max(680, available.width() - 60))
        content_height = 220 + min(len(flags), 12) * 34
        height = min(680, max(420, content_height))
        self.resize(
            min(width, available.width() - 40),
            min(height, available.height() - 40),
        )

    def _set_decision(self, path: str, accepted: bool, checked: bool):
        if not checked:
            return
        self.decisions[path] = accepted
        self._update_review_status()

    def _update_review_status(self):
        decided = len(self.decisions)
        total = len(self._decision_radios)
        self.review_status.setText(f"{decided} of {total} files reviewed")
        self.continue_button.setEnabled(decided == total)

    def _schedule_row_layout(self, *args):
        QTimer.singleShot(0, self.table.doItemsLayout)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_row_layout()

    def _preview(self, path: Path):
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.setWindowTitle(f"Preview: {path.name}")
        dialog.setMinimumSize(700, 450)
        layout = QVBoxLayout(dialog)
        viewer = TraceViewer(dialog, figsize=(7, 4))
        viewer.plot_abf(path)
        layout.addWidget(viewer)
        dialog.show()
