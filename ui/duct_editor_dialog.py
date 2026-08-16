"""Guided EVEL editor shared by water and gravity ducts."""

from __future__ import annotations

from enum import Enum
import math
from typing import Iterable

from qgis.PyQt.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, Qt, QVariant
from qgis.PyQt.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from qgis.PyQt.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsEditorWidgetSetup,
    QgsFeature,
    QgsVariantUtils,
    QgsVectorLayer,
)

from ..layers.duct_preview import (
    DuctEndpointPreview,
    DuctPreviewContextBuilder,
)

from .guided_feature_editor import (
    GuidedFeatureEditor,
    GuidedFeatureEditorError,
    GuidedFieldBinding,
)
from .date_editor import EvelDateEditor, evel_date_editor_for_binding
from .light_style import apply_evel_light_style
from .icon_catalog import (
    ICON_BACK,
    ICON_CANCEL,
    ICON_CLOSE,
    ICON_DUCT_TAB,
    ICON_EPANET_TAB,
    ICON_FIELD_ADDRESS,
    ICON_FIELD_ASSET,
    ICON_FIELD_CONDITION,
    ICON_FIELD_DATE,
    ICON_FIELD_DIAMETER,
    ICON_FIELD_FIRMNESS,
    ICON_FIELD_HYDRAULIC_STATUS,
    ICON_FIELD_INSTALLATION,
    ICON_FIELD_LENGTH_3D,
    ICON_FIELD_MATERIAL,
    ICON_FIELD_NOTE,
    ICON_FIELD_OWNER,
    ICON_FIELD_PERMIT,
    ICON_FIELD_PRESSURE,
    ICON_FIELD_PURPOSE,
    ICON_FIELD_SERVICE_LIFE,
    ICON_FIELD_SOURCE,
    ICON_FIELD_TENANT,
    ICON_FIELD_USAGE_STATE,
    ICON_HEIGHT_ACCURACY,
    ICON_LENGTH_2D,
    ICON_LOCATION_ACCURACY,
    ICON_MANAGEMENT_TAB,
    ICON_NEXT,
    ICON_REVERSE_FLOW,
    ICON_SAVE,
    catalog_icon,
    set_catalog_icon,
)


class DuctEditorProfile(str, Enum):
    WATER = "water"
    GRAVITY = "gravity"


FLOW_DIRECTION_SETUP = QgsEditorWidgetSetup(
    "ValueMap",
    {
        "map": [
            {"Algusest lõppu (+1)": 1.0},
            {"Lõpust algusse (−1)": -1.0},
        ]
    },
)

DUCT_PREFERENCE_PROFILES = {
    (DuctEditorProfile.WATER, 312, 308): (
        ("DUCT_TYPE_ID", "Tarbijatoru"),
        ("MATERIAL_ID", "PE"),
        ("DIAMETER_TYPE_ID", "De"),
        ("DIAMETER_ID", "32"),
        ("PRESSURE_CLASS_ID", "PN10"),
        ("FIRMNESS_CLASS_ID", "SN16"),
    ),
    (DuctEditorProfile.WATER, 313, 308): (
        ("DUCT_TYPE_ID", "Peatoru"),
        ("MATERIAL_ID", "PE"),
        ("DIAMETER_TYPE_ID", "De"),
        ("DIAMETER_ID", "110"),
        ("PRESSURE_CLASS_ID", "PN10"),
        ("FIRMNESS_CLASS_ID", "SN16"),
    ),
    (DuctEditorProfile.WATER, 314, 308): (
        ("DUCT_TYPE_ID", "Peatoru"),
        ("MATERIAL_ID", "PE"),
        ("DIAMETER_TYPE_ID", "De"),
        ("DIAMETER_ID", "110"),
        ("PRESSURE_CLASS_ID", "PN10"),
        ("FIRMNESS_CLASS_ID", "SN16"),
    ),
    (DuctEditorProfile.GRAVITY, 315, 309): (
        ("DUCT_TYPE_ID", "Peatoru"),
        ("MATERIAL_ID", "PVC"),
        ("DIAMETER_TYPE_ID", "De"),
        ("DIAMETER_ID", "160"),
        ("PRESSURE_CLASS_ID", "PN10"),
        ("FIRMNESS_CLASS_ID", "SN8"),
        ("FORM_CODE_ID", "Ümmargune"),
    ),
    (DuctEditorProfile.GRAVITY, 316, 309): (
        ("DUCT_TYPE_ID", "Peatoru"),
        ("MATERIAL_ID", "PP"),
        ("DIAMETER_TYPE_ID", "De"),
        ("DIAMETER_ID", "315"),
        ("PRESSURE_CLASS_ID", "PN10"),
        ("FIRMNESS_CLASS_ID", "SN8"),
        ("FORM_CODE_ID", "Ümmargune"),
    ),
    (DuctEditorProfile.GRAVITY, 317, None): (
        ("DUCT_TYPE_ID", "Peatoru"),
        ("MATERIAL_ID", "PP"),
        ("DIAMETER_TYPE_ID", "De"),
        ("DIAMETER_ID", "250"),
        ("PRESSURE_CLASS_ID", "PN10"),
        ("FIRMNESS_CLASS_ID", "SN8"),
        ("FORM_CODE_ID", "Ümmargune"),
    ),
    (DuctEditorProfile.GRAVITY, 318, None): (
        ("DUCT_TYPE_ID", "Peatoru"),
        ("MATERIAL_ID", "PP"),
        ("DIAMETER_TYPE_ID", "De"),
        ("DIAMETER_ID", "315"),
        ("PRESSURE_CLASS_ID", "PN10"),
        ("FIRMNESS_CLASS_ID", "SN8"),
        ("FORM_CODE_ID", "Ümmargune"),
    ),
}


TECHNICAL_FIELDS = (
    "MSLINK",
    "NETWORK_ID",
    "NETTYPE_ID",
    "BEGIN_NODE_ID",
    "END_NODE_ID",
    "LENGTH_2D",
)

HIDDEN_SYSTEM_FIELDS = {
    "GEOM",
    "CREATOR",
    "CREATION_DATE",
    "UPDATED_BY",
    "UPDATE_DATE",
}

PIPE_FIELDS = (
    "DUCT_TYPE_ID",
    "MATERIAL_ID",
    "DIAMETER_TYPE_ID",
    "DIAMETER_ID",
    "PRESSURE_CLASS_ID",
    "FIRMNESS_CLASS_ID",
    "LOCATION_ID",
)

SCHEMATIC_FIELDS = (
    "BEGIN_Z_COORD",
    "END_Z_COORD",
    "FLOWDIRECTION",
    "LOCATION_ACCURACY_ID",
    "HEIGHT_ACCURACY_ID",
)

COMMON_DUCT_PREFERENCES = (
    ("LOCATION_ID", "Maa-alune"),
)

ACCURACY_DEFAULTS = (
    ("LOCATION_ACCURACY_ID", "10 cm"),
    ("HEIGHT_ACCURACY_ID", "2 cm"),
)

FIELD_WIDTH_MIN = 120
FIELD_WIDTH_MAX = 520
COMBO_WIDTH_MIN = 150
COMBO_WIDTH_MAX = 360
YEAR_FIELDS = frozenset({"BUILD_YEAR", "REMOVAL_YEAR"})
SHORT_NUMBER_FIELDS = frozenset({"ESTIMATED_SERVICE_LIFE"})
LONG_TEXT_FIELDS = frozenset({"NOTE"})

MANAGEMENT_FIELDS = (
    "CONDITION_CLASS_ID",
    "USAGE_STATE",
    "INVENTORY_NR",
    "OWNER_ID",
    "LESSEE_ID",
    "BUILD_YEAR",
    "REMOVAL_YEAR",
    "ESTIMATED_SERVICE_LIFE",
    "NOTE",
)

ADVANCED_FIELDS = (
    "USAGE_PERMIT_NR",
    "USAGE_PERMIT_DATE",
    "MAPPING_METHOD_ID",
    "ADDRESS_ID",
    "LENGTH",
)

EPANET_FIELDS = (
    "PRESSURE",
    "EPANET_INNER_DIAMETER",
    "EPANET_ROUGHNESS",
    "EPANET_MLOSS",
    "EPANET_STATUS_ID",
    "DUCT_FRICTION_LOSS",
)

UI_FIELD_LABELS = {
    "IDENTIFICATION": "Toru tähis",
    "DUCT_TYPE_ID": "Otstarve",
    "MATERIAL_ID": "Materjal",
    "DIAMETER_TYPE_ID": "Läbimõõdu tüüp",
    "DIAMETER_ID": "Läbimõõt",
    "PRESSURE_CLASS_ID": "Rõhuklass",
    "FIRMNESS_CLASS_ID": "Ringjäikus",
    "LOCATION_ID": "Paigaldusviis",
    "FORM_CODE_ID": "Kuju",
    "CONDITION_CLASS_ID": "Seisukord",
    "USAGE_STATE": "Kasutuse olek",
    "INVENTORY_NR": "Põhivara number",
    "OWNER_ID": "Omanik",
    "LESSEE_ID": "Rentnik",
    "BUILD_YEAR": "Ehitusaasta",
    "REMOVAL_YEAR": "Kasutusest eemaldamise aasta",
    "ESTIMATED_SERVICE_LIFE": "Tehniline eluiga",
    "MAPPING_METHOD_ID": "Andmeallikas",
    "NOTE": "Märkused",
    "USAGE_PERMIT_NR": "Kasutusloa number",
    "USAGE_PERMIT_DATE": "Kasutusloa kuupäev",
    "ADDRESS_ID": "Asukoha aadress",
    "LENGTH": "3D pikkus",
    "PRESSURE": "Surve",
    "EPANET_INNER_DIAMETER": "Siseläbimõõt",
    "EPANET_ROUGHNESS": "Toru karedus",
    "EPANET_MLOSS": "Kohtkao tegur",
    "EPANET_STATUS_ID": "EPANET olek",
    "DUCT_FRICTION_LOSS": "Hõõrdesurvekadu",
}

FIELD_ICON_NAMES = {
    "DUCT_TYPE_ID": ICON_FIELD_PURPOSE,
    "MATERIAL_ID": ICON_FIELD_MATERIAL,
    "DIAMETER_TYPE_ID": ICON_FIELD_DIAMETER,
    "DIAMETER_ID": ICON_FIELD_DIAMETER,
    "PRESSURE_CLASS_ID": ICON_FIELD_PRESSURE,
    "FIRMNESS_CLASS_ID": ICON_FIELD_FIRMNESS,
    "LOCATION_ID": ICON_FIELD_INSTALLATION,
    "FORM_CODE_ID": ICON_FIELD_DIAMETER,
    "CONDITION_CLASS_ID": ICON_FIELD_CONDITION,
    "USAGE_STATE": ICON_FIELD_USAGE_STATE,
    "INVENTORY_NR": ICON_FIELD_ASSET,
    "OWNER_ID": ICON_FIELD_OWNER,
    "LESSEE_ID": ICON_FIELD_TENANT,
    "BUILD_YEAR": ICON_FIELD_DATE,
    "REMOVAL_YEAR": ICON_FIELD_DATE,
    "ESTIMATED_SERVICE_LIFE": ICON_FIELD_SERVICE_LIFE,
    "MAPPING_METHOD_ID": ICON_FIELD_SOURCE,
    "NOTE": ICON_FIELD_NOTE,
    "USAGE_PERMIT_NR": ICON_FIELD_PERMIT,
    "USAGE_PERMIT_DATE": ICON_FIELD_DATE,
    "ADDRESS_ID": ICON_FIELD_ADDRESS,
    "LENGTH": ICON_FIELD_LENGTH_3D,
    "PRESSURE": ICON_FIELD_PRESSURE,
    "EPANET_INNER_DIAMETER": ICON_FIELD_DIAMETER,
    "EPANET_ROUGHNESS": ICON_FIELD_FIRMNESS,
    "EPANET_MLOSS": ICON_FIELD_PRESSURE,
    "EPANET_STATUS_ID": ICON_FIELD_HYDRAULIC_STATUS,
    "DUCT_FRICTION_LOSS": ICON_FIELD_PRESSURE,
}

FIELD_UNITS = {
    "DIAMETER_ID": "mm",
    "ESTIMATED_SERVICE_LIFE": "a",
    "LENGTH": "m",
    "PRESSURE": "bar",
    "EPANET_INNER_DIAMETER": "mm",
    "EPANET_ROUGHNESS": "mm",
    "DUCT_FRICTION_LOSS": "bar/km",
}

FULL_WIDTH_FIELDS = frozenset({"NOTE"})
RESPONSIVE_FORM_BREAKPOINT = 640


class DuctFieldRow(QWidget):
    """Icon, UI label and QGIS editor kept together during grid reflow."""

    def __init__(
        self,
        field_name: str,
        title: str,
        editor_widget: QWidget,
        icon_name: str,
        parent: QWidget | None = None,
        *,
        required: bool = False,
        tooltip: str = "",
    ) -> None:
        super().__init__(parent)
        self.field_name = field_name
        self.setObjectName("ductFieldRow")
        self.setProperty("fieldName", field_name)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.row_layout = QHBoxLayout(self)
        self.row_layout.setContentsMargins(0, 0, 0, 0)
        self.row_layout.setSpacing(8)
        self.editor_widget = editor_widget

        icon = QLabel(self)
        icon.setObjectName("ductFieldIcon")
        icon.setFixedSize(20, 24)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(catalog_icon(icon_name).pixmap(18, 18))
        self.row_layout.addWidget(icon, 0, Qt.AlignVCenter)

        suffix = " *" if required else ""
        self.title_label = QLabel(title + suffix, self)
        self.title_label.setObjectName("fieldLabel")
        self.title_label.setWordWrap(True)
        self.title_label.setBuddy(editor_widget)
        self.row_layout.addWidget(self.title_label, 0, Qt.AlignVCenter)

        self.row_layout.addWidget(editor_widget, 0, Qt.AlignVCenter)
        self.row_layout.addStretch(1)
        if tooltip:
            self.title_label.setToolTip(tooltip)
            editor_widget.setToolTip(tooltip)
        self.set_compact(False)

    def set_compact(self, compact: bool) -> None:
        self.title_label.setFixedWidth(108 if compact else 145)

    def set_full_width(self, full_width: bool) -> None:
        """Let long editors use the row while compact fields stay bounded."""

        self.row_layout.setStretch(2, 1 if full_width else 0)
        self.row_layout.setStretch(3, 0 if full_width else 1)


class DuctFieldUnitAdornment(QLabel):
    """Non-editable unit rendered inside an existing QGIS line editor."""

    def __init__(self, unit: str, editor: QLineEdit) -> None:
        super().__init__(unit, editor)
        self.editor = editor
        self.setObjectName("ductFieldUnit")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.adjustSize()
        margins = editor.textMargins()
        editor.setTextMargins(
            margins.left(),
            margins.top(),
            margins.right() + self.sizeHint().width() + 10,
            margins.bottom(),
        )
        editor.installEventFilter(self)
        editor.textChanged.connect(self._sync_visibility)
        self._sync_visibility(editor.text())

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.editor and event.type() in {
            QEvent.Resize,
            QEvent.Show,
            QEvent.StyleChange,
        }:
            self._position()
        return False

    def _sync_visibility(self, text: str) -> None:
        normalized = " ".join(str(text).split()).casefold()
        self.setVisible(
            bool(normalized)
            and normalized not in {"null", "pole määratud"}
        )
        self._position()

    def _position(self) -> None:
        hint = self.sizeHint()
        self.move(
            max(4, self.editor.width() - hint.width() - 8),
            max(0, (self.editor.height() - hint.height()) // 2),
        )


class ResponsiveFieldGrid(QWidget):
    """Reflow complete field rows without changing their editor bindings."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        maximum_columns: int = 1,
        breakpoint: int = RESPONSIVE_FORM_BREAKPOINT,
    ) -> None:
        super().__init__(parent)
        self.maximum_columns = max(1, int(maximum_columns))
        self.breakpoint = int(breakpoint)
        self._rows: list[tuple[DuctFieldRow, bool]] = []
        self._column_count = 1
        self.setObjectName("responsiveFieldGrid")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 2, 0, 0)
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(9)
        self.setProperty("columnCount", 1)

    @property
    def column_count(self) -> int:
        return self._column_count

    def add_field(self, row: DuctFieldRow, *, full_width: bool = False) -> None:
        row.set_full_width(bool(full_width))
        self._rows.append((row, bool(full_width)))
        self._relayout(self._desired_column_count())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout(self._desired_column_count(event.size().width()))

    def _desired_column_count(self, width: int | None = None) -> int:
        available = self.width() if width is None else int(width)
        if self.maximum_columns > 1 and available >= self.breakpoint:
            return self.maximum_columns
        return 1

    def _relayout(self, columns: int) -> None:
        columns = max(1, min(int(columns), self.maximum_columns))
        while self.grid.count():
            self.grid.takeAt(0)
        line = 0
        column = 0
        compact = columns > 1
        for row, full_width in self._rows:
            row.set_compact(compact)
            if columns == 1 or full_width:
                if column:
                    line += 1
                    column = 0
                self.grid.addWidget(row, line, 0, 1, columns)
                line += 1
                continue
            self.grid.addWidget(row, line, column)
            column += 1
            if column == columns:
                line += 1
                column = 0
        for index in range(self.maximum_columns):
            self.grid.setColumnStretch(index, 1 if index < columns else 0)
        self._column_count = columns
        self.setProperty("columnCount", columns)


class DuctMetricButton(QPushButton):
    """Compact icon, label and value card used by the duct preview."""

    def __init__(
        self,
        title: str,
        icon_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.metric_title = title
        self.metric_value = "Pole määratud"
        self._icon_name = icon_name
        self.setObjectName("ductMetricButton")
        self.setAutoDefault(False)
        self.setText(f"{self.metric_title}\n{self.metric_value}")

    def set_metric_value(self, value: str) -> None:
        self.metric_value = str(value).strip() or "Pole määratud"
        self.setText(f"{self.metric_title}\n{self.metric_value}")
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        enabled = self.isEnabled()
        background = QColor("#ffffff")
        border = QColor("#d8e1e8")
        if enabled and self.isDown():
            background = QColor("#e8f3fc")
            border = QColor("#0878d1")
        elif enabled and self.underMouse():
            background = QColor("#f3f9fe")
            border = QColor("#79afd3")
        if self.hasFocus():
            border = QColor("#0878d1")
        if not enabled:
            background = QColor("#f6f7f8")
            border = QColor("#d0d7de")
        painter.setBrush(background)
        painter.setPen(QPen(border, 1.5 if self.hasFocus() else 1.0))
        painter.drawRoundedRect(rect, 7, 7)

        icon_size = 25
        icon = catalog_icon(self._icon_name)
        pixmap = icon.pixmap(icon_size, icon_size)
        painter.setOpacity(1.0 if enabled else 0.55)
        painter.drawPixmap(
            11,
            int((self.height() - icon_size) / 2),
            pixmap,
        )
        painter.setOpacity(1.0)

        text_left = 45
        available_width = max(self.width() - text_left - 7, 1)
        title_font = QFont(painter.font())
        title_font.setPointSizeF(7.0)
        title_font.setBold(False)
        painter.setFont(title_font)
        painter.setPen(QColor("#6e7781") if enabled else QColor("#8c959f"))
        title = painter.fontMetrics().elidedText(
            self.metric_title,
            Qt.ElideRight,
            available_width,
        )
        painter.drawText(
            QRectF(text_left, 6, available_width, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            title,
        )

        value_font = QFont(title_font)
        value_font.setPointSizeF(9.5)
        value_font.setBold(True)
        painter.setFont(value_font)
        painter.setPen(QColor("#172033") if enabled else QColor("#6e7781"))
        value = painter.fontMetrics().elidedText(
            self.metric_value,
            Qt.ElideRight,
            available_width,
        )
        painter.drawText(
            QRectF(text_left, 22, available_width, self.height() - 25),
            Qt.AlignLeft | Qt.AlignVCenter,
            value,
        )


class DuctEndpointButton(QPushButton):
    """Clickable endpoint card with topology state and chainage."""

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.endpoint_title = title
        self.node_text = "Sõlm: —"
        self.chainage_text = "0+000.00"
        self.status_text = "Sidumata"
        self.setObjectName("ductEndpointButton")
        self.setAutoDefault(False)
        self._update_accessible_text()

    def set_endpoint(
        self,
        endpoint: DuctEndpointPreview,
        chainage: float,
    ) -> None:
        if endpoint.identification:
            identity = endpoint.identification
        elif endpoint.node_id is not None:
            identity = str(endpoint.node_id)
        else:
            identity = "—"
        self.node_text = f"Sõlm: {identity}"
        self.chainage_text = DuctPreviewWidget._chainage(chainage)
        self.status_text = endpoint.status
        self._update_accessible_text()
        self.update()

    def _update_accessible_text(self) -> None:
        marker = "●" if self.status_text != "Sidumata" else "○"
        self.setText(
            f"{self.endpoint_title}\n{self.node_text}\n"
            f"{self.chainage_text}\n{marker} {self.status_text}"
        )

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        background = QColor("#ffffff")
        border = QColor("#d8e1e8")
        if self.isEnabled() and self.isDown():
            background = QColor("#e8f3fc")
            border = QColor("#0878d1")
        elif self.isEnabled() and self.underMouse():
            background = QColor("#f5faff")
            border = QColor("#79afd3")
        if self.hasFocus():
            border = QColor("#0878d1")
        if not self.isEnabled():
            background = QColor("#f6f7f8")
        painter.setBrush(background)
        painter.setPen(QPen(border, 1.5 if self.hasFocus() else 1.0))
        painter.drawRoundedRect(rect, 7, 7)

        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(7.5)
        painter.setFont(font)
        painter.setPen(QColor("#0878d1"))
        painter.drawText(
            QRectF(9, 5, self.width() - 18, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            self.endpoint_title,
        )
        font.setBold(False)
        font.setPointSizeF(7.0)
        painter.setFont(font)
        painter.setPen(QColor("#263645"))
        painter.drawText(
            QRectF(9, 20, self.width() - 18, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            painter.fontMetrics().elidedText(
                self.node_text,
                Qt.ElideRight,
                self.width() - 18,
            ),
        )
        painter.drawText(
            QRectF(9, 34, self.width() - 18, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            self.chainage_text,
        )
        status_color = (
            QColor("#67b82e")
            if self.status_text != "Sidumata"
            else QColor("#9aa6af")
        )
        painter.setBrush(status_color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(12, 58), 3.1, 3.1)
        painter.setPen(QColor("#3f4f5c"))
        painter.drawText(
            QRectF(20, 50, self.width() - 26, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            painter.fontMetrics().elidedText(
                self.status_text,
                Qt.ElideRight,
                self.width() - 26,
            ),
        )


class DuctPreviewWidget(QWidget):
    """Small live vector overview of the duct being created."""

    def __init__(
        self,
        editor: GuidedFeatureEditor,
        profile: DuctEditorProfile,
        parent: QWidget | None = None,
        *,
        editable: bool = True,
    ) -> None:
        super().__init__(parent)
        self.editor = editor
        self.profile = profile
        self.editable = bool(editable)
        self.preview_context = DuctPreviewContextBuilder().build(
            editor.layer,
            editor.feature,
            profile,
        )
        self.setMinimumSize(380, 500)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.begin_height_button = self._endpoint_button(
            "begin",
            "Sisesta toru alguskõrgus",
            lambda: self._prompt_height("BEGIN_Z_COORD", "alguskõrgus"),
        )
        self.end_height_button = self._endpoint_button(
            "end",
            "Sisesta toru lõppkõrgus",
            lambda: self._prompt_height("END_Z_COORD", "lõppkõrgus"),
        )
        self.flow_direction_button = QPushButton("Pööra suund", self)
        self.flow_direction_button.setObjectName("ductFlowDirectionButton")
        self.flow_direction_button.setCursor(Qt.PointingHandCursor)
        self.flow_direction_button.setAutoDefault(False)
        self.flow_direction_button.setFocusPolicy(Qt.NoFocus)
        set_catalog_icon(
            self.flow_direction_button,
            ICON_REVERSE_FLOW,
            size=20,
        )
        self.flow_direction_button.clicked.connect(
            self.toggle_flow_direction
        )
        self.location_accuracy_button = self._accuracy_button(
            "Asukoha täpsus",
            "LOCATION_ACCURACY_ID",
        )
        self.height_accuracy_button = self._accuracy_button(
            "Kõrguse täpsus",
            "HEIGHT_ACCURACY_ID",
        )
        self.length_metric = DuctMetricButton(
            "Pikkus 2D",
            ICON_LENGTH_2D,
            self,
        )
        self.length_metric.setFocusPolicy(Qt.NoFocus)
        self.length_metric.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.editor.fieldValueChanged.connect(self._editor_value_changed)
        self._refresh_controls()

    def _endpoint_button(
        self,
        endpoint: str,
        tooltip: str,
        callback,
    ) -> DuctEndpointButton:
        title = "ALGUS" if endpoint == "begin" else "LÕPP"
        button = DuctEndpointButton(title, self)
        button.setProperty("endpoint", endpoint)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tooltip)
        button.setAutoDefault(False)
        button.clicked.connect(callback)
        return button

    def _accuracy_button(
        self,
        label: str,
        field_name: str,
    ) -> DuctMetricButton:
        icon_name = (
            ICON_LOCATION_ACCURACY
            if field_name == "LOCATION_ACCURACY_ID"
            else ICON_HEIGHT_ACCURACY
        )
        button = DuctMetricButton(label, icon_name, self)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(f"Vali {label.casefold()}")
        button.setAutoDefault(False)
        button.clicked.connect(
            lambda _checked=False: self._show_accuracy_menu(
                field_name,
                button,
            )
        )
        return button

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_controls()

    def _position_controls(self) -> None:
        card = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        plan, _profile, metrics = self._content_rects(card)
        screen_points = self._active_screen_points(plan)
        start = screen_points[0] if screen_points else plan.bottomLeft()
        end = screen_points[-1] if screen_points else plan.topRight()
        self._position_endpoint_button(
            self.begin_height_button,
            start,
            plan,
            prefer_left=True,
        )
        self._position_endpoint_button(
            self.end_height_button,
            end,
            plan,
            prefer_left=False,
        )
        self.flow_direction_button.setGeometry(
            int(plan.left() + 126),
            int(plan.top() + 9),
            132,
            38,
        )
        gap = 7.0
        metric_width = (metrics.width() - gap * 2) / 3
        self.location_accuracy_button.setGeometry(
            int(metrics.left()),
            int(metrics.top()),
            int(metric_width),
            int(metrics.height()),
        )
        self.height_accuracy_button.setGeometry(
            int(metrics.left() + metric_width + gap),
            int(metrics.top()),
            int(metric_width),
            int(metrics.height()),
        )
        self.length_metric.setGeometry(
            int(metrics.left() + (metric_width + gap) * 2),
            int(metrics.top()),
            int(metric_width),
            int(metrics.height()),
        )

    @staticmethod
    def _position_endpoint_button(
        button: QPushButton,
        point: QPointF,
        bounds: QRectF,
        *,
        prefer_left: bool,
    ) -> None:
        width = 112
        height = 70
        x = (
            bounds.left() + 8
            if prefer_left
            else bounds.right() - width - 8
        )
        y = point.y() - height / 2
        y = max(bounds.top() + 54, min(y, bounds.bottom() - height - 6))
        button.setGeometry(int(x), int(y), width, height)

    def _editor_value_changed(self, _field_name: str, _value) -> None:
        self._refresh_controls()
        self._position_controls()
        self.update()

    def _refresh_controls(self) -> None:
        self.begin_height_button.set_endpoint(
            self.preview_context.begin,
            0.0,
        )
        self.end_height_button.set_endpoint(
            self.preview_context.end,
            self._length_2d(),
        )
        self._update_endpoint_tooltip(
            self.begin_height_button,
            "alguskõrgus",
            "BEGIN_Z_COORD",
            self.preview_context.begin,
        )
        self._update_endpoint_tooltip(
            self.end_height_button,
            "lõppkõrgus",
            "END_Z_COORD",
            self.preview_context.end,
        )
        self.begin_height_button.setEnabled(
            self._binding_is_editable("BEGIN_Z_COORD")
        )
        self.end_height_button.setEnabled(
            self._binding_is_editable("END_Z_COORD")
        )
        self.flow_direction_button.setEnabled(
            self._binding_is_editable("FLOWDIRECTION")
        )
        self.flow_direction_button.setToolTip(
            f"Praegu: {self.flow_direction_text()}. "
            "Klõpsa voolusuuna pööramiseks."
        )
        self.location_accuracy_button.set_metric_value(
            self._accuracy_value_text("LOCATION_ACCURACY_ID")
        )
        self.height_accuracy_button.set_metric_value(
            self._accuracy_value_text("HEIGHT_ACCURACY_ID")
        )
        self.location_accuracy_button.setEnabled(
            self._binding_is_editable("LOCATION_ACCURACY_ID")
        )
        self.height_accuracy_button.setEnabled(
            self._binding_is_editable("HEIGHT_ACCURACY_ID")
        )
        self.length_metric.set_metric_value(f"{self._length_2d():.2f} m")
        length_3d = self._length_3d()
        self.length_metric.setToolTip(
            f"Toru geomeetriast arvutatud 2D pikkus: {self._length_2d():.2f} m"
            + (
                f". Z-geomeetria 3D pikkus: {length_3d:.2f} m"
                if length_3d is not None
                else ""
            )
        )

    def _update_endpoint_tooltip(
        self,
        button: QPushButton,
        height_label: str,
        field_name: str,
        endpoint: DuctEndpointPreview,
    ) -> None:
        value = self._numeric_value(field_name)
        height = (
            f"{self._format_number(value)} m"
            if value is not None
            else "pole määratud"
        )
        button.setToolTip(
            f"{endpoint.title} · {endpoint.status}. Praegune {height_label}: "
            f"{height}. Klõpsa kõrguse muutmiseks."
        )

    def _accuracy_value_text(self, field_name: str) -> str:
        binding = self.editor.binding(field_name)
        if binding is None or self._is_missing_lookup_value(binding.value()):
            return "Pole määratud"
        return binding.display_text().strip() or "Pole määratud"

    def _show_accuracy_menu(
        self,
        field_name: str,
        button: QPushButton,
    ) -> None:
        binding = self.editor.binding(field_name)
        if binding is None or not self._binding_is_editable(field_name):
            return
        combo = binding.widget
        if not isinstance(combo, QComboBox):
            return

        menu = QMenu(button)
        current = binding.value()
        for index in range(combo.count()):
            value = combo.itemData(index)
            label = combo.itemText(index).strip()
            if self._is_missing_lookup_value(value) or not label:
                continue
            action = menu.addAction(label)
            action.setData(value)
            action.setCheckable(True)
            action.setChecked(self._lookup_values_equal(value, current))
        if not menu.actions():
            return
        selected = menu.exec_(
            button.mapToGlobal(QPoint(0, button.height()))
        )
        if selected is not None:
            binding.wrapper.setValues(selected.data(), [])

    @staticmethod
    def _is_missing_lookup_value(value) -> bool:
        if QgsVariantUtils.isNull(value):
            return True
        try:
            return int(value) == 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _lookup_values_equal(first, second) -> bool:
        if QgsVariantUtils.isNull(first) or QgsVariantUtils.isNull(second):
            return QgsVariantUtils.isNull(first) and QgsVariantUtils.isNull(second)
        return str(first) == str(second)

    def _binding_is_editable(self, field_name: str) -> bool:
        binding = self.editor.binding(field_name)
        return bool(
            self.editable
            and binding is not None
            and binding.widget.isEnabled()
        )

    def _prompt_height(self, field_name: str, label: str) -> None:
        binding = self.editor.binding(field_name)
        if binding is None or not self._binding_is_editable(field_name):
            return
        current = self._numeric_value(field_name)
        text, accepted = QInputDialog.getText(
            self,
            f"Toru {label}",
            "Sisesta kõrgus meetrites. Väärtuse eemaldamiseks jäta väli tühjaks.",
            text=self._format_number(current) if current is not None else "",
        )
        if not accepted:
            return
        normalized = text.strip().replace(",", ".")
        if not normalized:
            value = QVariant()
        else:
            try:
                value = float(normalized)
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Kõrgus ei ole arv",
                    "Sisesta kõrgus arvuna, näiteks 22.35.",
                )
                return
        binding.wrapper.setValues(value, [])
        if not QgsVariantUtils.isNull(value):
            self.apply_default_flow_direction(force=True)

    def apply_default_flow_direction(self, *, force: bool = False) -> None:
        binding = self.editor.binding("FLOWDIRECTION")
        if binding is None or not self._binding_is_editable("FLOWDIRECTION"):
            return
        current = self._flow_direction()
        begin_height = self._numeric_value("BEGIN_Z_COORD")
        end_height = self._numeric_value("END_Z_COORD")
        if begin_height is not None and end_height is not None:
            direction = 1.0 if begin_height <= end_height else -1.0
        elif current == 0:
            direction = 1.0
        else:
            return
        if force or current == 0:
            binding.wrapper.setValues(direction, [])

    def toggle_flow_direction(self) -> None:
        binding = self.editor.binding("FLOWDIRECTION")
        if binding is None or not self._binding_is_editable("FLOWDIRECTION"):
            return
        direction = -1.0 if self._flow_direction() > 0 else 1.0
        binding.wrapper.setValues(direction, [])

    def flow_direction_text(self) -> str:
        direction = self._flow_direction()
        if direction > 0:
            return "Vool algusest lõppu"
        if direction < 0:
            return "Vool lõpust algusse"
        return "Voolusuund määramata"

    def focus_field(self, field_name: str) -> None:
        controls = {
            "BEGIN_Z_COORD": self.begin_height_button,
            "END_Z_COORD": self.end_height_button,
            "FLOWDIRECTION": self.flow_direction_button,
            "LOCATION_ACCURACY_ID": self.location_accuracy_button,
            "HEIGHT_ACCURACY_ID": self.height_accuracy_button,
        }
        control = controls.get(field_name)
        if control is not None:
            control.setFocus(Qt.OtherFocusReason)

    def _numeric_value(self, field_name: str) -> float | None:
        value = self.editor.value(field_name)
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_number(value: float | None) -> str:
        if value is None:
            return ""
        return f"{value:g}"

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f6f7f8"))

        card = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        gradient = QLinearGradient(card.topLeft(), card.bottomRight())
        gradient.setColorAt(0.0, QColor("#ffffff"))
        gradient.setColorAt(1.0, QColor("#eef4f8"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#d0d7de"), 1))
        painter.drawRoundedRect(card, 14, 14)
        self._paint_header(painter, card)
        plan, profile, _metrics = self._content_rects(card)
        self._paint_plan(painter, plan)
        self._paint_profile(painter, profile)

    def _paint_header(self, painter: QPainter, card: QRectF) -> None:
        painter.setPen(QColor("#0078d4"))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(8.5)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        painter.setFont(font)
        painter.drawText(
            QRectF(card.left() + 18, card.top() + 13, card.width() - 36, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            "TORU RUUMILINE ÜLEVAADE",
        )

        font.setLetterSpacing(QFont.AbsoluteSpacing, 0)
        font.setPointSizeF(12.0)
        painter.setFont(font)
        painter.setPen(QColor("#111416"))
        title = (
            "Veetoru"
            if self.profile is DuctEditorProfile.WATER
            else "Isevoolne toru"
        )
        painter.drawText(
            QRectF(card.left() + 18, card.top() + 31, card.width() - 36, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            title,
        )

    def _content_rects(
        self,
        card: QRectF,
    ) -> tuple[QRectF, QRectF, QRectF]:
        metrics = QRectF(
            card.left() + 10,
            card.bottom() - 62,
            card.width() - 20,
            52,
        )
        profile_height = 146 if self._profile_points() else 40
        profile = QRectF(
            card.left() + 10,
            metrics.top() - profile_height - 8,
            card.width() - 20,
            profile_height,
        )
        plan = QRectF(
            card.left() + 10,
            card.top() + 58,
            card.width() - 20,
            profile.top() - card.top() - 66,
        )
        return plan, profile, metrics

    @staticmethod
    def _plan_viewport(plan: QRectF) -> QRectF:
        return plan.adjusted(18, 57, -18, -18)

    def _active_screen_points(self, plan: QRectF) -> list[QPointF]:
        mapper = self._coordinate_mapper(self._plan_viewport(plan))
        return [
            mapper(x, y) for x, y in self.preview_context.active_points
        ]

    def _coordinate_mapper(self, viewport: QRectF):
        all_points = list(self.preview_context.active_points)
        for line in self.preview_context.background_lines:
            all_points.extend(line)
        all_points.extend(self.preview_context.background_nodes)
        if not all_points:
            return lambda _x, _y: viewport.center()
        xs = [point[0] for point in all_points]
        ys = [point[1] for point in all_points]
        minimum_x, maximum_x = min(xs), max(xs)
        minimum_y, maximum_y = min(ys), max(ys)
        span_x = max(maximum_x - minimum_x, 1e-9)
        span_y = max(maximum_y - minimum_y, 1e-9)
        scale = min(viewport.width() / span_x, viewport.height() / span_y)
        scale *= 0.88
        center_x = (minimum_x + maximum_x) / 2
        center_y = (minimum_y + maximum_y) / 2
        screen_center = viewport.center()

        def map_point(x: float, y: float) -> QPointF:
            return QPointF(
                screen_center.x() + (x - center_x) * scale,
                screen_center.y() - (y - center_y) * scale,
            )

        return map_point

    def _paint_plan(self, painter: QPainter, plan: QRectF) -> None:
        painter.setBrush(QColor("#fbfdff"))
        painter.setPen(QPen(QColor("#d8e1e8"), 1))
        painter.drawRoundedRect(plan, 9, 9)
        painter.save()
        painter.setClipRect(plan.adjusted(1, 1, -1, -1))
        mapper = self._coordinate_mapper(self._plan_viewport(plan))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(
            QPen(QColor("#d9e3eb"), 1.4, Qt.SolidLine, Qt.RoundCap)
        )
        for line in self.preview_context.background_lines:
            self._draw_polyline(
                painter,
                [mapper(x, y) for x, y in line],
            )
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#c5d2dc"), 1.1))
        for x_value, y_value in self.preview_context.background_nodes:
            painter.drawEllipse(mapper(x_value, y_value), 3.5, 3.5)

        points = self._active_screen_points(plan)
        if len(points) < 2:
            painter.setPen(QColor("#6e7781"))
            painter.drawText(
                self._plan_viewport(plan),
                Qt.AlignCenter,
                "Toru geomeetria puudub",
            )
            painter.restore()
            self._paint_bearing_card(painter, plan)
            return
        pipe_color = QColor(
            "#0078d4"
            if self.profile is DuctEditorProfile.WATER
            else "#0f766e"
        )
        painter.setPen(QPen(QColor(0, 0, 0, 24), 10, Qt.SolidLine, Qt.RoundCap))
        self._draw_polyline(
            painter,
            [point + QPointF(2, 3) for point in points],
        )
        painter.setPen(QPen(pipe_color, 8, Qt.SolidLine, Qt.RoundCap))
        self._draw_polyline(painter, points)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(pipe_color, 3))
        painter.drawEllipse(points[0], 7, 7)
        painter.drawEllipse(points[-1], 7, 7)
        flow_direction = self._flow_direction()
        if flow_direction > 0:
            self._draw_flow_arrow(painter, points, pipe_color)
        elif flow_direction < 0:
            self._draw_flow_arrow(painter, list(reversed(points)), pipe_color)
        else:
            unknown_color = QColor("#6e7781")
            self._draw_flow_arrow(painter, points, unknown_color, size=10.0)
            self._draw_flow_arrow(
                painter,
                list(reversed(points)),
                unknown_color,
                size=10.0,
            )
        painter.restore()
        self._paint_bearing_card(painter, plan)

    @staticmethod
    def _draw_polyline(
        painter: QPainter,
        points: list[QPointF],
    ) -> None:
        if len(points) < 2:
            return
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.drawPath(path)

    def _draw_flow_arrow(
        self,
        painter: QPainter,
        points: list[QPointF],
        color: QColor,
        *,
        size: float = 14.0,
    ) -> None:
        segment = self._middle_segment(points)
        if segment is None:
            return
        start, end, fraction = segment
        self._draw_arrowhead(
            painter,
            start,
            end,
            fraction,
            color,
            size=size,
        )

    @staticmethod
    def _middle_segment(
        points: list[QPointF],
    ) -> tuple[QPointF, QPointF, float] | None:
        if len(points) < 2:
            return None
        lengths = [
            math.hypot(end.x() - start.x(), end.y() - start.y())
            for start, end in zip(points, points[1:])
        ]
        total = sum(lengths)
        if total <= 0:
            return None
        target = total / 2
        walked = 0.0
        for start, end, length in zip(points, points[1:], lengths):
            if length > 0 and walked + length >= target:
                return start, end, (target - walked) / length
            walked += length
        return points[-2], points[-1], 1.0

    def _paint_bearing_card(self, painter: QPainter, plan: QRectF) -> None:
        rect = QRectF(plan.left() + 9, plan.top() + 9, 108, 38)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#c7d5df"), 1))
        painter.drawRoundedRect(rect, 7, 7)
        bearing = self._flow_bearing()
        painter.setPen(QColor("#0078d4"))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(9.0)
        painter.setFont(font)
        value = "—" if bearing is None else self._bearing_text(bearing)
        painter.drawText(
            rect.adjusted(9, 3, -5, -15),
            Qt.AlignLeft | Qt.AlignVCenter,
            value,
        )
        font.setBold(False)
        font.setPointSizeF(7.0)
        painter.setFont(font)
        painter.setPen(QColor("#6e7781"))
        painter.drawText(
            rect.adjusted(9, 19, -5, -2),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Voolu suund",
        )

    def _flow_bearing(self) -> float | None:
        points = self.preview_context.active_points
        if len(points) < 2:
            return None
        start = points[0]
        end = points[-1]
        if self._flow_direction() < 0:
            start, end = end, start
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        if math.hypot(delta_x, delta_y) <= 0:
            return None
        return (math.degrees(math.atan2(delta_x, delta_y)) + 360) % 360

    @staticmethod
    def _bearing_text(bearing: float) -> str:
        directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        direction = directions[int((bearing + 22.5) // 45) % 8]
        return f"{direction} {bearing:.0f}°"

    def _profile_points(self) -> tuple[tuple[float, float], ...]:
        if self.preview_context.has_z_geometry:
            profile = list(self.preview_context.z_profile)
            begin = self._numeric_value("BEGIN_Z_COORD")
            end = self._numeric_value("END_Z_COORD")
            if begin is not None:
                profile[0] = (profile[0][0], begin)
            if end is not None:
                profile[-1] = (profile[-1][0], end)
            return tuple(profile)
        begin = self._numeric_value("BEGIN_Z_COORD")
        end = self._numeric_value("END_Z_COORD")
        length = self._length_2d()
        if begin is None or end is None or length <= 0:
            return ()
        return ((0.0, begin), (length, end))

    def _paint_profile(self, painter: QPainter, rect: QRectF) -> None:
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#d8e1e8"), 1))
        painter.drawRoundedRect(rect, 8, 8)
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(7.5)
        painter.setFont(font)
        painter.setPen(QColor("#0078d4"))
        painter.drawText(
            rect.adjusted(10, 5, -10, -5),
            Qt.AlignLeft | Qt.AlignTop,
            "PIKIPROFIIL",
        )
        profile = self._profile_points()
        if not profile:
            font.setBold(False)
            font.setPointSizeF(8.5)
            painter.setFont(font)
            painter.setPen(QColor("#6e7781"))
            painter.drawText(
                rect.adjusted(98, 0, -10, 0),
                Qt.AlignLeft | Qt.AlignVCenter,
                "Kõrgusandmed puuduvad",
            )
            return

        graph = rect.adjusted(15, 36, -100, -27)
        maximum_chainage = max(profile[-1][0], 1e-9)
        elevations = [point[1] for point in profile]
        minimum_z = min(elevations)
        maximum_z = max(elevations)
        padding = max((maximum_z - minimum_z) * 0.2, 0.5)
        low = minimum_z - padding
        high = maximum_z + padding

        def graph_point(chainage: float, elevation: float) -> QPointF:
            return QPointF(
                graph.left() + chainage / maximum_chainage * graph.width(),
                graph.bottom()
                - (elevation - low) / (high - low) * graph.height(),
            )

        font.setBold(False)
        font.setPointSizeF(6.5)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#d8e1e8"), 1, Qt.DashLine))
        reference_y = graph.bottom() - graph.height() * 0.32
        painter.drawLine(
            QPointF(graph.left(), reference_y),
            QPointF(graph.right(), reference_y),
        )
        painter.setPen(QPen(QColor("#98a6b3"), 1))
        painter.drawLine(graph.bottomLeft(), graph.bottomRight())
        painter.drawLine(
            QPointF(graph.left(), graph.bottom()),
            QPointF(graph.left(), graph.bottom() + 4),
        )
        painter.drawLine(
            QPointF(graph.right(), graph.bottom()),
            QPointF(graph.right(), graph.bottom() + 4),
        )
        painter.setPen(QColor("#6e7781"))
        painter.drawText(
            QRectF(graph.left() - 4, graph.bottom() + 5, 64, 13),
            Qt.AlignLeft | Qt.AlignVCenter,
            self._chainage(0.0),
        )
        painter.drawText(
            QRectF(graph.right() - 68, graph.bottom() + 5, 68, 13),
            Qt.AlignRight | Qt.AlignVCenter,
            self._chainage(maximum_chainage),
        )
        painter.drawText(
            QRectF(
                graph.center().x() - 42,
                graph.bottom() + 5,
                84,
                13,
            ),
            Qt.AlignCenter,
            "Ketaaž (m)",
        )

        screen_points = [graph_point(*point) for point in profile]
        pipe_color = QColor(
            "#0078d4"
            if self.profile is DuctEditorProfile.WATER
            else "#0f766e"
        )
        painter.setPen(QPen(pipe_color, 2.5, Qt.SolidLine, Qt.RoundCap))
        self._draw_polyline(painter, screen_points)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(pipe_color, 2))
        painter.drawEllipse(screen_points[0], 4, 4)
        painter.drawEllipse(screen_points[-1], 4, 4)
        self._paint_profile_elevation_label(
            painter,
            graph,
            screen_points[0],
            profile[0][1],
            align_right=False,
        )
        self._paint_profile_elevation_label(
            painter,
            graph,
            screen_points[-1],
            profile[-1][1],
            align_right=True,
        )

        delta = profile[-1][1] - profile[0][1]
        summary_rect = QRectF(
            rect.right() - 90,
            rect.top() + 8,
            82,
            rect.height() - 16,
        )
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#d8e1e8"), 1))
        painter.drawRoundedRect(summary_rect, 7, 7)
        painter.setPen(QPen(QColor("#e1e7ec"), 1))
        separator_y = summary_rect.center().y()
        painter.drawLine(
            QPointF(summary_rect.left() + 10, separator_y),
            QPointF(summary_rect.right() - 10, separator_y),
        )

        font.setBold(False)
        font.setPointSizeF(7.0)
        painter.setFont(font)
        painter.setPen(QColor("#6e7781"))
        painter.drawText(
            QRectF(
                summary_rect.left(),
                summary_rect.top() + 5,
                summary_rect.width(),
                15,
            ),
            Qt.AlignCenter,
            "ΔH",
        )
        font.setBold(True)
        font.setPointSizeF(10.0)
        painter.setFont(font)
        painter.setPen(QColor("#172033"))
        painter.drawText(
            QRectF(
                summary_rect.left(),
                summary_rect.top() + 20,
                summary_rect.width(),
                20,
            ),
            Qt.AlignCenter,
            f"{delta:+.2f} m",
        )
        font.setBold(False)
        font.setPointSizeF(7.0)
        painter.setFont(font)
        painter.setPen(QColor("#6e7781"))
        painter.drawText(
            QRectF(
                summary_rect.left(),
                separator_y + 4,
                summary_rect.width(),
                15,
            ),
            Qt.AlignCenter,
            "Pikkus 2D",
        )
        font.setBold(True)
        font.setPointSizeF(9.5)
        painter.setFont(font)
        painter.setPen(QColor("#172033"))
        painter.drawText(
            QRectF(
                summary_rect.left(),
                separator_y + 18,
                summary_rect.width(),
                20,
            ),
            Qt.AlignCenter,
            f"{self._length_2d():.2f} m",
        )

    @staticmethod
    def _paint_profile_elevation_label(
        painter: QPainter,
        bounds: QRectF,
        point: QPointF,
        elevation: float,
        *,
        align_right: bool,
    ) -> None:
        width = 70.0
        height = 15.0
        x_value = point.x() - width if align_right else point.x()
        x_value = max(
            bounds.left(),
            min(x_value, bounds.right() - width),
        )
        y_value = max(bounds.top() - 19, point.y() - height - 5)
        label_rect = QRectF(x_value, y_value, width, height)
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(7.0)
        painter.setFont(font)
        painter.setPen(QColor("#36566c"))
        painter.drawText(
            label_rect,
            (Qt.AlignRight if align_right else Qt.AlignLeft)
            | Qt.AlignVCenter,
            f"{elevation:+.2f} m",
        )

    def _length_2d(self) -> float:
        value = self.editor.value("LENGTH_2D")
        if not QgsVariantUtils.isNull(value):
            try:
                length = float(value)
                if length >= 0:
                    return length
            except (TypeError, ValueError):
                pass
        return max(self.preview_context.length_2d, 0.0)

    def _length_3d(self) -> float | None:
        profile = self.preview_context.z_profile
        if len(profile) < 2:
            return None
        return sum(
            math.hypot(end[0] - start[0], end[1] - start[1])
            for start, end in zip(profile, profile[1:])
        )

    @staticmethod
    def _chainage(value: float) -> str:
        value = max(float(value), 0.0)
        kilometres = int(value // 1000)
        metres = value - kilometres * 1000
        return f"{kilometres}+{metres:06.2f}"

    def _flow_direction(self) -> int:
        value = self.editor.value("FLOWDIRECTION")
        if QgsVariantUtils.isNull(value):
            return 0
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0
        if numeric > 0:
            return 1
        if numeric < 0:
            return -1
        return 0

    @staticmethod
    def _draw_arrowhead(
        painter: QPainter,
        start: QPointF,
        end: QPointF,
        fraction: float,
        color: QColor,
        *,
        size: float = 14.0,
    ) -> None:
        direction = end - start
        length = max(
            (direction.x() ** 2 + direction.y() ** 2) ** 0.5,
            1.0,
        )
        unit = QPointF(direction.x() / length, direction.y() / length)
        normal = QPointF(-unit.y(), unit.x())
        center = start + direction * fraction
        arrow_tip = center + unit * size
        wing = size * 0.48
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(
            QPolygonF(
                [
                    arrow_tip,
                    center - unit * wing + normal * wing,
                    center - unit * wing - normal * wing,
                ]
            )
        )

# Backwards-compatible public name for callers that used the earlier widget.
DuctSchematicWidget = DuctPreviewWidget


class DuctEditorDialog(QDialog):
    """Consistent EVEL creation dialog for both supported duct models."""

    def __init__(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        profile: DuctEditorProfile,
        parent: QWidget | None = None,
        *,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self.layer = layer
        self.feature = feature
        self.profile = DuctEditorProfile(profile)
        self.read_only = bool(read_only)
        self.is_new_feature = self._is_new_edit_buffer_feature()
        self.setObjectName("evelDuctEditorDialog")
        self.setWindowTitle(
            "Veetoru andmed"
            if self.profile is DuctEditorProfile.WATER
            else f"{layer.name()} — toru andmed"
        )
        self.resize(1240, 780)
        self.setMinimumSize(1050, 650)
        apply_evel_light_style(self, duct_editor=True)

        self.editor = GuidedFeatureEditor(layer, feature, parent=self)
        self._field_tabs: dict[str, int] = {}
        self._field_groups: dict[str, QGroupBox] = {}
        self._field_rows: dict[str, DuctFieldRow] = {}
        self._form_grids: dict[str, ResponsiveFieldGrid] = {}
        self._date_editors: dict[str, EvelDateEditor] = {}
        self._unit_adornments: list[DuctFieldUnitAdornment] = []
        self._preference_diagnostics: list[str] = []
        self._build_ui()
        if self.read_only:
            for binding in self.editor.bindings():
                binding.wrapper.setEnabled(False)
        self.schematic._refresh_controls()
        self._apply_duct_preferences()
        self._apply_accuracy_defaults()
        self._apply_field_presentation()
        if not self.read_only:
            self.schematic.apply_default_flow_direction(
                force=self.is_new_feature,
            )
        self._show_preference_diagnostics()
        self._update_navigation()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        hero = QFrame(self)
        hero.setObjectName("ductHeroFrame")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(12, 7, 12, 9)
        hero_layout.setSpacing(16)
        title_block = QVBoxLayout()
        title = QLabel(
            self._hero_title(),
            hero,
        )
        title.setObjectName("ductTitle")
        title_block.addWidget(title)
        context_text = self._hero_context()
        if context_text:
            context = QLabel(context_text, hero)
            context.setObjectName("ductContext")
            title_block.addWidget(context)
        hero_layout.addLayout(title_block, 1)
        layer_label = QLabel(f"Kiht: {self.layer.name()}", hero)
        layer_label.setObjectName("ductLayerBadge")
        hero_layout.addWidget(layer_label, 0, Qt.AlignTop)
        root.addWidget(hero)

        identification = self.editor.create_binding(
            "IDENTIFICATION",
            hero,
        )
        if identification is not None:
            self._field_tabs["IDENTIFICATION"] = 0
            identity_row = QHBoxLayout()
            identity_label = self._field_label(identification, hero)
            identity_row.addWidget(identity_label)
            self._apply_field_width(identification)
            identity_row.addWidget(identification.widget)
            identity_row.addStretch(1)
            root.addLayout(identity_row)

        self._create_schematic_bindings()

        body = QHBoxLayout()
        body.setSpacing(12)

        preview_frame = QFrame(self)
        preview_frame.setObjectName("ductPreviewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.schematic = DuctPreviewWidget(
            self.editor,
            self.profile,
            preview_frame,
            editable=not self.read_only,
        )
        preview_layout.addWidget(self.schematic, 1)
        preview_frame.setMinimumWidth(400)
        preview_frame.setMaximumWidth(480)
        body.addWidget(preview_frame, 4)

        editor_frame = QFrame(self)
        editor_frame.setObjectName("ductEditorFrame")
        editor_layout = QVBoxLayout(editor_frame)
        editor_layout.setContentsMargins(12, 10, 12, 10)
        editor_layout.setSpacing(8)

        self.notice_label = QLabel(editor_frame)
        self.notice_label.setObjectName("ductNoticeLabel")
        self.notice_label.setWordWrap(True)
        self.notice_label.hide()
        editor_layout.addWidget(self.notice_label)

        self.error_label = QLabel(editor_frame)
        self.error_label.setObjectName("ductErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        editor_layout.addWidget(self.error_label)

        self.tabs = QTabWidget(editor_frame)
        self.tabs.tabBar().setExpanding(True)
        self.tabs.tabBar().setElideMode(Qt.ElideNone)
        pipe_fields = list(PIPE_FIELDS)
        if self.profile is DuctEditorProfile.GRAVITY:
            pipe_fields.append("FORM_CODE_ID")
        self.tabs.addTab(
            self._step_widget(
                0,
                "Toru põhiandmed",
                "Materjal, läbimõõt, paiknemine ja konstruktsioonilised omadused.",
                pipe_fields,
                ICON_DUCT_TAB,
                grid_name="pipe",
            ),
            catalog_icon(ICON_DUCT_TAB),
            "01  Toru",
        )
        self.tabs.addTab(
            self._management_step(),
            catalog_icon(ICON_MANAGEMENT_TAB),
            "02  Haldus ja kvaliteet",
        )
        epanet_step = self._epanet_step()
        if epanet_step is not None:
            self.tabs.addTab(
                epanet_step,
                catalog_icon(ICON_EPANET_TAB),
                "03  EPANET",
            )
        self.tabs.currentChanged.connect(self._update_navigation)
        editor_layout.addWidget(self.tabs, 1)
        body.addWidget(editor_frame, 7)
        root.addLayout(body, 1)

        footer = QHBoxLayout()
        self.cancel_button = QPushButton(
            "Sulge" if self.read_only else (
                "Loobu" if not self.is_new_feature else "Tühista"
            ),
            self,
        )
        self.cancel_button.setObjectName("cancelButton")
        set_catalog_icon(self.cancel_button, ICON_CANCEL)
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)
        footer.addStretch(1)
        self.back_button = QPushButton("Tagasi", self)
        set_catalog_icon(self.back_button, ICON_BACK)
        self.back_button.clicked.connect(self._previous_step)
        footer.addWidget(self.back_button)
        self.next_button = QPushButton("Edasi", self)
        set_catalog_icon(self.next_button, ICON_NEXT)
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self._next_step)
        footer.addWidget(self.next_button)
        root.addLayout(footer)

    def _create_schematic_bindings(self) -> None:
        for field_name in SCHEMATIC_FIELDS:
            binding = self.editor.create_binding(
                field_name,
                self,
                setup_override=(
                    FLOW_DIRECTION_SETUP
                    if field_name == "FLOWDIRECTION"
                    else None
                ),
            )
            if binding is None:
                continue
            binding.widget.hide()
            self._field_tabs[field_name] = 0

    def _step_widget(
        self,
        tab_index: int,
        title: str,
        description: str,
        field_names: Iterable[str],
        icon_name: str,
        *,
        grid_name: str,
        info_text: str = "",
    ) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        content.setObjectName("tabContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(
            self._section_header(
                title,
                description,
                icon_name,
                content,
                info_text=info_text,
            )
        )
        form = ResponsiveFieldGrid(content)
        self._form_grids[grid_name] = form
        self._add_fields(form, field_names, tab_index, content)
        layout.addWidget(form)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _section_header(
        title: str,
        description: str,
        icon_name: str,
        parent: QWidget,
        *,
        info_text: str = "",
    ) -> QWidget:
        header = QWidget(parent)
        header.setObjectName("ductSectionHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(10)

        icon = QLabel(header)
        icon.setObjectName("ductSectionIcon")
        icon.setFixedSize(24, 28)
        icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        icon.setPixmap(catalog_icon(icon_name).pixmap(21, 21))
        header_layout.addWidget(icon, 0, Qt.AlignTop)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(2)
        heading = QLabel(title, header)
        heading.setObjectName("ductStepHeading")
        copy.addWidget(heading)
        hint = QLabel(description, header)
        hint.setObjectName("ductStepHint")
        hint.setWordWrap(True)
        copy.addWidget(hint)
        header_layout.addLayout(copy, 1)

        if info_text:
            info = QFrame(header)
            info.setObjectName("ductInfoCard")
            info.setMaximumWidth(230)
            info_layout = QHBoxLayout(info)
            info_layout.setContentsMargins(10, 8, 10, 8)
            info_layout.setSpacing(7)
            info_icon = QLabel("ⓘ", info)
            info_icon.setObjectName("ductInfoIcon")
            info_layout.addWidget(info_icon, 0, Qt.AlignTop)
            info_copy = QLabel(info_text, info)
            info_copy.setObjectName("ductInfoText")
            info_copy.setWordWrap(True)
            info_layout.addWidget(info_copy, 1)
            header_layout.addWidget(info, 0, Qt.AlignTop)
        return header

    def _management_step(self) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        content.setObjectName("tabContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(
            self._section_header(
                "Haldus ja kvaliteet",
                "Seisukord, omand, elukaar ja mõõdistusandmete kvaliteet.",
                ICON_MANAGEMENT_TAB,
                content,
            )
        )
        form = ResponsiveFieldGrid(content, maximum_columns=2)
        self._form_grids["management"] = form
        self._add_fields(form, MANAGEMENT_FIELDS, 1, content)
        layout.addWidget(form)

        advanced_names = [
            name for name in ADVANCED_FIELDS if self.editor.has_field(name)
        ]
        if advanced_names:
            advanced = QGroupBox("Täpsemad andmed", content)
            advanced.setObjectName("ductAdvancedGroup")
            advanced.setCheckable(True)
            advanced.setChecked(False)
            advanced_layout = QVBoxLayout(advanced)
            advanced_layout.setContentsMargins(10, 12, 10, 10)
            advanced_form = ResponsiveFieldGrid(
                advanced,
                maximum_columns=2,
            )
            self._form_grids["advanced"] = advanced_form
            advanced_form.setVisible(False)
            advanced.toggled.connect(advanced_form.setVisible)
            self._add_fields(
                advanced_form,
                advanced_names,
                1,
                advanced,
                group=advanced,
            )
            advanced_layout.addWidget(advanced_form)
            layout.addWidget(advanced)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _epanet_step(self) -> QScrollArea | None:
        field_names = [
            name for name in EPANET_FIELDS if self.editor.has_field(name)
        ]
        if not field_names:
            return None
        return self._step_widget(
            2,
            "EPANET ja hüdraulika",
            "Võrguarvutuse lähteandmed ja hüdraulilised tulemused.",
            field_names,
            ICON_EPANET_TAB,
            grid_name="epanet",
            info_text=(
                "Arvutusparameetrid\n"
                "Väärtuste päritolu märgistus lisatakse pärast "
                "mudelireeglite kinnitamist."
            ),
        )

    def _add_fields(
        self,
        form: ResponsiveFieldGrid,
        field_names: Iterable[str],
        tab_index: int,
        parent: QWidget,
        *,
        group: QGroupBox | None = None,
    ) -> None:
        for field_name in field_names:
            if field_name in TECHNICAL_FIELDS or field_name in HIDDEN_SYSTEM_FIELDS:
                continue
            binding = self.editor.create_binding(
                field_name,
                parent,
            )
            if binding is None:
                continue
            self._apply_field_width(binding)
            presentation_widget: QWidget = binding.widget
            date_control = evel_date_editor_for_binding(binding, parent)
            if date_control is not None:
                date_control.setMinimumWidth(binding.widget.minimumWidth())
                date_control.setMaximumWidth(binding.widget.maximumWidth())
                date_control.setProperty(
                    "evelPreferredFieldWidth",
                    binding.widget.property("evelPreferredFieldWidth"),
                )
                self._date_editors[field_name] = date_control
                presentation_widget = date_control
            field_comment = binding.wrapper.field().comment().strip()
            row = DuctFieldRow(
                field_name,
                UI_FIELD_LABELS.get(field_name, binding.label),
                presentation_widget,
                FIELD_ICON_NAMES.get(field_name, ICON_FIELD_SOURCE),
                parent,
                required=binding.required,
                tooltip=field_comment,
            )
            form.add_field(
                row,
                full_width=field_name in FULL_WIDTH_FIELDS,
            )
            self._field_rows[field_name] = row
            self._field_tabs[field_name] = tab_index
            if group is not None:
                self._field_groups[field_name] = group

    def _apply_field_width(self, binding: GuidedFieldBinding) -> None:
        width = self._preferred_field_width(binding)
        widget = binding.widget
        # Preserve a compact responsive floor, but do not let Qt collapse
        # short editors below the width calculated from their real content.
        # Wider free-text fields may still contract on a narrow layout.
        widget.setMinimumWidth(min(width, 160))
        widget.setMaximumWidth(width)
        policy = widget.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Preferred)
        widget.setSizePolicy(policy)
        widget.setProperty("evelPreferredFieldWidth", width)

    def _preferred_field_width(self, binding: GuidedFieldBinding) -> int:
        widget = binding.widget
        field = self.layer.fields()[binding.field_index]
        metrics = widget.fontMetrics()
        combo = self._widget_or_child(widget, QComboBox)
        if combo is not None:
            content_width = max(
                (
                    metrics.horizontalAdvance(combo.itemText(index))
                    for index in range(combo.count())
                ),
                default=0,
            )
            content_width = max(
                content_width,
                metrics.horizontalAdvance("Pole määratud"),
            )
            return self._bounded_width(
                content_width + 58,
                COMBO_WIDTH_MIN,
                COMBO_WIDTH_MAX,
            )

        if binding.field_name in YEAR_FIELDS:
            # The special null text is longer than a four-digit year and the
            # spin controls still need their own column.
            return 160
        if binding.field_name in SHORT_NUMBER_FIELDS:
            return 140
        if binding.field_name in LONG_TEXT_FIELDS:
            return 480
        if (
            self._widget_or_child(widget, QDateEdit) is not None
            or self._widget_or_child(widget, QDateTimeEdit) is not None
        ):
            return 170
        if (
            self._widget_or_child(widget, QPlainTextEdit) is not None
            or self._widget_or_child(widget, QTextEdit) is not None
        ):
            return 480
        if self._widget_or_child(widget, QAbstractSpinBox) is not None:
            return 150

        type_name = field.typeName().strip().casefold()
        if any(
            token in type_name
            for token in ("int", "numeric", "decimal", "double", "real")
        ):
            return 150

        line_edit = self._widget_or_child(widget, QLineEdit)
        if line_edit is not None:
            declared_length = int(field.length() or 0)
            character_count = declared_length if declared_length > 0 else 32
            character_count = max(10, min(character_count, 60))
            return self._bounded_width(
                metrics.horizontalAdvance("0" * character_count) + 34,
                180,
                FIELD_WIDTH_MAX,
            )
        return 260

    @staticmethod
    def _widget_or_child(widget: QWidget, widget_type):
        if isinstance(widget, widget_type):
            return widget
        return widget.findChild(widget_type)

    @staticmethod
    def _bounded_width(value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(int(value), maximum))

    def _apply_field_presentation(self) -> None:
        """Apply UI-only null text, units, calendars and status colours."""

        for binding in self.editor.bindings():
            widget = binding.widget
            combo = self._widget_or_child(widget, QComboBox)
            if combo is not None:
                self._present_combo(
                    binding.field_name,
                    combo,
                    binding.value(),
                )

            date_editor = self._widget_or_child(widget, QDateTimeEdit)
            if date_editor is not None:
                date_editor.setCalendarPopup(
                    binding.field_name not in self._date_editors
                )
                field_type = (
                    self.layer.fields()[binding.field_index]
                    .typeName()
                    .strip()
                    .casefold()
                )
                date_editor.setDisplayFormat(
                    "dd.MM.yyyy"
                    if binding.field_name in self._date_editors
                    or field_type == "date"
                    else "dd.MM.yyyy HH:mm"
                )

            text_editor = self._widget_or_child(widget, QLineEdit)
            spin_editor = self._widget_or_child(widget, QAbstractSpinBox)
            if text_editor is not None:
                text_editor.setClearButtonEnabled(False)
            if text_editor is not None and spin_editor is None:
                set_null_value = getattr(text_editor, "setNullValue", None)
                if callable(set_null_value):
                    set_null_value("Pole määratud")
                    clear_value = getattr(text_editor, "clearValue", None)
                    if (
                        callable(clear_value)
                        and QgsVariantUtils.isNull(binding.value())
                    ):
                        clear_value()
                text_editor.setPlaceholderText("Pole määratud")
                unit = FIELD_UNITS.get(binding.field_name)
                if unit and combo is None:
                    self._unit_adornments.append(
                        DuctFieldUnitAdornment(unit, text_editor)
                    )
            for text_type in (QPlainTextEdit, QTextEdit):
                editor = self._widget_or_child(widget, text_type)
                if editor is not None:
                    editor.setPlaceholderText("Pole määratud")

            if spin_editor is not None:
                show_clear_button = getattr(
                    spin_editor,
                    "setShowClearButton",
                    None,
                )
                if callable(show_clear_button):
                    show_clear_button(False)
                special_text = getattr(
                    spin_editor,
                    "setSpecialValueText",
                    None,
                )
                if callable(special_text):
                    special_text("Pole määratud")
                suffix = getattr(spin_editor, "setSuffix", None)
                unit = FIELD_UNITS.get(binding.field_name)
                if callable(suffix) and unit:
                    suffix(f" {unit}")

            self._apply_field_width(binding)

    def _present_combo(
        self,
        field_name: str,
        combo: QComboBox,
        current_value,
    ) -> None:
        unit = FIELD_UNITS.get(field_name)
        null_index: int | None = None
        for index in range(combo.count()):
            value = combo.itemData(index)
            text = combo.itemText(index).strip()
            normalized_text = text.casefold()
            if (
                QgsVariantUtils.isNull(value)
                or value == ""
                or not text
                or normalized_text in {"null", "(null)", "<null>"}
            ):
                combo.setItemText(index, "Pole määratud")
                if field_name == "CONDITION_CLASS_ID":
                    combo.setItemIcon(
                        index,
                        self._condition_status_icon(
                            "Pole määratud",
                            value,
                        ),
                    )
                if null_index is None:
                    null_index = index
                continue
            if unit and not text.casefold().endswith(unit.casefold()):
                try:
                    float(text.replace(",", "."))
                except (TypeError, ValueError):
                    pass
                else:
                    combo.setItemText(index, f"{text} {unit}")

            if field_name == "CONDITION_CLASS_ID":
                combo.setItemIcon(
                    index,
                    self._condition_status_icon(
                        combo.itemText(index),
                        value,
                    ),
                )
        if field_name == "CONDITION_CLASS_ID":
            combo.setIconSize(QSize(14, 14))
        if (
            combo.currentIndex() < 0
            and null_index is not None
            and QgsVariantUtils.isNull(current_value)
        ):
            combo.setCurrentIndex(null_index)

    @classmethod
    def _condition_status_icon(cls, label: str, value) -> QIcon:
        normalized = " ".join(str(label).split()).casefold()
        if any(
            token in normalized
            for token in ("väga hea", "hea", "suurepärane")
        ):
            color = "#2da44e"
        elif any(
            token in normalized
            for token in ("rahuldav", "keskmine")
        ):
            color = "#d4a72c"
        elif any(
            token in normalized
            for token in ("väga halb", "halb", "kriitiline", "puudulik")
        ):
            color = "#cf222e"
        elif "määramata" in normalized:
            color = "#8c959f"
        else:
            rating = cls._condition_numeric_rating(label, value)
            color = {
                0: "#cf222e",
                1: "#e16f24",
                2: "#d4a72c",
                3: "#7ca92d",
                4: "#2da44e",
            }.get(rating, "#8c959f")

        pixmap = QPixmap(14, 14)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(3, 3, 8, 8)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _condition_numeric_rating(label: str, value) -> int | None:
        for candidate in (label, value):
            try:
                rating = int(str(candidate).strip().split()[0])
            except (TypeError, ValueError, IndexError):
                continue
            if 0 <= rating <= 4:
                return rating
        return None

    def _apply_duct_preferences(self) -> None:
        """Apply network-specific, label-based defaults to a new duct."""

        if not self.is_new_feature:
            return
        key = (
            self.profile,
            self._integer_attribute("NETWORK_ID"),
            self._integer_attribute("NETTYPE_ID"),
        )
        preferences = (
            COMMON_DUCT_PREFERENCES
            + DUCT_PREFERENCE_PROFILES.get(key, ())
        )

        for field_name, preferred_label in preferences:
            binding = self.editor.binding(field_name)
            if binding is None or not DuctPreviewWidget._is_missing_lookup_value(
                binding.value()
            ):
                continue
            combo = binding.widget
            if not isinstance(combo, QComboBox):
                self._add_preference_diagnostic(
                    field_name,
                    preferred_label,
                    "ei ole valikloend",
                )
                continue
            matches = [
                index
                for index in range(combo.count())
                if self._normalized_label(combo.itemText(index))
                == self._normalized_label(preferred_label)
            ]
            if len(matches) != 1:
                reason = (
                    "puudub projektikihi valikutest"
                    if not matches
                    else "esineb projektikihi valikutes mitu korda"
                )
                self._add_preference_diagnostic(
                    field_name,
                    preferred_label,
                    reason,
                )
                continue
            binding.wrapper.setValues(combo.itemData(matches[0]), [])

    def _apply_accuracy_defaults(self) -> None:
        """Use the configured non-zero unknown value for new ducts."""

        if not self.is_new_feature:
            return
        for field_name, preferred_label in ACCURACY_DEFAULTS:
            binding = self.editor.binding(field_name)
            if binding is None or not DuctPreviewWidget._is_missing_lookup_value(
                binding.value()
            ):
                continue
            combo = binding.widget
            if not isinstance(combo, QComboBox):
                self._add_preference_diagnostic(
                    field_name,
                    preferred_label,
                    "ei ole valikloend",
                )
                continue
            matches = [
                index
                for index in range(combo.count())
                if self._normalized_label(combo.itemText(index))
                == self._normalized_label(preferred_label)
                and not DuctPreviewWidget._is_missing_lookup_value(
                    combo.itemData(index)
                )
            ]
            if len(matches) != 1:
                reason = (
                    "puudub projektikihi valikutest"
                    if not matches
                    else "esineb projektikihi valikutes mitu korda"
                )
                self._add_preference_diagnostic(
                    field_name,
                    preferred_label,
                    reason,
                )
                continue
            binding.wrapper.setValues(combo.itemData(matches[0]), [])

    def _is_new_edit_buffer_feature(self) -> bool:
        edit_buffer = self.layer.editBuffer()
        if edit_buffer is None:
            return False
        return self.feature.id() in edit_buffer.addedFeatures()

    def _integer_attribute(self, field_name: str) -> int | None:
        index = self.layer.fields().lookupField(field_name)
        if index < 0:
            return None
        value = self.feature.attribute(index)
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _add_preference_diagnostic(
        self,
        field_name: str,
        preferred_label: str,
        reason: str,
    ) -> None:
        index = self.layer.fields().lookupField(field_name)
        field_label = (
            self.layer.attributeDisplayName(index)
            if index >= 0
            else field_name
        )
        if field_name == "FIRMNESS_CLASS_ID" and preferred_label in {
            "SN8",
            "SN16",
        }:
            self._preference_diagnostics.append(
                f"Ringjäikuse {preferred_label} klass puudub EVEL-i "
                "FIRMNESS_CLASS "
                "referentsandmetest. Uuenda andmemudel generaatoriga."
            )
            return
        self._preference_diagnostics.append(
            f"{field_label}: eelistatud väärtus „{preferred_label}“ {reason}."
        )

    def _show_preference_diagnostics(self) -> None:
        if not self._preference_diagnostics:
            self.notice_label.hide()
            return
        self.notice_label.setText(" ".join(self._preference_diagnostics))
        self.notice_label.show()

    @staticmethod
    def _normalized_label(value: str) -> str:
        return " ".join(str(value).split()).casefold()

    @staticmethod
    def _field_label(
        binding: GuidedFieldBinding,
        parent: QWidget,
    ) -> QLabel:
        suffix = " *" if binding.required else ""
        label = QLabel(
            UI_FIELD_LABELS.get(binding.field_name, binding.label) + suffix,
            parent,
        )
        label.setObjectName("fieldLabel")
        label.setBuddy(binding.widget)
        field_comment = binding.wrapper.field().comment().strip()
        if field_comment:
            label.setToolTip(field_comment)
            binding.widget.setToolTip(field_comment)
        return label

    def _previous_step(self) -> None:
        self.tabs.setCurrentIndex(max(self.tabs.currentIndex() - 1, 0))

    def _next_step(self) -> None:
        index = self.tabs.currentIndex()
        if index < self.tabs.count() - 1:
            self.tabs.setCurrentIndex(index + 1)
            return
        self.accept()

    def _update_navigation(self, *_args) -> None:
        index = self.tabs.currentIndex()
        self.back_button.setEnabled(index > 0)
        if index == self.tabs.count() - 1:
            self.next_button.setText(
                "Sulge"
                if self.read_only
                else (
                    "Loo toru"
                    if self.is_new_feature
                    else "Salvesta muudatused"
                )
            )
            set_catalog_icon(
                self.next_button,
                ICON_CLOSE if self.read_only else ICON_SAVE,
            )
        else:
            self.next_button.setText("Edasi")
            set_catalog_icon(self.next_button, ICON_NEXT)

    def accept(self) -> None:
        if self.read_only:
            super().accept()
            return
        self.error_label.hide()
        invalid_date = next(
            (
                (field_name, control)
                for field_name, control in self._date_editors.items()
                if control.has_invalid_input()
            ),
            None,
        )
        if invalid_date is not None:
            field_name, control = invalid_date
            self._show_error(
                "Sisesta kuupäev kujul pp.kk.aaaa või vali see kalendrist."
            )
            self.tabs.setCurrentIndex(self._field_tabs.get(field_name, 0))
            group = self._field_groups.get(field_name)
            if group is not None:
                group.setChecked(True)
            control.setFocus(Qt.OtherFocusReason)
            return
        try:
            errors = self.editor.apply()
        except GuidedFeatureEditorError as error:
            self._show_error(str(error))
            return
        if errors:
            first_field = next(iter(errors))
            messages = errors[first_field]
            self._show_error(" ".join(messages))
            binding = self.editor.binding(first_field)
            if binding is not None:
                self.tabs.setCurrentIndex(
                    self._field_tabs.get(first_field, 0)
                )
                group = self._field_groups.get(first_field)
                if group is not None:
                    group.setChecked(True)
                if first_field in SCHEMATIC_FIELDS:
                    self.schematic.focus_field(first_field)
                else:
                    row = self._field_rows.get(first_field)
                    focus_widget = row.editor_widget if row is not None else binding.widget
                    focus_widget.setFocus(Qt.OtherFocusReason)
            else:
                index = self.layer.fields().lookupField(first_field)
                label = (
                    self.layer.attributeDisplayName(index)
                    if index >= 0
                    else first_field
                )
                self._show_error(
                    f"{' '.join(messages)} Välja „{label}“ ei saa "
                    "selles vaates muuta; kontrolli projektikihi "
                    "väljakonfiguratsiooni."
                )
            return
        super().accept()

    def _hero_title(self) -> str:
        if self.is_new_feature:
            return (
                "Uus veetoru"
                if self.profile is DuctEditorProfile.WATER
                else f"Uus toru · {self.layer.name()}"
            )
        mslink = self._integer_attribute("MSLINK")
        label = "Veetoru" if self.profile is DuctEditorProfile.WATER else "Toru"
        return f"{label} {mslink}" if mslink is not None else label

    def _hero_context(self) -> str:
        if self.read_only:
            return (
                "Vaaterežiim. Toru andmeid ei saa selle projektikihi kaudu "
                "muuta."
            )
        if not self.is_new_feature:
            return (
                "Toru atribuutide muutmine. Tehnilised ID-d, "
                "sõlmeviited ja geomeetriast arvutatud pikkus on lukus."
            )
        return ""

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
