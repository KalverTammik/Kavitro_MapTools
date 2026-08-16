"""Dedicated editor for an EVEL sewer pumping station."""

from __future__ import annotations

from dataclasses import replace
import re

from qgis.PyQt.QtCore import (
    QDate,
    QPointF,
    QRegularExpression,
    QRectF,
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
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
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
from .light_style import apply_evel_light_style, configure_evel_tabs
from .date_editor import EvelDateEditor
from .icon_catalog import (
    ICON_ADD,
    ICON_BACK,
    ICON_CANCEL,
    ICON_CONFIGURE,
    ICON_COPY,
    ICON_DUCT_TAB,
    ICON_FIELD_ADDRESS,
    ICON_NEXT,
    ICON_PREVIEW_HIDE,
    ICON_PREVIEW_SHOW,
    ICON_PUMPING_STATION,
    ICON_REMOVE,
    ICON_SAVE,
    catalog_icon,
    set_catalog_icon,
)


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


class _PumpStationPreviewHotspot(QGraphicsItem):
    """Transparent scene item providing a generous, scalable hit target."""

    def __init__(
        self,
        preview,
        rect: QRectF,
        section: int,
        callback,
        tooltip: str,
        *,
        z_value: float = 10.0,
    ) -> None:
        super().__init__()
        self.preview = preview
        self.section = section
        self.callback = callback
        self._rect = QRectF(0, 0, rect.width(), rect.height())
        self.setPos(rect.topLeft())
        self.setZValue(z_value)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._rect

    def paint(self, _painter, _option, _widget=None) -> None:
        return

    def hoverEnterEvent(self, event) -> None:  # noqa: N802
        self.preview._set_hovered_section(self.section)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802
        self.preview._set_hovered_section(-1)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.callback()
            event.accept()
            return
        super().mousePressEvent(event)


class _PumpStationPreviewArtwork(QGraphicsItem):
    """Single vector artwork item; interactions live in separate items."""

    def __init__(self, preview) -> None:
        super().__init__()
        self.preview = preview
        self.setZValue(0)

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(self.preview.SCENE_RECT)

    def paint(self, painter, _option, _widget=None) -> None:
        self.preview._paint_diagram(painter)


class SewerPumpingStationPreviewWidget(QGraphicsView):
    """Scalable, interactive 2.5D overview of a pumping station."""

    sectionSelected = pyqtSignal(int)
    pumpSelected = pyqtSignal(int)
    addPumpRequested = pyqtSignal()

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
    SCENE_RECT = QRectF(0, 0, 440, 570)

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
        self.selected_pump = -1
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
        self.pump_labels: tuple[str, ...] = ()
        self.pump_ready: tuple[bool, ...] = ()
        self._overlay_button: QPushButton | None = None
        self._graphics_scene = QGraphicsScene(self)
        self._graphics_scene.setSceneRect(self.SCENE_RECT)
        self.setScene(self._graphics_scene)
        self._artwork: _PumpStationPreviewArtwork | None = None
        self._section_rects: dict[int, tuple[QRectF, ...]] = {}

        self.setMinimumSize(340, 440)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignCenter)
        self.setBackgroundBrush(QColor("#f6f7f8"))
        self.setRenderHints(
            QPainter.Antialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAccessibleName(
            "Interaktiivne kanalisatsioonipumpla läbilõikeskeem"
        )
        self._rebuild_scene()
        self._update_description()

    def set_overlay_button(self, button: QPushButton) -> None:
        self._overlay_button = button
        button.adjustSize()
        button.raise_()
        self._position_overlay_button()

    def _position_overlay_button(self) -> None:
        button = self._overlay_button
        if button is None:
            return
        size = button.sizeHint()
        width = min(max(size.width(), 105), 125)
        button.setGeometry(
            max(self.width() - width - 15, 8),
            12,
            width,
            size.height(),
        )
        button.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_scene()
        self._position_overlay_button()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_scene()

    def _fit_scene(self) -> None:
        if self.viewport().width() <= 1 or self.viewport().height() <= 1:
            return
        self.resetTransform()
        self.fitInView(self.SCENE_RECT, Qt.KeepAspectRatio)

    def set_selected_section(self, index: int) -> None:
        if index < 0 or index >= len(self.SECTION_NAMES):
            return
        self.selected_section = index
        self._update_description()
        if self._artwork is not None:
            self._artwork.update()

    def set_selected_pump(self, index: int) -> None:
        bounded = index if 0 <= index < self.pump_count else -1
        if bounded == self.selected_pump:
            return
        self.selected_pump = bounded
        if self._artwork is not None:
            self._artwork.update()

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
        pump_labels: tuple[str, ...] = (),
        pump_ready: tuple[bool, ...] = (),
        selected_pump: int | None = None,
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
        self.pump_labels = tuple(pump_labels)
        self.pump_ready = tuple(bool(value) for value in pump_ready)
        if selected_pump is not None:
            self.selected_pump = (
                selected_pump
                if 0 <= selected_pump < self.pump_count
                else -1
            )
        elif self.selected_pump >= self.pump_count:
            self.selected_pump = -1
        self._update_description()
        self._rebuild_scene()

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
                    "Pumbad puuduvad",
                    "Lisa esimene pump, et pumbakomplekt seadistada",
                )
            return (
                f"{self.pump_count} pump"
                f"{'a' if self.pump_count != 1 else ''}",
                "Klõpsa pumbal selle tehniliste andmete avamiseks",
            )
        incoming, outgoing, unknown = self._flow_counts()
        unknown_text = f" · {unknown} määramata" if unknown else ""
        return (
            f"{self.port_count} toruühendust",
            f"{incoming} sisse · {outgoing} välja{unknown_text}",
        )

    def _update_description(self) -> None:
        first, second = self._summary_lines()
        hint = (
            f"{first}\n{second}\n\n"
            "Klõpsa pumpla osal, et avada selle parameetrite vaheleht."
        )
        self.setToolTip(hint)
        self.setAccessibleDescription(
            f"Pumpla ruumiline ülevaade. {first}. {second}. "
            "Skeemi elemendid avavad vastava töövoo sammu."
        )

    def _rebuild_scene(self) -> None:
        self._graphics_scene.clear()
        self._artwork = _PumpStationPreviewArtwork(self)
        self._graphics_scene.addItem(self._artwork)
        self._build_hotspots()
        self._graphics_scene.setSceneRect(self.SCENE_RECT)
        self._fit_scene()

    def _build_hotspots(self) -> None:
        self._section_rects = {
            self.SECTION_PUMPS: (QRectF(18, 42, 94, 29),),
            self.SECTION_CONTROL: (
                QRectF(297, 113, 70, 124),
                QRectF(317, 84, 111, 48),
            ),
            self.SECTION_FACILITY: (
                QRectF(112, 126, 210, 361),
                QRectF(128, 496, 185, 27),
            ),
            self.SECTION_PIPES: (
                QRectF(0, 232, 139, 116),
                QRectF(303, 220, 137, 112),
            ),
        }
        tooltips = {
            self.SECTION_PUMPS: "Ava pumpade andmed.",
            self.SECTION_CONTROL: "Ava juhtimissüsteemi ja seadmete andmed.",
            self.SECTION_FACILITY: "Ava pumpla rajatise ja asukoha andmed.",
            self.SECTION_PIPES: "Ava sisse- ja väljundtorustiku andmed.",
        }
        for section, rects in self._section_rects.items():
            for rect in rects:
                self._add_hotspot(
                    rect,
                    section,
                    lambda target=section: self._activate_section(target),
                    tooltips[section],
                    z_value=(
                        5.0
                        if section == self.SECTION_FACILITY
                        else 15.0
                    ),
                )

        if self.pump_count == 0:
            self._add_hotspot(
                QRectF(151, 286, 138, 141),
                self.SECTION_PUMPS,
                self._request_add_pump,
                "Lisa pumplale esimene pump.",
                z_value=30,
            )
            return

        positions = self._pump_positions()
        for index, x in enumerate(positions):
            pump_label = (
                self.pump_labels[index]
                if index < len(self.pump_labels)
                else f"Pump {index + 1}"
            )
            self._add_hotspot(
                QRectF(x - 8, 291, 60, 157),
                self.SECTION_PUMPS,
                lambda pump_index=index: self._activate_pump(pump_index),
                f"Ava pumba {index + 1} andmed: {pump_label}.",
                z_value=30,
            )
        if self.pump_count == 1:
            self._add_hotspot(
                QRectF(217, 306, 75, 122),
                self.SECTION_PUMPS,
                self._request_add_pump,
                "Lisa pumplale teine pump.",
                z_value=30,
            )

    def _add_hotspot(
        self,
        rect: QRectF,
        section: int,
        callback,
        tooltip: str,
        *,
        z_value: float = 10.0,
    ) -> None:
        self._graphics_scene.addItem(
            _PumpStationPreviewHotspot(
                self,
                rect,
                section,
                callback,
                tooltip,
                z_value=z_value,
            )
        )

    def _activate_section(self, section: int) -> None:
        self.set_selected_section(section)
        self.sectionSelected.emit(section)

    def _activate_pump(self, index: int) -> None:
        self._activate_section(self.SECTION_PUMPS)
        self.set_selected_pump(index)
        self.pumpSelected.emit(index)

    def _request_add_pump(self) -> None:
        self._activate_section(self.SECTION_PUMPS)
        # The add action rebuilds the scene. Defer it until the hotspot's
        # mouse event has returned so the active QGraphicsItem is not deleted
        # while Qt is still dispatching that event.
        QTimer.singleShot(0, self.addPumpRequested.emit)

    def _set_hovered_section(self, section: int) -> None:
        if section == self.hovered_section:
            return
        self.hovered_section = section
        if self._artwork is not None:
            self._artwork.update()

    def _pump_positions(self) -> tuple[float, ...]:
        if self.pump_count <= 0:
            return ()
        if self.pump_count == 1:
            return (151.0,)
        return (145.0, 225.0)

    def _paint_diagram(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        self._paint_background(painter)
        self._paint_header(painter)
        self._paint_selection_glow(painter)
        self._paint_station(painter)
        self._paint_footer(painter)

    @staticmethod
    def _paint_background(painter: QPainter) -> None:
        gradient = QLinearGradient(0, 0, 440, 570)
        gradient.setColorAt(0.0, QColor("#ffffff"))
        gradient.setColorAt(0.64, QColor("#f8fbfd"))
        gradient.setColorAt(1.0, QColor("#eef5f9"))
        painter.setPen(QPen(QColor("#d8e1e8"), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(QRectF(1, 1, 438, 568), 15, 15)

        painter.setPen(QPen(QColor(0, 120, 212, 13), 1))
        for x in range(20, 441, 20):
            painter.drawLine(x, 80, x, 554)
        for y in range(80, 555, 20):
            painter.drawLine(1, y, 439, y)

    def _paint_header(self, painter: QPainter) -> None:
        painter.save()
        title_font = QFont(painter.font())
        title_font.setBold(True)
        title_font.setPointSizeF(8.2)
        title_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        painter.setFont(title_font)
        painter.setPen(QColor("#0078d4"))
        painter.drawText(
            QRectF(19, 14, 185, 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            "PUMPLA RUUMILINE ÜLEVAADE",
        )

        pill = QRectF(18, 42, 94, 29)
        active = self.selected_section == self.SECTION_PUMPS
        painter.setBrush(QColor("#eaf4ff" if not active else "#0078d4"))
        painter.setPen(QPen(QColor("#67aaf9"), 1.2))
        painter.drawRoundedRect(pill, 7, 7)
        painter.setPen(QColor("#ffffff" if active else "#0066b3"))
        count_font = QFont(title_font)
        count_font.setLetterSpacing(QFont.AbsoluteSpacing, 0)
        count_font.setPointSizeF(9)
        painter.setFont(count_font)
        count_text = (
            "0 pumpa"
            if self.pump_count == 0
            else "1 pump"
            if self.pump_count == 1
            else f"{self.pump_count} pumpa"
        )
        self._paint_pump_count_icon(
            painter,
            active=active,
            count=self.pump_count,
        )
        painter.drawText(
            pill.adjusted(25, 0, -5, 0),
            Qt.AlignCenter,
            count_text,
        )

        first, second = self._summary_lines()
        summary_font = QFont(painter.font())
        summary_font.setBold(True)
        summary_font.setPointSizeF(8.3)
        painter.setFont(summary_font)
        painter.setPen(QColor("#17212b"))
        painter.drawText(
            QRectF(123, 41, 168, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(summary_font).elidedText(first, Qt.ElideRight, 168),
        )
        summary_font.setBold(False)
        summary_font.setPointSizeF(7.2)
        painter.setFont(summary_font)
        painter.setPen(QColor("#667788"))
        painter.drawText(
            QRectF(123, 57, 168, 15),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(summary_font).elidedText(second, Qt.ElideRight, 168),
        )
        painter.restore()

    @staticmethod
    def _paint_pump_count_icon(
        painter: QPainter,
        *,
        active: bool,
        count: int,
    ) -> None:
        color = QColor("#ffffff" if active else "#0078d4")
        if count == 0:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(color, 1.8, Qt.DashLine))
            painter.drawEllipse(QPointF(32, 56.5), 7, 7)
            return
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        centers = (29.5,) if count == 1 else (27.0, 35.0)
        for center_x in centers:
            drop = QPainterPath(QPointF(center_x, 49.5))
            drop.cubicTo(
                center_x - 7,
                57,
                center_x - 5,
                63,
                center_x,
                63,
            )
            drop.cubicTo(
                center_x + 5,
                63,
                center_x + 7,
                57,
                center_x,
                49.5,
            )
            painter.drawPath(drop)

    def _paint_selection_glow(self, painter: QPainter) -> None:
        rects = self._section_rects.get(self.selected_section, ())
        selected = QColor("#1689e6")
        selected.setAlpha(24)
        painter.setBrush(selected)
        painter.setPen(QPen(QColor(0, 120, 212, 95), 2))
        for rect in rects:
            painter.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 10, 10)
        if self.hovered_section < 0 or self.hovered_section == self.selected_section:
            return
        hovered = QColor("#0f766e")
        hovered.setAlpha(17)
        painter.setBrush(hovered)
        painter.setPen(QPen(QColor(15, 118, 110, 100), 1.5))
        for rect in self._section_rects.get(self.hovered_section, ()):
            painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 9, 9)

    def _paint_station(self, painter: QPainter) -> None:
        self._paint_connections(painter)
        self._paint_anchor_plate(painter)

        # Transparent, ribbed wet well. The shell is a continuous path whose
        # curved bottom reaches the anchor plate instead of floating above it.
        body_left = 118.0
        body_right = 323.0
        body_top = 166.0
        body_side_bottom = 456.0
        body_curve_bottom = 478.0
        body = QRectF(
            body_left,
            body_top,
            body_right - body_left,
            body_curve_bottom - body_top,
        )
        body_path = QPainterPath(QPointF(body_left + 18, body_top))
        body_path.quadTo(
            QPointF(body_left, body_top),
            QPointF(body_left, body_top + 18),
        )
        body_path.lineTo(body_left, body_side_bottom)
        body_path.cubicTo(
            body_left,
            body_curve_bottom,
            body_right,
            body_curve_bottom,
            body_right,
            body_side_bottom,
        )
        body_path.lineTo(body_right, body_top + 18)
        body_path.quadTo(
            QPointF(body_right, body_top),
            QPointF(body_right - 18, body_top),
        )
        body_path.closeSubpath()

        body_gradient = QLinearGradient(body.left(), 0, body.right(), 0)
        body_gradient.setColorAt(0.0, QColor(120, 137, 151, 225))
        body_gradient.setColorAt(0.17, QColor(237, 243, 247, 225))
        body_gradient.setColorAt(0.52, QColor(190, 203, 214, 195))
        body_gradient.setColorAt(0.82, QColor(246, 249, 251, 220))
        body_gradient.setColorAt(1.0, QColor(113, 132, 148, 230))
        painter.setBrush(QBrush(body_gradient))
        painter.setPen(QPen(QColor("#566674"), 2))
        painter.drawPath(body_path)

        water = QRectF(127, 347, 187, 124)
        water_gradient = QLinearGradient(0, water.top(), 0, water.bottom())
        water_gradient.setColorAt(0, QColor(45, 179, 222, 105))
        water_gradient.setColorAt(1, QColor(0, 93, 151, 180))
        water_path = QPainterPath(QPointF(water.left(), water.top()))
        water_path.lineTo(water.right(), water.top())
        water_path.lineTo(water.right(), 456)
        water_path.cubicTo(
            water.right(),
            471,
            water.left(),
            471,
            water.left(),
            456,
        )
        water_path.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(water_gradient))
        painter.drawPath(water_path)
        painter.setPen(QPen(QColor("#087fbf"), 2))
        painter.drawArc(QRectF(127, 338, 187, 20), 0, 180 * 16)
        painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
        for y in (373, 397, 421, 445):
            painter.drawArc(QRectF(133, y, 174, 11), 0, 180 * 16)

        painter.setPen(QPen(QColor(104, 120, 133, 145), 1.5))
        for y in range(187, 456, 18):
            painter.drawArc(QRectF(119, y - 5, 203, 14), 180 * 16, 180 * 16)
            painter.drawArc(QRectF(119, y - 5, 203, 14), 0, 180 * 16)

        self._paint_chamber_base_rim(painter)

        self._paint_station_top(painter)

        self._paint_control_cabinet(painter)
        self._paint_pumps(painter)

        incoming, outgoing, _unknown = self._flow_counts()
        self._paint_callout(
            painter,
            QRectF(317, 84, 111, 48),
            "02",
            "Juhtimine",
            self.control_label,
            self.SECTION_CONTROL,
            QPointF(326, 126),
        )
        self._paint_callout(
            painter,
            QRectF(5, 244, 101, 45),
            "04",
            "Sissevool",
            f"{incoming} ühendust" if incoming else "Sisend",
            self.SECTION_PIPES,
            QPointF(89, 315),
        )
        self._paint_callout(
            painter,
            QRectF(335, 229, 101, 45),
            "04",
            "Väljavool",
            f"{outgoing} ühendust" if outgoing else "Väljund",
            self.SECTION_PIPES,
            QPointF(349, 285),
        )
        self._paint_anchor_plate_badge(painter)

        painter.setPen(QPen(QColor("#087fbf"), 1))
        painter.drawLine(QPointF(18, 351), QPointF(123, 351))
        painter.setPen(QColor("#0870b8"))
        water_font = QFont(painter.font())
        water_font.setPointSizeF(7)
        water_font.setBold(True)
        painter.setFont(water_font)
        painter.drawText(QRectF(18, 337, 91, 14), Qt.AlignLeft, "VEETASE")

    @staticmethod
    def _paint_station_top(painter: QPainter) -> None:
        """Paint a centred isometric top collar and access hatch."""

        painter.save()
        center_x = 220.5

        # A circular collar is shown as a centred elliptical cylinder in the
        # isometric view. The lower edge follows the same curvature as its top.
        collar_half_width = 118.0
        collar_left = center_x - collar_half_width
        collar_right = center_x + collar_half_width
        collar_wall = QPainterPath(QPointF(collar_left, 158))
        collar_wall.lineTo(collar_right, 158)
        collar_wall.lineTo(collar_right, 170)
        collar_wall.cubicTo(
            collar_right,
            182,
            collar_left,
            182,
            collar_left,
            170,
        )
        collar_wall.closeSubpath()
        wall_gradient = QLinearGradient(
            collar_left,
            0,
            collar_right,
            0,
        )
        wall_gradient.setColorAt(0.0, QColor("#929fa9"))
        wall_gradient.setColorAt(0.16, QColor("#e5eaed"))
        wall_gradient.setColorAt(0.5, QColor("#c6cfd5"))
        wall_gradient.setColorAt(0.84, QColor("#e8ecef"))
        wall_gradient.setColorAt(1.0, QColor("#8996a0"))
        painter.setBrush(QBrush(wall_gradient))
        painter.setPen(QPen(QColor("#65747f"), 1.25))
        painter.drawPath(collar_wall)

        top_gradient = QLinearGradient(0, 147, 0, 169)
        top_gradient.setColorAt(0.0, QColor("#f6f8f9"))
        top_gradient.setColorAt(0.5, QColor("#e0e5e8"))
        top_gradient.setColorAt(1.0, QColor("#b9c4cb"))
        painter.setBrush(QBrush(top_gradient))
        painter.setPen(QPen(QColor("#6d7b86"), 1.2))
        painter.drawEllipse(QRectF(collar_left, 147, 236, 22))

        front_edge = QPainterPath(QPointF(collar_left, 158))
        front_edge.cubicTo(
            collar_left,
            169,
            collar_right,
            169,
            collar_right,
            158,
        )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(104, 119, 130, 145), 1.05))
        painter.drawPath(front_edge)

        lower_edge = QPainterPath(QPointF(collar_left, 170))
        lower_edge.cubicTo(
            collar_left,
            182,
            collar_right,
            182,
            collar_right,
            170,
        )
        painter.setPen(QPen(QColor(73, 87, 98, 135), 1.05))
        painter.drawPath(lower_edge)

        # Centred access-hatch wall. Its horizontal gradient mirrors the shell
        # and the shallow bottom curve keeps it seated on the upper collar.
        hatch_half_width = 69.0
        hatch_left = center_x - hatch_half_width
        hatch_right = center_x + hatch_half_width
        hatch_wall = QPainterPath(QPointF(hatch_left, 121))
        hatch_wall.lineTo(hatch_right, 121)
        hatch_wall.lineTo(hatch_right, 148)
        hatch_wall.cubicTo(
            hatch_right,
            154,
            hatch_left,
            154,
            hatch_left,
            148,
        )
        hatch_wall.closeSubpath()
        wall_gradient = QLinearGradient(hatch_left, 0, hatch_right, 0)
        wall_gradient.setColorAt(0.0, QColor("#a9b4bd"))
        wall_gradient.setColorAt(0.18, QColor("#edf1f3"))
        wall_gradient.setColorAt(0.52, QColor("#cbd3d9"))
        wall_gradient.setColorAt(0.84, QColor("#eef1f3"))
        wall_gradient.setColorAt(1.0, QColor("#929fa9"))
        painter.setBrush(QBrush(wall_gradient))
        painter.setPen(QPen(QColor("#64737e"), 1.25))
        painter.drawPath(hatch_wall)

        # The hatch roof repeats the same isometric six-point top plane.
        roof_rear_half_width = 51.0
        roof_front_half_width = 62.0
        roof_outer_half_width = 70.0
        roof = QPolygonF(
            [
                QPointF(center_x - roof_rear_half_width, 101),
                QPointF(center_x + roof_rear_half_width, 101),
                QPointF(center_x + roof_outer_half_width, 117),
                QPointF(center_x + roof_front_half_width, 124),
                QPointF(center_x - roof_front_half_width, 124),
                QPointF(center_x - roof_outer_half_width, 117),
            ]
        )
        roof_gradient = QLinearGradient(0, 101, 0, 124)
        roof_gradient.setColorAt(0.0, QColor("#f5f7f8"))
        roof_gradient.setColorAt(0.55, QColor("#e0e5e8"))
        roof_gradient.setColorAt(1.0, QColor("#bcc6cd"))
        painter.setBrush(QBrush(roof_gradient))
        painter.setPen(QPen(QColor("#697883"), 1.2))
        painter.drawPolygon(roof)
        painter.setPen(QPen(QColor(255, 255, 255, 175), 1))
        painter.drawLine(
            QPointF(center_x - roof_rear_half_width + 2, 103),
            QPointF(center_x + roof_rear_half_width - 2, 103),
        )
        painter.restore()

    @staticmethod
    def _paint_property_surface(painter: QPainter) -> None:
        """Paint a muted parcel/ground plane beneath the anchor plate."""

        center_x = 220.5
        rear_half_width = 164.0
        front_half_width = 158.0
        outer_half_width = 178.0
        top_back_y = 474.0
        outer_y = 489.0
        front_y = 497.0
        bottom_outer_y = 504.0
        bottom_y = 510.0

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(44, 62, 37, 18))
        painter.drawEllipse(QRectF(center_x - 184, 499, 368, 19))

        parcel_front = QPolygonF(
            [
                QPointF(center_x - outer_half_width, outer_y),
                QPointF(center_x - front_half_width, front_y),
                QPointF(center_x + front_half_width, front_y),
                QPointF(center_x + outer_half_width, outer_y),
                QPointF(center_x + outer_half_width - 3, bottom_outer_y),
                QPointF(center_x + front_half_width + 1, bottom_y),
                QPointF(center_x - front_half_width - 1, bottom_y),
                QPointF(center_x - outer_half_width + 3, bottom_outer_y),
            ]
        )
        front_gradient = QLinearGradient(0, outer_y, 0, bottom_y)
        front_gradient.setColorAt(0.0, QColor("#acbd9c"))
        front_gradient.setColorAt(0.48, QColor("#93a783"))
        front_gradient.setColorAt(1.0, QColor("#788d69"))
        painter.setBrush(QBrush(front_gradient))
        painter.setPen(QPen(QColor("#718365"), 1.15))
        painter.drawPolygon(parcel_front)

        parcel_top = QPolygonF(
            [
                QPointF(center_x - rear_half_width, top_back_y),
                QPointF(center_x + rear_half_width, top_back_y),
                QPointF(center_x + outer_half_width, outer_y),
                QPointF(center_x + front_half_width, front_y),
                QPointF(center_x - front_half_width, front_y),
                QPointF(center_x - outer_half_width, outer_y),
            ]
        )
        top_gradient = QLinearGradient(0, top_back_y, 0, front_y)
        top_gradient.setColorAt(0.0, QColor("#e5eddd"))
        top_gradient.setColorAt(0.5, QColor("#d2dfc7"))
        top_gradient.setColorAt(1.0, QColor("#b8c9aa"))
        painter.setBrush(QBrush(top_gradient))
        boundary_pen = QPen(QColor("#78906b"), 1.2)
        boundary_pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(boundary_pen)
        painter.drawPolygon(parcel_top)

        # Two short boundary strokes make the plane read as a parcel without
        # competing with the technical foundation drawing above it.
        boundary_detail = QPen(QColor(92, 119, 78, 115), 1, Qt.DashLine)
        painter.setPen(boundary_detail)
        painter.drawLine(
            QPointF(center_x - outer_half_width + 8, outer_y + 1),
            QPointF(center_x - front_half_width + 16, front_y - 1),
        )
        painter.drawLine(
            QPointF(center_x + outer_half_width - 8, outer_y + 1),
            QPointF(center_x + front_half_width - 16, front_y - 1),
        )

    def _paint_anchor_plate(self, painter: QPainter) -> None:
        """Paint the concrete anchor plate and its raised rear support."""

        painter.save()
        self._paint_property_surface(painter)

        # Every horizontal measure is mirrored from the chamber centre. This
        # prevents individual faces from drifting apart as the design evolves.
        center_x = 220.5
        rear_half_width = 128.0
        front_half_width = 139.0
        outer_half_width = 158.0
        top_back_y = 455.0
        outer_y = 472.0
        front_y = 480.0
        bottom_outer_y = 489.0
        bottom_y = 496.0

        # One continuous front body replaces separately positioned spacers.
        front_face = QPolygonF(
            [
                QPointF(center_x - outer_half_width, outer_y),
                QPointF(center_x - front_half_width, front_y),
                QPointF(center_x + front_half_width, front_y),
                QPointF(center_x + outer_half_width, outer_y),
                QPointF(center_x + outer_half_width - 3, bottom_outer_y),
                QPointF(center_x + front_half_width + 1, bottom_y),
                QPointF(center_x - front_half_width - 1, bottom_y),
                QPointF(center_x - outer_half_width + 3, bottom_outer_y),
            ]
        )
        front_gradient = QLinearGradient(0, outer_y, 0, bottom_y)
        front_gradient.setColorAt(0.0, QColor("#c8d0d6"))
        front_gradient.setColorAt(0.45, QColor("#aab5bd"))
        front_gradient.setColorAt(1.0, QColor("#7f8c96"))
        painter.setBrush(QBrush(front_gradient))
        painter.setPen(QPen(QColor("#687681"), 1.2))
        painter.drawPolygon(front_face)

        # The broad top plane is derived from the same mirrored dimensions.
        top_face = QPolygonF(
            [
                QPointF(center_x - rear_half_width, top_back_y),
                QPointF(center_x + rear_half_width, top_back_y),
                QPointF(center_x + outer_half_width, outer_y),
                QPointF(center_x + front_half_width, front_y),
                QPointF(center_x - front_half_width, front_y),
                QPointF(center_x - outer_half_width, outer_y),
            ]
        )
        top_gradient = QLinearGradient(0, top_back_y, 0, front_y)
        top_gradient.setColorAt(0.0, QColor("#f6f8f9"))
        top_gradient.setColorAt(0.48, QColor("#dfe4e8"))
        top_gradient.setColorAt(1.0, QColor("#b9c3ca"))
        painter.setBrush(QBrush(top_gradient))
        painter.setPen(QPen(QColor("#72808a"), 1.2))
        painter.drawPolygon(top_face)

        # Symmetrical bevel seams and restrained highlights define the plate
        # without making it look as if it was assembled from loose blocks.
        painter.setPen(QPen(QColor(92, 108, 120, 125), 1))
        painter.drawLine(
            QPointF(center_x - front_half_width, front_y),
            QPointF(center_x - front_half_width - 1, bottom_y),
        )
        painter.drawLine(
            QPointF(center_x + front_half_width, front_y),
            QPointF(center_x + front_half_width + 1, bottom_y),
        )
        painter.setPen(QPen(QColor(255, 255, 255, 178), 1.05))
        painter.drawLine(
            QPointF(center_x - rear_half_width + 2, top_back_y + 2),
            QPointF(center_x + rear_half_width - 2, top_back_y + 2),
        )

        painter.restore()

    @staticmethod
    def _paint_chamber_base_rim(painter: QPainter) -> None:
        """Join the shell's bottom curve cleanly to the anchor plate."""

        painter.save()
        center_x = 220.5
        rim_half_width = 106.0
        left = center_x - rim_half_width
        right = center_x + rim_half_width
        rim = QPainterPath(QPointF(left, 452))
        rim.cubicTo(left, 474, right, 474, right, 452)
        rim.lineTo(right, 461)
        rim.cubicTo(right, 483, left, 483, left, 461)
        rim.closeSubpath()

        rim_gradient = QLinearGradient(0, 452, 0, 483)
        rim_gradient.setColorAt(0.0, QColor("#e9eef1"))
        rim_gradient.setColorAt(0.42, QColor("#bcc6cd"))
        rim_gradient.setColorAt(1.0, QColor("#71808b"))
        painter.setBrush(QBrush(rim_gradient))
        painter.setPen(QPen(QColor("#61707b"), 1.35))
        painter.drawPath(rim)

        upper_edge = QPainterPath(QPointF(left, 452))
        upper_edge.cubicTo(
            left,
            474,
            right,
            474,
            right,
            452,
        )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 185), 1.15))
        painter.drawPath(upper_edge)

        lower_edge = QPainterPath(QPointF(left, 461))
        lower_edge.cubicTo(
            left,
            483,
            right,
            483,
            right,
            461,
        )
        painter.setPen(QPen(QColor(71, 84, 94, 135), 1.15))
        painter.drawPath(lower_edge)
        painter.restore()

    def _paint_anchor_plate_badge(self, painter: QPainter) -> None:
        """Place the facility/location workflow label on the anchor plate."""

        rect = QRectF(128, 497, 185, 25)
        active = self.selected_section == self.SECTION_FACILITY
        hovered = (
            self.hovered_section == self.SECTION_FACILITY and not active
        )
        painter.setBrush(QColor("#0078d4" if active else "#ffffff"))
        painter.setPen(
            QPen(
                QColor(
                    "#0078d4"
                    if active
                    else "#0f766e"
                    if hovered
                    else "#c4d0d9"
                ),
                1.35 if active or hovered else 1.0,
            )
        )
        painter.drawRoundedRect(rect, 6, 6)

        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(7.1)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff" if active else "#273947"))
        painter.drawText(
            rect.adjusted(9, 0, -18, 0),
            Qt.AlignCenter,
            "03  RAJATIS JA ASUKOHT",
        )
        state_color = (
            QColor("#35a854")
            if self._section_state(self.SECTION_FACILITY) == "ready"
            else QColor("#f0a32f")
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(state_color)
        painter.drawEllipse(
            QRectF(rect.right() - 11, rect.center().y() - 2.5, 5, 5)
        )

    def _paint_connections(self, painter: QPainter) -> None:
        self._paint_pipe(painter, QPointF(2, 315), QPointF(139, 315))
        self._paint_pipe(painter, QPointF(303, 285), QPointF(438, 285))
        self._paint_valve(painter, QPointF(84, 315))
        self._paint_valve(painter, QPointF(354, 285))
        self._paint_flow_arrow(painter, QPointF(28, 315), True)
        self._paint_flow_arrow(painter, QPointF(416, 285), True)

        incoming, outgoing, unknown = self._flow_counts()
        extra = max(incoming - 1, 0) + max(outgoing - 1, 0) + unknown
        if extra:
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#8ca0b1"), 1))
            painter.drawRoundedRect(QRectF(351, 309, 66, 22), 6, 6)
            painter.setPen(QColor("#526473"))
            font = QFont(painter.font())
            font.setBold(True)
            font.setPointSizeF(7)
            painter.setFont(font)
            painter.drawText(
                QRectF(351, 309, 66, 22),
                Qt.AlignCenter,
                f"+{extra} ühendust",
            )

    @staticmethod
    def _paint_pipe(painter: QPainter, start: QPointF, end: QPointF) -> None:
        main = QPen(QColor("#7d8994"), 19)
        main.setCapStyle(Qt.RoundCap)
        painter.setPen(main)
        painter.drawLine(start, end)
        highlight = QPen(QColor("#e8edf1"), 11)
        highlight.setCapStyle(Qt.RoundCap)
        painter.setPen(highlight)
        painter.drawLine(start, end)
        painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
        painter.drawLine(
            QPointF(start.x(), start.y() - 3),
            QPointF(end.x(), end.y() - 3),
        )

    @staticmethod
    def _paint_flow_arrow(
        painter: QPainter,
        center: QPointF,
        points_right: bool,
    ) -> None:
        direction = 1 if points_right else -1
        painter.setPen(QPen(QColor("#f2a800"), 3))
        painter.drawLine(
            QPointF(center.x() - 10 * direction, center.y()),
            QPointF(center.x() + 8 * direction, center.y()),
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f2a800"))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(center.x() + 8 * direction, center.y()),
                    QPointF(center.x() - 1 * direction, center.y() - 6),
                    QPointF(center.x() - 1 * direction, center.y() + 6),
                ]
            )
        )

    @staticmethod
    def _paint_valve(painter: QPainter, center: QPointF) -> None:
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#087fc5"), 2.5))
        painter.drawEllipse(center, 10, 10)
        painter.drawLine(
            QPointF(center.x() - 8, center.y() - 8),
            QPointF(center.x() + 8, center.y() + 8),
        )
        painter.drawLine(
            QPointF(center.x() - 8, center.y() + 8),
            QPointF(center.x() + 8, center.y() - 8),
        )
        painter.drawLine(
            QPointF(center.x(), center.y() - 10),
            QPointF(center.x(), center.y() - 17),
        )
        painter.drawLine(
            QPointF(center.x() - 7, center.y() - 17),
            QPointF(center.x() + 7, center.y() - 17),
        )

    @staticmethod
    def _paint_control_cabinet(painter: QPainter) -> None:
        painter.setPen(QPen(QColor(27, 44, 58, 32), 8))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(299, 116, 65, 118), 5, 5)
        cabinet = QLinearGradient(299, 116, 365, 234)
        cabinet.setColorAt(0, QColor("#f2f5f7"))
        cabinet.setColorAt(0.58, QColor("#c6d0d8"))
        cabinet.setColorAt(1, QColor("#8594a0"))
        painter.setBrush(QBrush(cabinet))
        painter.setPen(QPen(QColor("#536675"), 1.6))
        painter.drawRoundedRect(QRectF(299, 116, 65, 118), 4, 4)
        painter.setBrush(QColor("#243846"))
        painter.drawRoundedRect(QRectF(309, 129, 45, 48), 3, 3)
        screen = QLinearGradient(312, 132, 350, 172)
        screen.setColorAt(0, QColor("#14252f"))
        screen.setColorAt(1, QColor("#5d7a86"))
        painter.setBrush(QBrush(screen))
        painter.drawRoundedRect(QRectF(313, 133, 37, 39), 2, 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#45b649"))
        painter.drawEllipse(QRectF(313, 187, 7, 7))
        painter.setBrush(QColor("#f6ba2f"))
        painter.drawEllipse(QRectF(325, 187, 7, 7))
        painter.setBrush(QColor("#d7e0e6"))
        painter.setPen(QPen(QColor("#647786"), 1))
        painter.drawRoundedRect(QRectF(343, 184, 8, 20), 2, 2)

    def _paint_pumps(self, painter: QPainter) -> None:
        if self.pump_count == 0:
            self._paint_empty_pump_slot(
                painter,
                QRectF(151, 286, 138, 141),
                "Pumbad puuduvad",
                "Lisa esimene pump",
            )
            return

        positions = self._pump_positions()
        painter.setPen(QPen(QColor("#087fc5"), 5.5))
        manifold_y = 282.0
        centers = []
        for index, x in enumerate(positions):
            center_x = x + 22
            centers.append(center_x)
            painter.drawLine(QPointF(center_x, 323), QPointF(center_x, manifold_y))
            self._paint_pump(painter, x, 323, index)
        if centers:
            painter.drawLine(
                QPointF(min(centers), manifold_y),
                QPointF(max(centers), manifold_y),
            )

        if self.pump_count == 1:
            self._paint_empty_pump_slot(
                painter,
                QRectF(217, 306, 75, 122),
                "+",
                "Lisa teine pump",
            )
        elif self.pump_count > 2:
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#1689e6"), 1.5))
            painter.drawRoundedRect(QRectF(270, 298, 44, 25), 7, 7)
            painter.setPen(QColor("#0067b1"))
            font = QFont(painter.font())
            font.setBold(True)
            font.setPointSizeF(8)
            painter.setFont(font)
            painter.drawText(
                QRectF(270, 298, 44, 25),
                Qt.AlignCenter,
                f"+{self.pump_count - 2}",
            )

    def _paint_pump(
        self,
        painter: QPainter,
        x: float,
        y: float,
        index: int,
    ) -> None:
        selected = index == self.selected_pump
        ready = index < len(self.pump_ready) and self.pump_ready[index]
        if selected:
            painter.setPen(QPen(QColor(0, 120, 212, 55), 10))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(x - 4, y - 7, 52, 127), 16, 16)

        gradient = QLinearGradient(x, y, x + 44, y)
        gradient.setColorAt(0, QColor("#596a78"))
        gradient.setColorAt(0.18, QColor("#b9c4cc"))
        gradient.setColorAt(0.48, QColor("#f4f6f7"))
        gradient.setColorAt(0.76, QColor("#9caab5"))
        gradient.setColorAt(1, QColor("#4d5c69"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor("#435462"), 1.4))
        body_path = QPainterPath()
        body_path.moveTo(x + 10, y + 16)
        body_path.cubicTo(x + 7, y + 29, x + 3, y + 44, x + 3, y + 68)
        body_path.lineTo(x + 3, y + 89)
        body_path.cubicTo(x + 3, y + 101, x + 41, y + 101, x + 41, y + 89)
        body_path.lineTo(x + 41, y + 68)
        body_path.cubicTo(x + 41, y + 44, x + 37, y + 29, x + 34, y + 16)
        body_path.closeSubpath()
        painter.drawPath(body_path)
        painter.drawEllipse(QRectF(x + 10, y + 4, 24, 25))
        painter.setBrush(QColor("#344957"))
        painter.drawRoundedRect(QRectF(x, y + 84, 44, 30), 8, 8)
        painter.setPen(QPen(QColor("#80909b"), 2))
        for offset in (8, 17, 26, 35):
            painter.drawLine(
                QPointF(x + offset, y + 91),
                QPointF(x + offset - 2, y + 109),
            )

        label = QRectF(x - 4, y - 28, 52, 24)
        painter.setBrush(QColor("#0078d4" if selected else "#eaf4ff"))
        painter.setPen(QPen(QColor("#1689e6"), 1.1))
        painter.drawRoundedRect(label, 6, 6)
        painter.setPen(QColor("#ffffff" if selected else "#0067b1"))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(7.4)
        painter.setFont(font)
        painter.drawText(label, Qt.AlignCenter, f"Pump {index + 1}")
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#35a854" if ready else "#f0a32f"))
        painter.drawEllipse(QRectF(label.right() - 7, label.top() + 3, 5, 5))

    @staticmethod
    def _paint_empty_pump_slot(
        painter: QPainter,
        rect: QRectF,
        title: str,
        action: str,
    ) -> None:
        painter.setBrush(QColor(255, 255, 255, 205))
        pen = QPen(QColor("#8eb9dd"), 1.4, Qt.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 11, 11)
        title_font = QFont(painter.font())
        title_font.setBold(True)
        title_font.setPointSizeF(8)
        painter.setFont(title_font)
        painter.setPen(QColor("#31495b"))
        painter.drawText(
            rect.adjusted(5, 28, -5, -61),
            Qt.AlignCenter | Qt.TextWordWrap,
            title,
        )
        action_rect = QRectF(
            rect.left() + 9,
            rect.bottom() - 44,
            rect.width() - 18,
            30,
        )
        painter.setBrush(QColor("#eaf4ff"))
        painter.setPen(QPen(QColor("#67aaf9"), 1))
        painter.drawRoundedRect(action_rect, 7, 7)
        painter.setPen(QColor("#0067b1"))
        action_font = QFont(title_font)
        action_font.setPointSizeF(7.2)
        painter.setFont(action_font)
        painter.drawText(
            action_rect.adjusted(4, 0, -4, 0),
            Qt.AlignCenter | Qt.TextWordWrap,
            action,
        )

    def _section_state(self, section: int) -> str:
        if section == self.SECTION_PUMPS:
            if self.pump_count == 0:
                return "empty"
            complete = (
                len(self.pump_ready) >= self.pump_count
                and all(self.pump_ready[: self.pump_count])
            )
            return "ready" if complete else "warning"
        if section == self.SECTION_CONTROL:
            return "warning" if "valimata" in self.control_label.casefold() else "ready"
        if section == self.SECTION_FACILITY:
            missing = any(
                "valimata" in value.casefold()
                for value in (self.type_label, self.role_label, self.material_label)
            )
            return "warning" if missing else "ready"
        return "ready" if self.port_count else "warning"

    def _paint_callout(
        self,
        painter: QPainter,
        rect: QRectF,
        number: str,
        title: str,
        subtitle: str,
        section: int,
        target: QPointF,
    ) -> None:
        active = section == self.selected_section
        hovered = section == self.hovered_section and not active
        start = rect.center()
        painter.setPen(QPen(QColor("#b4c5d2"), 1.1))
        painter.drawLine(start, target)
        painter.setBrush(QColor("#0078d4" if active else "#ffffff"))
        painter.setPen(
            QPen(
                QColor("#0078d4" if active else "#0f766e" if hovered else "#c7d4de"),
                1.4 if active or hovered else 1.0,
            )
        )
        painter.drawRoundedRect(rect, 7, 7)
        title_font = QFont(painter.font())
        title_font.setBold(True)
        title_font.setPointSizeF(7.4)
        painter.setFont(title_font)
        painter.setPen(QColor("#ffffff" if active else "#0069b5"))
        painter.drawText(
            QRectF(rect.left() + 8, rect.top() + 4, rect.width() - 16, 15),
            Qt.AlignLeft | Qt.AlignVCenter,
            f"{number}  {title}",
        )
        subtitle_font = QFont(title_font)
        subtitle_font.setBold(False)
        subtitle_font.setPointSizeF(6.8)
        painter.setFont(subtitle_font)
        subtitle_color = QColor("#eaf5ff") if active else QColor("#4f6271")
        painter.setPen(subtitle_color)
        elided = QFontMetrics(subtitle_font).elidedText(
            subtitle or "Pole määratud",
            Qt.ElideRight,
            int(rect.width() - 25),
        )
        painter.drawText(
            QRectF(rect.left() + 8, rect.top() + 22, rect.width() - 18, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            elided,
        )
        state_colors = {
            "ready": QColor("#35a854"),
            "warning": QColor("#f0a32f"),
            "empty": QColor("#8a99a6"),
        }
        painter.setPen(Qt.NoPen)
        painter.setBrush(state_colors[self._section_state(section)])
        painter.drawEllipse(QRectF(rect.right() - 10, rect.top() + 7, 5, 5))

    @staticmethod
    def _paint_footer(painter: QPainter) -> None:
        painter.setPen(QColor("#687987"))
        font = QFont(painter.font())
        font.setPointSizeF(7)
        painter.setFont(font)
        painter.drawText(
            QRectF(14, 552, 412, 13),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Klõpsa skeemi elemendil, et avada või muuta selle andmeid.",
        )


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
        configure_evel_tabs(self.tabs)
        self.tabs.addTab(
            self._pumps_tab(),
            catalog_icon(ICON_PUMPING_STATION),
            "01  Pumbad",
        )
        self.tabs.addTab(
            self._electrical_tab(),
            catalog_icon(ICON_CONFIGURE),
            "02  Juhtimine",
        )
        self.tabs.addTab(
            self._general_tab(),
            catalog_icon(ICON_FIELD_ADDRESS),
            "03  Rajatis ja asukoht",
        )
        self.tabs.addTab(
            self._pipes_tab(),
            catalog_icon(ICON_DUCT_TAB),
            "04  Torud",
        )
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
        if self.pump_date_control.has_invalid_input():
            self.tabs.setCurrentIndex(0)
            QMessageBox.warning(
                self,
                "Vigane kuupäev",
                "Sisesta kuupäev kujul pp.kk.aaaa või vali see kalendrist.",
            )
            self.pump_date_control.setFocus(Qt.OtherFocusReason)
            return
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
        self.preview.pumpSelected.connect(self.pump_list.setCurrentRow)
        self.preview.addPumpRequested.connect(self._add_pump)
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
        facility_status = (
            "Valmis ✓"
            if facility_count == 4 and valid_location
            else "Kontrolli asukohta"
            if facility_count == 4
            else f"{facility_count}/4 täidetud"
        )
        pump_count = len(self._pump_configs)
        pumps_valid = self._pumps_valid()
        pump_status = (
            f"{pump_count} pump"
            f"{'a' if pump_count != 1 else ''} ✓"
            if pump_count and pumps_valid
            else "Kontrolli andmeid"
            if pump_count
            else "Lisamata"
        )
        control_status = (
            "Valmis ✓"
            if values["control"]
            else "Täitmata"
        )
        pipe_count = len(self.state.topology.ports)
        pipe_status = (
            f"{pipe_count} ühendus"
            f"{'t' if pipe_count != 1 else ''} ✓"
            if pipe_count
            else "Ühenduseta"
        )
        for index, (title, status) in enumerate(
            zip(
                (
                    "01  Pumbad",
                    "02  Juhtimine",
                    "03  Rajatis ja asukoht",
                    "04  Torud",
                ),
                (
                    pump_status,
                    control_status,
                    facility_status,
                    pipe_status,
                ),
            )
        ):
            self.tabs.setTabText(index, title)
            self.tabs.setTabToolTip(index, f"{title}: {status}")

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
        pump_labels = tuple(
            " ".join(
                value for value in (pump.manufacturer, pump.mark) if value
            )
            or f"Pump {index + 1}"
            for index, pump in enumerate(self._pump_configs)
        )
        pump_ready = tuple(
            self._pump_type_is_valid(pump) for pump in self._pump_configs
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
            pump_labels=pump_labels,
            pump_ready=pump_ready,
            selected_pump=self.pump_list.currentRow(),
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
        self.pump_date_known.hide()
        self.pump_date_edit = QDateEdit(QDate.currentDate(), date_control)
        self.pump_date_edit.setDisplayFormat("dd.MM.yyyy")
        self.pump_date_edit.setEnabled(True)
        self.pump_date_control = EvelDateEditor(
            self.pump_date_edit,
            lambda: (
                self.pump_date_edit.date()
                if self.pump_date_known.isChecked()
                else None
            ),
            parent=date_control,
            on_date_selected=lambda _date: self.pump_date_known.setChecked(
                True
            ),
            on_cleared=lambda: self.pump_date_known.setChecked(False),
        )
        date_layout.addWidget(self.pump_date_control, 1)
        service_grid.addWidget(
            self._field_block(
                "Paigalduskuupäev",
                date_control,
                self.pump_form_widget,
                buddy=self.pump_date_control,
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
            lambda _checked: self.pump_date_control.sync_value(
                self.pump_date_edit.date()
                if self.pump_date_known.isChecked()
                else None
            )
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
        self.preview.set_selected_pump(row)
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
            self.pump_date_edit.setEnabled(True)
            self.pump_date_control.sync_value(
                self.pump_date_edit.date()
                if pump.install_date is not None
                else None
            )
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
