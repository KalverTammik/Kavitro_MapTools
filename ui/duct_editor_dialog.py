"""Guided EVEL editor shared by water and gravity ducts."""

from __future__ import annotations

from enum import Enum
from typing import Iterable

from qgis.PyQt.QtCore import QPointF, QRectF, QSignalBlocker, Qt
from qgis.PyQt.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QPolygonF,
)
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    QgsEditorWidgetSetup,
    QgsFeature,
    QgsVariantUtils,
    QgsVectorLayer,
)

from .guided_feature_editor import (
    GuidedFeatureEditor,
    GuidedFeatureEditorError,
    GuidedFieldBinding,
)
from .light_style import apply_evel_light_style
from .icon_catalog import (
    ICON_BACK,
    ICON_CANCEL,
    ICON_CLOSE,
    ICON_NEXT,
    ICON_SAVE,
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
        ("FIRMNESS_CLASS_ID", "Määramata"),
    ),
    (DuctEditorProfile.WATER, 313, 308): (
        ("DUCT_TYPE_ID", "Peatoru"),
        ("MATERIAL_ID", "PE"),
        ("DIAMETER_TYPE_ID", "De"),
        ("DIAMETER_ID", "110"),
        ("PRESSURE_CLASS_ID", "PN10"),
        ("FIRMNESS_CLASS_ID", "Määramata"),
    ),
    (DuctEditorProfile.WATER, 314, 308): (
        ("DUCT_TYPE_ID", "Peatoru"),
        ("MATERIAL_ID", "PE"),
        ("DIAMETER_TYPE_ID", "De"),
        ("DIAMETER_ID", "110"),
        ("PRESSURE_CLASS_ID", "PN10"),
        ("FIRMNESS_CLASS_ID", "Määramata"),
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
)

HEIGHT_FLOW_FIELDS = (
    "BEGIN_Z_COORD",
    "END_Z_COORD",
    "FLOWDIRECTION",
    "LOCATION_ID",
)

MANAGEMENT_FIELDS = (
    "CONDITION_CLASS_ID",
    "USAGE_STATE",
    "INVENTORY_NR",
    "OWNER_ID",
    "LESSEE_ID",
    "BUILD_YEAR",
    "REMOVAL_YEAR",
    "ESTIMATED_SERVICE_LIFE",
    "LOCATION_ACCURACY_ID",
    "HEIGHT_ACCURACY_ID",
    "MAPPING_METHOD_ID",
    "NOTE",
)

ADVANCED_FIELDS = (
    "USAGE_PERMIT_NR",
    "USAGE_PERMIT_DATE",
    "PLAN_ID",
    "ADDRESS_ID",
    "LENGTH",
    "PRESSURE",
    "EPANET_INNER_DIAMETER",
    "EPANET_ROUGHNESS",
    "EPANET_MLOSS",
    "EPANET_STATUS_ID",
    "DUCT_FRICTION_LOSS",
)


class DuctSchematicWidget(QWidget):
    """Small live vector overview of the duct being created."""

    def __init__(
        self,
        editor: GuidedFeatureEditor,
        profile: DuctEditorProfile,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.editor = editor
        self.profile = profile
        self.setMinimumSize(300, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.editor.fieldValueChanged.connect(lambda *_: self.update())

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

        painter.setPen(QPen(QColor(0, 120, 212, 18), 1))
        x = int(card.left()) + 20
        while x < int(card.right()):
            painter.drawLine(x, int(card.top()) + 54, x, int(card.bottom()))
            x += 20
        y = int(card.top()) + 54
        while y < int(card.bottom()):
            painter.drawLine(int(card.left()), y, int(card.right()), y)
            y += 20

        self._paint_header(painter, card)
        self._paint_pipe(painter, card)

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
            "ILLUSTRATIIVNE TORUSKEEM",
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

    def _paint_pipe(self, painter: QPainter, card: QRectF) -> None:
        start = QPointF(card.left() + 45, card.bottom() - 100)
        end = QPointF(card.right() - 45, card.top() + 125)
        pipe_color = QColor(
            "#0078d4"
            if self.profile is DuctEditorProfile.WATER
            else "#0f766e"
        )

        painter.setPen(QPen(QColor(0, 0, 0, 24), 10, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(start + QPointF(2, 3), end + QPointF(2, 3))
        painter.setPen(QPen(pipe_color, 8, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(start, end)

        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(pipe_color, 3))
        painter.drawEllipse(start, 8, 8)
        painter.drawEllipse(end, 8, 8)

        flow_direction = self._flow_direction()
        if flow_direction > 0:
            self._draw_arrowhead(painter, start, end, 0.56, pipe_color)
            flow_text = "vool algusest lõppu"
        elif flow_direction < 0:
            self._draw_arrowhead(painter, end, start, 0.56, pipe_color)
            flow_text = "vool lõpust algusse"
        else:
            unknown_color = QColor("#6e7781")
            self._draw_arrowhead(
                painter,
                start,
                end,
                0.53,
                unknown_color,
                size=10.0,
            )
            self._draw_arrowhead(
                painter,
                end,
                start,
                0.53,
                unknown_color,
                size=10.0,
            )
            flow_text = "voolusuund määramata"

        material = self.editor.display_text("MATERIAL_ID")
        diameter_type = self.editor.display_text("DIAMETER_TYPE_ID")
        diameter = self.editor.display_text("DIAMETER_ID")
        descriptor = " · ".join(
            value
            for value in (diameter_type, diameter, material)
            if value and value != "—"
        )
        if not descriptor:
            descriptor = "Määra toru tehnilised andmed"

        painter.setPen(QColor("#111416"))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(9.5)
        painter.setFont(font)
        label_rect = QRectF(
            card.left() + 28,
            card.top() + 70,
            max(card.width() - 175, 115),
            34,
        )
        painter.setBrush(QColor(255, 255, 255, 225))
        painter.setPen(QPen(QColor("#d0d7de"), 1))
        painter.drawRoundedRect(label_rect, 7, 7)
        painter.setPen(QColor("#111416"))
        text_rect = label_rect.adjusted(8, 0, -8, 0)
        label_text = painter.fontMetrics().elidedText(
            descriptor,
            Qt.ElideRight,
            int(text_rect.width()),
        )
        painter.drawText(text_rect, Qt.AlignCenter, label_text)

        self._paint_endpoint_label(
            painter,
            start,
            "ALGUS",
            self.editor.display_text("BEGIN_Z_COORD"),
            align_right=False,
        )
        self._paint_endpoint_label(
            painter,
            end,
            "LÕPP",
            self.editor.display_text("END_Z_COORD"),
            align_right=True,
        )

        length_value = self.editor.value("LENGTH_2D")
        length_text = self._number_text(length_value, "m")
        painter.setPen(QColor("#57606a"))
        font.setBold(False)
        font.setPointSizeF(9.0)
        painter.setFont(font)
        painter.drawText(
            QRectF(
                card.left() + 18,
                card.bottom() - 42,
                card.width() - 36,
                20,
            ),
            Qt.AlignCenter,
            f"Pikkus {length_text}  ·  {flow_text}",
        )

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

    @staticmethod
    def _paint_endpoint_label(
        painter: QPainter,
        point: QPointF,
        title: str,
        height: str,
        *,
        align_right: bool,
    ) -> None:
        width = 100.0
        left = point.x() - width if align_right else point.x()
        top = point.y() + (13 if not align_right else -49)
        rect = QRectF(left, top, width, 36)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.setPen(QPen(QColor("#b6c2cd"), 1))
        painter.drawRoundedRect(rect, 6, 6)
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(8.0)
        painter.setFont(font)
        painter.setPen(QColor("#005a9e"))
        suffix = "" if not height or height == "—" else f"\n{height}"
        painter.drawText(rect.adjusted(5, 2, -5, -2), Qt.AlignCenter, title + suffix)

    @staticmethod
    def _number_text(value, suffix: str) -> str:
        if QgsVariantUtils.isNull(value):
            return "—"
        try:
            return f"{float(value):.2f} {suffix}"
        except (TypeError, ValueError):
            return f"{value} {suffix}"


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
        self.resize(1120, 720)
        self.setMinimumSize(900, 610)
        apply_evel_light_style(self, duct_editor=True)

        self.editor = GuidedFeatureEditor(layer, feature, parent=self)
        self._field_tabs: dict[str, int] = {}
        self._field_groups: dict[str, QGroupBox] = {}
        self._preference_diagnostics: list[str] = []
        self._build_ui()
        if self.read_only:
            for binding in self.editor.bindings():
                binding.wrapper.setEnabled(False)
        self._apply_duct_preferences()
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
        context = QLabel(
            (
                "Vaaterežiim. Toru andmeid ei saa selle projektikihi kaudu "
                "muuta."
                if self.read_only
                else (
                    "Toru atribuutide muutmine. Tehnilised ID-d, "
                    "sõlmeviited ja geomeetriast arvutatud pikkus on lukus."
                    if not self.is_new_feature
                    else "Toru tehnilised väärtused pärinevad EVEL-i "
                    "projektikihi seadistusest."
                )
            ),
            hero,
        )
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
            identification.widget.setMinimumWidth(280)
            identity_row.addWidget(identification.widget, 1)
            root.addLayout(identity_row)

        body = QHBoxLayout()
        body.setSpacing(12)

        preview_frame = QFrame(self)
        preview_frame.setObjectName("ductPreviewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.schematic = DuctSchematicWidget(
            self.editor,
            self.profile,
            preview_frame,
        )
        preview_layout.addWidget(self.schematic, 1)
        preview_layout.addWidget(self._technical_summary(preview_frame))
        preview_frame.setMinimumWidth(315)
        preview_frame.setMaximumWidth(390)
        body.addWidget(preview_frame, 3)

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
                "Materjal, läbimõõt ja konstruktsioonilised omadused.",
                pipe_fields,
            ),
            "01  Toru",
        )
        self.tabs.addTab(
            self._step_widget(
                1,
                "Kõrgused ja vool",
                "Toru otste kõrgused, paiknemine ja voolusuund.",
                HEIGHT_FLOW_FIELDS,
            ),
            "02  Kõrgused ja vool",
        )
        self.tabs.addTab(
            self._management_step(),
            "03  Haldus ja kvaliteet",
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

    def _technical_summary(self, parent: QWidget) -> QFrame:
        frame = QFrame(parent)
        frame.setObjectName("ductTechnicalCard")
        layout = QFormLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(5)
        for field_name in TECHNICAL_FIELDS:
            index = self.layer.fields().lookupField(field_name)
            if index < 0:
                continue
            label = QLabel(self.layer.attributeDisplayName(index), frame)
            value = QLabel(self._technical_value(field_name), frame)
            value.setObjectName("ductTechnicalValue")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addRow(label, value)
        return frame

    def _technical_value(self, field_name: str) -> str:
        value = self.editor.value(field_name)
        if QgsVariantUtils.isNull(value):
            return "Määramata"
        if field_name == "LENGTH_2D":
            try:
                return f"{float(value):.2f} m"
            except (TypeError, ValueError):
                pass
        return str(value)

    def _step_widget(
        self,
        tab_index: int,
        title: str,
        description: str,
        field_names: Iterable[str],
    ) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        content.setObjectName("tabContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        heading = QLabel(title, content)
        heading.setObjectName("ductStepHeading")
        layout.addWidget(heading)
        hint = QLabel(description, content)
        hint.setObjectName("ductStepHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(9)
        self._add_fields(form, field_names, tab_index, content)
        layout.addLayout(form)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _management_step(self) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        content.setObjectName("tabContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        heading = QLabel("Haldus ja kvaliteet", content)
        heading.setObjectName("ductStepHeading")
        layout.addWidget(heading)
        hint = QLabel(
            "Seisukord, omand, elukaar ja mõõdistusandmete kvaliteet.",
            content,
        )
        hint.setObjectName("ductStepHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(9)
        self._add_fields(form, MANAGEMENT_FIELDS, 2, content)
        layout.addLayout(form)

        advanced_names = [
            name for name in ADVANCED_FIELDS if self.editor.has_field(name)
        ]
        if advanced_names:
            advanced = QGroupBox("Täpsemad andmed", content)
            advanced.setCheckable(True)
            advanced.setChecked(False)
            advanced_form = QFormLayout(advanced)
            advanced_form.setFieldGrowthPolicy(
                QFormLayout.AllNonFixedFieldsGrow
            )
            self._add_fields(
                advanced_form,
                advanced_names,
                2,
                advanced,
                group=advanced,
            )
            layout.addWidget(advanced)
        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _add_fields(
        self,
        form: QFormLayout,
        field_names: Iterable[str],
        tab_index: int,
        parent: QWidget,
        *,
        group: QGroupBox | None = None,
    ) -> None:
        for field_name in field_names:
            if field_name in TECHNICAL_FIELDS or field_name in HIDDEN_SYSTEM_FIELDS:
                continue
            setup_override = (
                FLOW_DIRECTION_SETUP
                if field_name == "FLOWDIRECTION"
                else None
            )
            binding = self.editor.create_binding(
                field_name,
                parent,
                setup_override=setup_override,
            )
            if binding is None:
                continue
            binding.widget.setMinimumWidth(230)
            if field_name == "FLOWDIRECTION":
                self._configure_flow_combo(binding)
                binding.widget.setToolTip(
                    "Algusest lõppu järgib toru geomeetria suunda "
                    "BEGIN_NODE_ID → END_NODE_ID; lõpust algusse näitab "
                    "vastassuunda."
                )
            label = self._field_label(binding, parent)
            form.addRow(label, binding.widget)
            self._field_tabs[field_name] = tab_index
            if group is not None:
                self._field_groups[field_name] = group

    @staticmethod
    def _configure_flow_combo(binding: GuidedFieldBinding) -> None:
        """Localize and move QGIS's nullable ValueMap item to the top."""

        combo = binding.widget
        if not isinstance(combo, QComboBox):
            return
        current_value = binding.value()
        null_index = -1
        blocker = QSignalBlocker(combo)
        for index in range(combo.count()):
            combo.setCurrentIndex(index)
            if QgsVariantUtils.isNull(binding.wrapper.value()):
                null_index = index
                break
        if null_index >= 0:
            null_data = combo.itemData(null_index)
            combo.removeItem(null_index)
            combo.insertItem(0, "Määramata", null_data)
        binding.wrapper.setValues(current_value, [])
        del blocker

    def _apply_duct_preferences(self) -> None:
        """Apply network-specific, label-based defaults to a new duct."""

        if not self.is_new_feature:
            return
        key = (
            self.profile,
            self._integer_attribute("NETWORK_ID"),
            self._integer_attribute("NETTYPE_ID"),
        )
        preferences = DUCT_PREFERENCE_PROFILES.get(key)
        if preferences is None:
            return

        for field_name, preferred_label in preferences:
            binding = self.editor.binding(field_name)
            if binding is None or not QgsVariantUtils.isNull(binding.value()):
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
        if field_name == "FIRMNESS_CLASS_ID" and preferred_label == "SN8":
            self._preference_diagnostics.append(
                "Ringjäikuse SN8 klass puudub EVEL-i FIRMNESS_CLASS "
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
        label = QLabel(binding.label + suffix, parent)
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
                binding.widget.setFocus(Qt.OtherFocusReason)
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

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()
