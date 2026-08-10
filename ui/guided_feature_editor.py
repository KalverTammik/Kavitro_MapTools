"""Metadata-driven QGIS field bindings for EVEL guided dialogs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QComboBox, QWidget
from qgis.core import (
    QgsEditorWidgetSetup,
    QgsFeature,
    QgsFieldConstraints,
    QgsVariantUtils,
    QgsVectorLayer,
    QgsVectorLayerUtils,
)
from qgis.gui import (
    QgsAttributeEditorContext,
    QgsEditorWidgetWrapper,
    QgsGui,
)


class GuidedFeatureEditorError(RuntimeError):
    """Raised when a guided form cannot safely update its QGIS feature."""


@dataclass
class GuidedFieldBinding:
    """One QGIS editor wrapper and the field metadata it represents."""

    field_name: str
    field_index: int
    label: str
    required: bool
    wrapper: QgsEditorWidgetWrapper
    widget: QWidget
    initial_value: Any

    def value(self) -> Any:
        return self.wrapper.value()

    def display_text(self) -> str:
        if isinstance(self.widget, QComboBox):
            return self.widget.currentText().strip()
        text_method = getattr(self.widget, "text", None)
        if callable(text_method):
            return str(text_method()).strip()
        plain_text_method = getattr(self.widget, "toPlainText", None)
        if callable(plain_text_method):
            return str(plain_text_method()).strip()
        value = self.value()
        if QgsVariantUtils.isNull(value):
            return "—"
        return str(value)


class GuidedFeatureEditor(QObject):
    """Create official QGIS editor widgets inside an EVEL-owned layout."""

    fieldValueChanged = pyqtSignal(str, object)

    def __init__(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        *,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.layer = layer
        self.feature = feature
        self._draft = QgsFeature(feature)
        self._bindings: dict[str, GuidedFieldBinding] = {}
        self._syncing = False
        self._context = QgsAttributeEditorContext()
        self._context.setAttributeFormMode(
            QgsAttributeEditorContext.AddFeatureMode
        )
        self._context.setFormMode(
            QgsAttributeEditorContext.StandaloneDialog
        )
        self._context.setFormFeature(self._draft)
        self._ensure_editor_registry()

    @staticmethod
    def _ensure_editor_registry() -> None:
        registry = QgsGui.editorWidgetRegistry()
        if not registry.factories():
            registry.initEditors()

    def has_field(self, field_name: str) -> bool:
        return self.layer.fields().lookupField(field_name) >= 0

    def binding(self, field_name: str) -> GuidedFieldBinding | None:
        return self._bindings.get(field_name)

    def bindings(self) -> tuple[GuidedFieldBinding, ...]:
        return tuple(self._bindings.values())

    def create_binding(
        self,
        field_name: str,
        parent: QWidget,
        *,
        setup_override: QgsEditorWidgetSetup | None = None,
    ) -> GuidedFieldBinding | None:
        existing = self._bindings.get(field_name)
        if existing is not None:
            return existing

        field_index = self.layer.fields().lookupField(field_name)
        if field_index < 0:
            return None
        field = self.layer.fields()[field_index]
        setup = setup_override or self.layer.editorWidgetSetup(field_index)
        if setup.type() == "Hidden":
            return None

        registry = QgsGui.editorWidgetRegistry()
        wrapper = None
        if setup_override is None:
            wrapper = registry.create(
                self.layer,
                field_index,
                None,
                parent,
            )
        if wrapper is None:
            wrapper = registry.create(
                setup.type(),
                self.layer,
                field_index,
                setup.config(),
                None,
                parent,
            )
        if wrapper is None:
            setup = registry.findBest(self.layer, field_name)
            wrapper = registry.create(
                setup.type(),
                self.layer,
                field_index,
                setup.config(),
                None,
                parent,
            )
        if wrapper is None:
            raise GuidedFeatureEditorError(
                f"Väljale {field_name} ei õnnestunud QGIS-i "
                "sisestusvidinat luua."
            )

        wrapper.setContext(self._context)
        wrapper.setFormFeature(self._draft)
        wrapper.setFeature(self._draft)
        widget = wrapper.widget()
        if widget is None or not wrapper.valid():
            raise GuidedFeatureEditorError(
                f"Välja {field_name} QGIS-i sisestusvidin puudub."
            )
        widget.setObjectName(f"ductField_{field_name}")
        editable = QgsVectorLayerUtils.fieldIsEditable(
            self.layer,
            field_index,
            self._draft,
        )
        wrapper.setEnabled(editable)

        constraints = field.constraints().constraints()
        required = bool(
            constraints & QgsFieldConstraints.ConstraintNotNull
        )
        binding = GuidedFieldBinding(
            field_name=field_name,
            field_index=field_index,
            label=self.layer.attributeDisplayName(field_index),
            required=required,
            wrapper=wrapper,
            widget=widget,
            initial_value=self._draft.attribute(field_index),
        )
        self._bindings[field_name] = binding
        wrapper.valuesChanged.connect(
            lambda _value, extra, name=field_name: self._binding_value_changed(
                name,
                extra,
            )
        )
        return binding

    def value(self, field_name: str) -> Any:
        binding = self.binding(field_name)
        if binding is not None:
            return binding.value()
        field_index = self.layer.fields().lookupField(field_name)
        if field_index < 0:
            return None
        return self._draft.attribute(field_index)

    def display_text(self, field_name: str) -> str:
        binding = self.binding(field_name)
        if binding is not None:
            return binding.display_text()
        value = self.value(field_name)
        if QgsVariantUtils.isNull(value):
            return "—"
        return str(value)

    def draft_feature(self) -> QgsFeature:
        draft = QgsFeature(self._draft)
        for binding in self._bindings.values():
            draft.setAttribute(binding.field_index, binding.value())
            for name, value in zip(
                binding.wrapper.additionalFields(),
                binding.wrapper.additionalFieldValues(),
            ):
                index = self.layer.fields().lookupField(name)
                if index >= 0:
                    draft.setAttribute(index, value)
        return draft

    def validation_errors(
        self,
        draft: QgsFeature | None = None,
    ) -> dict[str, tuple[str, ...]]:
        candidate = draft if draft is not None else self.draft_feature()
        errors: dict[str, tuple[str, ...]] = {}
        for field_index, field in enumerate(self.layer.fields()):
            if not QgsVectorLayerUtils.attributeHasConstraints(
                self.layer,
                field_index,
            ):
                continue
            valid, messages = QgsVectorLayerUtils.validateAttribute(
                self.layer,
                candidate,
                field_index,
                QgsFieldConstraints.ConstraintStrengthHard,
                QgsFieldConstraints.ConstraintOriginNotSet,
            )
            if not valid:
                label = self.layer.attributeDisplayName(field_index)
                errors[field.name()] = tuple(messages) or (
                    f"Välja „{label}” väärtus ei ole lubatud.",
                )
        return errors

    def apply(self) -> dict[str, tuple[str, ...]]:
        """Validate and write changed values to the active edit buffer."""

        for binding in self._bindings.values():
            binding.wrapper.notifyAboutToSave()
        draft = self.draft_feature()
        errors = self.validation_errors(draft)
        if errors:
            return errors

        current = self.layer.getFeature(self.feature.id())
        if not current.isValid():
            raise GuidedFeatureEditorError(
                "Toru nähtust ei leitud enam redigeerimispuhvrist."
            )
        new_values: dict[int, Any] = {}
        old_values: dict[int, Any] = {}
        candidate_indices: set[int] = set()
        for binding in self._bindings.values():
            candidate_indices.add(binding.field_index)
            for field_name in binding.wrapper.additionalFields():
                field_index = self.layer.fields().lookupField(field_name)
                if field_index >= 0:
                    candidate_indices.add(field_index)

        for field_index in candidate_indices:
            value = draft.attribute(field_index)
            old_value = current.attribute(field_index)
            if self._values_equal(value, old_value):
                continue
            new_values[field_index] = value
            old_values[field_index] = old_value

        if new_values and not self.layer.changeAttributeValues(
            self.feature.id(),
            new_values,
            old_values,
            False,
        ):
            raise GuidedFeatureEditorError(
                "Toru atribuutide muutmine redigeerimispuhvris ebaõnnestus."
            )
        updated = self.layer.getFeature(self.feature.id())
        if not updated.isValid():
            raise GuidedFeatureEditorError(
                "Toru uuendatud väärtusi ei õnnestunud "
                "redigeerimispuhvrist lugeda."
            )
        for field_index in range(self.layer.fields().count()):
            self.feature.setAttribute(
                field_index,
                updated.attribute(field_index),
            )
        for binding in self._bindings.values():
            binding.initial_value = self.feature.attribute(binding.field_index)

        self._draft = QgsFeature(updated)
        self._context.setFormFeature(self._draft)
        return {}

    def _binding_value_changed(
        self,
        field_name: str,
        extra_values: list[Any],
    ) -> None:
        binding = self._bindings.get(field_name)
        if binding is None:
            return
        value = binding.value()
        self._draft.setAttribute(binding.field_index, value)
        changed_values = {field_name: value}
        for name, extra_value in zip(
            binding.wrapper.additionalFields(),
            extra_values,
        ):
            index = self.layer.fields().lookupField(name)
            if index >= 0:
                self._draft.setAttribute(index, extra_value)
                changed_values[name] = extra_value
        if self._syncing:
            self._context.setFormFeature(self._draft)
            return

        self._syncing = True
        try:
            self._context.setFormFeature(self._draft)
            for other in self._bindings.values():
                if other is binding:
                    continue
                for changed_name, changed_value in changed_values.items():
                    other.wrapper.setFormFeatureAttribute(
                        changed_name,
                        changed_value,
                    )
                other.wrapper.updateConstraint(self._draft)
            self._context.setFormFeature(self._draft)
        finally:
            self._syncing = False
        self.fieldValueChanged.emit(field_name, value)

    @staticmethod
    def _values_equal(first: Any, second: Any) -> bool:
        first_null = QgsVariantUtils.isNull(first)
        second_null = QgsVariantUtils.isNull(second)
        if first_null or second_null:
            return first_null and second_null
        return first == second
