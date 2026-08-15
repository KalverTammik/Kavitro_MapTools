"""Copyable detailed diagnostics for the EVEL toolbar status control."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from .icon_catalog import ICON_CLOSE, ICON_COPY, set_catalog_icon
from .light_style import apply_evel_light_style


class DiagnosticsDialog(QDialog):
    """Modeless diagnostics window whose complete report can be copied."""

    def __init__(
        self,
        report: str,
        status_text: str,
        status_icon: QIcon,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("evelDiagnosticsDialog")
        self.setWindowTitle("EVEL-i diagnostika")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMinimumSize(680, 480)
        self.resize(820, 590)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(12)

        hero = QFrame(self)
        hero.setObjectName("diagnosticsHeroFrame")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(12, 10, 12, 10)
        hero_layout.setSpacing(10)

        self.status_icon_label = QLabel(hero)
        self.status_icon_label.setObjectName("diagnosticsStatusIcon")
        self.status_icon_label.setFixedSize(28, 28)
        self.status_icon_label.setAlignment(Qt.AlignCenter)
        hero_layout.addWidget(self.status_icon_label)

        headings = QVBoxLayout()
        headings.setContentsMargins(0, 0, 0, 0)
        headings.setSpacing(2)
        title = QLabel("EVEL Võrgutööriistade diagnostika", hero)
        title.setObjectName("diagnosticsTitle")
        headings.addWidget(title)
        self.status_label = QLabel(hero)
        self.status_label.setObjectName("diagnosticsStatus")
        headings.addWidget(self.status_label)
        hero_layout.addLayout(headings, 1)
        root.addWidget(hero)

        hint = QLabel(
            "Allolevat teksti saab valida või tervikuna lõikelauale kopeerida.",
            self,
        )
        hint.setObjectName("diagnosticsHint")
        root.addWidget(hint)

        self.report_edit = QPlainTextEdit(self)
        self.report_edit.setObjectName("diagnosticsReport")
        self.report_edit.setReadOnly(True)
        self.report_edit.setTabChangesFocus(True)
        root.addWidget(self.report_edit, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)
        self.copy_feedback = QLabel("", self)
        self.copy_feedback.setObjectName("diagnosticsCopyFeedback")
        footer.addWidget(self.copy_feedback, 1)

        self.copy_button = QPushButton("Kopeeri kõik", self)
        self.copy_button.setObjectName("diagnosticsCopyButton")
        self.copy_button.setMinimumWidth(122)
        set_catalog_icon(self.copy_button, ICON_COPY)
        self.copy_button.clicked.connect(self.copy_report)
        footer.addWidget(self.copy_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        self.close_button = buttons.button(QDialogButtonBox.Close)
        self.close_button.setText("Sulge")
        set_catalog_icon(self.close_button, ICON_CLOSE)
        buttons.rejected.connect(self.close)
        footer.addWidget(buttons)
        root.addLayout(footer)

        self.set_report(report, status_text, status_icon)
        apply_evel_light_style(self, diagnostics=True)

    @property
    def report(self) -> str:
        return self.report_edit.toPlainText()

    def set_report(
        self,
        report: str,
        status_text: str,
        status_icon: QIcon,
    ) -> None:
        """Replace the report while preserving a useful scroll position."""

        cursor = self.report_edit.textCursor()
        position = cursor.position()
        vertical_position = self.report_edit.verticalScrollBar().value()
        self.report_edit.setPlainText(report)
        cursor = self.report_edit.textCursor()
        cursor.setPosition(min(position, len(report)))
        self.report_edit.setTextCursor(cursor)
        self.report_edit.verticalScrollBar().setValue(vertical_position)
        self.status_label.setText(status_text)
        if "vajab tähelepanu" in status_text.lower():
            severity = "error"
        elif "hoiatustega" in status_text.lower():
            severity = "warning"
        else:
            severity = "success"
        self.status_label.setProperty("severity", severity)
        style = self.status_label.style()
        style.unpolish(self.status_label)
        style.polish(self.status_label)
        self.status_icon_label.setPixmap(status_icon.pixmap(24, 24))
        self.copy_feedback.clear()

    def copy_report(self) -> None:
        QApplication.clipboard().setText(self.report)
        self.copy_feedback.setText("Diagnostika kopeeriti lõikelauale.")
