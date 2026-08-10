"""Non-blocking UI for EVEL GeoPackage SQL import."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event

from qgis.PyQt.QtCore import QObject, QSettings, QThread, Qt, pyqtSignal, pyqtSlot
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
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
    EvelImportPackageError,
    EvelImportPackageReader,
    EvelImportTargetError,
    EvelImportTargetInspector,
    EvelSqlImportCanceled,
    EvelSqlImporter,
)
from .light_style import apply_evel_light_style


class _ImportWorker(QObject):
    progress = pyqtSignal(int, int, str)
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    canceled = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, importer, plan, target, dry_run, cancel_event):
        super().__init__()
        self.importer = importer
        self.plan = plan
        self.target = target
        self.dry_run = dry_run
        self.cancel_event = cancel_event

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.importer.run(
                self.plan,
                self.target,
                dry_run=self.dry_run,
                progress=self.progress.emit,
                is_canceled=self.cancel_event.is_set,
            )
            self.succeeded.emit(result)
        except EvelSqlImportCanceled as error:
            self.canceled.emit(str(error))
        except Exception as error:  # SQL service already sanitizes details
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class EvelImportDialog(QDialog):
    """Select, validate, dry-run and import one client review package."""

    import_completed = pyqtSignal(object, object)
    SETTINGS_KEY = "EVELNetworkTools/importer/lastDirectory"
    IMPORT_ENTRY_SCOPE = "EVELNetworkTools"
    IMPORT_ENTRY_PREFIX = "importedPackage_"
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
        self.reader = EvelImportPackageReader()
        self.target_inspector = EvelImportTargetInspector()
        self.importer = EvelSqlImporter()
        self.plan = None
        self.target = None
        self._dry_run_hash = ""
        self._thread: QThread | None = None
        self._worker: _ImportWorker | None = None
        self._cancel_event: Event | None = None
        self._active_dry_run = False

        self.setObjectName("evelImportDialog")
        self.setWindowTitle("EVEL andmete import")
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModal)
        self.resize(820, 680)
        apply_evel_light_style(self)
        self._build_ui()
        self._update_buttons()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("Impordi kontrollitud GeoPackage EVEL-i", self)
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)
        intro = QLabel(
            "Importer kontrollib paketti ja sihtandmebaasi, teeb esmalt "
            "täieliku tagasipööratava SQL-proovi ning impordib sõlmed, "
            "detailid ja torud ühe tehinguna.",
            self,
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        file_frame = QFrame(self)
        file_frame.setObjectName("lightSurface")
        file_layout = QHBoxLayout(file_frame)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.path_edit = QLineEdit(file_frame)
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Vali EVEL-i kliendi kontrollpakett…")
        self.browse_button = QPushButton("Vali GeoPackage…", file_frame)
        self.browse_button.clicked.connect(self._browse)
        file_layout.addWidget(self.path_edit, 1)
        file_layout.addWidget(self.browse_button)
        layout.addWidget(file_frame)

        self.status_label = QLabel("Paketti pole valitud.", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background:#edf6ff; border:1px solid #b8d8f0; "
            "border-radius:7px; padding:9px;"
        )
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(
            ("EVEL-i objektid", "Sihttabel", "Arv")
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        layout.addWidget(self.table, 1)

        warning_title = QLabel("Kontrolli tähelepanekud", self)
        warning_title.setStyleSheet("font-weight: 700;")
        layout.addWidget(warning_title)
        self.warning_list = QListWidget(self)
        self.warning_list.setMinimumHeight(90)
        self.warning_list.setMaximumHeight(135)
        self.warning_list.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.warning_list)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)
        self.activity_label = QLabel("", self)
        self.activity_label.setWordWrap(True)
        layout.addWidget(self.activity_label)

        button_layout = QHBoxLayout()
        self.close_button = QPushButton("Sulge", self)
        self.close_button.clicked.connect(self._close_or_cancel)
        self.dry_run_button = QPushButton("Kontrolli SQL-importi", self)
        self.dry_run_button.clicked.connect(
            lambda: self._start_import(dry_run=True)
        )
        self.import_button = QPushButton("Impordi andmed", self)
        self.import_button.setDefault(True)
        self.import_button.clicked.connect(
            lambda: self._start_import(dry_run=False)
        )
        button_layout.addWidget(self.close_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.dry_run_button)
        button_layout.addWidget(self.import_button)
        layout.addLayout(button_layout)

    def set_package_path(self, path: str | Path) -> None:
        self._load_package(Path(path))

    def _browse(self) -> None:
        settings = QSettings()
        initial = str(settings.value(self.SETTINGS_KEY, "") or "")
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Vali EVEL-i kontrollpakett",
            initial,
            "GeoPackage (*.gpkg)",
        )
        if not path:
            return
        settings.setValue(self.SETTINGS_KEY, str(Path(path).parent))
        self._load_package(Path(path))

    def _load_package(self, path: Path) -> None:
        if self._thread is not None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            plan = self.reader.read(path)
            target = self.target_inspector.inspect(self.project)
            imported = self._import_timestamp(plan.package_sha256)
            if imported:
                raise EvelImportPackageError(
                    "See sama kontrollpakett on projekti andmetel juba "
                    f"imporditud ({imported})."
                )
        except (EvelImportPackageError, EvelImportTargetError) as error:
            self.plan = None
            self.target = None
            self.path_edit.setText(str(path))
            self._show_error(str(error))
            self._clear_summary()
            self._update_buttons()
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.plan = plan
        self.target = target
        self._dry_run_hash = ""
        self.path_edit.setText(str(path))
        self.status_label.setStyleSheet(
            "background:#eefaf2; border:1px solid #77b98a; "
            "border-radius:7px; padding:9px;"
        )
        self.status_label.setText(
            f"Pakett on loetav: {plan.total_count:,} EVEL-i kirjet. "
            "Järgmine samm on tagasipööratav SQL-kontroll."
        )
        self._fill_summary()
        self._update_buttons()

    def _fill_summary(self) -> None:
        self.table.setRowCount(0)
        self.warning_list.clear()
        if self.plan is None:
            return
        for table in TABLE_ORDER:
            count = self.plan.count(table)
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(
                row,
                0,
                QTableWidgetItem(self.TABLE_LABELS[table]),
            )
            self.table.setItem(row, 1, QTableWidgetItem(table))
            count_item = QTableWidgetItem(f"{count:,}")
            count_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 2, count_item)
        for warning in self.plan.warnings:
            self.warning_list.addItem(f"• {warning}")
        if not self.plan.warnings:
            self.warning_list.addItem("✓ Paketi eelhoiatused puuduvad.")

    def _clear_summary(self) -> None:
        self.table.setRowCount(0)
        self.warning_list.clear()
        self.progress_bar.setValue(0)
        self.activity_label.clear()

    def _start_import(self, *, dry_run: bool) -> None:
        if self.plan is None or self.target is None or self._thread is not None:
            return
        if not dry_run:
            try:
                current_plan = self.reader.read(self.plan.package_path)
                current_target = self.target_inspector.inspect(self.project)
            except (EvelImportPackageError, EvelImportTargetError) as error:
                self._show_error(str(error))
                return
            if current_plan.package_sha256 != self.plan.package_sha256:
                self.plan = current_plan
                self.target = current_target
                self._dry_run_hash = ""
                self._fill_summary()
                self._show_error(
                    "GeoPackage muutus pärast SQL-kontrolli. Tee kontroll "
                    "uuesti."
                )
                self._update_buttons()
                return
            imported = self._import_timestamp(current_plan.package_sha256)
            if imported:
                self._show_error(
                    "See sama kontrollpakett on projekti andmetel juba "
                    f"imporditud ({imported})."
                )
                self._dry_run_hash = ""
                self._update_buttons()
                return
            self.target = current_target
            answer = QMessageBox.question(
                self,
                "Kinnita EVEL-i import",
                f"Kas impordime {self.plan.total_count:,} kirjet aktiivse "
                "projekti PostgreSQL-andmebaasi?\n\n"
                "Import on lisav ja toimub ühe tehinguna. Sama paketti ei "
                "tohi teist korda importida.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return

        self._active_dry_run = dry_run
        self._cancel_event = Event()
        self._thread = QThread(self)
        self._worker = _ImportWorker(
            self.importer,
            self.plan,
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
        self.progress_bar.setRange(0, max(self.plan.total_count, 1))
        self.progress_bar.setValue(0)
        self.activity_label.setText(
            "Alustan tagasipööratavat SQL-kontrolli…"
            if dry_run
            else "Alustan EVEL-i andmete importi…"
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
            self._dry_run_hash = self.plan.package_sha256
            self.status_label.setStyleSheet(
                "background:#eefaf2; border:1px solid #77b98a; "
                "border-radius:7px; padding:9px;"
            )
            self.status_label.setText(
                "SQL-kontroll õnnestus. Kõik proovikirjed pöörati tagasi; "
                "andmebaasi ei jäänud muudatusi. Pakett on impordiks valmis."
            )
        else:
            completed_plan = self.plan
            timestamp = datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
            self._mark_imported(self.plan.package_sha256, timestamp)
            self.project.setDirty(True)
            self.status_label.setStyleSheet(
                "background:#eefaf2; border:1px solid #4a9b62; "
                "border-radius:7px; padding:9px; font-weight:600;"
            )
            self.status_label.setText(
                f"Import lõpetatud: {result.total_count:,} kirjet lisati "
                "ühe tehinguna."
            )
            self._dry_run_hash = ""
            self.plan = None
            self.target = None
            self.import_completed.emit(completed_plan, result)

    @pyqtSlot(str)
    def _on_failure(self, message: str) -> None:
        self._dry_run_hash = ""
        self._show_error(message)
        QMessageBox.critical(self, "EVEL-i import ebaõnnestus", message)

    @pyqtSlot(str)
    def _on_canceled(self, message: str) -> None:
        self._dry_run_hash = ""
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
                "Katkestan pärast aktiivse SQL-partii lõppu ja teen rollback’i…"
            )
            return
        self.close()

    def _update_buttons(self, *, running: bool = False) -> None:
        if running:
            self.browse_button.setEnabled(False)
            self.dry_run_button.setEnabled(False)
            self.import_button.setEnabled(False)
            self.close_button.setText("Katkesta")
            self.close_button.setEnabled(True)
            return
        ready = self.plan is not None and self.target is not None
        self.browse_button.setEnabled(True)
        self.dry_run_button.setEnabled(ready)
        self.import_button.setEnabled(
            ready
            and self._dry_run_hash == (
                self.plan.package_sha256 if self.plan is not None else ""
            )
        )
        self.close_button.setText("Sulge")
        self.close_button.setEnabled(True)

    def _show_error(self, message: str) -> None:
        self.status_label.setStyleSheet(
            "background:#fff1f1; border:1px solid #d36f76; "
            "border-radius:7px; padding:9px;"
        )
        self.status_label.setText(message)

    def _import_timestamp(self, package_sha256: str) -> str:
        value, found = self.project.readEntry(
            self.IMPORT_ENTRY_SCOPE,
            self.IMPORT_ENTRY_PREFIX + package_sha256,
            "",
        )
        return str(value) if found else ""

    def _mark_imported(self, package_sha256: str, timestamp: str) -> None:
        self.project.writeEntry(
            self.IMPORT_ENTRY_SCOPE,
            self.IMPORT_ENTRY_PREFIX + package_sha256,
            timestamp,
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread is not None:
            event.ignore()
            self._close_or_cancel()
            return
        super().closeEvent(event)
