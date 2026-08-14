"""Coordinate-entry dialog for creating an EVEL duct geometry."""

from __future__ import annotations

import math
import re

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsCsException,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)

from ..layers import DuctLayerOption
from .light_style import apply_evel_light_style
from .icon_catalog import (
    ICON_ADD,
    ICON_CANCEL,
    ICON_NEXT,
    ICON_PASTE,
    ICON_REMOVE,
    set_catalog_icon,
)


class CoordinateDuctInputError(ValueError):
    """Raised when entered vertices cannot form a valid duct geometry."""


class CoordinateDuctDialog(QDialog):
    """Collect an ordered vertex list and transform it to the layer CRS."""

    def __init__(
        self,
        options: tuple[DuctLayerOption, ...],
        *,
        selected_layer_id: str = "",
        project_crs: QgsCoordinateReferenceSystem | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._options = tuple(option for option in options if option.enabled)
        if not self._options:
            raise CoordinateDuctInputError(
                "Projektis puuduvad koordinaatidega lisatavad torukihid."
            )
        self._project_crs = project_crs or QgsProject.instance().crs()
        self._crs_choices: list[QgsCoordinateReferenceSystem] = []
        self._accepted_geometry: QgsGeometry | None = None

        self.setObjectName("evelCoordinateDuctDialog")
        self.setWindowTitle("Lisa toru koordinaatidega")
        self.setModal(True)
        self.resize(690, 520)
        apply_evel_light_style(self)
        self._build_ui(selected_layer_id)

    @property
    def selected_option(self) -> DuctLayerOption:
        return self._options[self.layer_combo.currentIndex()]

    @property
    def source_crs(self) -> QgsCoordinateReferenceSystem:
        return self._crs_choices[self.crs_combo.currentIndex()]

    def duct_geometry(self) -> QgsGeometry:
        """Return validated geometry in the selected duct layer's CRS."""

        if self._accepted_geometry is not None:
            return QgsGeometry(self._accepted_geometry)
        return self._build_geometry()

    def coordinate_edits(self, row: int) -> tuple[QLineEdit, QLineEdit]:
        """Return the X and Y editors for tests and guided integrations."""

        return self.table.cellWidget(row, 1), self.table.cellWidget(row, 2)

    def set_coordinates(self, points: tuple[tuple[float, float], ...]) -> None:
        """Replace the table contents with a coordinate sequence."""

        self.table.setRowCount(0)
        for x, y in points:
            self._append_row(str(x), str(y))
        while self.table.rowCount() < 2:
            self._append_row()
        self._renumber_rows()
        self._update_remove_button()

    def _build_ui(self, selected_layer_id: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)

        title = QLabel("Toru geomeetria koordinaatidest", self)
        title_font = QFont(title.font())
        title_font.setPointSize(title_font.pointSize() + 4)
        title_font.setBold(True)
        title.setFont(title_font)
        root.addWidget(title)

        intro = QLabel(
            "Sisesta punktid toru algusest lõpuni. Vähemalt kaks punkti on "
            "kohustuslikud; lisaread moodustavad toru murdepunktid. Vee- ja "
            "kanalisatsioonitorude senised topoloogiareeglid jäävad kehtima.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        settings = QFrame(self)
        settings.setObjectName("lightSurface")
        settings_layout = QVBoxLayout(settings)
        settings_layout.setContentsMargins(12, 10, 12, 10)
        settings_layout.setSpacing(8)

        layer_row = QHBoxLayout()
        layer_row.addWidget(QLabel("Torukiht", settings))
        self.layer_combo = QComboBox(settings)
        for option in self._options:
            crs_label = option.layer.crs().authid() or option.layer.crs().description()
            self.layer_combo.addItem(f"{option.label} — {crs_label}")
        selected_index = next(
            (
                index
                for index, option in enumerate(self._options)
                if option.layer.id() == selected_layer_id
            ),
            0,
        )
        self.layer_combo.setCurrentIndex(selected_index)
        layer_row.addWidget(self.layer_combo, 1)
        settings_layout.addLayout(layer_row)

        crs_row = QHBoxLayout()
        crs_row.addWidget(QLabel("Sisendi koordinaatsüsteem", settings))
        self.crs_combo = QComboBox(settings)
        crs_row.addWidget(self.crs_combo, 1)
        settings_layout.addLayout(crs_row)
        root.addWidget(settings)

        self.table = QTableWidget(0, 3, self)
        self.table.setObjectName("coordinateVertexTable")
        self.table.setHorizontalHeaderLabels(("Punkt", "X", "Y"))
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        root.addWidget(self.table, 1)

        tools = QHBoxLayout()
        self.add_button = QPushButton("Lisa murdepunkt", self)
        set_catalog_icon(self.add_button, ICON_ADD)
        self.add_button.clicked.connect(lambda: self._append_row())
        tools.addWidget(self.add_button)
        self.remove_button = QPushButton("Eemalda punkt", self)
        set_catalog_icon(self.remove_button, ICON_REMOVE)
        self.remove_button.clicked.connect(self._remove_selected_row)
        tools.addWidget(self.remove_button)
        self.paste_button = QPushButton("Aseta lõikelaualt", self)
        set_catalog_icon(self.paste_button, ICON_PASTE)
        self.paste_button.clicked.connect(self._paste_coordinates)
        tools.addWidget(self.paste_button)
        tools.addStretch(1)
        root.addLayout(tools)

        self.crs_hint = QLabel(self)
        self.crs_hint.setWordWrap(True)
        self.crs_hint.setStyleSheet("color: #57606a;")
        root.addWidget(self.crs_hint)
        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #cf222e; font-weight: 600;")
        self.error_label.hide()
        root.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self,
        )
        create_button = self.buttons.button(QDialogButtonBox.Ok)
        create_button.setText("Jätka toru andmetega")
        create_button.setDefault(True)
        set_catalog_icon(create_button, ICON_NEXT)
        cancel_button = self.buttons.button(QDialogButtonBox.Cancel)
        cancel_button.setText("Loobu")
        set_catalog_icon(cancel_button, ICON_CANCEL)
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        self.layer_combo.currentIndexChanged.connect(self._rebuild_crs_choices)
        self.crs_combo.currentIndexChanged.connect(self._update_crs_hint)
        self.table.itemSelectionChanged.connect(self._update_remove_button)
        self._append_row()
        self._append_row()
        self._rebuild_crs_choices()

    def _append_row(self, x_text: str = "", y_text: str = "") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        label = QTableWidgetItem(str(row + 1))
        label.setFlags(label.flags() & ~Qt.ItemIsEditable)
        label.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 0, label)
        self.table.setCellWidget(row, 1, self._coordinate_edit(x_text, "X"))
        self.table.setCellWidget(row, 2, self._coordinate_edit(y_text, "Y"))
        self.table.selectRow(row)
        self._update_remove_button()

    def _coordinate_edit(self, text: str, axis: str) -> QLineEdit:
        edit = QLineEdit(self.table)
        edit.setAlignment(Qt.AlignRight)
        edit.setPlaceholderText(f"{axis}, näiteks 500000.000")
        edit.setText(text)
        return edit

    def _remove_selected_row(self) -> None:
        if self.table.rowCount() <= 2:
            return
        row = self.table.currentRow()
        if row < 0:
            row = self.table.rowCount() - 1
        self.table.removeRow(row)
        self._renumber_rows()
        self.table.selectRow(min(row, self.table.rowCount() - 1))
        self._update_remove_button()

    def _renumber_rows(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setText(str(row + 1))

    def _update_remove_button(self) -> None:
        self.remove_button.setEnabled(self.table.rowCount() > 2)

    def _rebuild_crs_choices(self, *_args) -> None:
        previous = self.source_crs.authid() if self._crs_choices else ""
        target_crs = self.selected_option.layer.crs()
        candidates = (
            target_crs,
            self._project_crs,
            QgsCoordinateReferenceSystem("EPSG:4326"),
        )
        self._crs_choices = []
        self.crs_combo.blockSignals(True)
        self.crs_combo.clear()
        seen = set()
        for crs in candidates:
            if not crs.isValid():
                continue
            key = crs.authid() or crs.toWkt()
            if key in seen:
                continue
            seen.add(key)
            self._crs_choices.append(crs)
            role = "Kihi CRS" if crs == target_crs else "Projekti CRS"
            if crs.authid() == "EPSG:4326":
                role = "WGS 84"
            label = crs.authid() or crs.description()
            self.crs_combo.addItem(f"{role} — {label}")
        index = next(
            (
                idx
                for idx, crs in enumerate(self._crs_choices)
                if previous and crs.authid() == previous
            ),
            0,
        )
        self.crs_combo.setCurrentIndex(index)
        self.crs_combo.blockSignals(False)
        self._update_crs_hint()

    def _update_crs_hint(self, *_args) -> None:
        if not self._crs_choices:
            self.crs_hint.clear()
            return
        source = self.source_crs
        target = self.selected_option.layer.crs()
        source_label = source.authid() or source.description()
        target_label = target.authid() or target.description()
        if source == target:
            message = f"Koordinaadid salvestatakse muutmata kujul ({target_label})."
        else:
            message = (
                f"Koordinaadid teisendatakse süsteemist {source_label} "
                f"torukihi süsteemi {target_label}."
            )
        self.crs_hint.setText(message)

    def _paste_coordinates(self) -> None:
        text = QApplication.clipboard().text()
        try:
            points = self._parse_clipboard(text)
        except CoordinateDuctInputError as error:
            self._show_error(str(error))
            return
        self.set_coordinates(points)
        self.error_label.hide()

    @classmethod
    def _parse_clipboard(cls, text: str) -> tuple[tuple[float, float], ...]:
        points = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if ";" in line:
                parts = [part.strip() for part in line.split(";")]
            elif "\t" in line:
                parts = [part.strip() for part in line.split("\t")]
            else:
                parts = re.split(r"\s+", line)
                if len(parts) == 1 and line.count(",") == 1:
                    parts = [part.strip() for part in line.split(",")]
            if len(parts) != 2:
                raise CoordinateDuctInputError(
                    f"Lõikelaua real {line_number} peab olema X ja Y."
                )
            try:
                points.append(
                    (cls._parse_number(parts[0]), cls._parse_number(parts[1]))
                )
            except ValueError as error:
                raise CoordinateDuctInputError(
                    f"Lõikelaua real {line_number} on vigane koordinaat."
                ) from error
        if len(points) < 2:
            raise CoordinateDuctInputError(
                "Lõikelaual peab olema vähemalt kaks koordinaadirida."
            )
        return tuple(points)

    @staticmethod
    def _parse_number(text: str) -> float:
        cleaned = text.strip().replace("\u00a0", "").replace(" ", "")
        value = float(cleaned.replace(",", "."))
        if not math.isfinite(value):
            raise ValueError("Coordinate must be finite")
        return value

    def _points(self) -> tuple[QgsPointXY, ...]:
        points = []
        for row in range(self.table.rowCount()):
            x_edit, y_edit = self.coordinate_edits(row)
            try:
                x = self._parse_number(x_edit.text())
                y = self._parse_number(y_edit.text())
            except ValueError as error:
                raise CoordinateDuctInputError(
                    f"Punkti {row + 1} X- või Y-koordinaat on puudu või vigane."
                ) from error
            points.append(QgsPointXY(x, y))
        if len(points) < 2:
            raise CoordinateDuctInputError("Toru vajab vähemalt kahte punkti.")
        if all(point == points[0] for point in points[1:]):
            raise CoordinateDuctInputError(
                "Toru algus- ja lõpp-punkt ei tohi kattuda."
            )
        for index, (previous, current) in enumerate(
            zip(points, points[1:]),
            start=2,
        ):
            if previous == current:
                raise CoordinateDuctInputError(
                    f"Punkt {index} ei tohi eelmise punktiga kattuda."
                )
        if self.source_crs.isGeographic():
            for index, point in enumerate(points, start=1):
                if not -180 <= point.x() <= 180 or not -90 <= point.y() <= 90:
                    raise CoordinateDuctInputError(
                        f"Punkti {index} WGS84 koordinaadid on väljaspool "
                        "lubatud vahemikku."
                    )
        return tuple(points)

    def _build_geometry(self) -> QgsGeometry:
        geometry = QgsGeometry.fromPolylineXY(list(self._points()))
        source = self.source_crs
        target = self.selected_option.layer.crs()
        if source != target:
            try:
                geometry.transform(
                    QgsCoordinateTransform(source, target, QgsProject.instance())
                )
            except QgsCsException as error:
                raise CoordinateDuctInputError(
                    "Koordinaatide teisendamine torukihi süsteemi ebaõnnestus."
                ) from error
        if geometry.isNull() or geometry.isEmpty() or geometry.length() <= 0:
            raise CoordinateDuctInputError(
                "Sisestatud punktidest ei moodustu kehtivat torujoont."
            )
        return geometry

    def _validate_and_accept(self) -> None:
        try:
            self._accepted_geometry = self._build_geometry()
        except CoordinateDuctInputError as error:
            self._show_error(str(error))
            return
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
