"""Separate, guarded UI for clearing EVEL importer target tables."""

from __future__ import annotations

from threading import Event

from qgis.PyQt.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from qgis.core import QgsProject

from ..importer import (
    TABLE_ORDER,
    EvelImportTargetError,
    EvelImportTargetInspector,
    EvelSqlClearCanceled,
    EvelSqlClearer,
)
from .light_style import apply_evel_light_style


class _ClearWorker(QObject):
    progress = pyqtSignal(int, int, str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    canceled = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, clearer, target, dry_run, cancel_event):
        super().__init__()
        self.clearer = clearer
        self.target = target
        self.dry_run = dry_run
        self.cancel_event = cancel_event

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.clearer.run(
                self.target,
                dry_run=self.dry_run,
                progress=self.progress.emit,
                is_canceled=self.cancel_event.is_set,
            )
            self.succeeded.emit(result)
        except EvelSqlClearCanceled as error:
            self.canceled.emit(str(error))
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class EvelClearDataDialog(QDialog):
    """Preview, dry-run and clear only the importer target tables."""

    clear_completed = pyqtSignal(object)
    CONFIRMATION_TEXT = "TÜHJENDA"
    TABLE_LABELS = {
        "SN_WATER_NODE": "Veesõlmed",
        "SN_SEWER_NODE": "Kanalisatsioonisõlmed",
        "SN_WATER_MANHOLE": "Veekaevud",
        "SN_WATER_VALVE": "Vee sulgeseadmed",
        "SN_FIRE_PLUG": "Hüdrandid",
        "SN_SEWER_MANHOLE": "Kanalisatsioonikaevud",
        "SN_SEWER_VALVE": "Kanalisatsiooni sulgeseadmed",
        "SN_WATER_DUCT": "Veetorud",
        "SN_SEWER_DUCT": "Kanalisatsioonitorud",
    }

    def __init__(self, project: QgsProject, parent=None) -> None:
        super().__init__(parent)
        self.project = project
        self.target_inspector = EvelImportTargetInspector()
        self.clearer = EvelSqlClearer()
        self.target = None
        self.preview = None
        self._dry_run_ready = False
        self._thread: QThread | None = None
        self._worker: _ClearWorker | None = None
        self._cancel_event: Event | None = None

        self.setObjectName("evelClearDataDialog")
        self.setWindowTitle("EVEL-i impordiandmete tühjendamine")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModal)
        self.resize(760, 650)
        apply_evel_light_style(self)
        self._build_ui()
        self._load_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("Tühjenda EVEL-i impordi sihttabelid", self)
        title.setStyleSheet("font-size:20px; font-weight:700;")
        layout.addWidget(title)
        warning = QLabel(
            "See tööriist kustutab kõik allpool loetletud üheksa tabeli "
            "kirjed ning nende sõlmedest sõltuvad EVEL-i detailkirjed. "
            "Klassifikaatoreid ei muudeta. Kõik kaasatavad tabelid kuvatakse "
            "enne toimingut. "
            "Enne kustutamist tehakse kohustuslik tagasipööratav SQL-kontroll.",
            self,
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background:#fff4e5; border:1px solid #e3a447; "
            "border-radius:7px; padding:10px;"
        )
        layout.addWidget(warning)

        self.status_label = QLabel("Loen sihttabeleid…", self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(
            ("EVEL-i objektid", "Sihttabel", "Olemasolevaid kirjeid")
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.table, 1)

        blocker_title = QLabel("Seotud tabelite kontroll", self)
        blocker_title.setStyleSheet("font-weight:700;")
        layout.addWidget(blocker_title)
        self.blocker_list = QListWidget(self)
        self.blocker_list.setMaximumHeight(110)
        self.blocker_list.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.blocker_list)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.activity_label = QLabel("", self)
        self.activity_label.setWordWrap(True)
        layout.addWidget(self.activity_label)

        buttons = QHBoxLayout()
        self.close_button = QPushButton("Sulge", self)
        self.close_button.clicked.connect(self._close_or_cancel)
        self.refresh_button = QPushButton("Värskenda", self)
        self.refresh_button.clicked.connect(self._load_preview)
        self.dry_run_button = QPushButton("Kontrolli tühjendamist", self)
        self.dry_run_button.clicked.connect(
            lambda: self._start_clear(dry_run=True)
        )
        self.clear_button = QPushButton("Tühjenda andmed", self)
        self.clear_button.clicked.connect(
            lambda: self._start_clear(dry_run=False)
        )
        buttons.addWidget(self.close_button)
        buttons.addWidget(self.refresh_button)
        buttons.addStretch(1)
        buttons.addWidget(self.dry_run_button)
        buttons.addWidget(self.clear_button)
        layout.addLayout(buttons)

    def _load_preview(self) -> None:
        if self._thread is not None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.target = self.target_inspector.inspect(self.project)
            self.preview = self.clearer.preview(self.target)
        except Exception as error:
            self.target = None
            self.preview = None
            self._show_error(str(error))
        finally:
            QApplication.restoreOverrideCursor()
        self._dry_run_ready = False
        self._fill_preview()
        self._update_buttons()

    def _fill_preview(self) -> None:
        self.table.setRowCount(0)
        self.blocker_list.clear()
        if self.preview is None:
            return
        for table in TABLE_ORDER:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(
                row, 0, QTableWidgetItem(self.TABLE_LABELS[table])
            )
            self.table.setItem(row, 1, QTableWidgetItem(table))
            count = QTableWidgetItem(f"{self.preview.counts[table]:,}")
            count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, count)
        if self.preview.blockers:
            for blocker in self.preview.blockers:
                self.blocker_list.addItem(f"⚠ {blocker}")
            self._show_error(
                "Tühjendamine on blokeeritud teiste EVEL-i tabelite "
                "seotud kirjete tõttu."
            )
        else:
            for table, count in self.preview.dependent_counts.items():
                if count:
                    self.blocker_list.addItem(
                        f"• Kaasatakse {table}: {count:,} seotud kirjet."
                    )
            self.blocker_list.addItem(
                "✓ Väljaspool puhastatavat EVEL-i andmestikku blokeerivaid "
                "seoseid ei leitud."
            )
            self.status_label.setStyleSheet(
                "background:#eefaf2; border:1px solid #77b98a; "
                "border-radius:7px; padding:9px;"
            )
            self.status_label.setText(
                f"Tühjendatavates tabelites on kokku "
                f"{self.preview.total_count:,} kirjet."
            )

    def _start_clear(self, *, dry_run: bool) -> None:
        if self.target is None or self.preview is None or self._thread is not None:
            return
        try:
            current_target = self.target_inspector.inspect(self.project)
        except EvelImportTargetError as error:
            self._show_error(str(error))
            return
        self.target = current_target
        if not dry_run:
            text, accepted = QInputDialog.getText(
                self,
                "Kinnita andmete kustutamine",
                "Kõigi üheksa impordi sihttabeli kirjete kustutamiseks "
                f"sisesta {self.CONFIRMATION_TEXT}:",
                QLineEdit.Normal,
            )
            if (
                not accepted
                or text.strip().upper() != self.CONFIRMATION_TEXT
            ):
                return
            answer = QMessageBox.warning(
                self,
                "Viimane kinnitus",
                f"Kustutatakse {self.preview.total_count:,} kirjet. "
                "Seda toimingut ei saa pärast tehingu kinnitamist tagasi võtta.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return

        self._cancel_event = Event()
        self._thread = QThread(self)
        self._worker = _ClearWorker(
            self.clearer,
            self.target,
            dry_run,
            self._cancel_event,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.canceled.connect(self._on_canceled)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self.progress_bar.setRange(0, max(self.preview.total_count, 1))
        self.progress_bar.setValue(0)
        self.activity_label.setText(
            "Alustan tagasipööratavat tühjendamise kontrolli…"
            if dry_run
            else "Alustan EVEL-i impordiandmete tühjendamist…"
        )
        self._update_buttons(running=True)
        self._thread.start()

    @pyqtSlot(int, int, str)
    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(current)
        self.activity_label.setText(message)

    @pyqtSlot(object)
    def _on_success(self, result) -> None:
        if result.dry_run:
            self._dry_run_ready = True
            self.status_label.setStyleSheet(
                "background:#eefaf2; border:1px solid #77b98a; "
                "border-radius:7px; padding:9px;"
            )
            self.status_label.setText(
                "Tühjendamise SQL-kontroll õnnestus. Kõik proovikustutused "
                "pöörati tagasi; tegelik tühjendamine on nüüd lubatud."
            )
        else:
            self._dry_run_ready = False
            self.status_label.setStyleSheet(
                "background:#eefaf2; border:1px solid #4a9b62; "
                "border-radius:7px; padding:9px; font-weight:600;"
            )
            self.status_label.setText(
                f"Tühjendamine lõpetatud: {result.total_count:,} kirjet "
                "kustutati ühe tehinguna."
            )
            self.clear_completed.emit(result)
            self.preview = None
            self.target = None

    @pyqtSlot(str)
    def _on_failure(self, message: str) -> None:
        self._dry_run_ready = False
        self._show_error(message)
        QMessageBox.critical(self, "Tühjendamine ebaõnnestus", message)

    @pyqtSlot(str)
    def _on_canceled(self, message: str) -> None:
        self._dry_run_ready = False
        self.status_label.setStyleSheet(
            "background:#fff8dc; border:1px solid #e5bf45; "
            "border-radius:7px; padding:9px;"
        )
        self.status_label.setText(message)

    @pyqtSlot()
    def _on_thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._cancel_event = None
        self._update_buttons()

    def _close_or_cancel(self) -> None:
        if self._thread is not None:
            if self._cancel_event is not None:
                self._cancel_event.set()
            self.close_button.setEnabled(False)
            self.activity_label.setText(
                "Katkestan pärast aktiivset SQL-käsku ja teen rollback’i…"
            )
            return
        self.close()

    def _update_buttons(self, *, running: bool = False) -> None:
        if running:
            self.close_button.setText("Katkesta")
            self.close_button.setEnabled(True)
            self.refresh_button.setEnabled(False)
            self.dry_run_button.setEnabled(False)
            self.clear_button.setEnabled(False)
            return
        ready = (
            self.target is not None
            and self.preview is not None
            and self.preview.total_count > 0
            and not self.preview.blockers
        )
        self.close_button.setText("Sulge")
        self.close_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.dry_run_button.setEnabled(ready)
        self.clear_button.setEnabled(ready and self._dry_run_ready)

    def _show_error(self, message: str) -> None:
        self.status_label.setStyleSheet(
            "background:#fff1f1; border:1px solid #d36f76; "
            "border-radius:7px; padding:9px;"
        )
        self.status_label.setText(message)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread is not None:
            event.ignore()
            self._close_or_cancel()
            return
        super().closeEvent(event)
