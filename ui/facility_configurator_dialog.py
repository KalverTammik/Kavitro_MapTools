"""Editor for optional SN_WATER_PUMPING_STATION node facilities."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from qgis.PyQt.QtCore import QDateTime, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..layers import (
    FacilityConfigurationOptions,
    FacilityVariant,
    LookupOption,
)
from ..topology import FacilityConfiguration
from .light_style import apply_evel_light_style


class _OptionalDateTimeWidget(QWidget):
    """Checkbox-controlled nullable date/time editor."""

    def __init__(self, value: datetime | None, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.enabled_checkbox = QCheckBox("Määratud", self)
        self.editor = QDateTimeEdit(self)
        self.editor.setCalendarPopup(True)
        self.editor.setDisplayFormat("dd.MM.yyyy")
        self.editor.setDateTime(
            QDateTime(value) if value is not None else QDateTime.currentDateTime()
        )
        self.enabled_checkbox.setChecked(value is not None)
        self.editor.setEnabled(value is not None)
        self.enabled_checkbox.toggled.connect(self.editor.setEnabled)
        layout.addWidget(self.enabled_checkbox)
        layout.addWidget(self.editor, 1)

    def value(self) -> datetime | None:
        if not self.enabled_checkbox.isChecked():
            return None
        return self.editor.dateTime().toPyDateTime()


class FacilityConfiguratorDialog(QDialog):
    """Edit all user-facing values of one water facility detail."""

    def __init__(
        self,
        configuration: FacilityConfiguration,
        variant: FacilityVariant,
        options: FacilityConfigurationOptions,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("evelFacilityConfiguratorDialog")
        apply_evel_light_style(self)
        self.variant = variant
        self.options = options
        self.setWindowTitle(f"{variant.label} – parameetrid")
        self.setModal(True)
        self.resize(650, 560)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Parameetrid salvestatakse keskse veesõlme "
            "SN_WATER_PUMPING_STATION detailkirjesse. Rajatise tehniline "
            "liigitus täidetakse valitud tüübi järgi automaatselt.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        classification = QLabel(
            f"<b>{variant.label}</b> · võrk {variant.network_id} · "
            f"roll {variant.role_id} · veeliik {variant.water_type_id}",
            self,
        )
        classification.setTextFormat(Qt.RichText)
        root.addWidget(classification)

        self.tabs = QTabWidget(self)
        general_tab = QWidget(self.tabs)
        general_form = QFormLayout(general_tab)
        general_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.material_combo = self._combo(
            options.material_options,
            configuration.material_id,
            parent=general_tab,
        )
        general_form.addRow("Materjal", self.material_combo)
        self.productivity_spin = self._number(
            configuration.productivity,
            " l/s",
            general_tab,
        )
        general_form.addRow("Tootlikkus", self.productivity_spin)
        self.pressure_spin = self._number(
            configuration.pressure_increase,
            " atm",
            general_tab,
        )
        general_form.addRow("Surve tõus", self.pressure_spin)
        self.controlled_check = QCheckBox("Kaugjuhitav", general_tab)
        self.controlled_check.setChecked(configuration.is_controlled)
        general_form.addRow("", self.controlled_check)
        self.signalisation_check = QCheckBox(
            "Signalisatsioon on olemas",
            general_tab,
        )
        self.signalisation_check.setChecked(
            configuration.is_signalisation
        )
        general_form.addRow("", self.signalisation_check)
        self.tabs.addTab(general_tab, "Üldandmed")

        source_tab = QWidget(self.tabs)
        source_form = QFormLayout(source_tab)
        source_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.registry_edit = QLineEdit(
            configuration.registry_code or "",
            source_tab,
        )
        source_form.addRow("Registrikood", self.registry_edit)
        self.passport_edit = QLineEdit(
            configuration.passport_number or "",
            source_tab,
        )
        source_form.addRow("Passi number", self.passport_edit)
        self.depth_spin = self._number(
            configuration.depth,
            " m",
            source_tab,
        )
        source_form.addRow("Puurkaevu sügavus", self.depth_spin)
        self.water_source_combo = self._combo(
            options.water_source_options,
            configuration.water_source_id,
            parent=source_tab,
        )
        source_form.addRow("Veeallikas", self.water_source_combo)
        self.protection_zone_spin = self._number(
            configuration.protection_zone,
            " m",
            source_tab,
        )
        source_form.addRow(
            "Sanitaarkaitse ulatus",
            self.protection_zone_spin,
        )
        self.mantle_diam_spin = self._number(
            configuration.mantle_diam,
            " mm",
            source_tab,
        )
        source_form.addRow(
            "Mantli läbimõõt",
            self.mantle_diam_spin,
        )
        self.tabs.addTab(source_tab, "Allikas ja register")

        lifecycle_tab = QWidget(self.tabs)
        lifecycle_form = QFormLayout(lifecycle_tab)
        lifecycle_form.setFieldGrowthPolicy(
            QFormLayout.AllNonFixedFieldsGrow
        )
        self.renewal_date = _OptionalDateTimeWidget(
            configuration.renewal_date,
            lifecycle_tab,
        )
        lifecycle_form.addRow("Renoveerimise kuupäev", self.renewal_date)
        self.wipeout_date = _OptionalDateTimeWidget(
            configuration.wipeout_date,
            lifecycle_tab,
        )
        lifecycle_form.addRow("Likvideerimise kuupäev", self.wipeout_date)
        self.tabs.addTab(lifecycle_tab, "Elukaar")
        root.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.button(QDialogButtonBox.Save).setText("Salvesta valikud")
        buttons.button(QDialogButtonBox.Cancel).setText("Loobu")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def configuration(self) -> FacilityConfiguration:
        return FacilityConfiguration(
            variant_key=self.variant.key,
            material_id=self.material_combo.currentData(),
            productivity=self._optional_number(self.productivity_spin),
            pressure_increase=self._optional_number(self.pressure_spin),
            registry_code=self._optional_text(self.registry_edit.text()),
            passport_number=self._optional_text(self.passport_edit.text()),
            depth=self._optional_number(self.depth_spin),
            water_source_id=self.water_source_combo.currentData(),
            wipeout_date=self.wipeout_date.value(),
            renewal_date=self.renewal_date.value(),
            is_controlled=self.controlled_check.isChecked(),
            is_signalisation=self.signalisation_check.isChecked(),
            protection_zone=self._optional_number(
                self.protection_zone_spin
            ),
            mantle_diam=self._optional_number(self.mantle_diam_spin),
        )

    @staticmethod
    def _combo(
        options: tuple[LookupOption, ...],
        selected: int | None,
        *,
        parent=None,
    ) -> QComboBox:
        combo = QComboBox(parent)
        combo.addItem("— Puudub —", None)
        for option in options:
            combo.addItem(option.label, option.value)
        index = combo.findData(selected)
        if index < 0 and selected is not None:
            combo.addItem(f"Tundmatu väärtus ({selected})", selected)
            index = combo.count() - 1
        combo.setCurrentIndex(max(index, 0))
        return combo

    @staticmethod
    def _number(
        value: float | None,
        suffix: str,
        parent=None,
    ) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(parent)
        spin.setDecimals(3)
        spin.setRange(-1.0, 1_000_000_000.0)
        spin.setSpecialValueText("Määramata")
        spin.setSuffix(suffix)
        spin.setValue(value if value is not None else -1.0)
        return spin

    @staticmethod
    def _optional_number(spin: QDoubleSpinBox) -> float | None:
        return None if spin.value() < 0 else float(spin.value())

    @staticmethod
    def _optional_text(value: str) -> str | None:
        stripped = value.strip()
        return stripped or None


class FacilitySectionWidget(QGroupBox):
    """Reusable facility type selector and parameter summary."""

    configurationChanged = pyqtSignal(object)

    def __init__(
        self,
        configuration: FacilityConfiguration,
        node_network_id: int | None,
        options: FacilityConfigurationOptions,
        title: str,
        parent=None,
    ) -> None:
        super().__init__(title, parent)
        self.options = options
        self.node_network_id = node_network_id
        self._initial_variant_key = configuration.variant_key
        self._configuration = configuration
        self._variants = tuple(
            variant
            for variant in options.variants
            if variant.network_id == node_network_id
        )

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.variant_combo = QComboBox(self)
        self.variant_combo.addItem("— Rajatis puudub —", None)
        for variant in self._variants:
            self.variant_combo.addItem(variant.label, variant.key)
        controls.addWidget(self.variant_combo, 1)
        self.edit_button = QPushButton("Parameetrid…", self)
        controls.addWidget(self.edit_button)
        layout.addLayout(controls)
        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #57606a;")
        layout.addWidget(self.summary_label)

        selected_index = self.variant_combo.findData(
            configuration.variant_key
        )
        self.variant_combo.setCurrentIndex(max(selected_index, 0))
        self.variant_combo.setEnabled(bool(self._variants))
        self.variant_combo.currentIndexChanged.connect(
            self._variant_changed
        )
        self.edit_button.clicked.connect(self._edit_parameters)
        self._refresh()

    def configuration(self) -> FacilityConfiguration:
        return self._configuration

    def _variant_changed(self, _index: int) -> None:
        key = self.variant_combo.currentData()
        if key is None:
            self._configuration = replace(
                self._configuration,
                variant_key=None,
            )
        else:
            variant = self._variant(key)
            changed_type = key != self._configuration.variant_key
            self._configuration = replace(
                self._configuration,
                variant_key=key,
                material_id=(
                    variant.default_material_id
                    if changed_type
                    else self._configuration.material_id
                ),
                water_source_id=(
                    variant.default_water_source_id
                    if changed_type
                    else self._configuration.water_source_id
                ),
            )
        self._refresh()
        self.configurationChanged.emit(self._configuration)

    def _edit_parameters(self) -> None:
        variant = self._variant(self._configuration.variant_key)
        dialog = FacilityConfiguratorDialog(
            self._configuration,
            variant,
            self.options,
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            dialog.deleteLater()
            return
        self._configuration = dialog.configuration()
        dialog.deleteLater()
        self._refresh()
        self.configurationChanged.emit(self._configuration)

    def _refresh(self) -> None:
        key = self._configuration.variant_key
        self.edit_button.setEnabled(key is not None)
        if not self._variants:
            self.summary_label.setText(
                f"Sõlme võrgule {self.node_network_id} ei ole projektis "
                "rajatise varianti."
            )
            return
        if key is None:
            self.summary_label.setText(
                "Olemasolev rajatise detail eemaldatakse rakendamisel."
                if self._initial_variant_key is not None
                else "Rajatise detaili ei lisata."
            )
            return
        variant = self._variant(key)
        parts = [variant.label]
        material = self._label(
            self.options.material_options,
            self._configuration.material_id,
        )
        if material:
            parts.append(material)
        if self._configuration.productivity is not None:
            parts.append(
                f"{self._configuration.productivity:g} l/s"
            )
        self.summary_label.setText(" • ".join(parts))

    def _variant(self, key: str | None) -> FacilityVariant:
        variant = next(
            (item for item in self._variants if item.key == key),
            None,
        )
        if variant is None:
            raise ValueError("Valitud rajatise variant ei ole saadaval.")
        return variant

    @staticmethod
    def _label(
        options: tuple[LookupOption, ...],
        value: int | None,
    ) -> str:
        return next(
            (option.label for option in options if option.value == value),
            "",
        )
