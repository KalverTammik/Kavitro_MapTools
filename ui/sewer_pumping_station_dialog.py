"""Dedicated editor for an EVEL sewer pumping station."""

from __future__ import annotations

from dataclasses import replace
import re

from qgis.PyQt.QtCore import (
    QDate,
    QPointF,
    QRegularExpression,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from qgis.PyQt.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRegularExpressionValidator,
)
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..layers import LookupOption, SewerPumpingStationOptions
from ..topology import (
    SewerPumpConfiguration,
    SewerPumpingStationConfiguration,
    SewerPumpingStationPlan,
    SewerPumpingStationState,
)
from .light_style import apply_evel_light_style
from .icon_catalog import (
    ICON_ADD,
    ICON_BACK,
    ICON_CANCEL,
    ICON_COPY,
    ICON_NEXT,
    ICON_PREVIEW_HIDE,
    ICON_PREVIEW_SHOW,
    ICON_REMOVE,
    ICON_SAVE,
    set_catalog_icon,
)


class PumpStationStepTabBar(QTabBar):
    """Give each workflow step exactly one quarter of the available width."""

    def _available_width(self) -> int:
        parent = self.parentWidget()
        return max(parent.width() if parent is not None else self.width(), 1)

    def tabSizeHint(self, index: int) -> QSize:  # noqa: N802
        hint = super().tabSizeHint(index)
        if self.count():
            hint.setWidth(max(self._available_width() // self.count(), 1))
        hint.setHeight(max(hint.height(), 58))
        return hint

    def sizeHint(self) -> QSize:  # noqa: N802
        hint = super().sizeHint()
        hint.setWidth(self._available_width())
        return hint

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.updateGeometry()


class NullableDoubleSpinBox(QDoubleSpinBox):
    """A numeric editor with an explicit, user-clearable NULL state."""

    def __init__(
        self,
        value: float | None,
        suffix: str,
        *,
        valid_minimum: float,
        valid_maximum: float,
        decimals: int,
        single_step: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        quantum = 10 ** (-decimals)
        self._valid_minimum = valid_minimum
        self._null_sentinel = valid_minimum - quantum
        self._handling_clear = False
        self.setDecimals(decimals)
        self.setRange(self._null_sentinel, valid_maximum)
        self.setSingleStep(single_step)
        self.setSpecialValueText("—")
        self.setSuffix(suffix)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setKeyboardTracking(False)
        self.lineEdit().setClearButtonEnabled(True)
        self.lineEdit().textChanged.connect(self._clear_if_empty)
        self.setToolTip(
            "Väärtuse võib jätta tühjaks. Tühjendamiseks kasuta välja "
            "paremas servas olevat ×-nuppu."
        )
        if value is None:
            self.set_null()
        else:
            self.setValue(float(value))

    def _clear_if_empty(self, text: str) -> None:
        if self._handling_clear or text.strip():
            return
        self._handling_clear = True
        try:
            self.set_null()
        finally:
            self._handling_clear = False

    def set_null(self) -> None:
        self.setValue(self._null_sentinel)

    def is_null(self) -> bool:
        return abs(self.value() - self._null_sentinel) < 1e-12

    def optional_value(self) -> float | None:
        return None if self.is_null() else float(self.value())

    def clear(self) -> None:
        self.set_null()

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        QTimer.singleShot(0, self.lineEdit().selectAll)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.is_null() and event.text():
            self.setValue(self._valid_minimum)
            self.lineEdit().selectAll()
        super().keyPressEvent(event)

    def stepBy(self, steps: int) -> None:  # noqa: N802
        if self.is_null():
            if steps > 0:
                self.setValue(self._valid_minimum)
            return
        super().stepBy(steps)


class OptionalNumberLineEdit(QLineEdit):
    """A compact optional decimal editor without spin controls."""

    def __init__(
        self,
        value: float | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._replace_on_next_input = False
        pattern = QRegularExpression(
            r"(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)?"
        )
        self.setValidator(QRegularExpressionValidator(pattern, self))
        self.setClearButtonEnabled(True)
        self.setPlaceholderText("Sisesta väärtus")
        self.setToolTip(
            "Sisesta arv. Kümnendmärgina sobib nii koma kui punkt."
        )
        self.set_optional_value(value)

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._replace_on_next_input = True
        QTimer.singleShot(0, self.selectAll)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._replace_on_next_input and event.text():
            self.selectAll()
            self._replace_on_next_input = False
        super().keyPressEvent(event)

    def set_optional_value(self, value: float | None) -> None:
        self.setText("" if value is None else f"{float(value):g}")

    def optional_value(self) -> float | None:
        text = self.text().strip()
        if not text:
            return None
        return float(text.replace(",", "."))


class SewerPumpingStationPreviewWidget(QWidget):
    """Game-like interactive cutaway illustration of a pumping station."""

    sectionSelected = pyqtSignal(int)

    SECTION_PUMPS = 0
    SECTION_CONTROL = 1
    SECTION_FACILITY = 2
    SECTION_PIPES = 3
    SECTION_NAMES = (
        "Pumbad",
        "Juhtimine",
        "Rajatis ja asukoht",
        "Torud",
    )

    def __init__(
        self,
        network_label: str,
        node_id: int | None,
        ports: tuple,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.network_label = network_label
        self.node_id = node_id
        self.ports = ports
        self.port_count = len(ports)
        self.selected_section = self.SECTION_PUMPS
        self.hovered_section = -1
        self.facility_name = "Uus pumpla"
        self.type_label = "Liik valimata"
        self.role_label = "Roll valimata"
        self.material_label = "Materjal valimata"
        self.control_label = "Juhtimise liik valimata"
        self.parcel_nr = ""
        self.productivity: float | None = None
        self.pressure: float | None = None
        self.power: float | None = None
        self.pump_count = 0
        self._origin = QPointF()
        self._scale = 1.0
        self._hotspots: dict[int, tuple[QRectF, ...]] = {}
        self._overlay_button: QPushButton | None = None
        self.setMinimumSize(340, 440)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.ArrowCursor)
        self.setAccessibleName(
            "Interaktiivne kanalisatsioonipumpla läbilõikeskeem"
        )
        self.setAccessibleDescription(
            "Illustratiivne skeem. Töövoos liikumiseks kasuta ka "
            "skeemi kõrval olevat neljaosalist sammuriba."
        )
        self._update_description()

    def set_overlay_button(self, button: QPushButton) -> None:
        self._overlay_button = button
        button.adjustSize()
        self._position_overlay_button()

    def _position_overlay_button(self) -> None:
        button = self._overlay_button
        if button is None:
            return
        size = button.sizeHint()
        width = min(max(size.width(), 105), 125)
        height = size.height()
        right = self._origin.x() + 420.0 * self._scale
        top = self._origin.y()
        button.setGeometry(
            round(right - width - 12),
            round(top + 12),
            width,
            height,
        )

    def set_selected_section(self, index: int) -> None:
        if index < 0 or index >= len(self.SECTION_NAMES):
            return
        self.selected_section = index
        self._update_description()
        self.update()

    def set_configuration(
        self,
        *,
        facility_name: str,
        type_label: str,
        role_label: str,
        material_label: str,
        control_label: str,
        parcel_nr: str,
        productivity: float | None,
        pressure: float | None,
        power: float | None,
        pump_count: int,
    ) -> None:
        self.facility_name = facility_name or "Uus pumpla"
        self.type_label = type_label or "Liik valimata"
        self.role_label = role_label or "Roll valimata"
        self.material_label = material_label or "Materjal valimata"
        self.control_label = control_label or "Juhtimise liik valimata"
        self.parcel_nr = parcel_nr
        self.productivity = productivity
        self.pressure = pressure
        self.power = power
        self.pump_count = max(int(pump_count), 0)
        self._update_description()
        self.update()

    def _flow_counts(self) -> tuple[int, int, int]:
        incoming = sum(port.is_outgoing is False for port in self.ports)
        outgoing = sum(port.is_outgoing is True for port in self.ports)
        unknown = self.port_count - incoming - outgoing
        return incoming, outgoing, unknown

    @staticmethod
    def _metric(value: float | None, suffix: str) -> str:
        return "määramata" if value is None else f"{value:g} {suffix}"

    def _summary_lines(self) -> tuple[str, str]:
        if self.selected_section == self.SECTION_FACILITY:
            return (
                f"{self.facility_name} · {self.type_label}",
                (
                    f"{self.role_label} · {self.material_label} · "
                    f"Qmax {self._metric(self.productivity, 'l/s')} · "
                    f"Δp {self._metric(self.pressure, 'bar')}"
                ),
            )
        if self.selected_section == self.SECTION_CONTROL:
            return (
                self.control_label,
                f"Elektrikoguvõimsus {self._metric(self.power, 'kW')}",
            )
        if self.selected_section == self.SECTION_PUMPS:
            if self.pump_count == 0:
                return (
                    "Pumpasid ei ole lisatud",
                    "Lisa pumpla tehnilised pumbad eraldi kirjetena",
                )
            return (
                f"{self.pump_count} pump"
                f"{'a' if self.pump_count != 1 else ''}",
                "Üksikpumpade andmed on seotud pumpla ID-ga",
            )
        incoming, outgoing, unknown = self._flow_counts()
        unknown_text = f" · {unknown} määramata" if unknown else ""
        return (
            f"{self.port_count} toruühendust",
            f"{incoming} sisse · {outgoing} välja{unknown_text}",
        )

    def _update_description(self) -> None:
        first, second = self._summary_lines()
        self.setToolTip(
            f"{first}\n{second}\n\n"
            "Klõpsa pumpla osal, et avada selle parameetrite vaheleht."
        )
        self.setAccessibleDescription(
            f"Illustratiivne skeem. {first}. {second}. "
            "Töövoos liikumiseks kasuta skeemi kõrval olevat sammuriba."
        )

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f6f7f8"))

        scene_width = 420.0
        scene_height = 475.0
        available = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        self._scale = min(
            available.width() / scene_width,
            available.height() / scene_height,
        )
        self._origin = QPointF(
            available.center().x() - scene_width * self._scale / 2.0,
            available.center().y() - scene_height * self._scale / 2.0,
        )
        self._position_overlay_button()
        painter.translate(self._origin)
        painter.scale(self._scale, self._scale)

        self._paint_background(painter)
        self._paint_header(painter)
        self._paint_station(painter)

    def _paint_background(self, painter: QPainter) -> None:
        gradient = QLinearGradient(0, 0, 420, 560)
        gradient.setColorAt(0.0, QColor("#ffffff"))
        gradient.setColorAt(0.55, QColor("#f7fafc"))
        gradient.setColorAt(1.0, QColor("#eef4f8"))
        painter.setPen(QPen(QColor("#d0d7de"), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(QRectF(1, 1, 418, 473), 18, 18)

        painter.setPen(QPen(QColor(0, 120, 212, 20), 1))
        for x in range(20, 421, 20):
            painter.drawLine(x, 76, x, 463)
        for y in range(76, 464, 20):
            painter.drawLine(0, y, 420, y)

    def _paint_header(self, painter: QPainter) -> None:
        painter.setPen(QColor("#0078d4"))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(8.5)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        painter.setFont(font)
        painter.drawText(
            QRectF(22, 18, 245, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            "ILLUSTRATIIVNE SKEEM",
        )
        first, second = self._summary_lines()
        summary_font = QFont(painter.font())
        summary_font.setBold(True)
        summary_font.setPointSizeF(8.3)
        summary_font.setLetterSpacing(QFont.AbsoluteSpacing, 0)
        painter.setFont(summary_font)
        painter.setPen(QColor("#111416"))
        painter.drawText(
            QRectF(22, 39, 250, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(summary_font).elidedText(
                first,
                Qt.ElideRight,
                250,
            ),
        )
        summary_font.setBold(False)
        summary_font.setPointSizeF(7.8)
        painter.setFont(summary_font)
        painter.setPen(QColor("#57606a"))
        painter.drawText(
            QRectF(22, 55, 250, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(summary_font).elidedText(
                second,
                Qt.ElideRight,
                250,
            ),
        )

    def _paint_station(self, painter: QPainter) -> None:
        self._hotspots = {
            self.SECTION_FACILITY: (
                QRectF(112, 122, 158, 73),
                QRectF(78, 411, 278, 52),
                QRectF(22, 88, 112, 27),
            ),
            self.SECTION_PUMPS: (
                QRectF(139, 224, 145, 188),
                QRectF(147, 205, 130, 27),
            ),
            self.SECTION_CONTROL: (QRectF(270, 92, 68, 112),),
            self.SECTION_PIPES: (
                QRectF(28, 250, 120, 105),
                QRectF(272, 210, 120, 145),
            ),
        }
        self._paint_selection_glow(painter)

        # Concrete base slab.
        base = QPolygonF(
            [
                QPointF(82, 420),
                QPointF(320, 420),
                QPointF(360, 446),
                QPointF(120, 461),
            ]
        )
        base_gradient = QLinearGradient(100, 420, 340, 455)
        base_gradient.setColorAt(0, QColor("#d9dee4"))
        base_gradient.setColorAt(1, QColor("#aab4bf"))
        painter.setBrush(QBrush(base_gradient))
        painter.setPen(QPen(QColor("#768390"), 1))
        painter.drawPolygon(base)

        # Cylindrical chamber and water level.
        body = QRectF(126, 170, 170, 252)
        body_gradient = QLinearGradient(body.left(), 0, body.right(), 0)
        body_gradient.setColorAt(0.0, QColor("#aebbc7"))
        body_gradient.setColorAt(0.22, QColor("#eef2f5"))
        body_gradient.setColorAt(0.52, QColor("#c4ced7"))
        body_gradient.setColorAt(0.78, QColor("#f4f6f8"))
        body_gradient.setColorAt(1.0, QColor("#aab7c3"))
        painter.setBrush(QBrush(body_gradient))
        painter.setPen(QPen(QColor("#657687"), 2))
        painter.drawRoundedRect(body, 20, 20)

        water = QRectF(135, 319, 152, 91)
        water_gradient = QLinearGradient(0, water.top(), 0, water.bottom())
        water_gradient.setColorAt(0, QColor(24, 164, 220, 105))
        water_gradient.setColorAt(1, QColor(5, 69, 118, 165))
        painter.setBrush(QBrush(water_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(water, 11, 11)
        painter.setPen(QPen(QColor("#1687c9"), 2))
        painter.drawArc(QRectF(135, 311, 152, 17), 0, 180 * 16)

        # Chamber rings create the recognisable ribbed enclosure.
        painter.setPen(QPen(QColor("#7f8c98"), 2))
        for y in range(186, 416, 15):
            painter.drawArc(QRectF(126, y - 5, 170, 14), 180 * 16, 180 * 16)
            painter.drawArc(QRectF(126, y - 5, 170, 14), 0, 180 * 16)

        # Top collar and open service hatch.
        painter.setBrush(QColor("#e2e7ec"))
        painter.setPen(QPen(QColor("#657687"), 2))
        painter.drawEllipse(QRectF(115, 154, 192, 35))
        painter.drawRoundedRect(QRectF(147, 127, 128, 40), 4, 4)
        hatch = QPolygonF(
            [
                QPointF(150, 128),
                QPointF(181, 91),
                QPointF(258, 106),
                QPointF(272, 129),
            ]
        )
        painter.setBrush(QColor("#cbd3db"))
        painter.setPen(QPen(QColor("#657687"), 2))
        painter.drawPolygon(hatch)

        # Electrical control cabinet.
        cabinet_gradient = QLinearGradient(276, 96, 329, 195)
        cabinet_gradient.setColorAt(0, QColor("#d9e2e9"))
        cabinet_gradient.setColorAt(1, QColor("#667787"))
        painter.setBrush(QBrush(cabinet_gradient))
        painter.setPen(QPen(QColor("#d8e5ee"), 2))
        painter.drawRoundedRect(QRectF(278, 101, 51, 91), 3, 3)
        painter.setBrush(QColor("#344555"))
        painter.drawRoundedRect(QRectF(286, 114, 34, 43), 2, 2)
        painter.setBrush(QColor("#39e58c"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(290, 164, 6, 6))
        painter.setBrush(QColor("#ffbc3d"))
        painter.drawEllipse(QRectF(300, 164, 6, 6))

        # External pipe stubs reflect the real connection count and flow.
        self._paint_connections(painter)

        self._paint_pumps(painter)

        self._paint_component_badge(
            painter,
            QRectF(35, 274, 122, 27),
            f"04  TORUD · {self.port_count}",
            self.SECTION_PIPES,
        )
        self._paint_component_badge(
            painter,
            QRectF(22, 88, 112, 27),
            "03  RAJATIS",
            self.SECTION_FACILITY,
        )
        self._paint_component_badge(
            painter,
            QRectF(277, 76, 108, 27),
            "02  JUHTIMINE",
            self.SECTION_CONTROL,
        )
        self._paint_component_badge(
            painter,
            QRectF(118, 430, 132, 27),
            "03  ASUKOHT",
            self.SECTION_FACILITY,
        )
        self._paint_component_badge(
            painter,
            QRectF(147, 205, 130, 27),
            f"01  PUMBAD · {self.pump_count}",
            self.SECTION_PUMPS,
        )
        self._paint_facility_outline(painter)

    def _paint_pumps(self, painter: QPainter) -> None:
        visible_count = min(self.pump_count, 3)
        positions = {
            1: (193.0,),
            2: (157.0, 220.0),
            3: (139.0, 193.0, 247.0),
        }.get(visible_count, ())
        if not positions:
            painter.setPen(QPen(QColor("#93a4b3"), 1.5, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(158, 286, 106, 92), 12, 12)
            painter.setPen(QColor("#57606a"))
            painter.drawText(
                QRectF(158, 315, 106, 24),
                Qt.AlignCenter,
                "PUMPASID POLE",
            )
            return

        pipe_centers = []
        for x in positions:
            self._paint_pump(painter, x, 286)
            pipe_centers.append(x + 18)
        painter.setPen(QPen(QColor("#198fd4"), 7))
        manifold_y = 246.0
        for index, center in enumerate(pipe_centers):
            target_y = manifold_y - min(index, 1) * 8
            painter.drawLine(
                QPointF(center, 291),
                QPointF(center, target_y),
            )
        painter.drawLine(
            QPointF(min(pipe_centers), manifold_y),
            QPointF(max(pipe_centers), manifold_y),
        )
        if self.pump_count > visible_count:
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#0078d4"), 2))
            painter.drawEllipse(QRectF(246, 264, 42, 28))
            painter.setPen(QColor("#005a9e"))
            font = QFont(painter.font())
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRectF(246, 264, 42, 28),
                Qt.AlignCenter,
                f"+{self.pump_count - visible_count}",
            )

    def _paint_connections(self, painter: QPainter) -> None:
        incoming = [
            port for port in self.ports if port.is_outgoing is False
        ]
        outgoing = [
            port for port in self.ports if port.is_outgoing is True
        ]
        unknown = [
            port for port in self.ports if port.is_outgoing is None
        ]
        left_ports = [(port, False) for port in incoming]
        right_ports = [(port, False) for port in outgoing]
        for index, port in enumerate(unknown):
            target = left_ports if index % 2 == 0 else right_ports
            target.append((port, True))

        left_rows = (315.0, 278.0, 352.0)
        right_rows = (230.0, 268.0, 306.0)
        for side, entries, rows in (
            ("left", left_ports, left_rows),
            ("right", right_ports, right_rows),
        ):
            for index, (_port, direction_unknown) in enumerate(entries[:3]):
                y = rows[index]
                color = QColor(
                    "#e5a83b" if direction_unknown else "#198fd4"
                )
                pipe_pen = QPen(color, 9)
                pipe_pen.setCapStyle(Qt.RoundCap)
                pipe_pen.setJoinStyle(Qt.RoundJoin)
                if direction_unknown:
                    pipe_pen.setStyle(Qt.DashLine)
                painter.setPen(pipe_pen)
                painter.setBrush(Qt.NoBrush)
                if side == "left":
                    painter.drawLine(QPointF(35, y), QPointF(145, y))
                    self._paint_valve(painter, QPointF(104, y))
                    if not direction_unknown:
                        self._paint_flow_arrow(
                            painter,
                            QPointF(54, y),
                            points_right=True,
                        )
                else:
                    end_y = y - 16 if index == 0 else y
                    path = QPainterPath(QPointF(278, y))
                    path.lineTo(335, y)
                    path.lineTo(382, end_y)
                    painter.drawPath(path)
                    self._paint_valve(painter, QPointF(309, y))
                    if not direction_unknown:
                        self._paint_flow_arrow(
                            painter,
                            QPointF(365, end_y),
                            points_right=True,
                        )

            hidden_count = max(len(entries) - len(rows), 0)
            if hidden_count:
                painter.setPen(QColor("#57606a"))
                font = QFont(painter.font())
                font.setBold(True)
                font.setPointSizeF(8)
                painter.setFont(font)
                rect = (
                    QRectF(28, 368, 100, 18)
                    if side == "left"
                    else QRectF(294, 326, 100, 18)
                )
                painter.drawText(
                    rect,
                    Qt.AlignCenter,
                    f"+{hidden_count} ühendust",
                )

    @staticmethod
    def _paint_flow_arrow(
        painter: QPainter,
        center: QPointF,
        *,
        points_right: bool,
    ) -> None:
        direction = 1 if points_right else -1
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2188ff"))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(center.x() - 8 * direction, center.y() - 10),
                    QPointF(center.x() - 8 * direction, center.y() + 10),
                    QPointF(center.x() + 8 * direction, center.y()),
                ]
            )
        )

    def _paint_facility_outline(self, painter: QPainter) -> None:
        """Outline the station shell without highlighting its pumps."""
        if self.selected_section != self.SECTION_FACILITY:
            return
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#0078d4"), 3))
        painter.drawRoundedRect(QRectF(112, 124, 198, 303), 22, 22)
        painter.drawPolyline(
            QPolygonF(
                [
                    QPointF(82, 420),
                    QPointF(120, 461),
                    QPointF(360, 446),
                ]
            )
        )

    def _paint_selection_glow(self, painter: QPainter) -> None:
        selected_glow = QColor("#0078d4")
        selected_glow.setAlpha(32)
        painter.setBrush(selected_glow)
        painter.setPen(QPen(QColor("#0078d4"), 3))
        for rect in self._hotspots.get(self.selected_section, ()):
            painter.drawRoundedRect(rect.adjusted(-5, -5, 5, 5), 10, 10)
        if (
            self.hovered_section >= 0
            and self.hovered_section != self.selected_section
        ):
            hover_glow = QColor("#0f766e")
            hover_glow.setAlpha(20)
            painter.setBrush(hover_glow)
            painter.setPen(QPen(QColor("#0f766e"), 2))
            for rect in self._hotspots.get(self.hovered_section, ()):
                painter.drawRoundedRect(
                    rect.adjusted(-4, -4, 4, 4),
                    9,
                    9,
                )

    @staticmethod
    def _paint_pump(painter: QPainter, x: float, y: float) -> None:
        gradient = QLinearGradient(x, y, x + 36, y)
        gradient.setColorAt(0, QColor("#718090"))
        gradient.setColorAt(0.5, QColor("#e7ebef"))
        gradient.setColorAt(1, QColor("#657483"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor("#566675"), 1.5))
        painter.drawRoundedRect(QRectF(x, y, 36, 91), 13, 13)
        painter.drawEllipse(QRectF(x + 3, y - 8, 30, 20))
        painter.setBrush(QColor("#354655"))
        painter.drawRoundedRect(QRectF(x + 5, y + 65, 26, 25), 7, 7)

    @staticmethod
    def _paint_valve(painter: QPainter, center: QPointF) -> None:
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#0078d4"), 3))
        painter.drawEllipse(center, 11, 11)
        painter.drawLine(
            QPointF(center.x() - 9, center.y()),
            QPointF(center.x() + 9, center.y()),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - 9),
            QPointF(center.x(), center.y() + 9),
        )

    def _paint_component_badge(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        section: int,
    ) -> None:
        active = section == self.selected_section
        hovered = section == self.hovered_section and not active
        painter.setBrush(QColor("#0078d4" if active else "#f0f4f8"))
        painter.setPen(
            QPen(
                QColor(
                    "#005a9e"
                    if active
                    else "#0f766e"
                    if hovered
                    else "#b6c2cd"
                ),
                1.5 if active or hovered else 1,
            )
        )
        painter.drawRoundedRect(rect, 7, 7)
        painter.setPen(QColor("#ffffff" if active else "#24292e"))
        badge_font = QFont(painter.font())
        badge_font.setBold(True)
        badge_font.setPointSizeF(7.5)
        painter.setFont(badge_font)
        painter.drawText(rect, Qt.AlignCenter, text)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        hovered = self._section_at(event.pos())
        if hovered != self.hovered_section:
            self.hovered_section = hovered
            self.setCursor(
                Qt.PointingHandCursor
                if hovered >= 0
                else Qt.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self.hovered_section != -1:
            self.hovered_section = -1
            self.setCursor(Qt.ArrowCursor)
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        section = self._section_at(event.pos())
        if section < 0:
            return
        self.set_selected_section(section)
        self.sectionSelected.emit(section)

    def _section_at(self, widget_point) -> int:
        if self._scale <= 0:
            return -1
        scene_point = QPointF(
            (widget_point.x() - self._origin.x()) / self._scale,
            (widget_point.y() - self._origin.y()) / self._scale,
        )
        for section, rects in self._hotspots.items():
            if any(rect.contains(scene_point) for rect in rects):
                return section
        return -1


class SewerPumpingStationDialog(QDialog):
    """Edit a pumping station separately from the manhole clock."""

    PARCEL_PATTERN = re.compile(r"^\d{5}:\d{3}:\d{4}$")

    def __init__(
        self,
        state: SewerPumpingStationState,
        options: SewerPumpingStationOptions,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.state = state
        self.options = options
        self._pump_configs = list(state.pumps)
        self._loading_pump = False
        self.port_height_spins: dict[str, QDoubleSpinBox] = {}
        self.required_errors: dict[str, QLabel] = {}
        self._busy = False
        node_id = state.topology.node_id
        self.setWindowTitle(
            "Uue kanalisatsioonipumpla generaator"
            if node_id is None
            else f"Kanalisatsioonipumpla {node_id} — parameetrid"
        )
        self.setModal(True)
        self.resize(1180, 760)
        self.setMinimumSize(900, 620)
        self.setObjectName("evelPumpingStationDialog")
        apply_evel_light_style(self, pumping_station=True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)
        self.name_edit = QLineEdit(state.configuration.name, self)
        self.name_edit.setObjectName("heroNameEdit")
        self.name_edit.setPlaceholderText("Pumpla nimi")
        self.name_edit.setToolTip("Pumpla nimi on kohustuslik.")
        self.name_edit.setAccessibleName("Pumpla nimi")
        root.addWidget(self._hero_header())

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.preview_frame = QFrame(self.splitter)
        self.preview_frame.setObjectName("editorFrame")
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        self.preview = SewerPumpingStationPreviewWidget(
            state.network_label,
            node_id,
            state.topology.ports,
            self.preview_frame,
        )
        self.preview_toggle_button = QPushButton(
            "‹ Peida skeem",
            self.preview,
        )
        self.preview_toggle_button.setObjectName("previewToggleButton")
        set_catalog_icon(self.preview_toggle_button, ICON_PREVIEW_HIDE)
        self.preview_toggle_button.setToolTip(
            "Peida pumpla illustratiivne skeem."
        )
        self.preview_toggle_button.setMaximumWidth(125)
        self.preview_toggle_button.clicked.connect(self._toggle_preview)
        self.preview.set_overlay_button(self.preview_toggle_button)
        preview_layout.addWidget(self.preview)
        self.splitter.addWidget(self.preview_frame)

        editor_frame = QFrame(self.splitter)
        editor_frame.setObjectName("editorFrame")
        editor_layout = QVBoxLayout(editor_frame)
        editor_layout.setContentsMargins(14, 13, 14, 13)
        editor_layout.setSpacing(9)
        editor_intro = QHBoxLayout()
        editor_intro.addStretch(1)
        self.preview_show_button = QPushButton(
            "Näita skeemi ›",
            editor_frame,
        )
        self.preview_show_button.setObjectName("previewToggleButton")
        set_catalog_icon(self.preview_show_button, ICON_PREVIEW_SHOW)
        self.preview_show_button.setToolTip(
            "Taasta pumpla illustratiivne skeem."
        )
        self.preview_show_button.setMaximumWidth(125)
        self.preview_show_button.clicked.connect(self._toggle_preview)
        self.preview_show_button.setVisible(False)
        editor_intro.addWidget(self.preview_show_button)
        editor_layout.addLayout(editor_intro)
        self.tabs = QTabWidget(self)
        self.tabs.setTabBar(PumpStationStepTabBar(self.tabs))
        self.tabs.addTab(self._pumps_tab(), "01 · Pumbad")
        self.tabs.addTab(self._electrical_tab(), "02 · Juhtimine")
        self.tabs.addTab(
            self._general_tab(),
            "03 · Rajatis ja asukoht",
        )
        self.tabs.addTab(self._pipes_tab(), "04 · Torud")
        self.tabs.tabBar().setExpanding(True)
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        editor_layout.addWidget(self.tabs, 1)
        self.splitter.addWidget(editor_frame)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 5)
        self._preview_width = 400
        self.splitter.setSizes((self._preview_width, 710))
        root.addWidget(self.splitter, 1)

        self.busy_frame = QFrame(self)
        self.busy_frame.setObjectName("busyFrame")
        busy_layout = QHBoxLayout(self.busy_frame)
        busy_layout.setContentsMargins(12, 8, 12, 8)
        self.busy_label = QLabel("Pumpla andmete töötlemine…", self.busy_frame)
        self.busy_label.setWordWrap(True)
        busy_layout.addWidget(self.busy_label, 1)
        self.busy_progress = QProgressBar(self.busy_frame)
        self.busy_progress.setRange(0, 100)
        self.busy_progress.setValue(0)
        self.busy_progress.setMaximumWidth(260)
        busy_layout.addWidget(self.busy_progress)
        self.busy_frame.setVisible(False)
        root.addWidget(self.busy_frame)

        footer = QHBoxLayout()
        self.cancel_button = QPushButton("Tühista", self)
        self.cancel_button.setObjectName("cancelButton")
        set_catalog_icon(self.cancel_button, ICON_CANCEL)
        footer.addWidget(self.cancel_button)
        footer.addStretch(1)
        self.back_button = QPushButton("Tagasi", self)
        set_catalog_icon(self.back_button, ICON_BACK)
        self.next_button = QPushButton(self)
        set_catalog_icon(self.next_button, ICON_NEXT)
        self.next_button.setDefault(True)
        footer.addWidget(self.back_button)
        footer.addWidget(self.next_button)
        self.cancel_button.clicked.connect(self.reject)
        self.back_button.clicked.connect(self._go_back)
        self.next_button.clicked.connect(self._go_next)
        root.addLayout(footer)
        self._connect_live_preview()
        self._preview_changed()
        self._configure_tab_order()
        self._initial_snapshot = self._snapshot()

    def accept(self) -> None:
        required_valid = self._validate_required(show_errors=True)
        pumps_valid = self._pumps_valid(show_errors=True)
        if not required_valid or not pumps_valid:
            values = self._required_values()
            target = (
                0
                if not pumps_valid
                else 1
                if not values["control"]
                else 2
                if not all(
                    values[key]
                    for key in ("name", "type", "role", "material")
                )
                else 3
            )
            self.tabs.setCurrentIndex(target)
            self._update_navigation()
            if target == 0:
                self.pump_type_combo.setFocus(Qt.OtherFocusReason)
            else:
                self._focus_first_missing()
            return
        super().accept()

    def reject(self) -> None:
        if self._busy:
            return
        if (
            hasattr(self, "_initial_snapshot")
            and self._snapshot() != self._initial_snapshot
        ):
            message = QMessageBox(self)
            apply_evel_light_style(message)
            message.setIcon(QMessageBox.Warning)
            message.setWindowTitle("Loobu pumpla muudatustest?")
            message.setText(
                "Pumpla vormil on salvestamata muudatusi. "
                "Kas soovid neist loobuda?"
            )
            discard = message.addButton(
                "Loobu muudatustest",
                QMessageBox.DestructiveRole,
            )
            keep_editing = message.addButton(
                "Jätka sisestamist",
                QMessageBox.RejectRole,
            )
            message.setDefaultButton(keep_editing)
            message.exec()
            if message.clickedButton() is not discard:
                return
        super().reject()

    def _snapshot(self) -> tuple:
        plan = self.plan()
        return plan.configuration, plan.port_heights, plan.pumps

    def set_busy(
        self,
        busy: bool,
        message: str = "",
        progress: int | None = None,
    ) -> None:
        """Show a stable write-progress state without discarding the form."""

        self._busy = busy
        self.busy_label.setText(message or "Pumpla andmete töötlemine…")
        self.busy_frame.setProperty(
            "status",
            "busy" if busy else "error" if message else "",
        )
        self.busy_frame.style().unpolish(self.busy_frame)
        self.busy_frame.style().polish(self.busy_frame)
        if progress is None:
            self.busy_progress.setRange(0, 0)
        else:
            self.busy_progress.setRange(0, 100)
            self.busy_progress.setValue(max(0, min(int(progress), 100)))
        self.busy_progress.setVisible(busy)
        self.busy_frame.setVisible(busy or bool(message))
        self.name_edit.setEnabled(not busy)
        self.splitter.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)
        self.back_button.setEnabled(not busy and self.tabs.currentIndex() > 0)
        self.next_button.setEnabled(not busy)
        self.setCursor(Qt.WaitCursor if busy else Qt.ArrowCursor)
        if not busy:
            self._update_navigation()

    def plan(self) -> SewerPumpingStationPlan:
        config = SewerPumpingStationConfiguration(
            identification=self.identification_edit.text().strip(),
            element_height=self._optional_number(self.element_height_spin),
            bottom_height=self._optional_number(self.bottom_height_spin),
            ground_height=self._optional_number(self.ground_height_spin),
            type_aqua_id=self.type_combo.currentData(),
            material_id=self.material_combo.currentData(),
            role_id=self.role_combo.currentData(),
            name=self.name_edit.text().strip(),
            productivity=self._optional_number(self.productivity_spin),
            pressure_increase=self._optional_number(self.pressure_spin),
            power_consumption=self._optional_number(self.power_spin),
            el_max_current=self._optional_number(self.current_spin),
            control_id=self.control_combo.currentData(),
            parcel_nr=self.parcel_edit.text().strip(),
            address_id=self.state.configuration.address_id,
        )
        return SewerPumpingStationPlan(
            state=self.state.topology,
            configuration=config,
            port_heights=tuple(
                (
                    port.key,
                    self._optional_number(self.port_height_spins[port.key]),
                )
                for port in self.state.topology.ports
            ),
            pumps=tuple(self._pump_configs),
            original_pumps=self.state.pumps,
        )

    @staticmethod
    def _section_header(
        layout: QVBoxLayout,
        title: str,
        description: str,
    ) -> None:
        if layout.count():
            layout.addSpacing(6)
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setStyleSheet("color: #d0d7de;")
            layout.addWidget(line)
        heading = QLabel(title)
        heading.setStyleSheet(
            "color: #111416; font-size: 13px; font-weight: 700;"
        )
        layout.addWidget(heading)
        hint = QLabel(description)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #57606a; font-size: 10px;")
        layout.addWidget(hint)

    @staticmethod
    def _section_divider(layout: QVBoxLayout) -> None:
        layout.addSpacing(8)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #d0d7de;")
        layout.addWidget(line)

    def _scrollable_form_tab(
        self,
    ) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
        scroll = QScrollArea(self.tabs)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        content.setObjectName("tabContent")
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)
        scroll.setWidget(content)
        return scroll, content, layout

    @staticmethod
    def _field_block(
        label_text: str,
        control: QWidget,
        parent=None,
        *,
        buddy: QWidget | None = None,
    ) -> QWidget:
        block = QWidget(parent)
        block.setMinimumWidth(0)
        block.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        label = QLabel(label_text, block)
        label.setObjectName("fieldLabel")
        label.setWordWrap(True)
        focus_target = buddy or control
        label.setBuddy(focus_target)
        if not focus_target.accessibleName():
            focus_target.setAccessibleName(
                label_text.replace(" *", "")
            )
        layout.addWidget(label)
        layout.addWidget(control)
        return block

    def _required_widget(
        self,
        key: str,
        control: QWidget,
        message: str,
        parent=None,
    ) -> QWidget:
        wrapper = QWidget(parent)
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(control)
        error = QLabel(message, wrapper)
        error.setWordWrap(True)
        error.setStyleSheet("color: #c53030; font-size: 10px;")
        error.setVisible(False)
        layout.addWidget(error)
        self.required_errors[key] = error
        return wrapper

    def _hero_header(self) -> QFrame:
        frame = QFrame(self)
        frame.setObjectName("heroFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 10)
        layout.setSpacing(3)
        name_row = QHBoxLayout()
        name_row.addWidget(
            self._required_widget(
                "name",
                self.name_edit,
                "Pumpla nimi on kohustuslik.",
                frame,
            ),
            1,
        )
        name_row.addStretch(1)
        context = QLabel(
            f"Võrk: {self.state.network_label}",
            frame,
        )
        context.setStyleSheet("color: #4a5568;")
        name_row.addWidget(context, 0, Qt.AlignRight | Qt.AlignVCenter)
        layout.addLayout(name_row)
        return frame

    def _connect_live_preview(self) -> None:
        self.preview.sectionSelected.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self._section_changed)
        for combo in (
            self.type_combo,
            self.role_combo,
            self.material_combo,
            self.control_combo,
        ):
            combo.currentIndexChanged.connect(self._preview_changed)
        for edit in (
            self.identification_edit,
            self.name_edit,
            self.parcel_edit,
        ):
            edit.textChanged.connect(self._preview_changed)
        for spin in (
            self.productivity_spin,
            self.pressure_spin,
            self.power_spin,
            self.current_spin,
            self.element_height_spin,
            self.bottom_height_spin,
            self.ground_height_spin,
            *self.port_height_spins.values(),
        ):
            spin.valueChanged.connect(self._preview_changed)

    def _configure_tab_order(self) -> None:
        controls = [
            self.name_edit,
            self.preview_toggle_button,
            self.preview_show_button,
            self.tabs,
            self.pump_add_button,
            self.pump_duplicate_button,
            self.pump_remove_button,
            self.pump_list,
            self.pump_type_combo,
            self.pump_install_combo,
            self.pump_manufacturer_edit,
            self.pump_mark_edit,
            self.pump_productivity_edit,
            self.pump_head_edit,
            self.pump_power_edit,
            self.pump_date_known,
            self.pump_date_edit,
            self.pump_running_time_spin,
            self.pump_in_diameter_combo,
            self.pump_out_diameter_combo,
            self.pump_current_edit,
            self.pump_voltage_edit,
            self.pump_remarks_edit,
            self.control_combo,
            self.power_spin,
            self.current_spin,
            self.identification_edit,
            self.type_combo,
            self.role_combo,
            self.material_combo,
            self.productivity_spin,
            self.pressure_spin,
            self.element_height_spin,
            self.bottom_height_spin,
            self.ground_height_spin,
            self.parcel_edit,
            *self.port_height_spins.values(),
            self.cancel_button,
            self.back_button,
            self.next_button,
        ]
        for current, following in zip(controls, controls[1:]):
            self.setTabOrder(current, following)

    def _section_changed(self, index: int) -> None:
        if 0 <= index < self.tabs.count():
            self.preview.set_selected_section(index)
            self._update_navigation()

    def _toggle_preview(self) -> None:
        visible = not self.preview_frame.isHidden()
        if visible:
            sizes = self.splitter.sizes()
            if sizes and sizes[0] > 0:
                self._preview_width = sizes[0]
        self.preview_frame.setVisible(not visible)
        self.preview_show_button.setVisible(visible)
        if not visible:
            total = max(sum(self.splitter.sizes()), self.width() - 40)
            preview_width = min(
                max(self._preview_width, 340),
                max(total - 420, 340),
            )
            self.splitter.setSizes(
                (preview_width, max(total - preview_width, 420))
            )

    def _go_back(self) -> None:
        self.tabs.setCurrentIndex(max(self.tabs.currentIndex() - 1, 0))

    def _go_next(self) -> None:
        index = self.tabs.currentIndex()
        if index == 0 and not self._pumps_valid(show_errors=True):
            self.pump_type_combo.setFocus(Qt.OtherFocusReason)
            return
        if index == 1 and not self._meaningful_combo_value(
            self.control_combo
        ):
            self.required_errors["control"].setVisible(True)
            self.control_combo.setFocus(Qt.OtherFocusReason)
            return
        if index == 2 and not self._facility_required_complete(
            show_errors=True
        ):
            self._focus_first_missing(
                ("name", "type", "role", "material")
            )
            return
        if index < self.tabs.count() - 1:
            self.tabs.setCurrentIndex(index + 1)
            return
        self.accept()

    def _required_values(self) -> dict[str, bool]:
        return {
            "name": bool(self.name_edit.text().strip()),
            "type": self._meaningful_combo_value(self.type_combo),
            "role": self._meaningful_combo_value(self.role_combo),
            "material": self._meaningful_combo_value(self.material_combo),
            "control": self._meaningful_combo_value(self.control_combo),
        }

    @staticmethod
    def _meaningful_combo_value(combo: QComboBox) -> bool:
        if combo.currentData() is None:
            return False
        return not combo.currentText().strip().casefold().startswith(
            "määramata"
        )

    def _focus_first_missing(
        self,
        keys: tuple[str, ...] | None = None,
    ) -> None:
        values = self._required_values()
        ordered = keys or ("name", "type", "role", "material", "control")
        widgets = {
            "name": self.name_edit,
            "type": self.type_combo,
            "role": self.role_combo,
            "material": self.material_combo,
            "control": self.control_combo,
        }
        for key in ordered:
            if values[key]:
                continue
            widgets[key].setFocus(Qt.OtherFocusReason)
            return

    def _facility_required_complete(self, *, show_errors: bool) -> bool:
        values = self._required_values()
        for key in ("name", "type", "role", "material"):
            if show_errors or values[key]:
                self.required_errors[key].setVisible(not values[key])
        return all(
            values[key] for key in ("name", "type", "role", "material")
        )

    def _validate_required(self, *, show_errors: bool) -> bool:
        values = self._required_values()
        for key, complete in values.items():
            if show_errors or complete:
                self.required_errors[key].setVisible(not complete)
        return all(values.values())

    def _update_step_labels(self) -> None:
        values = self._required_values()
        facility_count = sum(
            values[key] for key in ("name", "type", "role", "material")
        )
        parcel = self.parcel_edit.text().strip()
        valid_location = not parcel or bool(
            self.PARCEL_PATTERN.fullmatch(parcel)
        )
        facility_label = (
            "03  Rajatis ja asukoht\nValmis ✓"
            if facility_count == 4 and valid_location
            else "03  Rajatis ja asukoht\nKontrolli asukohta"
            if facility_count == 4
            else f"03  Rajatis ja asukoht\n{facility_count}/4 täidetud"
        )
        pump_count = len(self._pump_configs)
        pumps_valid = self._pumps_valid()
        pump_label = (
            f"01  Pumbad\n{pump_count} pump"
            f"{'a' if pump_count != 1 else ''} ✓"
            if pump_count and pumps_valid
            else "01  Pumbad\nKontrolli andmeid"
            if pump_count
            else "01  Pumbad\nLisamata"
        )
        control_label = (
            "02  Juhtimine\nValmis ✓"
            if values["control"]
            else "02  Juhtimine\nTäitmata"
        )
        pipe_count = len(self.state.topology.ports)
        pipe_label = (
            f"04  Torud\n{pipe_count} ühendus"
            f"{'t' if pipe_count != 1 else ''} ✓"
            if pipe_count
            else "04  Torud\nÜhenduseta"
        )
        for index, text in enumerate(
            (
                pump_label,
                control_label,
                facility_label,
                pipe_label,
            )
        ):
            self.tabs.setTabText(index, text)

    def _update_navigation(self) -> None:
        if not hasattr(self, "next_button"):
            return
        index = self.tabs.currentIndex()
        values = self._required_values()
        labels = (
            "Edasi: Juhtimine",
            "Edasi: Rajatis ja asukoht",
            "Edasi: Torud",
            (
                "Salvesta pumpla"
                if self.state.topology.node_id is not None
                else "Loo pumpla"
            ),
        )
        self.next_button.setText(labels[index])
        set_catalog_icon(
            self.next_button,
            ICON_SAVE if index == self.tabs.count() - 1 else ICON_NEXT,
        )
        self.back_button.setEnabled(index > 0)
        if index == 1:
            relevant_keys = ("control",)
        elif index == 2:
            relevant_keys = ("name", "type", "role", "material")
        elif index == self.tabs.count() - 1:
            relevant_keys = tuple(values)
        else:
            relevant_keys = ()
        missing_keys = [key for key in relevant_keys if not values[key]]
        pumps_missing = (
            not self._pumps_valid()
            and index in {0, self.tabs.count() - 1}
        )
        self.next_button.setEnabled(True)
        missing_names = {
            "name": "pumpla nimi",
            "type": "pumpla liik",
            "role": "pumpla roll",
            "material": "korpuse materjal",
            "control": "juhtimise liik",
        }
        self.next_button.setToolTip(
            (
                "Jätkamiseks täida: "
                + ", ".join(missing_names[key] for key in missing_keys)
                + "."
            )
            if missing_keys
            else "Jätkamiseks vali igale lisatud pumbale pumba tüüp."
            if pumps_missing
            else labels[index]
        )

    def _preview_changed(self, *_args) -> None:
        productivity = self._optional_number(self.productivity_spin)
        pressure = self._optional_number(self.pressure_spin)
        power = self._optional_number(self.power_spin)
        name = (
            self.name_edit.text().strip()
            or self.identification_edit.text().strip()
            or "Uus pumpla"
        )
        type_label = (
            self.type_combo.currentText()
            if self._meaningful_combo_value(self.type_combo)
            else "Liik valimata"
        )
        role_label = (
            self.role_combo.currentText()
            if self._meaningful_combo_value(self.role_combo)
            else "Roll valimata"
        )
        material_label = (
            self.material_combo.currentText()
            if self._meaningful_combo_value(self.material_combo)
            else "Materjal valimata"
        )
        control_label = (
            self.control_combo.currentText()
            if self._meaningful_combo_value(self.control_combo)
            else "Juhtimise liik valimata"
        )
        self.preview.set_configuration(
            facility_name=name,
            type_label=type_label,
            role_label=role_label,
            material_label=material_label,
            control_label=control_label,
            parcel_nr=self.parcel_edit.text().strip(),
            productivity=productivity,
            pressure=pressure,
            power=power,
            pump_count=len(self._pump_configs),
        )
        parcel = self.parcel_edit.text().strip()
        self.parcel_warning.setVisible(
            bool(parcel)
            and not bool(self.PARCEL_PATTERN.fullmatch(parcel))
        )
        self._validate_required(show_errors=False)
        self._update_step_labels()
        self._update_navigation()

    def _general_tab(self) -> QWidget:
        config = self.state.configuration
        scroll, tab, layout = self._scrollable_form_tab()

        identity_hint = QLabel(
            "Sõlme tähis võib järgida ettevõtte olemasolevat "
            "tähistussüsteemi.",
            tab,
        )
        identity_hint.setWordWrap(True)
        identity_hint.setStyleSheet("color: #57606a; font-size: 10px;")
        layout.addWidget(identity_hint)
        identity_grid = QGridLayout()
        identity_grid.setHorizontalSpacing(12)
        identity_grid.setVerticalSpacing(10)
        identity_grid.setColumnStretch(0, 1)
        identity_grid.setColumnStretch(1, 1)
        self.identification_edit = QLineEdit(config.identification, tab)
        self.identification_edit.setPlaceholderText("Näiteks KP-102")
        identity_grid.addWidget(
            self._field_block(
                "Sõlme tähis",
                self.identification_edit,
                tab,
            ),
            0,
            0,
            1,
            2,
        )
        layout.addLayout(identity_grid)

        self._section_divider(layout)
        classification_grid = QGridLayout()
        classification_grid.setHorizontalSpacing(12)
        classification_grid.setVerticalSpacing(10)
        classification_grid.setColumnStretch(0, 1)
        classification_grid.setColumnStretch(1, 1)
        self.type_combo = self._combo(
            self.options.type_options,
            config.type_aqua_id,
            tab,
            placeholder="Vali pumpla liik…",
        )
        classification_grid.addWidget(
            self._field_block(
                "Pumpla liik *",
                self._required_widget(
                    "type",
                    self.type_combo,
                    "Pumpla liik peab olema valitud.",
                    tab,
                ),
                tab,
                buddy=self.type_combo,
            ),
            0,
            0,
        )
        self.role_combo = self._combo(
            self.options.role_options,
            config.role_id,
            tab,
            placeholder="Vali pumpla roll…",
        )
        classification_grid.addWidget(
            self._field_block(
                "Pumpla roll *",
                self._required_widget(
                    "role",
                    self.role_combo,
                    "Pumpla roll peab olema valitud.",
                    tab,
                ),
                tab,
                buddy=self.role_combo,
            ),
            0,
            1,
        )
        self.material_combo = self._combo(
            self.options.material_options,
            config.material_id,
            tab,
            placeholder="Vali korpuse materjal…",
        )
        classification_grid.addWidget(
            self._field_block(
                "Pumpla korpuse materjal *",
                self._required_widget(
                    "material",
                    self.material_combo,
                    "Pumpla korpuse materjal peab olema valitud.",
                    tab,
                ),
                tab,
                buddy=self.material_combo,
            ),
            1,
            0,
            1,
            2,
        )
        layout.addLayout(classification_grid)

        self._section_divider(layout)
        hydraulic_grid = QGridLayout()
        hydraulic_grid.setHorizontalSpacing(12)
        hydraulic_grid.setVerticalSpacing(10)
        hydraulic_grid.setColumnStretch(0, 1)
        hydraulic_grid.setColumnStretch(1, 1)
        self.productivity_spin = self._number(
            config.productivity,
            " l/s",
            tab,
            minimum=0.0,
            maximum=1_000_000.0,
            single_step=0.1,
        )
        hydraulic_grid.addWidget(
            self._field_block(
                "Maksimaalne tootlikkus Qmax",
                self.productivity_spin,
                tab,
            ),
            0,
            0,
        )
        self.pressure_spin = self._number(
            config.pressure_increase,
            " bar",
            tab,
            minimum=0.0,
            maximum=1_000.0,
            single_step=0.1,
        )
        hydraulic_grid.addWidget(
            self._field_block(
                "Projekteeritud rõhutõus Δp",
                self.pressure_spin,
                tab,
            ),
            0,
            1,
        )
        layout.addLayout(hydraulic_grid)

        self._section_divider(layout)
        height_grid = QGridLayout()
        height_grid.setHorizontalSpacing(12)
        for column in range(3):
            height_grid.setColumnStretch(column, 1)
        self.element_height_spin = self._number(
            config.element_height,
            " m",
            tab,
            minimum=-1_000.0,
            maximum=10_000.0,
            single_step=0.01,
        )
        height_grid.addWidget(
            self._field_block(
                "Elemendi kõrgus",
                self.element_height_spin,
                tab,
            ),
            0,
            0,
        )
        self.bottom_height_spin = self._number(
            config.bottom_height,
            " m",
            tab,
            minimum=-1_000.0,
            maximum=10_000.0,
            single_step=0.01,
        )
        height_grid.addWidget(
            self._field_block(
                "Põhja kõrgus",
                self.bottom_height_spin,
                tab,
            ),
            0,
            1,
        )
        self.ground_height_spin = self._number(
            config.ground_height,
            " m",
            tab,
            minimum=-1_000.0,
            maximum=10_000.0,
            single_step=0.01,
        )
        height_grid.addWidget(
            self._field_block(
                "Maapinna kõrgus",
                self.ground_height_spin,
                tab,
            ),
            0,
            2,
        )
        layout.addLayout(height_grid)

        self._section_divider(layout)
        self._section_header(
            layout,
            "Asukoht",
            "Katastritunnus seob pumpla kinnistuga. Selle võib jätta tühjaks.",
        )
        location_grid = QGridLayout()
        location_grid.setHorizontalSpacing(12)
        location_grid.setColumnStretch(0, 1)
        self.parcel_edit = QLineEdit(config.parcel_nr, tab)
        self.parcel_edit.setPlaceholderText("Näiteks 78401:101:1234")
        self.parcel_edit.setMaxLength(14)
        location_grid.addWidget(
            self._field_block(
                "Katastritunnus",
                self.parcel_edit,
                tab,
            ),
            0,
            0,
        )
        self.parcel_warning = QLabel(
            "Kontrolli katastritunnust. Oodatud kuju on "
            "78401:101:1234.",
            tab,
        )
        self.parcel_warning.setWordWrap(True)
        self.parcel_warning.setStyleSheet(
            "color: #9a6700; font-size: 10px;"
        )
        self.parcel_warning.setVisible(False)
        location_grid.addWidget(self.parcel_warning, 1, 0)
        layout.addLayout(location_grid)
        layout.addStretch(1)
        return scroll

    def _pumps_tab(self) -> QWidget:
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)

        intro = QLabel(
            "Halda pumplasse paigaldatud üksikpumpasid. Pumbad salvestatakse "
            "pumpla alamkirjetena ja neid ei kuvata QGIS-i kaardil.",
            tab,
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #4a5568;")
        layout.addWidget(intro)

        toolbar = QHBoxLayout()
        self.pump_add_button = QPushButton("+ Lisa pump", tab)
        self.pump_duplicate_button = QPushButton("Kopeeri", tab)
        self.pump_remove_button = QPushButton("Eemalda", tab)
        set_catalog_icon(self.pump_add_button, ICON_ADD)
        set_catalog_icon(self.pump_duplicate_button, ICON_COPY)
        set_catalog_icon(self.pump_remove_button, ICON_REMOVE)
        self.pump_add_button.setToolTip("Lisa pumplale uus pumbakirje.")
        self.pump_duplicate_button.setToolTip(
            "Loo valitud pumba andmetest uus pumbakirje."
        )
        self.pump_remove_button.setToolTip(
            "Märgi valitud pump salvestamisel eemaldatavaks."
        )
        toolbar.addWidget(self.pump_add_button)
        toolbar.addWidget(self.pump_duplicate_button)
        toolbar.addWidget(self.pump_remove_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        body = QHBoxLayout()
        body.setSpacing(12)
        self.pump_list = QListWidget(tab)
        self.pump_list.setAccessibleName("Pumpla pumbad")
        self.pump_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.pump_list.setMinimumWidth(210)
        self.pump_list.setMaximumWidth(260)
        body.addWidget(self.pump_list)

        scroll = QScrollArea(tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        form = QWidget(scroll)
        form.setObjectName("tabContent")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(4, 0, 4, 4)
        form_layout.setSpacing(8)
        self.pump_editor_title = QLabel("Vali pump", form)
        self.pump_editor_title.setStyleSheet(
            "color: #111416; font-size: 14px; font-weight: 700;"
        )
        form_layout.addWidget(self.pump_editor_title)
        self.pump_empty_label = QLabel(
            "Lisa esimene pump või vali loendist olemasolev pump.",
            form,
        )
        self.pump_empty_label.setWordWrap(True)
        self.pump_empty_label.setStyleSheet(
            "color: #57606a; background: #f9fafb; "
            "border: 1px dashed #b6c2cd; "
            "border-radius: 7px; padding: 18px;"
        )
        form_layout.addWidget(self.pump_empty_label)

        self.pump_form_widget = QWidget(form)
        pump_form_layout = QVBoxLayout(self.pump_form_widget)
        pump_form_layout.setContentsMargins(0, 0, 0, 0)
        pump_form_layout.setSpacing(8)

        identity_grid = QGridLayout()
        identity_grid.setHorizontalSpacing(12)
        identity_grid.setColumnStretch(0, 1)
        identity_grid.setColumnStretch(1, 1)
        self.pump_type_combo = self._combo(
            self.options.pump_type_options,
            None,
            self.pump_form_widget,
            placeholder="Vali pumba tüüp…",
        )
        type_wrapper = QWidget(self.pump_form_widget)
        type_layout = QVBoxLayout(type_wrapper)
        type_layout.setContentsMargins(0, 0, 0, 0)
        type_layout.setSpacing(2)
        type_layout.addWidget(self.pump_type_combo)
        self.pump_type_error = QLabel(
            "Pumba tüüp peab olema valitud.",
            type_wrapper,
        )
        self.pump_type_error.setStyleSheet(
            "color: #c53030; font-size: 10px;"
        )
        self.pump_type_error.setVisible(False)
        type_layout.addWidget(self.pump_type_error)
        identity_grid.addWidget(
            self._field_block(
                "Tööratta tüüp *",
                type_wrapper,
                self.pump_form_widget,
                buddy=self.pump_type_combo,
            ),
            0,
            0,
        )
        self.pump_install_combo = self._combo(
            self.options.pump_install_method_options,
            None,
            self.pump_form_widget,
            placeholder="Paigaldusviis määramata",
        )
        identity_grid.addWidget(
            self._field_block(
                "Paigaldusviis",
                self.pump_install_combo,
                self.pump_form_widget,
            ),
            0,
            1,
        )
        pump_form_layout.addLayout(identity_grid)

        name_grid = QGridLayout()
        name_grid.setHorizontalSpacing(12)
        name_grid.setColumnStretch(0, 1)
        name_grid.setColumnStretch(1, 1)
        self.pump_manufacturer_edit = QLineEdit(self.pump_form_widget)
        self.pump_manufacturer_edit.setMaxLength(50)
        self.pump_manufacturer_edit.setPlaceholderText("Näiteks Grundfos")
        self.pump_mark_edit = QLineEdit(self.pump_form_widget)
        self.pump_mark_edit.setMaxLength(30)
        self.pump_mark_edit.setPlaceholderText("Pumba mark või mudel")
        name_grid.addWidget(
            self._field_block(
                "Tootja",
                self.pump_manufacturer_edit,
                self.pump_form_widget,
            ),
            0,
            0,
        )
        name_grid.addWidget(
            self._field_block(
                "Mark",
                self.pump_mark_edit,
                self.pump_form_widget,
            ),
            0,
            1,
        )
        pump_form_layout.addLayout(name_grid)

        hydraulic_grid = QGridLayout()
        hydraulic_grid.setHorizontalSpacing(12)
        for column in range(3):
            hydraulic_grid.setColumnStretch(column, 1)
        self.pump_productivity_edit = OptionalNumberLineEdit(
            parent=self.pump_form_widget,
        )
        self.pump_head_edit = OptionalNumberLineEdit(
            parent=self.pump_form_widget,
        )
        self.pump_power_edit = OptionalNumberLineEdit(
            parent=self.pump_form_widget,
        )
        hydraulic_grid.addWidget(
            self._field_block(
                "Maksimaalne tootlikkus Q (l/s)",
                self.pump_productivity_edit,
                self.pump_form_widget,
            ),
            0,
            0,
        )
        hydraulic_grid.addWidget(
            self._field_block(
                "Tõstekõrgus H (m)",
                self.pump_head_edit,
                self.pump_form_widget,
            ),
            0,
            1,
        )
        hydraulic_grid.addWidget(
            self._field_block(
                "Võimsus (W)",
                self.pump_power_edit,
                self.pump_form_widget,
            ),
            0,
            2,
        )
        pump_form_layout.addLayout(hydraulic_grid)

        service_grid = QGridLayout()
        service_grid.setHorizontalSpacing(12)
        service_grid.setColumnStretch(0, 1)
        service_grid.setColumnStretch(1, 1)
        date_control = QWidget(self.pump_form_widget)
        date_layout = QHBoxLayout(date_control)
        date_layout.setContentsMargins(0, 0, 0, 0)
        self.pump_date_known = QCheckBox("Kuupäev teada", date_control)
        self.pump_date_edit = QDateEdit(QDate.currentDate(), date_control)
        self.pump_date_edit.setCalendarPopup(True)
        self.pump_date_edit.setDisplayFormat("dd.MM.yyyy")
        date_layout.addWidget(self.pump_date_known)
        date_layout.addWidget(self.pump_date_edit, 1)
        self.pump_date_edit.setEnabled(False)
        service_grid.addWidget(
            self._field_block(
                "Paigalduskuupäev",
                date_control,
                self.pump_form_widget,
                buddy=self.pump_date_known,
            ),
            0,
            0,
        )
        self.pump_running_time_spin = self._number(
            None,
            " h",
            self.pump_form_widget,
            minimum=0.0,
            maximum=1_000_000_000.0,
            single_step=1.0,
        )
        service_grid.addWidget(
            self._field_block(
                "Töötunnid",
                self.pump_running_time_spin,
                self.pump_form_widget,
            ),
            0,
            1,
        )
        pump_form_layout.addLayout(service_grid)

        connection_grid = QGridLayout()
        connection_grid.setHorizontalSpacing(12)
        for column in range(2):
            connection_grid.setColumnStretch(column, 1)
        self.pump_in_diameter_combo = self._diameter_combo(
            None,
            self.pump_form_widget,
        )
        self.pump_out_diameter_combo = self._diameter_combo(
            None,
            self.pump_form_widget,
        )
        connection_grid.addWidget(
            self._field_block(
                "Sisendi läbimõõt (DN)",
                self.pump_in_diameter_combo,
                self.pump_form_widget,
            ),
            0,
            0,
        )
        connection_grid.addWidget(
            self._field_block(
                "Väljundi läbimõõt (DN)",
                self.pump_out_diameter_combo,
                self.pump_form_widget,
            ),
            0,
            1,
        )
        pump_form_layout.addLayout(connection_grid)

        motor_grid = QGridLayout()
        motor_grid.setHorizontalSpacing(12)
        motor_grid.setColumnStretch(0, 1)
        motor_grid.setColumnStretch(1, 1)
        self.pump_current_edit = OptionalNumberLineEdit(
            parent=self.pump_form_widget,
        )
        self.pump_voltage_edit = OptionalNumberLineEdit(
            parent=self.pump_form_widget,
        )
        motor_grid.addWidget(
            self._field_block(
                "Mootori nimivool (A)",
                self.pump_current_edit,
                self.pump_form_widget,
            ),
            0,
            0,
        )
        motor_grid.addWidget(
            self._field_block(
                "Mootori nimipinge (V)",
                self.pump_voltage_edit,
                self.pump_form_widget,
            ),
            0,
            1,
        )
        pump_form_layout.addLayout(motor_grid)

        self.pump_remarks_edit = QPlainTextEdit(self.pump_form_widget)
        self.pump_remarks_edit.setPlaceholderText(
            "Pumba täpsustavad märkused"
        )
        self.pump_remarks_edit.setMaximumBlockCount(6)
        self.pump_remarks_edit.setMaximumHeight(76)
        pump_form_layout.addWidget(
            self._field_block(
                "Märkused",
                self.pump_remarks_edit,
                self.pump_form_widget,
            )
        )
        form_layout.addWidget(self.pump_form_widget)
        form_layout.addStretch(1)
        scroll.setWidget(form)
        body.addWidget(scroll, 1)
        layout.addLayout(body, 1)

        self.pump_add_button.clicked.connect(self._add_pump)
        self.pump_duplicate_button.clicked.connect(self._duplicate_pump)
        self.pump_remove_button.clicked.connect(self._remove_pump)
        self.pump_list.currentRowChanged.connect(
            self._pump_selection_changed
        )
        self.pump_date_known.toggled.connect(
            self.pump_date_edit.setEnabled
        )
        for combo in (
            self.pump_type_combo,
            self.pump_install_combo,
            self.pump_in_diameter_combo,
            self.pump_out_diameter_combo,
        ):
            combo.currentIndexChanged.connect(self._pump_editor_changed)
        for edit in (
            self.pump_manufacturer_edit,
            self.pump_mark_edit,
            self.pump_productivity_edit,
            self.pump_head_edit,
            self.pump_power_edit,
            self.pump_current_edit,
            self.pump_voltage_edit,
        ):
            edit.textChanged.connect(self._pump_editor_changed)
        self.pump_remarks_edit.textChanged.connect(
            self._pump_editor_changed
        )
        self.pump_date_known.toggled.connect(self._pump_editor_changed)
        self.pump_date_edit.dateChanged.connect(self._pump_editor_changed)
        for spin in (
            self.pump_running_time_spin,
        ):
            spin.valueChanged.connect(self._pump_editor_changed)

        self._refresh_pump_list(0 if self._pump_configs else -1)
        return tab

    def _add_pump(self) -> None:
        self._pump_configs.append(SewerPumpConfiguration())
        self._refresh_pump_list(len(self._pump_configs) - 1)
        self.pump_type_combo.setFocus(Qt.OtherFocusReason)
        self._preview_changed()

    def _duplicate_pump(self) -> None:
        row = self.pump_list.currentRow()
        if row < 0 or row >= len(self._pump_configs):
            return
        duplicate = replace(
            self._pump_configs[row],
            feature_id=None,
            record_id=None,
        )
        self._pump_configs.insert(row + 1, duplicate)
        self._refresh_pump_list(row + 1)
        self._preview_changed()

    def _remove_pump(self) -> None:
        row = self.pump_list.currentRow()
        if row < 0 or row >= len(self._pump_configs):
            return
        self._pump_configs.pop(row)
        next_row = min(row, len(self._pump_configs) - 1)
        self._refresh_pump_list(next_row)
        self._preview_changed()

    def _refresh_pump_list(self, selected_row: int) -> None:
        self._loading_pump = True
        try:
            self.pump_list.clear()
            for index, pump in enumerate(self._pump_configs):
                item = QListWidgetItem(self._pump_list_label(index, pump))
                item.setToolTip(
                    "Vali pump selle tehniliste andmete muutmiseks."
                )
                self.pump_list.addItem(item)
            if self._pump_configs:
                self.pump_list.setCurrentRow(
                    max(0, min(selected_row, len(self._pump_configs) - 1))
                )
            else:
                self.pump_list.setCurrentRow(-1)
        finally:
            self._loading_pump = False
        self._pump_selection_changed(self.pump_list.currentRow())

    def _refresh_pump_item(self, row: int) -> None:
        item = self.pump_list.item(row)
        if item is not None and 0 <= row < len(self._pump_configs):
            item.setText(
                self._pump_list_label(row, self._pump_configs[row])
            )

    def _pump_list_label(
        self,
        index: int,
        pump: SewerPumpConfiguration,
    ) -> str:
        identity = " ".join(
            value for value in (pump.manufacturer, pump.mark) if value
        )
        if not identity:
            identity = "Andmed täitmata"
        type_labels = {
            option.value: option.label
            for option in self.options.pump_type_options
        }
        type_label = type_labels.get(pump.type_id, "Tüüp valimata")
        return f"◉ Pump {index + 1}\n{identity} · {type_label}"

    def _pump_selection_changed(self, row: int) -> None:
        has_selection = 0 <= row < len(self._pump_configs)
        self.pump_duplicate_button.setEnabled(has_selection)
        self.pump_remove_button.setEnabled(has_selection)
        self.pump_form_widget.setVisible(has_selection)
        self.pump_empty_label.setVisible(not has_selection)
        self.pump_editor_title.setText(
            f"Pump {row + 1} — tehnilised andmed"
            if has_selection
            else "Pumpasid ei ole lisatud"
        )
        if not has_selection or self._loading_pump:
            return
        pump = self._pump_configs[row]
        self._loading_pump = True
        try:
            self._set_combo_value(self.pump_type_combo, pump.type_id)
            self._set_combo_value(
                self.pump_install_combo,
                pump.install_method_id,
            )
            self.pump_manufacturer_edit.setText(pump.manufacturer)
            self.pump_mark_edit.setText(pump.mark)
            self.pump_productivity_edit.set_optional_value(
                pump.productivity
            )
            self.pump_head_edit.set_optional_value(pump.pump_head)
            self.pump_power_edit.set_optional_value(pump.power_w)
            self._set_optional_number(
                self.pump_running_time_spin,
                pump.running_time,
            )
            self._populate_diameter_combo(
                self.pump_in_diameter_combo,
                pump.in_diameter,
            )
            self._populate_diameter_combo(
                self.pump_out_diameter_combo,
                pump.out_diameter,
            )
            self.pump_current_edit.set_optional_value(
                pump.engine_current
            )
            self.pump_voltage_edit.set_optional_value(
                pump.engine_voltage
            )
            self.pump_date_known.setChecked(pump.install_date is not None)
            if pump.install_date is not None:
                self.pump_date_edit.setDate(
                    QDate(
                        pump.install_date.year,
                        pump.install_date.month,
                        pump.install_date.day,
                    )
                )
            self.pump_date_edit.setEnabled(pump.install_date is not None)
            self.pump_remarks_edit.setPlainText(pump.remarks)
            self.pump_type_error.setVisible(False)
        finally:
            self._loading_pump = False

    def _pump_editor_changed(self, *_args) -> None:
        if self._loading_pump:
            return
        row = self.pump_list.currentRow()
        if row < 0 or row >= len(self._pump_configs):
            return
        current = self._pump_configs[row]
        selected_date = (
            self.pump_date_edit.date().toPyDate()
            if self.pump_date_known.isChecked()
            else None
        )
        self._pump_configs[row] = replace(
            current,
            type_id=self.pump_type_combo.currentData(),
            install_method_id=self.pump_install_combo.currentData(),
            install_date=selected_date,
            power_w=self.pump_power_edit.optional_value(),
            manufacturer=self.pump_manufacturer_edit.text().strip(),
            mark=self.pump_mark_edit.text().strip(),
            productivity=self.pump_productivity_edit.optional_value(),
            pump_head=self.pump_head_edit.optional_value(),
            running_time=self._optional_number(
                self.pump_running_time_spin
            ),
            in_diameter=self.pump_in_diameter_combo.currentData(),
            out_diameter=self.pump_out_diameter_combo.currentData(),
            engine_current=self.pump_current_edit.optional_value(),
            engine_voltage=self.pump_voltage_edit.optional_value(),
            remarks=self.pump_remarks_edit.toPlainText().strip()[:250],
        )
        self.pump_type_error.setVisible(
            not self._pump_type_is_valid(self._pump_configs[row])
        )
        self._refresh_pump_item(row)
        self._preview_changed()

    def _pump_type_is_valid(
        self,
        pump: SewerPumpConfiguration,
    ) -> bool:
        return pump.type_id in {
            option.value
            for option in self.options.pump_type_options
            if not option.label.strip().casefold().startswith("määramata")
        }

    def _pumps_valid(self, *, show_errors: bool = False) -> bool:
        invalid = [
            index
            for index, pump in enumerate(self._pump_configs)
            if not self._pump_type_is_valid(pump)
        ]
        if show_errors and invalid:
            self.pump_list.setCurrentRow(invalid[0])
            self.pump_type_error.setVisible(True)
        return not invalid

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: int | None) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(max(index, 0))

    @staticmethod
    def _set_optional_number(
        spin: NullableDoubleSpinBox,
        value: float | None,
    ) -> None:
        if value is None:
            spin.set_null()
        else:
            spin.setValue(float(value))

    def _electrical_tab(self) -> QWidget:
        config = self.state.configuration
        scroll, tab, layout = self._scrollable_form_tab()
        self._section_header(
            layout,
            "Automaatika",
            "Määra pumpla juhtimisviis generaatori lookup-valikust.",
        )
        control_grid = QGridLayout()
        control_grid.setColumnStretch(0, 1)
        self.control_combo = self._combo(
            self.options.control_options,
            config.control_id,
            tab,
            placeholder="Vali juhtimise liik…",
        )
        control_grid.addWidget(
            self._field_block(
                "Juhtimise liik *",
                self._required_widget(
                    "control",
                    self.control_combo,
                    "Pumpla juhtimise liik peab olema valitud.",
                    tab,
                ),
                tab,
                buddy=self.control_combo,
            ),
            0,
            0,
        )
        layout.addLayout(control_grid)
        self._section_header(
            layout,
            "Elektrilised näitajad",
            "Sisesta pumpla summaarne elektrivõimsus ja peakaitse "
            "läbilaskevõime.",
        )
        electrical_grid = QGridLayout()
        electrical_grid.setHorizontalSpacing(12)
        electrical_grid.setColumnStretch(0, 1)
        electrical_grid.setColumnStretch(1, 1)
        self.power_spin = self._number(
            config.power_consumption,
            " kW",
            tab,
            minimum=0.0,
            maximum=1_000_000.0,
            single_step=0.1,
        )
        electrical_grid.addWidget(
            self._field_block(
                "Elektrikoguvõimsus P",
                self.power_spin,
                tab,
            ),
            0,
            0,
        )
        self.current_spin = self._number(
            config.el_max_current,
            " A",
            tab,
            minimum=0.0,
            maximum=1_000_000.0,
            single_step=0.1,
        )
        electrical_grid.addWidget(
            self._field_block(
                "Peakaitse läbilaskevõime Imax",
                self.current_spin,
                tab,
            ),
            0,
            1,
        )
        layout.addLayout(electrical_grid)
        layout.addStretch(1)
        return scroll

    def _pipes_tab(self) -> QWidget:
        tab = QWidget(self.tabs)
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(9)
        intro = QLabel(
            "Kontrolli pumplaga ühendatud isevoolsete torude "
            "sõlmepoolseid põhjakõrgusi. Voolusuunda siin ei muudeta.",
            tab,
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #4a5568;")
        layout.addWidget(intro)
        ports = self.state.topology.ports
        if not ports:
            empty = QLabel(
                "Pumplal ei ole praegu ühtegi toruühendust.",
                tab,
            )
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                "color: #57606a; background: #f9fafb; "
                "border: 1px dashed #b6c2cd; "
                "border-radius: 7px; padding: 24px;"
            )
            layout.addWidget(empty)
            layout.addStretch(1)
            return tab

        table = QTableWidget(len(ports), 5, tab)
        table.setHorizontalHeaderLabels(
            (
                "Toru",
                "Läbimõõt",
                "Materjal",
                "Voolusuund",
                "Sõlmepoolne\npõhjakõrgus",
            )
        )
        table.setAccessibleName("Pumpla toruühendused")
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(42)
        header = table.horizontalHeader()
        header.setMinimumSectionSize(72)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        table.setColumnWidth(4, 168)
        for row, port in enumerate(ports):
            flow = (
                "↗ Väljub"
                if port.is_outgoing is True
                else "↘ Siseneb"
                if port.is_outgoing is False
                else "— Määramata"
            )
            values = (
                port.identification
                or f"Toru {port.edge_id or port.feature_id}",
                port.diameter_label or "—",
                port.material_label or "—",
                flow,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, column, item)
            pipe_name = values[0]
            height_spin = self._number(
                port.height,
                " m",
                table,
                minimum=-1_000.0,
                maximum=10_000.0,
                single_step=0.01,
            )
            height_spin.setAccessibleName(
                f"{pipe_name} sõlmepoolne põhjakõrgus"
            )
            height_spin.setToolTip(
                f"{pipe_name}: toru põhja kõrgus pumpla sõlmes. "
                "Tühjendamiseks kasuta ×-nuppu."
            )
            self.port_height_spins[port.key] = height_spin
            table.setCellWidget(row, 4, height_spin)
        visible_rows = min(len(ports), 6)
        compact_height = (
            table.horizontalHeader().sizeHint().height()
            + visible_rows * table.verticalHeader().defaultSectionSize()
            + 24
        )
        table.setMinimumHeight(compact_height)
        if len(ports) <= 6:
            table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            table.setMaximumHeight(compact_height)
            layout.addWidget(table)
            layout.addStretch(1)
        else:
            layout.addWidget(table, 1)
        return tab

    def _diameter_combo(
        self,
        selected: float | None,
        parent=None,
    ) -> QComboBox:
        combo = QComboBox(parent)
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(8)
        combo.setMinimumWidth(0)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        combo.setToolTip(
            "DN-valikud pärinevad EVEL-i "
            "SW_DUCT_DIAMETER standardkataloogist."
        )
        self._populate_diameter_combo(combo, selected)
        return combo

    def _populate_diameter_combo(
        self,
        combo: QComboBox,
        selected: float | None,
    ) -> None:
        previous = combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("Vali DN…", None)
            for value in self.options.pump_diameter_options:
                combo.addItem(f"DN {value:g}", float(value))
            index = -1
            if selected is not None:
                selected_value = float(selected)
                for candidate in range(1, combo.count()):
                    if abs(
                        float(combo.itemData(candidate)) - selected_value
                    ) < 1e-9:
                        index = candidate
                        break
                if index < 0:
                    combo.addItem(
                        f"DN {selected_value:g} · olemasolev",
                        selected_value,
                    )
                    index = combo.count() - 1
            combo.setCurrentIndex(max(index, 0))
        finally:
            combo.blockSignals(previous)

    @staticmethod
    def _combo(
        options: tuple[LookupOption, ...],
        selected: int | None,
        parent=None,
        *,
        placeholder: str = "",
    ) -> QComboBox:
        combo = QComboBox(parent)
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(8)
        combo.setMinimumWidth(0)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if placeholder:
            combo.addItem(placeholder, None)
        for option in options:
            combo.addItem(option.label, option.value)
        index = combo.findData(selected)
        if index < 0 and selected is not None:
            combo.addItem(f"Tundmatu väärtus ({selected})", selected)
            index = combo.count() - 1
        if (
            placeholder
            and index > 0
            and "määramata" in combo.itemText(index).casefold()
        ):
            index = 0
        combo.setCurrentIndex(max(index, 0))
        return combo

    @staticmethod
    def _number(
        value: float | None,
        suffix: str,
        parent=None,
        *,
        minimum: float = 0.0,
        maximum: float = 1_000_000.0,
        decimals: int = 3,
        single_step: float = 0.1,
    ) -> NullableDoubleSpinBox:
        return NullableDoubleSpinBox(
            value,
            suffix,
            valid_minimum=minimum,
            valid_maximum=maximum,
            decimals=decimals,
            single_step=single_step,
            parent=parent,
        )

    @staticmethod
    def _optional_number(spin: QDoubleSpinBox) -> float | None:
        if isinstance(spin, NullableDoubleSpinBox):
            return spin.optional_value()
        return float(spin.value())
