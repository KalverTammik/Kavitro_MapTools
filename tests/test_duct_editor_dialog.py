"""Tests for the metadata-driven EVEL duct editor."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from qgis.PyQt.QtCore import QDate, QVariant
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QWidget,
)
from qgis.core import (
    QgsEditorWidgetSetup,
    QgsFeature,
    QgsFieldConstraints,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVariantUtils,
    QgsVectorLayer,
    QgsVectorLayerUtils,
)

from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.ui import (
    DuctEditorDialog,
    DuctEditorProfile,
    EvelDateEditor,
    GuidedFeatureEditor,
)


start_qgis()


class DuctEditorDialogTest(unittest.TestCase):
    def setUp(self) -> None:
        QgsProject.instance().clear()
        self.lookup = QgsVectorLayer(
            "None?field=ID:integer&field=TXT:string",
            "EVEL valikud",
            "memory",
        )
        for key, label in (
            (104, "De"),
            (108, "Peatoru"),
            (110, "Tarbijatoru"),
            (163, "Määramata"),
            (190, "Ümmargune"),
            (358, "PN10"),
            (404, "250"),
            (407, "315"),
            (401, "160"),
            (432, "PE"),
            (433, "PP"),
            (434, "PVC"),
            (538, "32"),
            (544, "110"),
            (700, "10 cm"),
            (701, "2 cm"),
            (702, "Maa-alune"),
            (703, "Teostusjoonis"),
            (704, "Digitud"),
        ):
            feature = QgsFeature(self.lookup.fields())
            feature.setAttributes([key, label])
            self.assertTrue(self.lookup.dataProvider().addFeature(feature))
        QgsProject.instance().addMapLayer(self.lookup)

        self.layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=IDENTIFICATION:string&field=NETWORK_ID:integer&"
            "field=NETTYPE_ID:integer&field=DUCT_TYPE_ID:integer&"
            "field=MATERIAL_ID:integer&field=DIAMETER_TYPE_ID:integer&"
            "field=DIAMETER_ID:integer&field=FORM_CODE_ID:integer&"
            "field=PRESSURE_CLASS_ID:integer&"
            "field=FIRMNESS_CLASS_ID:integer&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64&"
            "field=BEGIN_Z_COORD:double&field=END_Z_COORD:double&"
            "field=LOCATION_ID:integer&field=FLOWDIRECTION:double&"
            "field=CONDITION_CLASS_ID:integer&field=USAGE_STATE:string(24)&"
            "field=INVENTORY_NR:string(30)&field=OWNER_ID:integer&"
            "field=LESSEE_ID:integer&field=BUILD_YEAR:integer&"
            "field=REMOVAL_YEAR:integer&"
            "field=ESTIMATED_SERVICE_LIFE:integer&"
            "field=LOCATION_ACCURACY_ID:integer&"
            "field=HEIGHT_ACCURACY_ID:integer&"
            "field=MAPPING_METHOD_ID:integer&field=LENGTH_2D:double&"
            "field=NOTE:string(120)&field=ADDRESS_ID:integer&"
            "field=USAGE_PERMIT_NR:string(30)&"
            "field=USAGE_PERMIT_DATE:date&field=LENGTH:double&"
            "field=PRESSURE:double&field=EPANET_INNER_DIAMETER:double&"
            "field=EPANET_ROUGHNESS:double&field=EPANET_MLOSS:double&"
            "field=EPANET_STATUS_ID:integer&field=DUCT_FRICTION_LOSS:double",
            "Isevoolne kanal",
            "memory",
        )
        preference_fields = (
            "DUCT_TYPE_ID",
            "MATERIAL_ID",
            "DIAMETER_TYPE_ID",
            "DIAMETER_ID",
            "PRESSURE_CLASS_ID",
            "FIRMNESS_CLASS_ID",
            "FORM_CODE_ID",
            "LOCATION_ID",
            "LOCATION_ACCURACY_ID",
            "HEIGHT_ACCURACY_ID",
        )
        material_index = self.layer.fields().lookupField("MATERIAL_ID")
        self.layer.setFieldAlias(material_index, "Torumaterjal")
        self.layer.setFieldAlias(
            self.layer.fields().lookupField("LENGTH_2D"),
            "Pikkus 2D",
        )
        for field_name in preference_fields:
            self.layer.setEditorWidgetSetup(
                self.layer.fields().lookupField(field_name),
                QgsEditorWidgetSetup(
                    "ValueRelation",
                    {
                        "Layer": self.lookup.id(),
                        "Key": "ID",
                        "Value": "TXT",
                        "AllowNull": True,
                        "OrderByValue": True,
                    },
                ),
            )
        self.layer.setEditorWidgetSetup(
            self.layer.fields().lookupField("MAPPING_METHOD_ID"),
            QgsEditorWidgetSetup(
                "ValueRelation",
                {
                    "Layer": self.lookup.id(),
                    "Key": "ID",
                    "Value": "TXT",
                    "AllowNull": True,
                    "OrderByValue": True,
                },
            ),
        )
        self.layer.setEditorWidgetSetup(
            self.layer.fields().lookupField("CONDITION_CLASS_ID"),
            QgsEditorWidgetSetup(
                "ValueMap",
                {
                    "map": [
                        {"Väga madal": 0},
                        {"Madal": 1},
                        {"Rahuldav": 2},
                        {"Hea": 3},
                        {"Väga hea": 4},
                    ]
                },
            ),
        )
        self.layer.setEditorWidgetSetup(
            self.layer.fields().lookupField("USAGE_STATE"),
            QgsEditorWidgetSetup(
                "ValueMap",
                {"map": [{"Kasutuses": "Kasutuses"}]},
            ),
        )
        self.layer.setEditorWidgetSetup(
            self.layer.fields().lookupField("EPANET_STATUS_ID"),
            QgsEditorWidgetSetup(
                "ValueMap",
                {"map": [{"Avatud": 1}, {"Suletud": 0}]},
            ),
        )
        self.assertTrue(self.layer.startEditing())
        self.feature = QgsVectorLayerUtils.createFeature(
            self.layer,
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            ),
            {
                self.layer.fields().lookupField("MSLINK"): 4001,
                self.layer.fields().lookupField("NETWORK_ID"): 315,
                self.layer.fields().lookupField("NETTYPE_ID"): 309,
                self.layer.fields().lookupField("BEGIN_NODE_ID"): 10,
                self.layer.fields().lookupField("END_NODE_ID"): 20,
                self.layer.fields().lookupField("LENGTH_2D"): 10.0,
            },
        )
        self.assertTrue(self.layer.addFeature(self.feature))

    def tearDown(self) -> None:
        if self.layer.isEditable():
            self.layer.rollBack()
        QgsProject.instance().clear()

    def test_dialog_uses_layer_metadata_and_locks_technical_fields(self) -> None:
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )
        dialog.show()
        QApplication.processEvents()

        self.assertTrue(dialog.property("evelLightTheme"))
        self.assertIn("#f6f7f8", dialog.styleSheet())
        self.assertEqual(3, dialog.tabs.count())
        self.assertEqual("01  Toru", dialog.tabs.tabText(0))
        self.assertEqual("02  Haldus ja kvaliteet", dialog.tabs.tabText(1))
        self.assertEqual("03  EPANET", dialog.tabs.tabText(2))
        material = dialog.editor.binding("MATERIAL_ID")
        self.assertIsNotNone(material)
        self.assertEqual("Torumaterjal", material.label)
        self.assertIsInstance(material.widget, QComboBox)
        self.assertEqual(self.lookup.id(), material.wrapper.config()["Layer"])
        self.assertEqual("PVC", material.display_text())
        self.assertIsNotNone(dialog.editor.binding("FORM_CODE_ID"))
        flow = dialog.editor.binding("FLOWDIRECTION")
        self.assertIsNotNone(flow)
        self.assertIsInstance(flow.widget, QComboBox)
        self.assertTrue(flow.widget.isHidden())
        self.assertEqual(1, dialog.schematic._flow_direction())
        self.assertEqual(
            "Vool algusest lõppu",
            dialog.schematic.flow_direction_text(),
        )
        self.assertEqual(
            "Pööra suund",
            dialog.schematic.flow_direction_button.text(),
        )
        self.assertEqual(0, dialog._field_tabs["LOCATION_ID"])
        self.assertEqual(0, dialog._field_tabs["BEGIN_Z_COORD"])
        self.assertEqual(0, dialog._field_tabs["END_Z_COORD"])
        self.assertEqual(0, dialog._field_tabs["FLOWDIRECTION"])
        self.assertEqual(0, dialog._field_tabs["LOCATION_ACCURACY_ID"])
        self.assertEqual(0, dialog._field_tabs["HEIGHT_ACCURACY_ID"])
        self.assertEqual(
            "Asukoha täpsus\n10 cm",
            dialog.schematic.location_accuracy_button.text(),
        )
        self.assertEqual(
            "Kõrguse täpsus\n2 cm",
            dialog.schematic.height_accuracy_button.text(),
        )
        self.assertEqual(
            "Maa-alune",
            dialog.editor.binding("LOCATION_ID").display_text(),
        )
        for field_name in (
            "PRESSURE",
            "EPANET_INNER_DIAMETER",
            "EPANET_ROUGHNESS",
            "EPANET_MLOSS",
            "EPANET_STATUS_ID",
            "DUCT_FRICTION_LOSS",
        ):
            self.assertEqual(2, dialog._field_tabs[field_name])

        management_texts = {
            label.text()
            for label in dialog.tabs.widget(1).findChildren(QLabel)
        }
        self.assertNotIn("Asukoha täpsus", management_texts)
        self.assertNotIn("Kõrguse täpsus", management_texts)

        for field_name in (
            "MSLINK",
            "NETWORK_ID",
            "NETTYPE_ID",
            "BEGIN_NODE_ID",
            "END_NODE_ID",
            "LENGTH_2D",
        ):
            self.assertIsNone(dialog.editor.binding(field_name))

        dialog.close()
        dialog.deleteLater()

    def test_accuracy_defaults_replace_zero_and_can_be_changed_on_schematic(
        self,
    ) -> None:
        for field_name in (
            "LOCATION_ACCURACY_ID",
            "HEIGHT_ACCURACY_ID",
        ):
            index = self.layer.fields().lookupField(field_name)
            self.assertTrue(
                self.layer.changeAttributeValue(self.feature.id(), index, 0)
            )
            self.feature.setAttribute(index, 0)

        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.WATER,
        )

        self.assertEqual(
            700,
            dialog.editor.binding("LOCATION_ACCURACY_ID").value(),
        )
        self.assertEqual(
            701,
            dialog.editor.binding("HEIGHT_ACCURACY_ID").value(),
        )

        def choose_unknown(menu: QMenu, *_args):
            return next(
                action
                for action in menu.actions()
                if action.text() == "Määramata"
            )

        with patch.object(QMenu, "exec_", new=choose_unknown):
            dialog.schematic.location_accuracy_button.click()

        self.assertEqual(
            163,
            dialog.editor.binding("LOCATION_ACCURACY_ID").value(),
        )
        self.assertEqual(
            "Asukoha täpsus\nMääramata",
            dialog.schematic.location_accuracy_button.text(),
        )

        dialog.accept()
        updated = self.layer.getFeature(self.feature.id())
        self.assertEqual(163, updated["LOCATION_ACCURACY_ID"])
        self.assertEqual(701, updated["HEIGHT_ACCURACY_ID"])
        self.assertEqual(702, updated["LOCATION_ID"])
        dialog.deleteLater()

    def test_schematic_height_buttons_set_default_and_reverse_flow(self) -> None:
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.WATER,
        )

        with patch(
            "EVEL_network_tools.ui.duct_editor_dialog.QInputDialog.getText",
            return_value=("23", True),
        ):
            dialog.schematic.begin_height_button.click()
        with patch(
            "EVEL_network_tools.ui.duct_editor_dialog.QInputDialog.getText",
            return_value=("22", True),
        ):
            dialog.schematic.end_height_button.click()

        self.assertEqual(
            23.0,
            dialog.editor.binding("BEGIN_Z_COORD").value(),
        )
        self.assertEqual(
            22.0,
            dialog.editor.binding("END_Z_COORD").value(),
        )
        self.assertEqual(
            "ALGUS\nSõlm: 10\n0+000.00\n● Seotud",
            dialog.schematic.begin_height_button.text(),
        )
        self.assertEqual(
            "LÕPP\nSõlm: 20\n0+010.00\n● Seotud",
            dialog.schematic.end_height_button.text(),
        )
        self.assertEqual(((0.0, 23.0), (10.0, 22.0)), dialog.schematic._profile_points())
        self.assertEqual(
            "W 270°",
            dialog.schematic._bearing_text(
                dialog.schematic._flow_bearing()
            ),
        )
        self.assertEqual(-1, dialog.schematic._flow_direction())
        self.assertEqual(
            "Vool lõpust algusse",
            dialog.schematic.flow_direction_text(),
        )
        self.assertNotIn(
            "-1",
            dialog.schematic.flow_direction_button.toolTip(),
        )

        dialog.schematic.flow_direction_button.click()

        self.assertEqual(1, dialog.schematic._flow_direction())
        self.assertEqual(
            "Vool algusest lõppu",
            dialog.schematic.flow_direction_text(),
        )
        self.assertEqual(
            "E 90°",
            dialog.schematic._bearing_text(
                dialog.schematic._flow_bearing()
            ),
        )
        dialog.accept()
        updated = self.layer.getFeature(self.feature.id())
        self.assertEqual(23.0, updated["BEGIN_Z_COORD"])
        self.assertEqual(22.0, updated["END_Z_COORD"])
        self.assertEqual(1.0, updated["FLOWDIRECTION"])
        dialog.deleteLater()

    def test_new_dialog_hides_redundant_technical_information(self) -> None:
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.WATER,
        )

        self.assertIsNone(dialog.findChild(QLabel, "ductContext"))
        self.assertIsNone(dialog.findChild(QWidget, "ductTechnicalCard"))
        self.assertEqual(10.0, dialog.schematic._length_2d())
        self.assertEqual("0+010.00", dialog.schematic._chainage(10.0))

        dialog.close()
        dialog.deleteLater()

    def test_field_widths_follow_content_and_data_type(self) -> None:
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )

        identification = dialog.editor.binding("IDENTIFICATION")
        material = dialog.editor.binding("MATERIAL_ID")
        location = dialog.editor.binding("LOCATION_ID")
        note = dialog.editor.binding("NOTE")
        build_year = dialog.editor.binding("BUILD_YEAR")
        service_life = dialog.editor.binding("ESTIMATED_SERVICE_LIFE")
        self.assertIsNotNone(identification)
        self.assertIsNotNone(material)
        self.assertIsNotNone(location)
        self.assertIsNotNone(note)
        self.assertIsNotNone(build_year)
        self.assertIsNotNone(service_life)
        self.assertLessEqual(material.widget.maximumWidth(), 360)
        self.assertEqual(150, location.widget.maximumWidth())
        self.assertEqual(480, note.widget.maximumWidth())
        self.assertEqual(160, build_year.widget.maximumWidth())
        self.assertEqual(140, service_life.widget.maximumWidth())
        self.assertGreater(
            identification.widget.maximumWidth(),
            location.widget.maximumWidth(),
        )
        self.assertEqual(
            material.widget.maximumWidth(),
            material.widget.property("evelPreferredFieldWidth"),
        )
        self.assertLess(
            material.widget.maximumWidth(),
            note.widget.maximumWidth(),
        )

        dialog.close()
        dialog.deleteLater()

    def test_form_uses_icons_ui_labels_and_responsive_columns(self) -> None:
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )
        dialog.show()
        dialog.tabs.setCurrentIndex(1)
        QApplication.processEvents()

        self.assertFalse(dialog.tabs.tabIcon(0).isNull())
        self.assertFalse(dialog.tabs.tabIcon(1).isNull())
        self.assertFalse(dialog.tabs.tabIcon(2).isNull())
        self.assertEqual(
            "Materjal",
            dialog._field_rows["MATERIAL_ID"].title_label.text(),
        )
        self.assertEqual(
            "Paigaldusviis",
            dialog._field_rows["LOCATION_ID"].title_label.text(),
        )
        self.assertEqual(
            "Andmeallikas",
            dialog._field_rows["MAPPING_METHOD_ID"].title_label.text(),
        )
        self.assertFalse(
            dialog._field_rows["MATERIAL_ID"]
            .findChild(QLabel, "ductFieldIcon")
            .pixmap()
            .isNull()
        )

        management = dialog._form_grids["management"]
        self.assertEqual(2, management.column_count)
        dialog.resize(1050, 650)
        QApplication.processEvents()
        self.assertEqual(1, management.column_count)
        dialog.resize(1240, 780)
        QApplication.processEvents()
        self.assertEqual(2, management.column_count)
        self.assertFalse(
            dialog._field_groups["MAPPING_METHOD_ID"].isChecked()
        )
        advanced = dialog._form_grids["advanced"]
        self.assertTrue(advanced.isHidden())
        dialog._field_groups["MAPPING_METHOD_ID"].setChecked(True)
        QApplication.processEvents()
        self.assertFalse(advanced.isHidden())
        self.assertNotIn("__EVEL_", dialog.styleSheet())
        self.assertIn("control_chevron_down.svg", dialog.styleSheet())

        service_life = dialog.editor.binding("ESTIMATED_SERVICE_LIFE")
        service_line = service_life.widget.findChild(QLineEdit)
        self.assertIsNotNone(service_line)
        self.assertFalse(service_line.isClearButtonEnabled())
        self.assertFalse(service_life.widget.showClearButton())

        dialog.close()
        dialog.deleteLater()

    def test_null_text_condition_colours_calendar_and_units(self) -> None:
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )

        condition = dialog.editor.binding("CONDITION_CLASS_ID").widget
        self.assertIsInstance(condition, QComboBox)
        self.assertTrue(
            all(
                not condition.itemIcon(index).isNull()
                for index in range(condition.count())
            )
        )
        lowest = condition.itemIcon(0).pixmap(14, 14).toImage().pixelColor(7, 7)
        highest = condition.itemIcon(4).pixmap(14, 14).toImage().pixelColor(7, 7)
        self.assertGreater(lowest.red(), lowest.green())
        self.assertGreater(highest.green(), highest.red())
        self.assertEqual("Pole määratud", condition.itemText(5))
        self.assertEqual(
            "Pole määratud",
            dialog.editor.binding("USAGE_STATE").widget.currentText(),
        )

        permit_date = dialog.editor.binding("USAGE_PERMIT_DATE").widget
        date_control = dialog._date_editors["USAGE_PERMIT_DATE"]
        self.assertIsInstance(date_control, EvelDateEditor)
        self.assertFalse(permit_date.calendarPopup())
        self.assertEqual("dd.MM.yyyy", permit_date.displayFormat())
        self.assertEqual("", date_control.line_edit.text())
        self.assertEqual(
            "Pole määratud",
            date_control.line_edit.placeholderText(),
        )

        date_control.set_date(QDate(2024, 9, 12))
        self.assertEqual(QDate(2024, 9, 12), dialog.editor.binding("USAGE_PERMIT_DATE").value())
        self.assertEqual("12.09.2024", date_control.line_edit.text())
        date_control.clear_date()
        self.assertTrue(
            QgsVariantUtils.isNull(
                dialog.editor.binding("USAGE_PERMIT_DATE").value()
            )
        )
        self.assertEqual("", date_control.line_edit.text())

        pressure = dialog.editor.binding("PRESSURE")
        pressure.wrapper.setValues(4.2, [])
        QApplication.processEvents()
        unit = pressure.widget.findChild(QLabel, "ductFieldUnit")
        self.assertIsNotNone(unit)
        self.assertEqual("bar", unit.text())
        self.assertFalse(unit.isHidden())

        dialog.close()
        dialog.deleteLater()

    def test_invalid_manual_date_is_not_silently_saved(self) -> None:
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )
        date_control = dialog._date_editors["USAGE_PERMIT_DATE"]
        date_control.line_edit.setText("31.02.2025")
        date_control._commit_text()

        self.assertTrue(date_control.has_invalid_input())
        dialog.accept()
        self.assertEqual(0, dialog.result())
        self.assertIn("pp.kk.aaaa", dialog.error_label.text())
        self.assertTrue(
            dialog._field_groups["USAGE_PERMIT_DATE"].isChecked()
        )

        dialog.close()
        dialog.deleteLater()

    def test_semantic_permit_date_uses_custom_editor_for_datetime_column(
        self,
    ) -> None:
        layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=USAGE_PERMIT_DATE:datetime",
            "Timestamp duct",
            "memory",
        )
        self.assertTrue(layer.startEditing())
        feature = QgsVectorLayerUtils.createFeature(
            layer,
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(1, 1)]
            ),
        )
        self.assertTrue(layer.addFeature(feature))

        dialog = DuctEditorDialog(
            layer,
            feature,
            DuctEditorProfile.GRAVITY,
        )
        binding = dialog.editor.binding("USAGE_PERMIT_DATE")
        date_control = dialog._date_editors["USAGE_PERMIT_DATE"]
        self.assertEqual("datetime", layer.fields()[0].typeName())
        self.assertIsInstance(date_control, EvelDateEditor)
        self.assertFalse(binding.widget.calendarPopup())
        self.assertEqual("dd.MM.yyyy", binding.widget.displayFormat())

        dialog.close()
        dialog.deleteLater()

    def test_new_sewer_main_gets_label_based_preferred_values(self) -> None:
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )

        expected = {
            "DUCT_TYPE_ID": (108, "Peatoru"),
            "MATERIAL_ID": (434, "PVC"),
            "DIAMETER_TYPE_ID": (104, "De"),
            "DIAMETER_ID": (401, "160 mm"),
            "PRESSURE_CLASS_ID": (358, "PN10"),
            "FORM_CODE_ID": (190, "Ümmargune"),
        }
        for field_name, (value, label) in expected.items():
            binding = dialog.editor.binding(field_name)
            self.assertIsNotNone(binding)
            self.assertEqual(value, binding.value(), field_name)
            self.assertEqual(label, binding.display_text(), field_name)

        firmness = dialog.editor.binding("FIRMNESS_CLASS_ID")
        self.assertIsNotNone(firmness)
        self.assertTrue(QgsVariantUtils.isNull(firmness.value()))
        self.assertFalse(dialog.notice_label.isHidden())
        self.assertIn("SN8", dialog.notice_label.text())
        self.assertIn("FIRMNESS_CLASS", dialog.notice_label.text())
        dialog.close()
        dialog.deleteLater()

    def test_standard_firmness_choices_are_available_and_sn8_selected(
        self,
    ) -> None:
        sn8 = QgsFeature(self.lookup.fields())
        sn8.setAttributes([609, "SN8"])
        self.assertTrue(self.lookup.dataProvider().addFeature(sn8))
        sn16 = QgsFeature(self.lookup.fields())
        sn16.setAttributes([610, "SN16"])
        self.assertTrue(self.lookup.dataProvider().addFeature(sn16))

        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )

        firmness = dialog.editor.binding("FIRMNESS_CLASS_ID")
        self.assertIsNotNone(firmness)
        self.assertEqual(609, firmness.value())
        self.assertEqual("SN8", firmness.display_text())
        self.assertIn(
            "SN16",
            [
                firmness.widget.itemText(index)
                for index in range(firmness.widget.count())
            ],
        )
        self.assertTrue(dialog.notice_label.isHidden())
        dialog.close()
        dialog.deleteLater()

    def test_all_supported_networks_get_initial_preferences(self) -> None:
        for value_id, label in ((609, "SN8"), (610, "SN16")):
            feature = QgsFeature(self.lookup.fields())
            feature.setAttributes([value_id, label])
            self.assertTrue(self.lookup.dataProvider().addFeature(feature))

        cases = (
            (
                DuctEditorProfile.WATER,
                312,
                308,
                (
                    "Tarbijatoru",
                    "PE",
                    "De",
                    "32 mm",
                    "PN10",
                    "SN16",
                    None,
                ),
            ),
            (
                DuctEditorProfile.WATER,
                313,
                308,
                (
                    "Peatoru",
                    "PE",
                    "De",
                    "110 mm",
                    "PN10",
                    "SN16",
                    None,
                ),
            ),
            (
                DuctEditorProfile.WATER,
                314,
                308,
                (
                    "Peatoru",
                    "PE",
                    "De",
                    "110 mm",
                    "PN10",
                    "SN16",
                    None,
                ),
            ),
            (
                DuctEditorProfile.GRAVITY,
                316,
                309,
                (
                    "Peatoru",
                    "PP",
                    "De",
                    "315 mm",
                    "PN10",
                    "SN8",
                    "Ümmargune",
                ),
            ),
            (
                DuctEditorProfile.GRAVITY,
                317,
                None,
                (
                    "Peatoru",
                    "PP",
                    "De",
                    "250 mm",
                    "PN10",
                    "SN8",
                    "Ümmargune",
                ),
            ),
            (
                DuctEditorProfile.GRAVITY,
                318,
                None,
                (
                    "Peatoru",
                    "PP",
                    "De",
                    "315 mm",
                    "PN10",
                    "SN8",
                    "Ümmargune",
                ),
            ),
        )
        fields = (
            "DUCT_TYPE_ID",
            "MATERIAL_ID",
            "DIAMETER_TYPE_ID",
            "DIAMETER_ID",
            "PRESSURE_CLASS_ID",
            "FIRMNESS_CLASS_ID",
            "FORM_CODE_ID",
        )

        for profile, network_id, nettype_id, expected in cases:
            with self.subTest(
                profile=profile,
                network_id=network_id,
                nettype_id=nettype_id,
            ):
                self._set_network_context(network_id, nettype_id)
                dialog = DuctEditorDialog(
                    self.layer,
                    self.feature,
                    profile,
                )
                for field_name, label in zip(fields, expected):
                    binding = dialog.editor.binding(field_name)
                    if label is None:
                        self.assertIsNone(binding)
                    else:
                        self.assertIsNotNone(binding)
                        self.assertEqual(
                            label,
                            binding.display_text(),
                            field_name,
                        )
                self.assertTrue(dialog.notice_label.isHidden())
                dialog.close()
                dialog.deleteLater()

    def test_preference_does_not_overwrite_non_null_project_value(self) -> None:
        material_index = self.layer.fields().lookupField("MATERIAL_ID")
        self.assertTrue(
            self.layer.changeAttributeValue(
                self.feature.id(),
                material_index,
                432,
            )
        )
        self.feature.setAttribute(material_index, 432)

        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )

        material = dialog.editor.binding("MATERIAL_ID")
        self.assertIsNotNone(material)
        self.assertEqual(432, material.value())
        self.assertEqual("PE", material.display_text())
        dialog.close()
        dialog.deleteLater()

    def test_preference_is_not_applied_to_unsupported_profile(self) -> None:
        self._set_network_context(315, 308)

        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )

        duct_type = dialog.editor.binding("DUCT_TYPE_ID")
        self.assertIsNotNone(duct_type)
        self.assertTrue(QgsVariantUtils.isNull(duct_type.value()))
        self.assertTrue(dialog.notice_label.isHidden())
        dialog.close()
        dialog.deleteLater()

    def _set_network_context(
        self,
        network_id: int,
        nettype_id: int | None,
    ) -> None:
        for field_name, value in (
            ("NETWORK_ID", network_id),
            ("NETTYPE_ID", nettype_id),
        ):
            field_index = self.layer.fields().lookupField(field_name)
            self.assertTrue(
                self.layer.changeAttributeValue(
                    self.feature.id(),
                    field_index,
                    value,
                )
            )
            self.feature.setAttribute(field_index, value)

    def test_preference_is_not_applied_to_existing_feature(self) -> None:
        self.assertTrue(self.layer.commitChanges())
        existing = next(self.layer.getFeatures())
        self.assertTrue(self.layer.startEditing())

        dialog = DuctEditorDialog(
            self.layer,
            existing,
            DuctEditorProfile.GRAVITY,
        )

        duct_type = dialog.editor.binding("DUCT_TYPE_ID")
        self.assertIsNotNone(duct_type)
        self.assertTrue(QgsVariantUtils.isNull(duct_type.value()))
        self.assertTrue(dialog.notice_label.isHidden())
        self.assertFalse(dialog.is_new_feature)
        dialog.tabs.setCurrentIndex(dialog.tabs.count() - 1)
        self.assertEqual("Salvesta muudatused", dialog.next_button.text())
        dialog.close()
        dialog.deleteLater()

    def test_editor_applies_only_bound_values_to_edit_buffer(self) -> None:
        editor = GuidedFeatureEditor(self.layer, self.feature)
        parent = QWidget()
        identification = editor.create_binding(
            "IDENTIFICATION",
            parent,
        )
        material = editor.create_binding(
            "MATERIAL_ID",
            parent,
        )
        self.assertIsNotNone(identification)
        self.assertIsNotNone(material)
        identification.wrapper.setValues("K-42", [])
        material.wrapper.setValues(434, [])

        self.assertEqual({}, editor.apply())
        updated = self.layer.getFeature(self.feature.id())
        self.assertEqual("K-42", updated["IDENTIFICATION"])
        self.assertEqual(434, updated["MATERIAL_ID"])
        self.assertEqual(315, updated["NETWORK_ID"])
        self.assertEqual(10, updated["BEGIN_NODE_ID"])
        self.assertAlmostEqual(10.0, updated["LENGTH_2D"])
        parent.deleteLater()

    def test_flow_direction_selection_is_applied_as_evel_value(self) -> None:
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )
        flow = dialog.editor.binding("FLOWDIRECTION")
        self.assertIsNotNone(flow)
        flow.wrapper.setValues(-1.0, [])

        dialog.accept()

        self.assertEqual(QDialog.Accepted, dialog.result())
        self.assertEqual(
            -1.0,
            self.layer.getFeature(self.feature.id())["FLOWDIRECTION"],
        )
        self.assertEqual(-1, dialog.schematic._flow_direction())
        dialog.deleteLater()

    def test_hard_layer_constraint_blocks_accept(self) -> None:
        identification_index = self.layer.fields().lookupField(
            "IDENTIFICATION"
        )
        self.layer.setFieldConstraint(
            identification_index,
            QgsFieldConstraints.ConstraintNotNull,
            QgsFieldConstraints.ConstraintStrengthHard,
        )
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.WATER,
        )
        identification = dialog.editor.binding("IDENTIFICATION")
        self.assertIsNotNone(identification)
        identification.wrapper.setValues(QVariant(), [])

        dialog.accept()

        self.assertNotEqual(QDialog.Accepted, dialog.result())
        self.assertFalse(dialog.error_label.isHidden())
        self.assertIsNone(dialog.editor.binding("FORM_CODE_ID"))
        dialog.close()
        dialog.deleteLater()

    def test_validation_opens_advanced_group_for_required_field(self) -> None:
        address_index = self.layer.fields().lookupField("ADDRESS_ID")
        self.layer.setFieldConstraint(
            address_index,
            QgsFieldConstraints.ConstraintNotNull,
            QgsFieldConstraints.ConstraintStrengthHard,
        )
        dialog = DuctEditorDialog(
            self.layer,
            self.feature,
            DuctEditorProfile.GRAVITY,
        )
        address = dialog.editor.binding("ADDRESS_ID")
        self.assertIsNotNone(address)
        group = dialog._field_groups["ADDRESS_ID"]
        self.assertFalse(group.isChecked())
        address.wrapper.setValues(QVariant(), [])

        dialog.accept()

        self.assertNotEqual(QDialog.Accepted, dialog.result())
        self.assertTrue(group.isChecked())
        self.assertFalse(dialog._form_grids["advanced"].isHidden())
        self.assertFalse(dialog.error_label.isHidden())
        dialog.close()
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
