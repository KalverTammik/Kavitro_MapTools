"""Light guided editor for an EVEL connection point."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QMessageBox,
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

from ..layers.connection_point import ConnectionPointContext
from ..topology.connection_point import (
    ConnectionPointPlan,
    ConnectionPointState,
    NETWORK_FIELDS,
    NETWORK_LABELS,
)
from .guided_feature_editor import GuidedFeatureEditor
from .light_style import apply_evel_light_style


class ConnectionPointDialog(QDialog):
    """Edit one CONSUMER_POINT feature without exposing technical IDs."""

    EDITABLE_FIELDS = (
        "IDENTIFICATION",
        "CP_TYPE_ID",
        "CP_STATE_ID",
        "CONSUMERPOINT_GROUP",
        "REAL_ESTATE_NR",
        "WATER_NETWORK_NODE",
        "SEWER_NETWORK_NODE",
        "RAIN_NETWORK_NODE",
        "OWNER_ID",
        "INVOICING_ID",
        "RESIDENTS",
        "CRITICALCUSTOMER_IS",
        "SPRINKLERCUSTOMER_IS",
        "INDUSTRIALWWCONT_IS",
        "COMMENTS",
    )

    def __init__(
        self,
        context: ConnectionPointContext,
        state: ConnectionPointState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.context = context
        self.state = state
        self.setObjectName("evelConnectionPointDialog")
        self.setWindowTitle(
            "Uus liitumispunkt"
            if state.is_new
            else f"Liitumispunkt {state.point_id}"
        )
        self.resize(820, 610)
        self.setMinimumSize(720, 540)
        apply_evel_light_style(self)
        self.editor = GuidedFeatureEditor(
            context.point_layer,
            state.feature,
            parent=self,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)
        root.addWidget(self._header())
        root.addWidget(self._editor_frame(), 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            self,
        )
        save_button = self.buttons.button(QDialogButtonBox.Save)
        save_button.setText("Salvesta liitumispunkt")
        save_button.setObjectName("connectionPointSaveButton")
        save_button.setDefault(True)
        cancel_button = self.buttons.button(QDialogButtonBox.Cancel)
        cancel_button.setText("Loobu")
        cancel_button.setObjectName("connectionPointCancelButton")
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def _header(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("guidedHeroFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 10)
        title = QLabel(
            "Lisa liitumispunkt"
            if self.state.is_new
            else "Vaata ja muuda liitumispunkti",
            frame,
        )
        font = QFont(title.font())
        font.setPointSizeF(18)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        if self.state.node_candidate is not None:
            candidate = self.state.node_candidate
            context_text = (
                f"Seos: {NETWORK_LABELS[candidate.network_kind]}, "
                f"sõlm {candidate.node_id}."
            )
        else:
            context_text = (
                "EVEL-i andmemudelis on selle objekti tehniline nimi "
                "tarbimispunkt."
            )
        subtitle = QLabel(
            context_text + " ID ja geomeetria täidetakse automaatselt.",
            frame,
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return frame

    def _editor_frame(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("guidedEditorFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._tabs())
        return frame

    def _tabs(self) -> QTabWidget:
        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)

        basic = QWidget(tabs)
        basic_form = self._form(basic)
        for field_name, label in (
            ("IDENTIFICATION", "Liitumispunkti tähis"),
            ("CP_TYPE_ID", "Liitumispunkti tüüp"),
            ("CP_STATE_ID", "Liitumispunkti olek"),
            ("CONSUMERPOINT_GROUP", "Liitumispunkti grupp"),
            ("REAL_ESTATE_NR", "Katastritunnus"),
        ):
            self._add_binding(basic_form, field_name, label)
        tabs.addTab(basic, "01 Põhiandmed")

        network = QWidget(tabs)
        network_form = self._form(network)
        self._add_binding(
            network_form,
            "WATER_NETWORK_NODE",
            "Veevõrgu sõlm",
            setup=self._value_relation(
                context_layer=self.context.water_node_layer,
                key_field="MSLINK",
                value_field="MSLINK",
            ),
        )
        self._add_binding(
            network_form,
            "SEWER_NETWORK_NODE",
            "Reoveevõrgu sõlm",
            setup=self._value_relation(
                context_layer=self.context.sewer_node_layer,
                key_field="MSLINK",
                value_field="MSLINK",
            ),
        )
        self._add_binding(
            network_form,
            "RAIN_NETWORK_NODE",
            "Sademeveevõrgu sõlm",
            setup=self._value_relation(
                context_layer=self.context.sewer_node_layer,
                key_field="MSLINK",
                value_field="MSLINK",
            ),
        )
        hint = QLabel(
            "Liitumispunkt võib olla seotud mitme teenusega. "
            "Teenuse tunnus märgitakse salvestamisel sõlmeseose põhjal.",
            network,
        )
        hint.setWordWrap(True)
        network_form.addRow("", hint)
        tabs.addTab(network, "02 Võrguseosed")

        customer = QWidget(tabs)
        customer_form = self._form(customer)
        customer_setup = self._value_relation(
            context_layer=self.context.customer_layer,
            key_field="ID",
            value_field="CUSTOMER_NAME",
        )
        self._add_binding(
            customer_form,
            "OWNER_ID",
            "Omanik",
            setup=customer_setup,
        )
        self._add_binding(
            customer_form,
            "INVOICING_ID",
            "Arve saaja",
            setup=customer_setup,
        )
        self._add_binding(customer_form, "RESIDENTS", "Elanike arv")
        self._add_binding(
            customer_form,
            "CRITICALCUSTOMER_IS",
            "Kriitiline klient",
        )
        self._add_binding(
            customer_form,
            "SPRINKLERCUSTOMER_IS",
            "Sprinklerklient",
        )
        self._add_binding(
            customer_form,
            "INDUSTRIALWWCONT_IS",
            "Tööstusliku reovee klient",
        )
        tabs.addTab(customer, "03 Klient")

        notes = QWidget(tabs)
        notes_form = self._form(notes)
        self._add_binding(notes_form, "COMMENTS", "Märkused")
        tabs.addTab(notes, "04 Märkused")
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
        field_name: str,
        label: str,
        *,
        setup: QgsEditorWidgetSetup | None = None,
    ) -> None:
        binding = self.editor.create_binding(
            field_name,
            form.parentWidget(),
            setup_override=setup,
        )
        if binding is not None:
            form.addRow(label, binding.widget)

    @staticmethod
    def _value_relation(
        *,
        context_layer: QgsVectorLayer | None,
        key_field: str,
        value_field: str,
    ) -> QgsEditorWidgetSetup | None:
        if context_layer is None:
            return None
        if (
            context_layer.fields().lookupField(key_field) < 0
            or context_layer.fields().lookupField(value_field) < 0
        ):
            return None
        return QgsEditorWidgetSetup(
            "ValueRelation",
            {
                "AllowMulti": False,
                "AllowNull": True,
                "FilterExpression": "",
                "Key": key_field,
                "Layer": context_layer.id(),
                "LayerName": context_layer.name(),
                "LayerProviderName": context_layer.providerType(),
                "LayerSource": context_layer.source(),
                "NofColumns": 1,
                "OrderByValue": True,
                "UseCompleter": True,
                "Value": value_field,
            },
        )

    def _validate_and_accept(self) -> None:
        draft = self.editor.draft_feature()
        has_network = any(
            not QgsVariantUtils.isNull(draft[field_name])
            for field_name, _junction_field in NETWORK_FIELDS.values()
        )
        if not has_network:
            QMessageBox.warning(
                self,
                "Võrguseos puudub",
                "Liitumispunkt peab olema seotud vähemalt ühe vee-, "
                "reovee- või sademeveesõlmega.",
            )
            return
        self.accept()

    def plan(self) -> ConnectionPointPlan:
        draft: QgsFeature = self.editor.draft_feature()
        values = {
            field_name: draft[field_name]
            for field_name in self.EDITABLE_FIELDS
            if draft.fields().lookupField(field_name) >= 0
        }
        for field_name in (
            "WATER_NETWORK_NODE",
            "SEWER_NETWORK_NODE",
            "RAIN_NETWORK_NODE",
            "OWNER_ID",
            "INVOICING_ID",
        ):
            value = values.get(field_name)
            if QgsVariantUtils.isNull(value):
                continue
            try:
                values[field_name] = int(value)
            except (TypeError, ValueError):
                pass
        for _kind, (node_field, junction_field) in NETWORK_FIELDS.items():
            node_value = values.get(node_field)
            values[junction_field] = not QgsVariantUtils.isNull(node_value)
        return ConnectionPointPlan(
            state=self.state,
            values=values,
        )
