"""Tests for the metadata-driven EVEL duct editor."""

from __future__ import annotations

import unittest

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
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
            "field=CONDITION_CLASS_ID:integer&field=LENGTH_2D:double&"
            "field=NOTE:string&field=ADDRESS_ID:integer",
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
        )
        material_index = self.layer.fields().lookupField("MATERIAL_ID")
        self.layer.setFieldAlias(material_index, "Torumaterjal")
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
        self.assertEqual(
            [
                "Määramata",
                "Algusest lõppu (+1)",
                "Lõpust algusse (−1)",
            ],
            [
                flow.widget.itemText(index)
                for index in range(flow.widget.count())
            ],
        )

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
            "DIAMETER_ID": (401, "160"),
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
                    "32",
                    "PN10",
                    "Määramata",
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
                    "110",
                    "PN10",
                    "Määramata",
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
                    "110",
                    "PN10",
                    "Määramata",
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
                    "315",
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
                    "250",
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
                    "315",
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
        self.assertFalse(dialog.error_label.isHidden())
        dialog.close()
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
