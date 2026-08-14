"""Light, visual editor for one EVEL water hydrant."""

from __future__ import annotations

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsEditorWidgetSetup, QgsVariantUtils

from ..layers import HydrantContext
from ..topology import HydrantPlan, HydrantState
from .guided_feature_editor import GuidedFeatureEditor
from .light_style import apply_evel_light_style
from .icon_catalog import apply_standard_button_icons


TEXT_SETUP = QgsEditorWidgetSetup(
    "TextEdit",
    {
        "IsMultiline": False,
        "UseHtml": False,
    },
)


class HydrantSchematicWidget(QWidget):
    """A compact live illustration of the selected hydrant."""

    def __init__(
        self,
        detail_editor: GuidedFeatureEditor,
        state: HydrantState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.detail_editor = detail_editor
        self.state = state
        self.setMinimumSize(290, 410)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        detail_editor.fieldValueChanged.connect(lambda *_: self.update())

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
        self._draw_grid(painter, card)
        self._draw_header(painter, card)
        self._draw_hydrant(painter, card)
        self._draw_summary(painter, card)

    @staticmethod
    def _draw_grid(painter: QPainter, card: QRectF) -> None:
        painter.setPen(QPen(QColor(0, 120, 212, 18), 1))
        x = int(card.left()) + 20
        while x < int(card.right()):
            painter.drawLine(x, int(card.top()) + 58, x, int(card.bottom()))
            x += 20
        y = int(card.top()) + 58
        while y < int(card.bottom()):
            painter.drawLine(int(card.left()), y, int(card.right()), y)
            y += 20

    def _draw_header(self, painter: QPainter, card: QRectF) -> None:
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(8.5)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        painter.setFont(font)
        painter.setPen(QColor("#0078d4"))
        painter.drawText(
            QRectF(card.left() + 18, card.top() + 13, card.width() - 36, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            "ILLUSTRATIIVNE SKEEM",
        )
        font.setLetterSpacing(QFont.AbsoluteSpacing, 0)
        font.setPointSizeF(13)
        painter.setFont(font)
        painter.setPen(QColor("#111416"))
        painter.drawText(
            QRectF(card.left() + 18, card.top() + 31, card.width() - 36, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Tuletõrjehüdrant",
        )

    def _draw_hydrant(self, painter: QPainter, card: QRectF) -> None:
        center_x = card.center().x()
        ground_y = card.bottom() - 80
        blue = QColor("#0078d4")
        dark = QColor("#14364d")
        shadow = QColor(0, 0, 0, 28)

        painter.setPen(QPen(QColor("#8c959f"), 3))
        painter.drawLine(
            QPointF(card.left() + 34, ground_y),
            QPointF(card.right() - 34, ground_y),
        )
        painter.setPen(QPen(shadow, 24, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(
            QPointF(center_x + 3, ground_y - 5),
            QPointF(center_x + 3, ground_y - 170),
        )
        painter.setPen(QPen(blue, 22, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(
            QPointF(center_x, ground_y - 5),
            QPointF(center_x, ground_y - 170),
        )

        painter.setBrush(blue)
        painter.setPen(QPen(dark, 3))
        painter.drawRoundedRect(
            QRectF(center_x - 31, ground_y - 191, 62, 43),
            18,
            18,
        )
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(
            QPointF(center_x, ground_y - 191),
            9,
            9,
        )
        for direction in (-1, 1):
            nozzle_x = center_x + direction * 43
            painter.setPen(QPen(blue, 14, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(
                QPointF(center_x + direction * 17, ground_y - 139),
                QPointF(nozzle_x, ground_y - 139),
            )
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(dark, 3))
            painter.drawEllipse(
                QPointF(nozzle_x, ground_y - 139),
                12,
                12,
            )

        if self.state.edge_layer is not None:
            painter.setPen(QPen(QColor("#0f766e"), 8, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(
                QPointF(card.left() + 48, ground_y + 25),
                QPointF(card.right() - 48, ground_y + 25),
            )
            painter.setPen(QPen(blue, 7))
            painter.drawLine(
                QPointF(center_x, ground_y),
                QPointF(center_x, ground_y + 25),
            )

    def _draw_summary(self, painter: QPainter, card: QRectF) -> None:
        location = self.detail_editor.display_text("LOCATION_ID")
        subtype = self.detail_editor.display_text("PLUG_TYPE_ID")
        capacity = self.detail_editor.display_text("CAPACITY")
        text = " · ".join(
            value
            for value in (location, f"tüüp {subtype}", f"Q {capacity} l/s")
            if value and "—" not in value
        )
        if not text:
            text = "Määra hüdrandi tehnilised andmed"
        box = QRectF(
            card.left() + 20,
            card.bottom() - 54,
            card.width() - 40,
            34,
        )
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.setPen(QPen(QColor("#d0d7de"), 1))
        painter.drawRoundedRect(box, 7, 7)
        painter.setPen(QColor("#24292e"))
        font = QFont(painter.font())
        font.setBold(True)
        font.setPointSizeF(8.5)
        painter.setFont(font)
        painter.drawText(box.adjusted(8, 0, -8, 0), Qt.AlignCenter, text)


class HydrantDialog(QDialog):
    """Edit hydrant and selected base-node fields in one guided dialog."""

    DETAIL_FIELDS = (
        "TYPE_AQUA_ID",
        "PLUG_TYPE_ID",
        "LOCATION_ID",
        "MANUFACTURER",
        "DUCT_SIZE",
        "CONNECTION_STANDARD",
        "CAPACITY",
        "MEASURED_CAPACITY",
        "MEASURE_DATE",
        "MEASURE_NR",
    )
    NODE_FIELDS = (
        "IDENTIFICATION",
        "INVENTORY_NR",
        "USAGE_STATE",
        "CONDITION_CLASS_ID",
        "BUILD_YEAR",
        "NOTE",
    )
    TEXT_NUMBER_FIELDS = {
        "DUCT_SIZE",
        "CAPACITY",
        "MEASURED_CAPACITY",
        "BUILD_YEAR",
    }

    def __init__(
        self,
        context: HydrantContext,
        state: HydrantState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.state = state
        self.setObjectName("evelHydrantDialog")
        self.setWindowTitle(
            "Uus hüdrant"
            if state.is_new
            else f"Hüdrant sõlmel {state.node_id}"
        )
        self.resize(940, 610)
        self.setMinimumSize(840, 560)
        apply_evel_light_style(self, hydrant_editor=True)

        self.detail_editor = GuidedFeatureEditor(
            context.detail_layer,
            state.detail_feature,
            parent=self,
        )
        self.node_editor = GuidedFeatureEditor(
            context.node_layer,
            state.node_feature,
            parent=self,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)
        root.addWidget(self._header())

        content = QHBoxLayout()
        content.setSpacing(16)
        preview_frame = QFrame(self)
        preview_frame.setObjectName("hydrantPreviewFrame")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        self.schematic = HydrantSchematicWidget(
            self.detail_editor,
            state,
            preview_frame,
        )
        preview_layout.addWidget(self.schematic)
        content.addWidget(preview_frame, 4)

        editor_frame = QFrame(self)
        editor_frame.setObjectName("hydrantEditorFrame")
        editor_layout = QVBoxLayout(editor_frame)
        editor_layout.setContentsMargins(8, 8, 8, 8)
        editor_layout.addWidget(self._editor_tabs())
        content.addWidget(editor_frame, 7)
        root.addLayout(content, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            self,
        )
        self.buttons.button(QDialogButtonBox.Save).setText(
            "Salvesta hüdrant"
        )
        self.buttons.button(QDialogButtonBox.Save).setObjectName(
            "hydrantSaveButton"
        )
        self.buttons.button(QDialogButtonBox.Save).setDefault(True)
        self.buttons.button(QDialogButtonBox.Cancel).setText("Loobu")
        self.buttons.button(QDialogButtonBox.Cancel).setObjectName(
            "hydrantCancelButton"
        )
        apply_standard_button_icons(self.buttons)
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def _header(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("hydrantHeroFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 10)
        title = QLabel(
            "Lisa hüdrant"
            if self.state.is_new
            else "Vaata ja muuda hüdranti",
            frame,
        )
        title.setObjectName("hydrantTitle")
        font = QFont(title.font())
        font.setPointSizeF(18)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        location = (
            "olemasoleval sõlmel"
            if self.state.node_id is not None
            else (
                "veetorul; toru poolitatakse"
                if self.state.splits_edge
                else (
                    "veetoru otsas"
                    if self.state.edge_layer is not None
                    else "uues eraldiseisvas punktis"
                )
            )
        )
        subtitle = QLabel(
            f"Asukoht: {location}. Tehnilised ID-väljad täidetakse "
            "automaatselt.",
            frame,
        )
        subtitle.setObjectName("hydrantContext")
        layout.addWidget(subtitle)
        return frame

    def _editor_tabs(self) -> QTabWidget:
        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)

        basic = QWidget(tabs)
        basic.setObjectName("tabContent")
        basic_form = self._form(basic)
        self._add_binding(
            basic_form,
            self.detail_editor,
            "TYPE_AQUA_ID",
            "Hüdrandi liik",
        )
        self._add_binding(
            basic_form,
            self.detail_editor,
            "PLUG_TYPE_ID",
            "Hüdrandi alamtüüp",
        )
        self._add_binding(
            basic_form,
            self.detail_editor,
            "LOCATION_ID",
            "Paiknemine",
        )
        self._add_binding(
            basic_form,
            self.detail_editor,
            "MANUFACTURER",
            "Tootja",
        )
        self._add_binding(
            basic_form,
            self.detail_editor,
            "DUCT_SIZE",
            "Tarnetorustiku läbimõõt DN",
        )
        self._add_binding(
            basic_form,
            self.detail_editor,
            "CONNECTION_STANDARD",
            "Voolikuühenduse standard",
        )
        tabs.addTab(basic, "01 Hüdrant")

        capacity = QWidget(tabs)
        capacity.setObjectName("tabContent")
        capacity_form = self._form(capacity)
        self._add_binding(
            capacity_form,
            self.detail_editor,
            "CAPACITY",
            "Nimitootlikkus Q (l/s)",
        )
        self._add_binding(
            capacity_form,
            self.detail_editor,
            "MEASURED_CAPACITY",
            "Mõõdetud tootlikkus Q (l/s)",
        )
        self._add_binding(
            capacity_form,
            self.detail_editor,
            "MEASURE_DATE",
            "Mõõtmise kuupäev",
        )
        self._add_binding(
            capacity_form,
            self.detail_editor,
            "MEASURE_NR",
            "Mõõtmise akti number",
        )
        tabs.addTab(capacity, "02 Tootlikkus")

        management = QWidget(tabs)
        management.setObjectName("tabContent")
        management_form = self._form(management)
        labels = {
            "IDENTIFICATION": "Sõlme tähis",
            "INVENTORY_NR": "Inventarinumber",
            "USAGE_STATE": "Kasutusolek",
            "CONDITION_CLASS_ID": "Seisukorraklass",
            "BUILD_YEAR": "Paigaldusaasta",
            "NOTE": "Märkused",
        }
        for field_name in self.NODE_FIELDS:
            self._add_binding(
                management_form,
                self.node_editor,
                field_name,
                labels[field_name],
            )
        tabs.addTab(management, "03 Haldus")
        return tabs

    @staticmethod
    def _form(parent: QWidget) -> QFormLayout:
        form = QFormLayout(parent)
        form.setContentsMargins(16, 18, 16, 16)
        form.setSpacing(11)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return form

    def _add_binding(
        self,
        form: QFormLayout,
        editor: GuidedFeatureEditor,
        field_name: str,
        label: str,
    ) -> None:
        override = TEXT_SETUP if field_name in self.TEXT_NUMBER_FIELDS else None
        binding = editor.create_binding(
            field_name,
            form.parentWidget(),
            setup_override=override,
        )
        if binding is not None:
            form.addRow(label, binding.widget)

    def _validate_and_accept(self) -> None:
        missing = []
        for editor in (self.detail_editor, self.node_editor):
            for binding in editor.bindings():
                value = binding.value()
                if binding.required and (
                    QgsVariantUtils.isNull(value)
                    or not str(value).strip()
                ):
                    missing.append(binding.label)
        if missing:
            QMessageBox.warning(
                self,
                "Täida kohustuslikud väljad",
                "Puuduvad väärtused: " + ", ".join(sorted(set(missing))),
            )
            return
        self.accept()

    def plan(self) -> HydrantPlan:
        detail = self.detail_editor.draft_feature()
        node = self.node_editor.draft_feature()
        return HydrantPlan(
            state=self.state,
            node_values={
                field_name: node[field_name]
                for field_name in self.NODE_FIELDS
                if node.fields().lookupField(field_name) >= 0
            },
            detail_values={
                field_name: detail[field_name]
                for field_name in self.DETAIL_FIELDS
                if detail.fields().lookupField(field_name) >= 0
            },
        )
