"""Compact editor for an SN_WATER_MANHOLE detail record."""

from __future__ import annotations

from dataclasses import replace

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..layers import LookupOption, ManholeConfigurationOptions
from ..topology import ManholeConfiguration
from .light_style import apply_evel_light_style


class ManholeConfiguratorDialog(QDialog):
    """Edit all user-facing fields of one water-manhole detail."""

    def __init__(
        self,
        configuration: ManholeConfiguration,
        options: ManholeConfigurationOptions,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("evelManholeConfiguratorDialog")
        apply_evel_light_style(self)
        self.options = options
        self.setWindowTitle("Kaevu parameetrid")
        self.setModal(True)
        self.resize(600, 500)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Need väärtused salvestatakse keskse veesõlme "
            "SN_WATER_MANHOLE detailkirjesse.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.tabs = QTabWidget(self)
        manhole_tab = QWidget(self.tabs)
        manhole_form = QFormLayout(manhole_tab)
        manhole_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.type_combo = self._combo(
            options.type_options,
            configuration.type_id or options.default_type_id,
            optional=False,
            parent=manhole_tab,
        )
        manhole_form.addRow("Kaevu liik", self.type_combo)
        self.material_combo = self._combo(
            options.material_options,
            configuration.material_id,
            parent=manhole_tab,
        )
        manhole_form.addRow("Materjal", self.material_combo)
        self.diameter_type_combo = self._combo(
            options.diameter_type_options,
            configuration.diameter_type_id,
            parent=manhole_tab,
        )
        manhole_form.addRow(
            "Läbimõõdu tüüp",
            self.diameter_type_combo,
        )
        self.diameter_combo = self._combo(
            options.diameter_options,
            configuration.diameter_id,
            parent=manhole_tab,
        )
        manhole_form.addRow("Läbimõõt", self.diameter_combo)
        self.firmness_combo = self._combo(
            options.firmness_options,
            configuration.firmness_class_id,
            parent=manhole_tab,
        )
        manhole_form.addRow("Ringjäikus SN", self.firmness_combo)
        self.access_duct_spin = QSpinBox(manhole_tab)
        self.access_duct_spin.setRange(0, 10000)
        self.access_duct_spin.setSpecialValueText("Määramata")
        self.access_duct_spin.setSuffix(" mm")
        self.access_duct_spin.setMaximumWidth(320)
        self.access_duct_spin.setValue(configuration.access_duct_diam or 0)
        manhole_form.addRow(
            "Tõusutoru läbimõõt",
            self.access_duct_spin,
        )
        self.anchor_plate_check = QCheckBox(
            "Kaevul on ankurdusplaat",
            manhole_tab,
        )
        self.anchor_plate_check.setChecked(configuration.anchor_plate)
        manhole_form.addRow("", self.anchor_plate_check)
        self.load_leveling_plate_check = QCheckBox(
            "Kaevul on koormustasandusplaat",
            manhole_tab,
        )
        self.load_leveling_plate_check.setChecked(
            configuration.load_leveling_plate
        )
        manhole_form.addRow("", self.load_leveling_plate_check)
        self.tabs.addTab(manhole_tab, "Kaev")

        lid_tab = QWidget(self.tabs)
        lid_form = QFormLayout(lid_tab)
        lid_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.lid_type_combo = self._combo(
            options.lid_type_options,
            configuration.lid_type_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane tüüp", self.lid_type_combo)
        self.lid_material_combo = self._combo(
            options.lid_material_options,
            configuration.lid_material_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane materjal", self.lid_material_combo)
        self.lid_shape_combo = self._combo(
            options.lid_shape_options,
            configuration.lid_shape_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane kuju", self.lid_shape_combo)
        self.lid_diameter_combo = self._combo(
            options.lid_diameter_options,
            configuration.lid_diameter_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane läbimõõt", self.lid_diameter_combo)
        self.lid_capacity_combo = self._combo(
            options.lid_capacity_options,
            configuration.lid_capacity_id,
            parent=lid_tab,
        )
        lid_form.addRow("Kaane kandevõime (t)", self.lid_capacity_combo)
        self.lid_insulation_check = QCheckBox(
            "Kaanel on soojustus",
            lid_tab,
        )
        self.lid_insulation_check.setChecked(
            configuration.lid_insulation
        )
        lid_form.addRow("", self.lid_insulation_check)
        self.tabs.addTab(lid_tab, "Kaas")
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

    def configuration(self) -> ManholeConfiguration:
        access_duct_diam = self.access_duct_spin.value()
        return ManholeConfiguration(
            enabled=True,
            type_id=self.type_combo.currentData(),
            material_id=self.material_combo.currentData(),
            diameter_type_id=self.diameter_type_combo.currentData(),
            diameter_id=self.diameter_combo.currentData(),
            firmness_class_id=self.firmness_combo.currentData(),
            anchor_plate=self.anchor_plate_check.isChecked(),
            load_leveling_plate=self.load_leveling_plate_check.isChecked(),
            lid_type_id=self.lid_type_combo.currentData(),
            lid_material_id=self.lid_material_combo.currentData(),
            lid_shape_id=self.lid_shape_combo.currentData(),
            lid_diameter_id=self.lid_diameter_combo.currentData(),
            lid_capacity_id=self.lid_capacity_combo.currentData(),
            lid_insulation=self.lid_insulation_check.isChecked(),
            access_duct_diam=(
                access_duct_diam if access_duct_diam > 0 else None
            ),
        )

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
            combo.addItem("— Puudub —", None)
        for option in options:
            combo.addItem(option.label, option.value)
        combo.setMinimumContentsLength(18)
        combo.setMaximumWidth(320)
        combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        index = combo.findData(selected)
        if index < 0 and selected is not None:
            combo.addItem(f"Tundmatu väärtus ({selected})", selected)
            index = combo.count() - 1
        combo.setCurrentIndex(max(index, 0))
        return combo


class ManholeSectionWidget(QGroupBox):
    """Reusable compact toggle and summary for both node configurators."""

    configurationChanged = pyqtSignal(object)

    def __init__(
        self,
        configuration: ManholeConfiguration,
        options: ManholeConfigurationOptions,
        title: str,
        parent=None,
    ) -> None:
        super().__init__(title, parent)
        self.options = options
        self._initially_enabled = configuration.enabled
        self._configuration = self._normalized(configuration)

        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.enabled_checkbox = QCheckBox(
            "Sõlm asub kaevus",
            self,
        )
        self.enabled_checkbox.setChecked(self._configuration.enabled)
        controls.addWidget(self.enabled_checkbox)
        controls.addStretch(1)
        self.edit_button = QPushButton("Parameetrid…", self)
        controls.addWidget(self.edit_button)
        layout.addLayout(controls)
        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #57606a;")
        layout.addWidget(self.summary_label)

        self.enabled_checkbox.toggled.connect(self._enabled_changed)
        self.edit_button.clicked.connect(self._edit_parameters)
        self._refresh()

    def configuration(self) -> ManholeConfiguration:
        return self._configuration

    def set_configuration(
        self,
        configuration: ManholeConfiguration,
    ) -> None:
        self._configuration = self._normalized(configuration)
        self.enabled_checkbox.blockSignals(True)
        self.enabled_checkbox.setChecked(self._configuration.enabled)
        self.enabled_checkbox.blockSignals(False)
        self._refresh()
        self.configurationChanged.emit(self._configuration)

    def _normalized(
        self,
        configuration: ManholeConfiguration,
    ) -> ManholeConfiguration:
        if configuration.type_id is not None:
            return configuration
        return replace(
            configuration,
            type_id=self.options.default_type_id,
        )

    def _enabled_changed(self, enabled: bool) -> None:
        self._configuration = replace(
            self._configuration,
            enabled=enabled,
        )
        self._refresh()
        self.configurationChanged.emit(self._configuration)

    def _edit_parameters(self) -> None:
        dialog = ManholeConfiguratorDialog(
            replace(self._configuration, enabled=True),
            self.options,
            self,
        )
        if dialog.exec() != QDialog.Accepted:
            dialog.deleteLater()
            return
        self._configuration = dialog.configuration()
        self.enabled_checkbox.blockSignals(True)
        self.enabled_checkbox.setChecked(True)
        self.enabled_checkbox.blockSignals(False)
        dialog.deleteLater()
        self._refresh()
        self.configurationChanged.emit(self._configuration)

    def _refresh(self) -> None:
        enabled = self._configuration.enabled
        self.edit_button.setEnabled(enabled)
        if not enabled:
            text = (
                "Olemasolev kaevu detail eemaldatakse rakendamisel."
                if self._initially_enabled
                else "Kaevu detaili ei lisata."
            )
            self.summary_label.setText(text)
            return

        parts = [
            self._label(
                self.options.type_options,
                self._configuration.type_id,
                "Määramata kaev",
            )
        ]
        material = self._label(
            self.options.material_options,
            self._configuration.material_id,
        )
        diameter_type = self._label(
            self.options.diameter_type_options,
            self._configuration.diameter_type_id,
        )
        diameter = self._label(
            self.options.diameter_options,
            self._configuration.diameter_id,
        )
        if material:
            parts.append(material)
        if diameter_type and diameter:
            parts.append(f"{diameter_type} {diameter}")
        elif diameter:
            parts.append(diameter)
        lid_material = self._label(
            self.options.lid_material_options,
            self._configuration.lid_material_id,
        )
        lid_diameter = self._label(
            self.options.lid_diameter_options,
            self._configuration.lid_diameter_id,
        )
        lid_parts = [value for value in (lid_material, lid_diameter) if value]
        if lid_parts:
            parts.append(f"kaas: {' '.join(lid_parts)}")
        self.summary_label.setText(" • ".join(parts))

    @staticmethod
    def _label(
        options: tuple[LookupOption, ...],
        value: int | None,
        fallback: str = "",
    ) -> str:
        return next(
            (
                option.label
                for option in options
                if option.value == value
            ),
            fallback,
        )
