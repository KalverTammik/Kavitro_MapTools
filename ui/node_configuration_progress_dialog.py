"""Progress and activity overview for an atomic node configuration write."""

from __future__ import annotations

from qgis.PyQt.QtCore import QEventLoop, Qt
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QVBoxLayout,
)

from .light_style import apply_evel_light_style


class NodeConfigurationProgressDialog(QDialog):
    """Keep users informed while QGIS performs synchronous layer edits."""

    def __init__(self, node_id: int, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("evelNodeConfigurationProgressDialog")
        apply_evel_light_style(self)
        self._active_item: QListWidgetItem | None = None
        self._active_message = ""

        self.setWindowTitle(f"Veesõlme {node_id} rakendamine")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModal)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Palun oota. Torude, sõlmede ja detailkirjete muudatused "
            "rakendatakse ühe tagasipööratava operatsioonina."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.activity_label = QLabel("Valmistan toimingut ette…", self)
        self.activity_label.setWordWrap(True)
        self.activity_label.setStyleSheet("font-weight: bold; padding-top: 6px;")
        layout.addWidget(self.activity_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Etapp %v / %m")
        layout.addWidget(self.progress_bar)

        self.timeline = QListWidget(self)
        self.timeline.setFocusPolicy(Qt.NoFocus)
        self.timeline.setSelectionMode(QListWidget.NoSelection)
        self.timeline.setMinimumHeight(170)
        layout.addWidget(self.timeline)

    def update_progress(
        self,
        current: int,
        total: int,
        message: str,
    ) -> None:
        """Advance the bar and append one user-readable activity."""

        total = max(int(total), 1)
        current = min(max(int(current), 0), total)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(current)
        self.activity_label.setText(message)

        if message != self._active_message:
            if self._active_item is not None:
                self._active_item.setText(f"✓ {self._active_message}")
            prefix = "✓" if current >= total else "▶"
            self._active_item = QListWidgetItem(f"{prefix} {message}")
            self.timeline.addItem(self._active_item)
            self._active_message = message
            self.timeline.scrollToBottom()

        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def show_failure(self, message: str) -> None:
        """Display a final failed activity before the controller reports it."""

        if self._active_item is not None:
            self._active_item.setText(f"✓ {self._active_message}")
        self._active_item = QListWidgetItem(f"✕ {message}")
        self.timeline.addItem(self._active_item)
        self._active_message = message
        self.activity_label.setText(message)
        self.progress_bar.setStyleSheet(
            "QProgressBar::chunk { background-color: #c53030; }"
        )
        self.timeline.scrollToBottom()
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
