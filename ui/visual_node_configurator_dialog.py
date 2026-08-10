"""Interactive schematic editor for one EVEL water-node assembly."""

from __future__ import annotations

from dataclasses import dataclass
import math

from qgis.PyQt.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QFont,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..layers import (
    FacilityConfigurationOptions,
    LookupOption,
    ManholeConfigurationOptions,
)
from ..topology import (
    MAX_VALVE_DISTANCE_METERS,
    NodeAssemblyPlan,
    NodeAssemblyState,
    PortValveConfiguration,
    branch_type_is_compatible,
)
from .light_style import apply_evel_light_style
from .manhole_configurator_dialog import ManholeSectionWidget
from .facility_configurator_dialog import FacilitySectionWidget


_BRANCH_UNSPECIFIED = 522
_BRANCH_ELBOW = 523
_BRANCH_COLLAR = 524
_BRANCH_TEE = 525
_BRANCH_CROSS = 526
_BRANCH_GENERIC = 527
_BRANCH_TRANSITION = 528
_BRANCH_FLANGE = 529
_BRANCH_SADDLE = 530
_BRANCH_END_CAP = 531


@dataclass
class _VisualPortState:
    enabled: bool
    distance: float
    valve_type_id: int | None
    valve_subtype_id: int | None
    existing: bool


@dataclass
class _SchematicComponent:
    enabled: bool = False
    label: str = ""
    existing: bool = False
    distance: float = MAX_VALVE_DISTANCE_METERS
    maximum_distance: float = MAX_VALVE_DISTANCE_METERS


def valve_component_icon(label: str | None) -> QIcon:
    """Return a compact schematic icon for one valve subtype."""

    pixmap = QPixmap(36, 28)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.translate(18, 14)

    red = QColor("#d82626")
    dark_red = QColor("#8d1717")
    blue = QColor("#168dcc")
    key = label.casefold() if label is not None else ""

    if label is None:
        painter.setPen(QPen(blue, 2.4))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 9, 9)
        painter.drawLine(QPointF(-5, 0), QPointF(5, 0))
        painter.drawLine(QPointF(0, -5), QPointF(0, 5))
    elif "määramata" in key:
        painter.setPen(QPen(red, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(
            QPolygonF(
                (
                    QPointF(0, -10),
                    QPointF(11, 0),
                    QPointF(0, 10),
                    QPointF(-11, 0),
                )
            )
        )
        font = QFont(painter.font())
        font.setBold(True)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.drawText(QRectF(-8, -9, 16, 18), Qt.AlignCenter, "?")
    elif "klapp" in key:
        painter.setPen(QPen(red, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(-14, 0), QPointF(14, 0))
        painter.drawEllipse(QRectF(-9, -9, 18, 18))
        painter.drawLine(QPointF(-6, 6), QPointF(6, -6))
        painter.setBrush(red)
        painter.drawEllipse(QPointF(0, 0), 2.5, 2.5)
    elif "kuul" in key:
        painter.setPen(QPen(red, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(-15, 0), QPointF(15, 0))
        painter.drawEllipse(QRectF(-9, -9, 18, 18))
        painter.setBrush(red)
        painter.drawEllipse(QPointF(0, 0), 4, 4)
    elif "kork" in key:
        painter.setPen(QPen(red, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(-15, 0), QPointF(15, 0))
        painter.drawEllipse(QRectF(-9, -9, 18, 18))
        painter.setBrush(red)
        painter.drawPolygon(
            QPolygonF(
                (QPointF(-3, -7), QPointF(5, 0), QPointF(-3, 7))
            )
        )
    elif "vene" in key:
        painter.setPen(QPen(dark_red, 2))
        painter.drawLine(QPointF(-14, -9), QPointF(-14, 9))
        painter.drawLine(QPointF(14, -9), QPointF(14, 9))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(
            QPolygonF(
                (QPointF(-12, -8), QPointF(0, 0), QPointF(-12, 8))
            )
        )
        painter.drawPolygon(
            QPolygonF(
                (QPointF(12, -8), QPointF(0, 0), QPointF(12, 8))
            )
        )
    else:
        painter.setPen(QPen(dark_red, 1.5))
        painter.setBrush(red)
        painter.drawPolygon(
            QPolygonF(
                (QPointF(-14, -9), QPointF(0, 0), QPointF(-14, 9))
            )
        )
        painter.drawPolygon(
            QPolygonF(
                (QPointF(14, -9), QPointF(0, 0), QPointF(14, 9))
            )
        )
        if "kummi" in key:
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(QPointF(0, 0), 3.5, 3.5)

    painter.end()
    return QIcon(pixmap)


class NodeSchematicWidget(QWidget):
    """Draw actual incident-pipe bearings and clickable component slots."""

    portSelected = pyqtSignal(int)
    componentDistanceChanged = pyqtSignal(int, float)

    _MIN_DISTANCE = 0.01
    _MIN_COMPONENT_FRACTION = 0.17
    _MAX_COMPONENT_FRACTION = 0.68
    _LABEL_WIDTH = 172.0
    _LABEL_GAP = 14.0

    def __init__(self, state: NodeAssemblyState, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self._selected_port = 0
        self._hovered_port: int | None = None
        self._dragging_port: int | None = None
        self._branch_label = "Tehniline sõlm"
        self._branch_type_id: int | None = None
        self._manhole_enabled = state.manhole.enabled
        self._facility_label: str | None = None
        self._port_components: list[_SchematicComponent] = [
            _SchematicComponent() for _port in state.ports
        ]
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(440, 380)
        self.setAccessibleName("Veesõlme toruharude interaktiivne skeem")
        self.setToolTip(
            "Vali haru klõpsuga. Lisatud sulgeseadme kauguse muutmiseks "
            "lohista selle sümbolit piki toru. Roheline nool näitab määratud "
            "voolusuunda; hall kahepoolne nool tähendab, et voolusuund on "
            "määramata."
        )

    def sizeHint(self) -> QSize:
        return QSize(620, 500)

    @property
    def selected_port(self) -> int:
        return self._selected_port

    @property
    def branch_type_id(self) -> int | None:
        return self._branch_type_id

    @property
    def manhole_enabled(self) -> bool:
        return self._manhole_enabled

    @property
    def facility_label(self) -> str | None:
        return self._facility_label

    def select_port(self, index: int) -> None:
        if index < 0 or index >= len(self.state.ports):
            return
        if index == self._selected_port:
            return
        self._selected_port = index
        self.update()
        self.portSelected.emit(index)

    def set_branch_type(
        self,
        branch_type_id: int | None,
        label: str,
    ) -> None:
        self._branch_type_id = branch_type_id
        self._branch_label = label
        self.update()

    def set_manhole_enabled(self, enabled: bool) -> None:
        if self._manhole_enabled == enabled:
            return
        self._manhole_enabled = enabled
        self.update()

    def set_facility(self, label: str | None) -> None:
        if self._facility_label == label:
            return
        self._facility_label = label
        self.update()

    def set_port_component(
        self,
        index: int,
        enabled: bool,
        label: str,
        existing: bool,
        distance: float,
        maximum_distance: float,
    ) -> None:
        self._port_components[index] = _SchematicComponent(
            enabled=enabled,
            label=label,
            existing=existing,
            distance=distance,
            maximum_distance=maximum_distance,
        )
        self.update()

    def port_slot_center(self, index: int) -> QPointF:
        component = self._port_components[index]
        if component.enabled:
            return self.port_distance_point(index, component.distance)
        center, endpoint = self._arm_geometry(index)
        return center + (endpoint - center) * self._MAX_COMPONENT_FRACTION

    def port_distance_point(self, index: int, distance: float) -> QPointF:
        """Return the schematic position for a real component distance."""

        component = self._port_components[index]
        maximum = max(
            component.maximum_distance,
            self._MIN_DISTANCE,
        )
        if maximum <= self._MIN_DISTANCE:
            ratio = 1.0
        else:
            ratio = (
                min(max(distance, self._MIN_DISTANCE), maximum)
                - self._MIN_DISTANCE
            ) / (maximum - self._MIN_DISTANCE)
        fraction = self._MIN_COMPONENT_FRACTION + ratio * (
            self._MAX_COMPONENT_FRACTION - self._MIN_COMPONENT_FRACTION
        )
        center, endpoint = self._arm_geometry(index)
        return center + (endpoint - center) * fraction

    def port_endpoint(self, index: int) -> QPointF:
        return self._arm_geometry(index)[1]

    def port_label_rect(self, index: int) -> QRectF:
        """Return the laid-out callout rectangle for one pipe arm."""

        return QRectF(self._label_layout()[index])

    def port_flow_outward(self, index: int) -> bool | None:
        """Return flow relative to the configured node, if explicitly known."""

        port = self.state.ports[index]
        value = port.flow_direction
        if value is None or abs(value) <= 1e-9:
            return None
        along_geometry = value > 0
        return (
            along_geometry
            if port.central_at_start
            else not along_geometry
        )

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))

        for index, port in enumerate(self.state.ports):
            center, endpoint = self._arm_geometry(index)
            selected = index == self._selected_port
            hovered = index == self._hovered_port
            if selected or hovered:
                painter.setPen(
                    QPen(
                        QColor("#ffb300"),
                        10 if selected else 7,
                        Qt.SolidLine,
                    )
                )
                painter.drawLine(center, endpoint)
            painter.setPen(
                QPen(QColor("#168dcc"), 5, Qt.SolidLine, Qt.RoundCap)
            )
            painter.drawLine(center, endpoint)
            self._draw_flow_direction(painter, index, center, endpoint)

            slot = self.port_slot_center(index)
            component = self._port_components[index]
            if component.enabled:
                self._draw_valve(
                    painter, slot, port.bearing, component.existing
                )
                if selected:
                    self._draw_distance_label(
                        painter, slot, component.distance
                    )
            else:
                self._draw_empty_slot(painter, slot, selected)

        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        self._draw_manhole(painter, center)
        self._draw_facility(painter, center)
        self._draw_central_fitting(painter, center)
        painter.setPen(QColor("#24292e"))
        bold = QFont(painter.font())
        bold.setBold(True)
        painter.setFont(bold)
        label_rect = QRectF(center.x() - 105, center.y() + 18, 210, 52)
        center_label = self._branch_label
        if self._facility_label:
            center_label += f"\n{self._facility_label}"
        painter.drawText(
            label_rect, Qt.AlignHCenter | Qt.AlignTop, center_label
        )

        painter.setFont(self.font())
        painter.setPen(QColor("#b6c2cd"))
        painter.drawText(
            QRectF(14, 10, max(self.width() - 28, 180), 24),
            Qt.AlignLeft | Qt.AlignVCenter,
            "N ↑  •  tegelikud suunad     → vool     ↔ määramata",
        )

        label_rects = self._label_layout()
        for index, port in enumerate(self.state.ports):
            self._draw_port_label(
                painter,
                self.port_endpoint(index),
                label_rects[index],
                port.label,
                port.technical_parameters,
                self._flow_label(index),
                index == self._selected_port,
            )
        painter.end()

    def _draw_manhole(
        self,
        painter: QPainter,
        center: QPointF,
    ) -> None:
        if not self._manhole_enabled:
            return
        painter.save()
        color = QColor("#4f6f7a")
        fill = QColor(color)
        fill.setAlpha(38)
        painter.setPen(QPen(color, 3, Qt.SolidLine))
        painter.setBrush(fill)
        painter.drawEllipse(center, 34, 34)
        painter.setPen(QPen(color, 1.5, Qt.DashLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, 27, 27)
        painter.restore()

    def _draw_facility(
        self,
        painter: QPainter,
        center: QPointF,
    ) -> None:
        label = self._facility_label
        if not label:
            return
        key = label.casefold()
        painter.save()
        color = QColor("#7a3db8")
        fill = QColor(color)
        fill.setAlpha(35)
        painter.setPen(QPen(color, 2.5))
        painter.setBrush(fill)
        if "puurkaev" in key or "veeallik" in key:
            painter.drawEllipse(center, 25, 25)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, 17, 17)
            painter.drawLine(
                center + QPointF(-12, 4),
                center + QPointF(12, 4),
            )
        elif "töötlus" in key:
            polygon = QPolygonF(
                (
                    center + QPointF(-26, -15),
                    center + QPointF(0, -27),
                    center + QPointF(26, -15),
                    center + QPointF(26, 17),
                    center + QPointF(-26, 17),
                )
            )
            painter.drawPolygon(polygon)
        else:
            painter.drawRoundedRect(
                QRectF(center.x() - 28, center.y() - 22, 56, 44),
                6,
                6,
            )
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, 12, 12)
        painter.restore()

    def _draw_central_fitting(
        self,
        painter: QPainter,
        center: QPointF,
    ) -> None:
        branch_type_id = self._branch_type_id
        red = QColor("#d82626")
        painter.save()

        if branch_type_id is None:
            painter.setPen(QPen(QColor("#b6c2cd"), 2, Qt.DashLine))
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(center, 8, 8)
            painter.restore()
            return

        if branch_type_id == _BRANCH_UNSPECIFIED:
            painter.setPen(QPen(red, 2.5))
            painter.setBrush(QColor("#ffffff"))
            painter.drawPolygon(
                QPolygonF(
                    (
                        center + QPointF(0, -10),
                        center + QPointF(10, 0),
                        center + QPointF(0, 10),
                        center + QPointF(-10, 0),
                    )
                )
            )
            font = QFont(painter.font())
            font.setBold(True)
            font.setPixelSize(12)
            painter.setFont(font)
            painter.drawText(
                QRectF(center.x() - 7, center.y() - 8, 14, 16),
                Qt.AlignCenter,
                "?",
            )
            painter.restore()
            return

        painter.setPen(QPen(red, 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for port in self.state.ports:
            direction = self._bearing_vector(port.bearing)
            painter.drawLine(center, center + direction * 19.0)

        if branch_type_id == _BRANCH_END_CAP and self.state.ports:
            direction = self._bearing_vector(self.state.ports[0].bearing)
            perpendicular = QPointF(-direction.y(), direction.x())
            painter.setPen(QPen(red, 3.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(
                center - perpendicular * 10.0,
                center + perpendicular * 10.0,
            )
        elif branch_type_id in {_BRANCH_COLLAR, _BRANCH_FLANGE}:
            width = 11.0 if branch_type_id == _BRANCH_FLANGE else 8.0
            self._draw_fitting_bars(painter, center, width)
        elif branch_type_id == _BRANCH_TRANSITION and self.state.ports:
            direction = self._bearing_vector(self.state.ports[0].bearing)
            perpendicular = QPointF(-direction.y(), direction.x())
            painter.setPen(QPen(red, 2))
            painter.setBrush(QColor("#ffffff"))
            painter.drawPolygon(
                QPolygonF(
                    (
                        center - direction * 7.0 - perpendicular * 7.0,
                        center - direction * 7.0 + perpendicular * 7.0,
                        center + direction * 7.0 + perpendicular * 4.0,
                        center + direction * 7.0 - perpendicular * 4.0,
                    )
                )
            )
        elif branch_type_id == _BRANCH_SADDLE:
            painter.setPen(QPen(red, 2.5))
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(center, 8, 8)
        elif branch_type_id == _BRANCH_GENERIC:
            painter.setPen(QPen(red, 2.5))
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(center, 6, 6)
        elif branch_type_id in {
            _BRANCH_ELBOW,
            _BRANCH_TEE,
            _BRANCH_CROSS,
        }:
            painter.setPen(QPen(red, 2))
            painter.setBrush(red)
            painter.drawEllipse(center, 4, 4)
        else:
            painter.setPen(QPen(red, 2.5))
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(center, 6, 6)

        painter.restore()

    def _draw_fitting_bars(
        self,
        painter: QPainter,
        center: QPointF,
        half_width: float,
    ) -> None:
        if not self.state.ports:
            return
        direction = self._bearing_vector(self.state.ports[0].bearing)
        perpendicular = QPointF(-direction.y(), direction.x())
        painter.setPen(QPen(QColor("#d82626"), 2.5, Qt.SolidLine))
        for offset in (-4.0, 4.0):
            bar_center = center + direction * offset
            painter.drawLine(
                bar_center - perpendicular * half_width,
                bar_center + perpendicular * half_width,
            )

    @staticmethod
    def _bearing_vector(bearing: float) -> QPointF:
        radians = math.radians(bearing)
        return QPointF(math.sin(radians), -math.cos(radians))

    def _draw_flow_direction(
        self,
        painter: QPainter,
        index: int,
        center: QPointF,
        endpoint: QPointF,
    ) -> None:
        direction = self._bearing_vector(self.state.ports[index].bearing)
        perpendicular = QPointF(-direction.y(), direction.x())
        arrow_center = (
            center
            + (endpoint - center) * 0.82
            + perpendicular * 11.0
        )
        flow_outward = self.port_flow_outward(index)

        painter.save()
        if flow_outward is None:
            color = QColor("#b6c2cd")
            painter.setPen(
                QPen(color, 2, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin)
            )
            start = arrow_center - direction * 10.0
            end = arrow_center + direction * 10.0
            painter.drawLine(start, end)
            self._draw_arrow_head(painter, end, direction, color)
            self._draw_arrow_head(painter, start, -direction, color)
        else:
            color = QColor("#24a148")
            arrow_direction = direction if flow_outward else -direction
            painter.setPen(
                QPen(color, 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            )
            start = arrow_center - arrow_direction * 12.0
            end = arrow_center + arrow_direction * 12.0
            painter.drawLine(start, end)
            self._draw_arrow_head(
                painter,
                end,
                arrow_direction,
                color,
            )
        painter.restore()

    @staticmethod
    def _draw_arrow_head(
        painter: QPainter,
        tip: QPointF,
        direction: QPointF,
        color: QColor,
    ) -> None:
        perpendicular = QPointF(-direction.y(), direction.x())
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(color)
        painter.drawPolygon(
            QPolygonF(
                (
                    tip,
                    tip - direction * 7.0 + perpendicular * 4.5,
                    tip - direction * 7.0 - perpendicular * 4.5,
                )
            )
        )

    def _flow_label(self, index: int) -> str:
        flow_outward = self.port_flow_outward(index)
        if flow_outward is None:
            return "Vool: määramata"
        if flow_outward:
            return "Vool: sõlmest välja"
        return "Vool: sõlme suunas"

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton:
            return
        component_index = self._component_at(event.pos())
        if component_index is not None:
            self.select_port(component_index)
            self._dragging_port = component_index
            self.setCursor(Qt.ClosedHandCursor)
            self._drag_component(event.pos())
            event.accept()
            return
        index = self._port_at(event.pos())
        if index is not None:
            self.select_port(index)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging_port is not None:
            self._drag_component(event.pos())
            return
        hovered = self._port_at(event.pos())
        if hovered != self._hovered_port:
            self._hovered_port = hovered
            if hovered is not None and self._component_at(event.pos()) is not None:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._dragging_port is not None:
            self._drag_component(event.pos())
            self._dragging_port = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._hovered_port = None
        if self._dragging_port is None:
            self.setCursor(Qt.PointingHandCursor)
            self.update()

    def _arm_geometry(self, index: int) -> tuple[QPointF, QPointF]:
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        direction = self._bearing_vector(self.state.ports[index].bearing)
        bounds = self._label_bounds()
        half_width = self._LABEL_WIDTH / 2.0
        half_height = self._label_height(index) / 2.0
        maximum_center_distances: list[float] = []
        if direction.x() > 1e-9:
            maximum_center_distances.append(
                (bounds.right() - half_width - center.x()) / direction.x()
            )
        elif direction.x() < -1e-9:
            maximum_center_distances.append(
                (center.x() - bounds.left() - half_width) / -direction.x()
            )
        if direction.y() > 1e-9:
            maximum_center_distances.append(
                (bounds.bottom() - half_height - center.y()) / direction.y()
            )
        elif direction.y() < -1e-9:
            maximum_center_distances.append(
                (center.y() - bounds.top() - half_height) / -direction.y()
            )

        projected_half_size = (
            abs(direction.x()) * half_width
            + abs(direction.y()) * half_height
        )
        maximum_center_distance = min(maximum_center_distances)
        radius = maximum_center_distance - projected_half_size - self._LABEL_GAP
        radius = min(max(radius, 72.0), 180.0)
        return center, center + direction * radius

    def _port_at(self, point) -> int | None:
        mouse = QPointF(point)
        nearest: tuple[float, int] | None = None
        label_rects = self._label_layout()
        for index in range(len(self.state.ports)):
            if label_rects[index].contains(mouse):
                return index
            center, endpoint = self._arm_geometry(index)
            slot = self.port_slot_center(index)
            slot_distance = math.hypot(
                mouse.x() - slot.x(), mouse.y() - slot.y()
            )
            line_distance = self._segment_distance(mouse, center, endpoint)
            distance = min(slot_distance, line_distance)
            if distance <= 22 and (
                nearest is None or distance < nearest[0]
            ):
                nearest = (distance, index)
        return nearest[1] if nearest is not None else None

    def _label_height(self, index: int) -> float:
        return (
            86.0
            if self.state.ports[index].technical_parameters
            else 68.0
        )

    def _label_bounds(self) -> QRectF:
        return QRectF(
            10.0,
            38.0,
            max(float(self.width()) - 20.0, 1.0),
            max(float(self.height()) - 48.0, 1.0),
        )

    def _preferred_label_rect(self, index: int) -> QRectF:
        center, endpoint = self._arm_geometry(index)
        direction = self._bearing_vector(self.state.ports[index].bearing)
        half_width = self._LABEL_WIDTH / 2.0
        half_height = self._label_height(index) / 2.0
        projected_half_size = (
            abs(direction.x()) * half_width
            + abs(direction.y()) * half_height
        )
        label_center = (
            endpoint
            + direction * (projected_half_size + self._LABEL_GAP)
        )
        return QRectF(
            label_center.x() - half_width,
            label_center.y() - half_height,
            self._LABEL_WIDTH,
            self._label_height(index),
        )

    def _label_layout(self) -> list[QRectF]:
        bounds = self._label_bounds()
        placed: list[QRectF] = []
        for index, port in enumerate(self.state.ports):
            preferred = self._preferred_label_rect(index)
            direction = self._bearing_vector(port.bearing)
            perpendicular = QPointF(-direction.y(), direction.x())
            best_rect: QRectF | None = None
            best_score: float | None = None
            for offset in (0.0, 96.0, -96.0, 192.0, -192.0):
                candidate = QRectF(preferred)
                candidate.translate(perpendicular * offset)
                unclamped_center = candidate.center()
                candidate = self._clamp_rect(candidate, bounds)
                clamp_distance = math.hypot(
                    candidate.center().x() - unclamped_center.x(),
                    candidate.center().y() - unclamped_center.y(),
                )
                overlap_area = 0.0
                for existing in placed:
                    overlap = candidate.intersected(
                        existing.adjusted(-6, -6, 6, 6)
                    )
                    if not overlap.isEmpty():
                        overlap_area += overlap.width() * overlap.height()
                score = (
                    overlap_area * 1000.0
                    + abs(offset)
                    + clamp_distance * 4.0
                )
                if best_score is None or score < best_score:
                    best_score = score
                    best_rect = candidate
            placed.append(best_rect if best_rect is not None else preferred)
        return placed

    @staticmethod
    def _clamp_rect(rect: QRectF, bounds: QRectF) -> QRectF:
        clamped = QRectF(rect)
        if clamped.width() >= bounds.width():
            clamped.moveLeft(bounds.left())
        else:
            if clamped.left() < bounds.left():
                clamped.moveLeft(bounds.left())
            if clamped.right() > bounds.right():
                clamped.moveRight(bounds.right())
        if clamped.height() >= bounds.height():
            clamped.moveTop(bounds.top())
        else:
            if clamped.top() < bounds.top():
                clamped.moveTop(bounds.top())
            if clamped.bottom() > bounds.bottom():
                clamped.moveBottom(bounds.bottom())
        return clamped

    def _component_at(self, point) -> int | None:
        mouse = QPointF(point)
        nearest: tuple[float, int] | None = None
        for index, component in enumerate(self._port_components):
            if not component.enabled:
                continue
            slot = self.port_slot_center(index)
            distance = math.hypot(
                mouse.x() - slot.x(), mouse.y() - slot.y()
            )
            if distance <= 24 and (
                nearest is None or distance < nearest[0]
            ):
                nearest = (distance, index)
        return nearest[1] if nearest is not None else None

    def _drag_component(self, point) -> None:
        index = self._dragging_port
        if index is None:
            return
        component = self._port_components[index]
        center, endpoint = self._arm_geometry(index)
        mouse = QPointF(point)
        delta_x = endpoint.x() - center.x()
        delta_y = endpoint.y() - center.y()
        denominator = delta_x * delta_x + delta_y * delta_y
        if denominator <= 1e-12:
            return
        fraction = (
            (mouse.x() - center.x()) * delta_x
            + (mouse.y() - center.y()) * delta_y
        ) / denominator
        ratio = (
            fraction - self._MIN_COMPONENT_FRACTION
        ) / (
            self._MAX_COMPONENT_FRACTION
            - self._MIN_COMPONENT_FRACTION
        )
        ratio = min(max(ratio, 0.0), 1.0)
        maximum = max(component.maximum_distance, self._MIN_DISTANCE)
        distance = self._MIN_DISTANCE + ratio * (
            maximum - self._MIN_DISTANCE
        )
        distance = round(distance, 2)
        if abs(distance - component.distance) <= 1e-9:
            return
        component.distance = distance
        self.update()
        self.componentDistanceChanged.emit(index, distance)

    @staticmethod
    def _segment_distance(
        point: QPointF, start: QPointF, end: QPointF
    ) -> float:
        delta_x = end.x() - start.x()
        delta_y = end.y() - start.y()
        denominator = delta_x * delta_x + delta_y * delta_y
        if denominator <= 1e-12:
            return math.hypot(point.x() - start.x(), point.y() - start.y())
        ratio = (
            (point.x() - start.x()) * delta_x
            + (point.y() - start.y()) * delta_y
        ) / denominator
        ratio = min(max(ratio, 0.0), 1.0)
        nearest_x = start.x() + ratio * delta_x
        nearest_y = start.y() + ratio * delta_y
        return math.hypot(point.x() - nearest_x, point.y() - nearest_y)

    def _draw_empty_slot(
        self, painter: QPainter, center: QPointF, selected: bool
    ) -> None:
        color = QColor("#ffb300") if selected else QColor("#168dcc")
        painter.setPen(QPen(color, 3))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(center, 14, 14)
        painter.drawLine(center + QPointF(-6, 0), center + QPointF(6, 0))
        painter.drawLine(center + QPointF(0, -6), center + QPointF(0, 6))

    @staticmethod
    def _draw_valve(
        painter: QPainter,
        center: QPointF,
        bearing: float,
        existing: bool,
    ) -> None:
        painter.save()
        painter.translate(center)
        painter.rotate(bearing - 90.0)
        color = QColor("#24a148") if existing else QColor("#d82626")
        painter.setPen(QPen(color, 2))
        painter.setBrush(color)
        painter.drawPolygon(
            QPolygonF(
                (QPointF(-15, -10), QPointF(0, 0), QPointF(-15, 10))
            )
        )
        painter.drawPolygon(
            QPolygonF(
                (QPointF(15, -10), QPointF(0, 0), QPointF(15, 10))
            )
        )
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 3, 3)
        painter.restore()

    def _draw_distance_label(
        self,
        painter: QPainter,
        center: QPointF,
        distance: float,
    ) -> None:
        text = f"{distance:.2f} m"
        rect = QRectF(center.x() + 13, center.y() - 30, 62, 24)
        painter.setPen(QPen(QColor("#ffb300"), 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor("#24292e"))
        painter.drawText(rect, Qt.AlignCenter, text)

    def _draw_port_label(
        self,
        painter: QPainter,
        endpoint: QPointF,
        rect: QRectF,
        label: str,
        technical_parameters: tuple[str, ...],
        flow_label: str,
        selected: bool,
    ) -> None:
        parts = [part.strip() for part in label.split("•")]
        lines = [parts[0]]
        if technical_parameters:
            lines.append(" • ".join(technical_parameters))
        if len(parts) > 1:
            lines.append(parts[-1])
        lines.append(flow_label)
        text = "\n".join(lines)

        painter.save()
        border_color = (
            QColor("#ffb300")
            if selected
            else QColor("#edf2f6")
        )
        anchor = QPointF(
            min(max(endpoint.x(), rect.left()), rect.right()),
            min(max(endpoint.y(), rect.top()), rect.bottom()),
        )
        painter.setPen(
            QPen(
                border_color,
                2 if selected else 1,
                Qt.DashLine,
            )
        )
        painter.drawLine(endpoint, anchor)
        painter.setPen(
            QPen(
                border_color,
                2 if selected else 1,
            )
        )
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(
            QColor("#d47b00") if selected else QColor("#24292e")
        )
        font = QFont(painter.font())
        font.setBold(selected)
        painter.setFont(font)
        painter.drawText(
            rect.adjusted(6, 4, -6, -4),
            Qt.AlignCenter | Qt.TextWordWrap,
            text,
        )
        painter.restore()


class VisualNodeConfiguratorDialog(QDialog):
    """Configure a node by selecting real pipe arms on a schematic."""

    _SUGGESTED_BRANCH_LABELS = {
        1: "otsakork",
        3: "kolmik",
        4: "nelik",
    }

    def __init__(
        self,
        state: NodeAssemblyState,
        branch_options: tuple[LookupOption, ...],
        valve_options: tuple[LookupOption, ...],
        valve_subtype_options: tuple[LookupOption, ...],
        valve_default_type_id: int,
        valve_default_subtype_id: int,
        manhole_options: ManholeConfigurationOptions,
        facility_options: FacilityConfigurationOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("evelVisualNodeConfiguratorDialog")
        apply_evel_light_style(self)
        self.state = state
        self.branch_options = branch_options
        self.valve_options = valve_options
        self.valve_subtype_options = valve_subtype_options
        self.valve_default_type_id = valve_default_type_id
        self.valve_default_subtype_id = valve_default_subtype_id
        self.manhole_options = manhole_options
        self.facility_options = facility_options
        self._selected_port = 0
        self._loading_port = False
        self._port_states = [
            self._initial_port_state(port) for port in state.ports
        ]
        self._component_buttons: dict[int | None, QToolButton] = {}

        self.setWindowTitle(
            f"Veesõlme {state.node_id} visuaalne konfiguraator"
        )
        self.setModal(True)
        self.resize(1040, 800)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Vali skeemilt toruharu ning klõpsa komponendil, mille soovid "
            "sellele harule lisada. Skeemi harud järgivad torude tegelikke "
            "suundi kaardil. Kauguse muutmiseks lohista lisatud komponenti "
            "piki toru."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        fitting_row = QHBoxLayout()
        fitting_row.addWidget(QLabel("Keskne liitmik"))
        self.branch_combo = QComboBox(self)
        self.branch_combo.addItem(
            "Tehniline sõlm (liitmiku detailita)", None
        )
        for option in branch_options:
            if branch_type_is_compatible(
                option.value, len(state.ports)
            ):
                self.branch_combo.addItem(option.label, option.value)
        self._select_branch_type()
        fitting_row.addWidget(self.branch_combo, 1)
        root.addLayout(fitting_row)
        self.branch_hint = QLabel(self._branch_hint_text(), self)
        self.branch_hint.setWordWrap(True)
        if not branch_type_is_compatible(
            state.branch_type_id, len(state.ports)
        ):
            self.branch_hint.setStyleSheet("color: #9a6700;")
        else:
            self.branch_hint.setStyleSheet("color: #57606a;")
        root.addWidget(self.branch_hint)

        body = QHBoxLayout()
        self.schematic = NodeSchematicWidget(state, self)
        schematic_frame = QFrame(self)
        schematic_frame.setFrameShape(QFrame.StyledPanel)
        schematic_layout = QVBoxLayout(schematic_frame)
        schematic_layout.setContentsMargins(0, 0, 0, 0)
        schematic_layout.addWidget(self.schematic)
        body.addWidget(schematic_frame, 3)

        editor = QWidget(self)
        editor.setObjectName("lightSurface")
        editor.setMinimumWidth(310)
        editor.setMaximumWidth(390)
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        self.facility_section = None
        if facility_options is not None:
            self.facility_section = FacilitySectionWidget(
                state.facility,
                state.node_network_id,
                facility_options,
                "Sõlme rajatis",
                editor,
            )
            editor_layout.addWidget(self.facility_section)

        self.manhole_section = ManholeSectionWidget(
            state.manhole,
            manhole_options,
            "Sõlm kaevus",
            editor,
        )
        editor_layout.addWidget(self.manhole_section)

        selected_group = QGroupBox("1. Valitud toruharu", editor)
        selected_layout = QVBoxLayout(selected_group)
        self.port_label = QLabel(selected_group)
        self.port_label.setWordWrap(True)
        selected_layout.addWidget(self.port_label)
        hint = QLabel(
            "Haru vahetamiseks klõpsa skeemil torul või komponendipesal."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #57606a;")
        selected_layout.addWidget(hint)
        editor_layout.addWidget(selected_group)

        component_group = QGroupBox(
            "2. Klõpsa lisatav komponent", editor
        )
        component_layout = QGridLayout(component_group)
        component_layout.setColumnStretch(0, 1)
        component_layout.setColumnStretch(1, 1)
        self.component_group = QButtonGroup(self)
        self.component_group.setExclusive(True)
        component_options: list[tuple[int | None, str]] = [
            (None, "＋ Ilma seadmeta")
        ] + [
            (option.value, option.label)
            for option in valve_subtype_options
        ]
        for index, (subtype_id, label) in enumerate(component_options):
            button = QToolButton(component_group)
            button.setText(label)
            button.setIcon(
                valve_component_icon(
                    label if subtype_id is not None else None
                )
            )
            button.setIconSize(QSize(30, 24))
            button.setCheckable(True)
            button.setMinimumHeight(44)
            button.setMinimumWidth(138)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.setToolTip(
                "Eemalda uue seadme valik valitud toruharult."
                if subtype_id is None
                else f"Lisa valitud toruharule: {label}."
            )
            button.setAccessibleName(
                "Ilma sulgeseadmeta"
                if subtype_id is None
                else f"Sulgeseade {label}"
            )
            button.setStyleSheet(
                "QToolButton { padding: 7px; border: 1px solid #d0d7de; "
                "border-radius: 6px; background: #ffffff; color: #24292e; } "
                "QToolButton:hover { border-color: #2188ff; "
                "background: #f0f4f8; } "
                "QToolButton:checked { background: #0078d4; color: white; "
                "border: 2px solid #005a9e; }"
            )
            button.clicked.connect(
                lambda checked, value=subtype_id: self._component_selected(
                    value, checked
                )
            )
            self.component_group.addButton(button)
            self._component_buttons[subtype_id] = button
            component_layout.addWidget(button, index // 2, index % 2)
        editor_layout.addWidget(component_group)

        properties_group = QGroupBox("3. Komponendi omadused", editor)
        properties_layout = QGridLayout(properties_group)
        properties_layout.addWidget(QLabel("Kasutuskoht"), 0, 0)
        self.valve_type_combo = QComboBox(properties_group)
        for option in valve_options:
            self.valve_type_combo.addItem(option.label, option.value)
        properties_layout.addWidget(self.valve_type_combo, 0, 1)
        properties_layout.addWidget(QLabel("Kaugus sõlmest"), 1, 0)
        self.distance_spin = QDoubleSpinBox(properties_group)
        self.distance_spin.setDecimals(2)
        self.distance_spin.setSuffix(" m")
        self.distance_spin.setSingleStep(0.01)
        self.distance_spin.setMinimum(0.01)
        self.distance_spin.setToolTip(
            "Sulgeseade võib paikneda kesksest sõlmest kuni 0,30 m "
            "kaugusel."
        )
        properties_layout.addWidget(self.distance_spin, 1, 1)
        editor_layout.addWidget(properties_group)

        editor_layout.addStretch(1)
        editor.setMinimumHeight(520)
        editor_scroll = QScrollArea(self)
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.NoFrame)
        editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        editor_scroll.setWidget(editor)
        editor_scroll.setMinimumWidth(330)
        editor_scroll.setMaximumWidth(410)
        body.addWidget(editor_scroll, 2)
        root.addLayout(body, 1)

        note = QLabel(
            "Roheline sümbol tähistab olemasolevat sulgeseadet. Selle tüüpi "
            "ja kaugust saab muuta, kuid eemaldamine ei kuulu veel sellesse "
            "versiooni."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #57606a;")
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.button(QDialogButtonBox.Save).setText("Rakenda")
        buttons.button(QDialogButtonBox.Cancel).setText("Loobu")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.schematic.portSelected.connect(self._load_port)
        self.schematic.componentDistanceChanged.connect(
            self._schematic_distance_changed
        )
        self.branch_combo.currentIndexChanged.connect(
            self._branch_selection_changed
        )
        self.valve_type_combo.currentIndexChanged.connect(
            self._type_changed
        )
        self.distance_spin.valueChanged.connect(self._distance_changed)
        self.manhole_section.configurationChanged.connect(
            lambda configuration: self.schematic.set_manhole_enabled(
                configuration.enabled
            )
        )
        if self.facility_section is not None:
            self.facility_section.configurationChanged.connect(
                self._facility_changed
            )
        self._branch_selection_changed(self.branch_combo.currentIndex())
        if self.facility_section is not None:
            self._facility_changed(
                self.facility_section.configuration()
            )
        self._refresh_all_components()
        self._load_port(0)

    def configuration(self) -> NodeAssemblyPlan:
        ports = tuple(
            PortValveConfiguration(
                port=port,
                enabled=editor.enabled,
                distance=editor.distance,
                valve_type_id=editor.valve_type_id,
                valve_subtype_id=editor.valve_subtype_id,
            )
            for port, editor in zip(
                self.state.ports, self._port_states, strict=True
            )
        )
        return NodeAssemblyPlan(
            state=self.state,
            branch_type_id=self.branch_combo.currentData(),
            ports=ports,
            manhole=self.manhole_section.configuration(),
            facility=(
                self.facility_section.configuration()
                if self.facility_section is not None
                else self.state.facility
            ),
        )

    def _facility_changed(self, configuration) -> None:
        label = None
        if (
            configuration.variant_key is not None
            and self.facility_options is not None
        ):
            label = next(
                (
                    variant.label
                    for variant in self.facility_options.variants
                    if variant.key == configuration.variant_key
                ),
                None,
            )
        self.schematic.set_facility(label)

    def select_port(self, index: int) -> None:
        """Select a port from code or accessibility tooling."""

        if index == self.schematic.selected_port:
            self._load_port(index)
        else:
            self.schematic.select_port(index)

    def _initial_port_state(self, port) -> _VisualPortState:
        existing = port.existing_valve_detail_feature_id is not None
        maximum = self._maximum_distance(port, existing)
        return _VisualPortState(
            enabled=existing,
            distance=(
                min(
                    max(port.length, 0.01),
                    MAX_VALVE_DISTANCE_METERS,
                )
                if existing
                else maximum
            ),
            valve_type_id=(
                port.existing_valve_type_id
                if existing
                else self.valve_default_type_id
            ),
            valve_subtype_id=(
                port.existing_valve_subtype_id
                if existing
                else self.valve_default_subtype_id
            ),
            existing=existing,
        )

    @staticmethod
    def _maximum_distance(port, existing: bool) -> float:
        maximum = MAX_VALVE_DISTANCE_METERS
        if not existing:
            maximum = min(
                maximum, max(port.length - 0.01, 0.01)
            )
        return max(maximum, 0.01)

    def _select_branch_type(self) -> None:
        selected = self.state.branch_type_id
        if not branch_type_is_compatible(
            selected, len(self.state.ports)
        ):
            selected = None
        if selected is None:
            suggestion = self._SUGGESTED_BRANCH_LABELS.get(
                len(self.state.ports)
            )
            if suggestion is not None:
                for option in self.branch_options:
                    if suggestion in option.label.casefold():
                        selected = option.value
                        break
        index = self.branch_combo.findData(selected)
        self.branch_combo.setCurrentIndex(max(index, 0))

    def _branch_hint_text(self) -> str:
        port_count = len(self.state.ports)
        labels = [
            option.label
            for option in self.branch_options
            if branch_type_is_compatible(option.value, port_count)
        ]
        available = ", ".join(labels) if labels else "detailivalik puudub"
        current = self.state.branch_type_id
        if not branch_type_is_compatible(current, port_count):
            current_label = next(
                (
                    option.label
                    for option in self.branch_options
                    if option.value == current
                ),
                str(current),
            )
            return (
                f"Olemasolev „{current_label}“ ei sobi {port_count} "
                "toruharuga. Vali sobiv detail."
            )
        return (
            f"Sõlmel on {port_count} toruharu. Saadaval on tehniline sõlm "
            f"või: {available}."
        )

    def _load_port(self, index: int) -> None:
        if index < 0 or index >= len(self._port_states):
            return
        self._selected_port = index
        editor = self._port_states[index]
        port = self.state.ports[index]
        self._loading_port = True
        try:
            self.port_label.setText(f"<b>{port.label}</b>")
            self.distance_spin.setMaximum(
                self._maximum_distance(port, editor.existing)
            )
            self.distance_spin.setValue(editor.distance)
            type_index = self.valve_type_combo.findData(
                editor.valve_type_id
            )
            self.valve_type_combo.setCurrentIndex(max(type_index, 0))
            subtype = editor.valve_subtype_id if editor.enabled else None
            button = self._component_buttons.get(subtype)
            if button is not None:
                button.setChecked(True)
            self._component_buttons[None].setEnabled(not editor.existing)
            self.distance_spin.setEnabled(editor.enabled)
            self.valve_type_combo.setEnabled(editor.enabled)
        finally:
            self._loading_port = False

    def _component_selected(
        self, subtype_id: int | None, checked: bool
    ) -> None:
        if self._loading_port or not checked:
            return
        editor = self._port_states[self._selected_port]
        if subtype_id is None and editor.existing:
            current = self._component_buttons.get(
                editor.valve_subtype_id
            )
            if current is not None:
                current.setChecked(True)
            return
        editor.enabled = subtype_id is not None
        if subtype_id is not None:
            editor.valve_subtype_id = subtype_id
        self.distance_spin.setEnabled(editor.enabled)
        self.valve_type_combo.setEnabled(editor.enabled)
        self._refresh_component(self._selected_port)

    def _type_changed(self, _index: int) -> None:
        if self._loading_port:
            return
        self._port_states[
            self._selected_port
        ].valve_type_id = self.valve_type_combo.currentData()

    def _distance_changed(self, value: float) -> None:
        if self._loading_port:
            return
        self._port_states[self._selected_port].distance = value
        self._refresh_component(self._selected_port)

    def _schematic_distance_changed(
        self, index: int, value: float
    ) -> None:
        self._port_states[index].distance = value
        if index == self._selected_port:
            self._loading_port = True
            try:
                self.distance_spin.setValue(value)
            finally:
                self._loading_port = False
        self._refresh_component(index)

    def _refresh_all_components(self) -> None:
        for index in range(len(self._port_states)):
            self._refresh_component(index)

    def _refresh_component(self, index: int) -> None:
        editor = self._port_states[index]
        label = ""
        if editor.enabled:
            label = next(
                (
                    option.label
                    for option in self.valve_subtype_options
                    if option.value == editor.valve_subtype_id
                ),
                "Sulgeseade",
            )
        self.schematic.set_port_component(
            index,
            editor.enabled,
            label,
            editor.existing,
            editor.distance,
            self._maximum_distance(
                self.state.ports[index], editor.existing
            ),
        )

    def _branch_selection_changed(self, _index: int) -> None:
        self.schematic.set_branch_type(
            self.branch_combo.currentData(),
            self.branch_combo.currentText(),
        )
