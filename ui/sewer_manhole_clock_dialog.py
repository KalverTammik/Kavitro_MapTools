"""Analog manhole-clock editor for EVEL gravity sewer nodes."""

from __future__ import annotations

import math

from qgis.PyQt.QtCore import QPointF, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QDoubleValidator,
    QPainter,
    QPen,
    QPolygonF,
)
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..layers import LookupOption, SewerManholeOptions
from ..topology import (
    DETAIL_KIND_CONNECTION,
    DETAIL_KIND_MANHOLE,
    SewerManholeConfiguration,
    SewerManholePlan,
    SewerManholePort,
    SewerManholeState,
    select_sewer_reference_outlet,
    sewer_clock_angle,
)
from .light_style import apply_evel_light_style


class SewerManholeClockWidget(QWidget):
    """Draw sewer pipes relative to the deepest outgoing pipe."""

    portSelected = pyqtSignal(int)

    def __init__(
        self,
        ports: tuple[SewerManholePort, ...],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.ports = ports
        self.port_heights = {port.key: port.height for port in ports}
        self.detail_kind = DETAIL_KIND_MANHOLE
        self.selected_index = 0 if ports else -1
        self.setMinimumSize(360, 360)
        self.setAccessibleName("Kanalisatsioonisõlme torude skeem")

    def set_selected_index(self, index: int) -> None:
        if index < 0 or index >= len(self.ports):
            return
        self.selected_index = index
        self.update()

    def set_detail_kind(self, detail_kind: str) -> None:
        self.detail_kind = detail_kind
        self.update()

    def set_port_heights(
        self,
        heights: dict[str, float | None],
    ) -> None:
        self.port_heights = dict(heights)
        self.update()

    def reference_outlet(self) -> SewerManholePort | None:
        return select_sewer_reference_outlet(
            self.ports,
            self.port_heights,
        )

    def display_angle(self, port: SewerManholePort) -> float:
        return sewer_clock_angle(port, self.reference_outlet())

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(20, 20, -20, -20)
        radius = min(bounds.width(), bounds.height()) * 0.34
        center = bounds.center()

        text_color = QColor("#24292e")
        muted = QColor(text_color)
        muted.setAlpha(150)
        pipe_color = QColor("#1687c9")
        selected_color = QColor("#ffb300")
        outlet_color = QColor("#1a9b50")
        manhole_color = QColor("#555555")
        reference_outlet = self.reference_outlet()

        painter.setPen(QPen(muted, 1))
        north_angle = (
            (360.0 - reference_outlet.bearing) % 360.0
            if reference_outlet is not None
            else 0.0
        )
        north_radians = math.radians(north_angle)
        north_direction = QPointF(
            math.sin(north_radians),
            -math.cos(north_radians),
        )
        north_center = center + north_direction * (radius + 29)
        painter.drawText(
            QRectF(
                north_center.x() - 18,
                north_center.y() - 10,
                36,
                20,
            ),
            Qt.AlignCenter,
            "N",
        )
        for degree in range(0, 360, 5):
            angle = math.radians(degree)
            outer = QPointF(
                center.x() + math.sin(angle) * radius,
                center.y() - math.cos(angle) * radius,
            )
            tick = 10 if degree % 30 == 0 else 5
            inner = QPointF(
                center.x() + math.sin(angle) * (radius - tick),
                center.y() - math.cos(angle) * (radius - tick),
            )
            painter.drawLine(inner, outer)
        painter.drawEllipse(center, radius, radius)

        for index, port in enumerate(self.ports):
            angle = math.radians(
                sewer_clock_angle(port, reference_outlet)
            )
            direction = QPointF(math.sin(angle), -math.cos(angle))
            endpoint = center + direction * (radius - 14)
            if index == self.selected_index:
                color = selected_color
            elif reference_outlet is not None and (
                port.key == reference_outlet.key
            ):
                color = outlet_color
            else:
                color = pipe_color
            painter.setPen(QPen(color, 5 if index == self.selected_index else 3))
            painter.drawLine(center, endpoint)
            self._draw_flow_arrow(
                painter,
                center,
                direction,
                radius,
                port,
                color,
            )
            label_center = center + direction * (radius + 13)
            painter.setPen(QPen(text_color, 1))
            painter.drawText(
                QRectF(
                    label_center.x() - 13,
                    label_center.y() - 11,
                    26,
                    22,
                ),
                Qt.AlignCenter,
                str(index + 1),
            )
            if reference_outlet is not None and port.key == reference_outlet.key:
                painter.setPen(QPen(outlet_color, 1))
                painter.drawText(
                    QRectF(
                        label_center.x() - 40,
                        label_center.y() + 8,
                        80,
                        18,
                    ),
                    Qt.AlignCenter,
                    "VÄLJA · 0°",
                )

        painter.setPen(QPen(manhole_color, 3))
        painter.setBrush(Qt.NoBrush)
        if self.detail_kind == DETAIL_KIND_CONNECTION:
            painter.save()
            painter.translate(center)
            painter.rotate(45)
            painter.drawRect(QRectF(-14, -14, 28, 28))
            painter.restore()
            center_label = "Põlv / ühenduskoht"
        else:
            painter.drawEllipse(center, 19, 19)
            painter.drawEllipse(center, 12, 12)
            center_label = "Kanalisatsioonikaev"
        painter.setPen(QPen(text_color, 1))
        painter.drawText(
            QRectF(center.x() - 70, center.y() + 25, 140, 22),
            Qt.AlignCenter,
            center_label,
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or not self.ports:
            return
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        radius = min(self.width() - 40, self.height() - 40) * 0.34
        click = QPointF(event.pos())
        candidates = []
        reference_outlet = self.reference_outlet()
        for index, port in enumerate(self.ports):
            angle = math.radians(
                sewer_clock_angle(port, reference_outlet)
            )
            endpoint = QPointF(
                center.x() + math.sin(angle) * radius,
                center.y() - math.cos(angle) * radius,
            )
            candidates.append(
                (self._segment_distance(click, center, endpoint), index)
            )
        distance, index = min(candidates)
        if distance <= 20:
            self.set_selected_index(index)
            self.portSelected.emit(index)

    @staticmethod
    def _draw_flow_arrow(
        painter: QPainter,
        center: QPointF,
        direction: QPointF,
        radius: float,
        port: SewerManholePort,
        color: QColor,
    ) -> None:
        flow = port.flow_direction
        if flow is None or abs(flow) < 1e-9:
            return
        outward = port.central_at_start if flow > 0 else not port.central_at_start
        axis = direction if outward else -direction
        position = center + direction * (radius * 0.58)
        normal = QPointF(-axis.y(), axis.x())
        tip = position + axis * 9
        base = position - axis * 6
        triangle = QPolygonF(
            [
                tip,
                base + normal * 5,
                base - normal * 5,
            ]
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(triangle)

    @staticmethod
    def _segment_distance(
        point: QPointF,
        start: QPointF,
        end: QPointF,
    ) -> float:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length_squared = dx * dx + dy * dy
        if length_squared <= 0:
            return math.hypot(point.x() - start.x(), point.y() - start.y())
        ratio = (
            (point.x() - start.x()) * dx
            + (point.y() - start.y()) * dy
        ) / length_squared
        ratio = min(max(ratio, 0.0), 1.0)
        nearest = QPointF(start.x() + ratio * dx, start.y() + ratio * dy)
        return math.hypot(point.x() - nearest.x(), point.y() - nearest.y())


class SewerManholeClockDialog(QDialog):
    """Edit one sewer manhole and its incident pipe elevations."""

    def __init__(
        self,
        state: SewerManholeState,
        options: SewerManholeOptions,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("evelSewerManholeClockDialog")
        apply_evel_light_style(self)
        self.state = state
        self.options = options
        self.height_edits: dict[str, QLineEdit] = {}
        self.setWindowTitle(
            "Uue kanalisatsioonisõlme generaator"
            if state.node_id is None
            else f"Kanalisatsioonisõlm {state.node_id} — generaator"
        )
        self.setModal(True)
        self.resize(1120, 720)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Kaevukella nurgad arvutatakse päripäeva väljavoolust. "
            "Mitme väljuva toru korral on 0° referents madalaim väljuv "
            "toru; N näitab põhjasuunda skeemi suhtes. "
            "Toru kõrgus kirjutatakse toru sõlmepoolsesse kõrgusvälja.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        root.addWidget(self._header_group())

        splitter = QSplitter(Qt.Horizontal, self)
        clock_group = QGroupBox("Kaevukell / sõlmeskeem", splitter)
        clock_layout = QVBoxLayout(clock_group)
        self.reference_label = QLabel(clock_group)
        self.reference_label.setWordWrap(True)
        clock_layout.addWidget(self.reference_label)
        self.clock = SewerManholeClockWidget(state.ports, clock_group)
        clock_layout.addWidget(self.clock, 1)
        splitter.addWidget(clock_group)

        table_group = QGroupBox("Sõlmega seotud torud", splitter)
        table_layout = QVBoxLayout(table_group)
        self.table = QTableWidget(len(state.ports), 7, table_group)
        self.table.setHorizontalHeaderLabels(
            (
                "Nr",
                "Toru tähis",
                "Läbimõõt",
                "Materjal",
                "Voolusuund",
                "Nurk väljavoolust",
                "Toru kõrgus",
            )
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.Stretch,
        )
        self._populate_table()
        self._refresh_clock_reference()
        table_layout.addWidget(self.table)
        splitter.addWidget(table_group)
        splitter.setSizes((430, 650))
        root.addWidget(splitter, 1)

        self.detail_tabs = self._detail_tabs()
        root.addWidget(self.detail_tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.button(QDialogButtonBox.Save).setText("Rakenda sõlm")
        buttons.button(QDialogButtonBox.Cancel).setText("Loobu")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.table.currentCellChanged.connect(self._table_selection_changed)
        self.clock.portSelected.connect(self._clock_selection_changed)
        if state.ports:
            self.table.selectRow(0)
        self._kind_changed()

    def plan(self) -> SewerManholePlan:
        access_diameter = self.access_duct_spin.value()
        configuration = SewerManholeConfiguration(
            detail_kind=self.kind_combo.currentData(),
            identification=self.identification_edit.text().strip(),
            element_height=self._nullable_value(self.element_height_edit),
            bottom_height=self._nullable_value(self.bottom_height_edit),
            ground_height=self._nullable_value(self.ground_height_edit),
            type_id=self.type_combo.currentData(),
            material_id=self.material_combo.currentData(),
            diameter_type_id=self.diameter_type_combo.currentData(),
            diameter_id=self.diameter_combo.currentData(),
            firmness_class_id=self.firmness_combo.currentData(),
            lid_type_id=self.lid_type_combo.currentData(),
            lid_material_id=self.lid_material_combo.currentData(),
            lid_shape_id=self.lid_shape_combo.currentData(),
            lid_diameter_id=self.lid_diameter_combo.currentData(),
            lid_capacity_id=self.lid_capacity_combo.currentData(),
            access_duct_diam=(
                access_diameter if access_diameter > 0 else None
            ),
            branch_type_id=self.branch_type_combo.currentData(),
            branch_subtype_id=self.branch_subtype_combo.currentData(),
        )
        return SewerManholePlan(
            state=self.state,
            configuration=configuration,
            port_heights=tuple(
                (
                    port.key,
                    self._nullable_value(self.height_edits[port.key]),
                )
                for port in self.state.ports
            ),
        )

    def _header_group(self) -> QGroupBox:
        group = QGroupBox("Sõlme põhiandmed", self)
        layout = QGridLayout(group)
        config = self.state.configuration

        layout.addWidget(QLabel("Sõlme ID", group), 0, 0)
        id_value = (
            str(self.state.node_id)
            if self.state.node_id is not None
            else "luuakse serveris"
        )
        id_label = QLabel(id_value, group)
        id_label.setStyleSheet("font-weight: 600;")
        layout.addWidget(id_label, 0, 1)

        layout.addWidget(QLabel("Sõlme tähis", group), 0, 2)
        self.identification_edit = QLineEdit(config.identification, group)
        layout.addWidget(self.identification_edit, 0, 3)
        layout.addWidget(QLabel("Kirjeldatav element", group), 0, 4)
        self.kind_combo = QComboBox(group)
        self.kind_combo.addItem("Kaev", DETAIL_KIND_MANHOLE)
        self.kind_combo.addItem(
            "Põlv / ühenduskoht (EVEL: Ühenduskoht)",
            DETAIL_KIND_CONNECTION,
        )
        kind_index = self.kind_combo.findData(config.detail_kind)
        self.kind_combo.setCurrentIndex(max(kind_index, 0))
        self.kind_combo.currentIndexChanged.connect(self._kind_changed)
        layout.addWidget(self.kind_combo, 0, 5)

        layout.addWidget(QLabel("Elemendi kõrgus", group), 1, 0)
        self.element_height_edit = self._nullable_number(
            config.element_height,
            group,
        )
        layout.addWidget(self.element_height_edit, 1, 1)
        layout.addWidget(QLabel("Põhja kõrgus", group), 1, 2)
        self.bottom_height_edit = self._nullable_number(
            config.bottom_height,
            group,
        )
        layout.addWidget(self.bottom_height_edit, 1, 3)
        layout.addWidget(QLabel("Maapinna kõrgus", group), 1, 4)
        self.ground_height_edit = self._nullable_number(
            config.ground_height,
            group,
        )
        layout.addWidget(self.ground_height_edit, 1, 5)
        return group

    def _detail_tabs(self) -> QTabWidget:
        config = self.state.configuration
        tabs = QTabWidget(self)

        manhole_tab = QWidget(tabs)
        manhole_form = QFormLayout(manhole_tab)
        self.type_combo = self._combo(
            self.options.type_options,
            config.type_id or self.options.default_type_id,
            optional=False,
            parent=manhole_tab,
        )
        manhole_form.addRow("Kaevu liik", self.type_combo)
        self.material_combo = self._combo(
            self.options.material_options,
            config.material_id,
            parent=manhole_tab,
        )
        manhole_form.addRow("Materjal", self.material_combo)
        self.diameter_type_combo = self._combo(
            self.options.diameter_type_options,
            config.diameter_type_id,
            parent=manhole_tab,
        )
        manhole_form.addRow("Läbimõõdu tüüp", self.diameter_type_combo)
        self.diameter_combo = self._combo(
            self.options.diameter_options,
            config.diameter_id,
            parent=manhole_tab,
        )
        manhole_form.addRow("Läbimõõt", self.diameter_combo)
        self.firmness_combo = self._combo(
            self.options.firmness_options,
            config.firmness_class_id,
            parent=manhole_tab,
        )
        manhole_form.addRow("Ringjäikus", self.firmness_combo)
        self.access_duct_spin = QSpinBox(manhole_tab)
        self.access_duct_spin.setRange(0, 10000)
        self.access_duct_spin.setSpecialValueText("Määramata")
        self.access_duct_spin.setSuffix(" mm")
        self.access_duct_spin.setValue(config.access_duct_diam or 0)
        manhole_form.addRow("Tõusutoru läbimõõt", self.access_duct_spin)
        tabs.addTab(manhole_tab, "Kaev")

        lid_tab = QWidget(tabs)
        lid_form = QFormLayout(lid_tab)
        self.lid_type_combo = self._combo(
            self.options.lid_type_options,
            config.lid_type_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane tüüp", self.lid_type_combo)
        self.lid_material_combo = self._combo(
            self.options.lid_material_options,
            config.lid_material_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane materjal", self.lid_material_combo)
        self.lid_shape_combo = self._combo(
            self.options.lid_shape_options,
            config.lid_shape_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane kuju", self.lid_shape_combo)
        self.lid_diameter_combo = self._combo(
            self.options.lid_diameter_options,
            config.lid_diameter_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane läbimõõt", self.lid_diameter_combo)
        self.lid_capacity_combo = self._combo(
            self.options.lid_capacity_options,
            config.lid_capacity_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane kandevõime", self.lid_capacity_combo)
        tabs.addTab(lid_tab, "Kaas")

        connection_tab = QWidget(tabs)
        connection_form = QFormLayout(connection_tab)
        self.branch_type_combo = self._combo(
            self.options.branch_type_options,
            (
                config.branch_type_id
                or self.options.connection_branch_type_id
            ),
            optional=False,
            parent=connection_tab,
        )
        connection_form.addRow(
            "Liitmiku liik",
            self.branch_type_combo,
        )
        self.branch_subtype_combo = self._combo(
            self.options.branch_subtype_options,
            (
                config.branch_subtype_id
                or self.options.default_branch_subtype_id
            ),
            optional=False,
            parent=connection_tab,
        )
        connection_form.addRow(
            "Liitmiku alamtüüp",
            self.branch_subtype_combo,
        )
        note = QLabel(
            "EVEL-i praeguses kanalisatsioonimudelis puudub eraldi "
            "„Põlve” lookup-väärtus. Põlv salvestatakse ametliku "
            "„Ühenduskoht” liitmikuna.",
            connection_tab,
        )
        note.setWordWrap(True)
        connection_form.addRow("", note)
        self.connection_tab_index = tabs.addTab(
            connection_tab,
            "Põlv / ühenduskoht",
        )
        return tabs

    def _kind_changed(self, *_args) -> None:
        if not hasattr(self, "detail_tabs"):
            return
        is_connection = (
            self.kind_combo.currentData() == DETAIL_KIND_CONNECTION
        )
        self.detail_tabs.setTabEnabled(0, not is_connection)
        self.detail_tabs.setTabEnabled(1, not is_connection)
        self.detail_tabs.setTabEnabled(
            self.connection_tab_index,
            is_connection,
        )
        self.detail_tabs.setCurrentIndex(
            self.connection_tab_index if is_connection else 0
        )
        self.clock.set_detail_kind(self.kind_combo.currentData())

    def _populate_table(self) -> None:
        for row, port in enumerate(self.state.ports):
            values = (
                str(row + 1),
                port.identification
                or f"Toru {port.edge_id if port.edge_id is not None else port.feature_id}",
                port.diameter_label,
                port.material_label,
                "",
                "",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (0, 4, 5):
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)
            height_edit = self._nullable_number(port.height, self.table)
            height_edit.setPlaceholderText("määramata")
            self.height_edits[port.key] = height_edit
            height_edit.textChanged.connect(
                lambda _text: self._refresh_clock_reference()
            )
            self.table.setCellWidget(row, 6, height_edit)

    def _refresh_clock_reference(self) -> None:
        heights = {}
        for key, edit in self.height_edits.items():
            try:
                heights[key] = self._nullable_value(edit)
            except ValueError:
                heights[key] = None
        self.clock.set_port_heights(heights)
        reference = self.clock.reference_outlet()
        angle_header = self.table.horizontalHeaderItem(5)
        if reference is None:
            self.reference_label.setText(
                "Väljavoolu ei saa FLOWDIRECTION väärtustest määrata. "
                "Nurgad kuvatakse ajutiselt põhjasuunast."
            )
            self.reference_label.setStyleSheet("color: #b36b00;")
            angle_header.setText("Nurk põhjast")
        else:
            label = (
                reference.identification
                or f"Toru {reference.edge_id if reference.edge_id is not None else reference.feature_id}"
            )
            height = heights.get(reference.key)
            height_text = (
                f", kõrgus {height:.3f} m"
                if height is not None
                else ", kõrgus määramata"
            )
            self.reference_label.setText(
                f"0° referents: {label} — madalaim väljuv toru"
                f"{height_text}."
            )
            self.reference_label.setStyleSheet(
                "color: #1a7f43; font-weight: 600;"
            )
            angle_header.setText("Nurk väljavoolust")

        for row, port in enumerate(self.state.ports):
            if port.is_outgoing is True:
                flow_text = (
                    "Välja · referents"
                    if reference is not None and port.key == reference.key
                    else "Välja"
                )
            elif port.is_outgoing is False:
                flow_text = "Sisse"
            else:
                flow_text = "Määramata"
            self.table.item(row, 4).setText(flow_text)
            self.table.item(row, 5).setText(
                f"{sewer_clock_angle(port, reference):.1f}°"
            )

    def _table_selection_changed(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        self.clock.set_selected_index(current_row)

    def _clock_selection_changed(self, index: int) -> None:
        self.table.selectRow(index)
        self.table.scrollToItem(
            self.table.item(index, 0),
            QAbstractItemView.PositionAtCenter,
        )

    @staticmethod
    def _nullable_number(
        value: float | None,
        parent,
    ) -> QLineEdit:
        edit = QLineEdit(parent)
        validator = QDoubleValidator(-9999.999, 99999.999, 3, edit)
        validator.setNotation(QDoubleValidator.StandardNotation)
        edit.setValidator(validator)
        edit.setText("" if value is None else f"{value:.3f}")
        edit.setPlaceholderText("määramata")
        edit.setMaximumWidth(150)
        return edit

    @staticmethod
    def _nullable_value(edit: QLineEdit) -> float | None:
        text = edit.text().strip().replace(",", ".")
        return float(text) if text else None

    @staticmethod
    def _combo(
        options: tuple[LookupOption, ...],
        selected: int | None,
        *,
        optional: bool = True,
        parent=None,
    ) -> QComboBox:
        combo = QComboBox(parent)
        if optional:
            combo.addItem("— Määramata —", None)
        for option in options:
            combo.addItem(option.label, option.value)
        index = combo.findData(selected)
        if index < 0 and selected is not None:
            combo.addItem(f"Tundmatu väärtus ({selected})", selected)
            index = combo.count() - 1
        combo.setCurrentIndex(max(index, 0))
        combo.setMinimumContentsLength(18)
        return combo
