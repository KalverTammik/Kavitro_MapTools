"""Tests for reading and atomically writing a water-node assembly."""

from __future__ import annotations

import unittest

from qgis.PyQt.QtCore import QDateTime, Qt
from qgis.PyQt.QtTest import QTest
from qgis.core import (
    QgsDefaultValue,
    QgsEditorWidgetSetup,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)

from EVEL_network_tools.layers import (
    FacilityConfigurationOptions,
    FacilityVariant,
    LookupOption,
    ManholeConfigurationOptions,
    NodeConfigurationContext,
)
from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.topology import (
    FacilityConfiguration,
    NodeAssemblyPlan,
    NodeAssemblyReader,
    NodeAssemblyWriter,
    NodeConfigurationError,
    ManholeConfiguration,
    PortValveConfiguration,
    branch_type_is_compatible,
)
from EVEL_network_tools.ui import (
    FacilityConfiguratorDialog,
    ManholeConfiguratorDialog,
    NodeConfigurationProgressDialog,
    VisualNodeConfiguratorDialog,
)


start_qgis()


class NodeConfigurationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.edge_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64&"
            "field=LENGTH_2D:double&field=MATERIAL_ID:integer&"
            "field=DIAMETER_TYPE_ID:integer&field=DIAMETER_ID:integer&"
            "field=PRESSURE_CLASS_ID:integer&field=FLOWDIRECTION:double",
            "Vesi",
            "memory",
        )
        self.node_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer&"
            "field=PNT_ROTATION:integer",
            "Veesõlmede baas",
            "memory",
        )
        self.branch_layer = QgsVectorLayer(
            "None?field=ID:integer64&field=NODE_ID:integer64&"
            "field=TYPE_AQUA_ID:integer",
            "Liitmike detail",
            "memory",
        )
        self.valve_layer = QgsVectorLayer(
            "None?field=ID:integer64&field=NODE_ID:integer64&"
            "field=TYPE_AQUA_ID:integer&field=TYPE_ID:integer",
            "Sulgeseadmete detail",
            "memory",
        )
        self.manhole_layer = QgsVectorLayer(
            "None?field=ID:integer64&field=NODE_ID:integer64&"
            "field=TYPE_ID:integer&field=MATERIAL_ID:integer&"
            "field=DIAMETER_TYPE_ID:integer&field=DIAMETER_ID:integer&"
            "field=FIRMNESS_CLASS_ID:integer&field=ANCHOR_PLATE:boolean&"
            "field=LOAD_LEVELING_PLATE:boolean&field=LID_TYPE_ID:integer&"
            "field=LID_MATERIAL_ID:integer&field=LID_SHAPE_ID:integer&"
            "field=LID_DIAMETER_ID:integer&field=LID_CAPACITY_ID:integer&"
            "field=LID_INSULATION:boolean&field=ACCESS_DUCT_DIAM:integer",
            "Kaevude detail",
            "memory",
        )
        self.facility_layer = QgsVectorLayer(
            "None?field=ID:integer64&field=NODE_ID:integer64&"
            "field=MATERIAL_ID:integer&field=ROLE_ID:integer&"
            "field=PRODUCTIVITY:double&field=PRESSURE_INCREASE:double&"
            "field=P_REG_CODE:string&field=P_PASPORT_NR:string&"
            "field=P_DEPTH:double&field=WATER_TYPE_ID:integer&"
            "field=WATER_SOURCE_ID:integer&field=WIPEOUT_DATE:datetime&"
            "field=RENEWAL_DATE:datetime&field=IS_CONTROLLED:boolean&"
            "field=IS_SIGNALISATION:boolean&field=PROTECTION_ZONE:double&"
            "field=MANTLE_DIAM:double",
            "Rajatiste detail",
            "memory",
        )
        self.constant_layer = QgsVectorLayer(
            "None?field=ID:integer&field=GROUPNAME:string&field=TXT:string",
            "Konstandid",
            "memory",
        )
        self._set_default(self.node_layer, "MSLINK", "1001")
        self._set_default(self.edge_layer, "MSLINK", "2001")
        self._set_default(self.branch_layer, "ID", "3001")
        self._set_default(self.valve_layer, "ID", "4001")
        self._set_default(self.manhole_layer, "ID", "5001")
        self._set_default(self.manhole_layer, "TYPE_ID", "570")
        self._set_default(self.facility_layer, "ID", "6001")
        self.edge_layer.setCustomProperty(
            "evel_topology_node_network_id", 312
        )
        self.edge_layer.setCustomProperty(
            "evel_topology_node_nettype_id", 308
        )
        self._set_value_map(self.edge_layer, "MATERIAL_ID", "PE", 7)
        self._set_value_map(
            self.edge_layer, "DIAMETER_TYPE_ID", "De", 104
        )
        self._set_value_map(self.edge_layer, "DIAMETER_ID", "32", 538)
        self._set_value_map(
            self.edge_layer, "PRESSURE_CLASS_ID", "PN10", 358
        )

        self._add_node(10, 0, 0)
        self._add_node(20, 10, 0)
        edge = QgsFeature(self.edge_layer.fields())
        edge.setAttributes(
            [501, 312, 311, 10, 20, 10.0, 7, 104, 538, 358, 1.0]
        )
        edge.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            )
        )
        self.assertTrue(self.edge_layer.dataProvider().addFeature(edge))

        self.context = NodeConfigurationContext(
            edge_layer=self.edge_layer,
            node_layer=self.node_layer,
            branch_detail_layer=self.branch_layer,
            valve_detail_layer=self.valve_layer,
            manhole_detail_layer=self.manhole_layer,
            constant_layer=self.constant_layer,
            branch_options=(
                LookupOption(522, "Määramata"),
                LookupOption(523, "Käänik"),
                LookupOption(524, "Kaelus"),
                LookupOption(525, "Kolmik"),
                LookupOption(526, "Nelik"),
                LookupOption(527, "Liitmik"),
                LookupOption(528, "Üleminek"),
                LookupOption(529, "Äärik"),
                LookupOption(530, "Sadul"),
                LookupOption(531, "Otsakork"),
            ),
            valve_options=(
                LookupOption(589, "Liini"),
                LookupOption(590, "Kinnistu"),
            ),
            valve_subtype_options=(
                LookupOption(591, "Määramata"),
                LookupOption(592, "Kiil"),
                LookupOption(595, "Kuulkraan"),
                LookupOption(596, "Korkkraan"),
            ),
            valve_default_type_id=589,
            valve_default_subtype_id=591,
            manhole_options=ManholeConfigurationOptions(
                type_options=(
                    LookupOption(570, "Määramata"),
                    LookupOption(571, "Arvestikaev"),
                    LookupOption(572, "Hoolduskaev"),
                ),
                material_options=(
                    LookupOption(446, "Määramata"),
                    LookupOption(447, "Betoon rõngas"),
                    LookupOption(454, "PE"),
                ),
                diameter_type_options=(
                    LookupOption(104, "De"),
                    LookupOption(105, "Di"),
                    LookupOption(106, "Dn"),
                ),
                diameter_options=(
                    LookupOption(562, "400"),
                    LookupOption(565, "1000"),
                ),
                firmness_options=(LookupOption(163, "Määramata"),),
                lid_type_options=(
                    LookupOption(284, "Määramata"),
                    LookupOption(286, "Kinnine"),
                ),
                lid_material_options=(
                    LookupOption(275, "Määramata"),
                    LookupOption(277, "Malm"),
                ),
                lid_shape_options=(
                    LookupOption(281, "Määramata"),
                    LookupOption(282, "Ümar"),
                ),
                lid_diameter_options=(
                    LookupOption(268, "200"),
                    LookupOption(271, "600"),
                ),
                lid_capacity_options=(
                    LookupOption(265, "Määramata"),
                    LookupOption(267, "40"),
                ),
                default_type_id=570,
            ),
            facility_options=FacilityConfigurationOptions(
                variants=(
                    FacilityVariant(
                        key="312:370:378",
                        label="Veevõrgupumpla",
                        network_id=312,
                        role_id=370,
                        water_type_id=378,
                        detail_layer=self.facility_layer,
                        visible_layer=self.node_layer,
                        default_material_id=363,
                        default_water_source_id=373,
                    ),
                    FacilityVariant(
                        key="312:369:376",
                        label="Veetöötlusjaam",
                        network_id=312,
                        role_id=369,
                        water_type_id=376,
                        detail_layer=self.facility_layer,
                        visible_layer=self.node_layer,
                        default_material_id=363,
                        default_water_source_id=373,
                    ),
                    FacilityVariant(
                        key="314:369:376",
                        label="Puurkaevud ja veeallikad",
                        network_id=314,
                        role_id=369,
                        water_type_id=376,
                        detail_layer=self.facility_layer,
                        visible_layer=self.node_layer,
                        default_material_id=363,
                        default_water_source_id=373,
                    ),
                ),
                material_options=(
                    LookupOption(363, "Määramata"),
                    LookupOption(364, "Betoon"),
                ),
                water_source_options=(
                    LookupOption(373, "Määramata"),
                    LookupOption(374, "Põhjavesi"),
                ),
            ),
        )
        for layer in self._editable_layers():
            self.assertTrue(layer.startEditing())

    def tearDown(self) -> None:
        for layer in self._editable_layers():
            if layer.isEditable():
                layer.rollBack()

    def test_reader_finds_incident_port_and_dialog_suggests_end_cap(self) -> None:
        state = NodeAssemblyReader(self.context).read(10)

        self.assertEqual(1, len(state.ports))
        self.assertTrue(state.ports[0].central_at_start)
        self.assertEqual(20, state.ports[0].other_node_id)
        self.assertEqual(
            ("De 32", "PE", "PN10"),
            state.ports[0].technical_parameters,
        )
        self.assertEqual(1.0, state.ports[0].flow_direction)
        self.assertFalse(state.manhole.enabled)
        self.assertEqual(570, state.manhole.type_id)
        dialog = VisualNodeConfiguratorDialog(
            state,
            self.context.branch_options,
            self.context.valve_options,
            self.context.valve_subtype_options,
            self.context.valve_default_type_id,
            self.context.valve_default_subtype_id,
            self.context.manhole_options,
            self.context.facility_options,
        )
        self.assertTrue(dialog.property("evelLightTheme"))
        self.assertIn("#f6f7f8", dialog.styleSheet())
        self.assertEqual(531, dialog.configuration().branch_type_id)
        self.assertEqual(589, dialog.configuration().ports[0].valve_type_id)
        self.assertEqual(591, dialog.configuration().ports[0].valve_subtype_id)
        self.assertFalse(dialog.configuration().manhole.enabled)
        self.assertIsNotNone(dialog.facility_section)
        self.assertIsNone(dialog.configuration().facility.variant_key)
        self.assertEqual(
            -1,
            dialog.facility_section.variant_combo.findData("314:369:376"),
        )
        self.assertGreaterEqual(dialog.branch_combo.findData(531), 0)
        self.assertGreaterEqual(dialog.branch_combo.findData(522), 0)
        self.assertEqual(-1, dialog.branch_combo.findData(525))
        self.assertEqual(-1, dialog.branch_combo.findData(526))
        self.assertIn("1 toruharu", dialog.branch_hint.text())
        self.assertAlmostEqual(0.30, dialog.distance_spin.maximum())
        self.assertAlmostEqual(0.30, dialog.distance_spin.value())
        dialog.manhole_section.enabled_checkbox.setChecked(True)
        self.assertTrue(dialog.configuration().manhole.enabled)
        dialog.deleteLater()

    def test_visual_dialog_uses_real_bearings_and_configures_clicked_arm(
        self,
    ) -> None:
        self._add_node(30, -10, 0)
        self._add_node(40, 0, 10)
        self._add_edge(
            502,
            30,
            10,
            [QgsPointXY(-10, 0), QgsPointXY(0, 0)],
        )
        self._add_edge(
            503,
            10,
            40,
            [QgsPointXY(0, 0), QgsPointXY(0, 10)],
        )
        state = NodeAssemblyReader(self.context).read(10)
        self.assertEqual([90.0, 270.0, 0.0], [port.bearing for port in state.ports])

        dialog = VisualNodeConfiguratorDialog(
            state,
            self.context.branch_options,
            self.context.valve_options,
            self.context.valve_subtype_options,
            self.context.valve_default_type_id,
            self.context.valve_default_subtype_id,
            self.context.manhole_options,
            self.context.facility_options,
        )
        dialog.show()
        start_qgis().processEvents()
        self.assertEqual(525, dialog.branch_combo.currentData())
        self.assertGreaterEqual(dialog.branch_combo.findData(530), 0)
        self.assertEqual(-1, dialog.branch_combo.findData(526))
        self.assertEqual(-1, dialog.branch_combo.findData(531))
        self.assertEqual(-1, dialog.branch_combo.findData(527))
        self.assertIn("3 toruharu", dialog.branch_hint.text())
        self.assertFalse(hasattr(dialog, "summary_label"))
        self.assertEqual(525, dialog.schematic.branch_type_id)
        self.assertFalse(dialog.schematic.manhole_enabled)
        self.assertIsNone(dialog.schematic.facility_label)
        dialog.facility_section.variant_combo.setCurrentIndex(
            dialog.facility_section.variant_combo.findData("312:370:378")
        )
        self.assertEqual("Veevõrgupumpla", dialog.schematic.facility_label)
        self.assertEqual(
            "312:370:378",
            dialog.configuration().facility.variant_key,
        )
        dialog.manhole_section.enabled_checkbox.setChecked(True)
        self.assertTrue(dialog.schematic.manhole_enabled)
        self.assertTrue(dialog.configuration().manhole.enabled)
        dialog.branch_combo.setCurrentIndex(
            dialog.branch_combo.findData(530)
        )
        self.assertEqual(530, dialog.schematic.branch_type_id)
        dialog.branch_combo.setCurrentIndex(
            dialog.branch_combo.findData(525)
        )
        self.assertEqual(525, dialog.schematic.branch_type_id)
        self.assertTrue(
            all(
                not button.icon().isNull()
                for button in dialog._component_buttons.values()
            )
        )
        self.assertTrue(
            all(
                button.toolButtonStyle() == Qt.ToolButtonTextBesideIcon
                for button in dialog._component_buttons.values()
            )
        )

        center_x = dialog.schematic.width() / 2.0
        center_y = dialog.schematic.height() / 2.0
        east = dialog.schematic.port_endpoint(0)
        west = dialog.schematic.port_endpoint(1)
        north = dialog.schematic.port_endpoint(2)
        self.assertGreater(east.x(), center_x)
        self.assertLess(west.x(), center_x)
        self.assertLess(north.y(), center_y)
        self.assertTrue(dialog.schematic.port_flow_outward(0))
        self.assertFalse(dialog.schematic.port_flow_outward(1))
        self.assertTrue(dialog.schematic.port_flow_outward(2))
        label_rects = [
            dialog.schematic.port_label_rect(index)
            for index in range(len(state.ports))
        ]
        self.assertTrue(
            all(
                not label_rects[index].contains(
                    dialog.schematic.port_endpoint(index)
                )
                for index in range(len(state.ports))
            )
        )
        self.assertTrue(
            all(
                not label_rects[left].intersects(label_rects[right])
                for left in range(len(label_rects))
                for right in range(left + 1, len(label_rects))
            )
        )

        QTest.mouseClick(
            dialog.schematic,
            Qt.LeftButton,
            pos=dialog.schematic.port_slot_center(2).toPoint(),
        )
        self.assertEqual(2, dialog.schematic.selected_port)
        dialog._component_buttons[595].click()
        dialog.valve_type_combo.setCurrentIndex(
            dialog.valve_type_combo.findData(590)
        )
        dialog.distance_spin.setValue(0.18)
        drag_start = dialog.schematic.port_slot_center(2).toPoint()
        drag_target = dialog.schematic.port_distance_point(
            2, 0.05
        ).toPoint()
        QTest.mousePress(
            dialog.schematic,
            Qt.LeftButton,
            pos=drag_start,
        )
        QTest.mouseMove(dialog.schematic, pos=drag_target)
        QTest.mouseRelease(
            dialog.schematic,
            Qt.LeftButton,
            pos=drag_target,
        )

        plan = dialog.configuration()
        self.assertEqual([False, False, True], [port.enabled for port in plan.ports])
        self.assertEqual(595, plan.ports[2].valve_subtype_id)
        self.assertEqual(590, plan.ports[2].valve_type_id)
        self.assertAlmostEqual(0.05, dialog.distance_spin.value())
        self.assertAlmostEqual(0.05, plan.ports[2].distance)
        dialog.close()
        dialog.deleteLater()

        result = NodeAssemblyWriter(self.context).write(plan)
        self.assertEqual(1, len(result.created_valve_node_ids))
        self.assertTrue(result.manhole_enabled)
        self.assertEqual(1, self.manhole_layer.featureCount())
        self.assertEqual("312:370:378", result.facility_variant_key)
        self.assertEqual(1, self.facility_layer.featureCount())
        branch = next(self.branch_layer.getFeatures())
        self.assertEqual(525, branch["TYPE_AQUA_ID"])
        valve = next(self.valve_layer.getFeatures())
        self.assertEqual(590, valve["TYPE_AQUA_ID"])
        self.assertEqual(595, valve["TYPE_ID"])
        self.assertAlmostEqual(
            0.05,
            min(
                feature.geometry().length()
                for feature in self.edge_layer.getFeatures()
            ),
        )

    def test_adds_updates_and_removes_manhole_detail(self) -> None:
        state = NodeAssemblyReader(self.context).read(10)
        editor = ManholeConfiguratorDialog(
            state.manhole,
            self.context.manhole_options,
        )
        self.assertTrue(editor.property("evelLightTheme"))
        self.assertIn("#f6f7f8", editor.styleSheet())
        self.assertEqual(2, editor.tabs.count())
        editor.type_combo.setCurrentIndex(
            editor.type_combo.findData(572)
        )
        editor.material_combo.setCurrentIndex(
            editor.material_combo.findData(447)
        )
        editor.diameter_type_combo.setCurrentIndex(
            editor.diameter_type_combo.findData(104)
        )
        editor.diameter_combo.setCurrentIndex(
            editor.diameter_combo.findData(565)
        )
        editor.lid_type_combo.setCurrentIndex(
            editor.lid_type_combo.findData(286)
        )
        editor.lid_material_combo.setCurrentIndex(
            editor.lid_material_combo.findData(277)
        )
        editor.lid_shape_combo.setCurrentIndex(
            editor.lid_shape_combo.findData(282)
        )
        editor.lid_diameter_combo.setCurrentIndex(
            editor.lid_diameter_combo.findData(271)
        )
        editor.lid_capacity_combo.setCurrentIndex(
            editor.lid_capacity_combo.findData(267)
        )
        editor.anchor_plate_check.setChecked(True)
        editor.load_leveling_plate_check.setChecked(True)
        editor.lid_insulation_check.setChecked(True)
        editor.access_duct_spin.setValue(630)
        manhole = editor.configuration()
        editor.deleteLater()

        result = NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=state,
                branch_type_id=None,
                ports=self._disabled_ports(state),
                manhole=manhole,
            )
        )
        self.assertTrue(result.manhole_enabled)
        self.assertEqual(1, self.manhole_layer.featureCount())
        detail = next(self.manhole_layer.getFeatures())
        self.assertEqual(10, detail["NODE_ID"])
        self.assertEqual(572, detail["TYPE_ID"])
        self.assertEqual(447, detail["MATERIAL_ID"])
        self.assertEqual(104, detail["DIAMETER_TYPE_ID"])
        self.assertEqual(565, detail["DIAMETER_ID"])
        self.assertTrue(detail["ANCHOR_PLATE"])
        self.assertTrue(detail["LOAD_LEVELING_PLATE"])
        self.assertEqual(286, detail["LID_TYPE_ID"])
        self.assertEqual(277, detail["LID_MATERIAL_ID"])
        self.assertEqual(282, detail["LID_SHAPE_ID"])
        self.assertEqual(271, detail["LID_DIAMETER_ID"])
        self.assertEqual(267, detail["LID_CAPACITY_ID"])
        self.assertTrue(detail["LID_INSULATION"])
        self.assertEqual(630, detail["ACCESS_DUCT_DIAM"])

        existing_state = NodeAssemblyReader(self.context).read(10)
        self.assertTrue(existing_state.manhole.enabled)
        self.assertIsNotNone(existing_state.manhole_detail_feature_id)
        self.assertEqual(572, existing_state.manhole.type_id)
        self.assertEqual(447, existing_state.manhole.material_id)
        self.assertEqual(630, existing_state.manhole.access_duct_diam)

        updated = ManholeConfiguration(
            enabled=True,
            type_id=571,
            material_id=454,
            diameter_type_id=105,
            diameter_id=562,
            lid_type_id=284,
            access_duct_diam=500,
        )
        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=existing_state,
                branch_type_id=None,
                ports=self._disabled_ports(existing_state),
                manhole=updated,
            )
        )
        self.assertEqual(1, self.manhole_layer.featureCount())
        detail = next(self.manhole_layer.getFeatures())
        self.assertEqual(571, detail["TYPE_ID"])
        self.assertEqual(454, detail["MATERIAL_ID"])
        self.assertEqual(500, detail["ACCESS_DUCT_DIAM"])

        removable_state = NodeAssemblyReader(self.context).read(10)
        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=removable_state,
                branch_type_id=None,
                ports=self._disabled_ports(removable_state),
                manhole=ManholeConfiguration(
                    enabled=False,
                    type_id=570,
                ),
            )
        )
        self.assertEqual(0, self.manhole_layer.featureCount())

    def test_adds_switches_and_removes_facility_detail(self) -> None:
        state = NodeAssemblyReader(self.context).read(10)
        self.assertIsNone(state.facility.variant_key)
        pump_variant = self.context.facility_options.variants[0]
        editor = FacilityConfiguratorDialog(
            FacilityConfiguration(
                variant_key=pump_variant.key,
                material_id=pump_variant.default_material_id,
                water_source_id=pump_variant.default_water_source_id,
            ),
            pump_variant,
            self.context.facility_options,
        )
        self.assertTrue(editor.property("evelLightTheme"))
        self.assertIn("#f6f7f8", editor.styleSheet())
        editor.material_combo.setCurrentIndex(
            editor.material_combo.findData(364)
        )
        editor.productivity_spin.setValue(12.5)
        editor.pressure_spin.setValue(2.4)
        editor.registry_edit.setText("REG-42")
        editor.passport_edit.setText("PASS-7")
        editor.depth_spin.setValue(48.3)
        editor.water_source_combo.setCurrentIndex(
            editor.water_source_combo.findData(374)
        )
        editor.protection_zone_spin.setValue(50.0)
        editor.mantle_diam_spin.setValue(160.0)
        editor.controlled_check.setChecked(True)
        editor.signalisation_check.setChecked(True)
        editor.renewal_date.enabled_checkbox.setChecked(True)
        editor.renewal_date.editor.setDateTime(
            QDateTime.fromString("2024-05-06T00:00:00", Qt.ISODate)
        )
        facility = editor.configuration()
        editor.deleteLater()

        result = NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=state,
                branch_type_id=None,
                ports=self._disabled_ports(state),
                facility=facility,
            )
        )
        self.assertEqual("312:370:378", result.facility_variant_key)
        self.assertEqual(1, self.facility_layer.featureCount())
        detail = next(self.facility_layer.getFeatures())
        self.assertEqual(10, detail["NODE_ID"])
        self.assertEqual(370, detail["ROLE_ID"])
        self.assertEqual(378, detail["WATER_TYPE_ID"])
        self.assertEqual(364, detail["MATERIAL_ID"])
        self.assertAlmostEqual(12.5, detail["PRODUCTIVITY"])
        self.assertAlmostEqual(2.4, detail["PRESSURE_INCREASE"])
        self.assertEqual("REG-42", detail["P_REG_CODE"])
        self.assertEqual("PASS-7", detail["P_PASPORT_NR"])
        self.assertAlmostEqual(48.3, detail["P_DEPTH"])
        self.assertEqual(374, detail["WATER_SOURCE_ID"])
        self.assertTrue(detail["IS_CONTROLLED"])
        self.assertTrue(detail["IS_SIGNALISATION"])
        self.assertAlmostEqual(50.0, detail["PROTECTION_ZONE"])
        self.assertAlmostEqual(160.0, detail["MANTLE_DIAM"])

        existing = NodeAssemblyReader(self.context).read(10)
        self.assertEqual("312:370:378", existing.facility.variant_key)
        self.assertEqual(364, existing.facility.material_id)
        self.assertEqual("REG-42", existing.facility.registry_code)
        self.assertIsNotNone(existing.facility.renewal_date)
        self.assertEqual(2024, existing.facility.renewal_date.year)

        treatment = FacilityConfiguration(
            variant_key="312:369:376",
            material_id=363,
            productivity=8.0,
            water_source_id=373,
        )
        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=existing,
                branch_type_id=None,
                ports=self._disabled_ports(existing),
                facility=treatment,
            )
        )
        self.assertEqual(1, self.facility_layer.featureCount())
        detail = next(self.facility_layer.getFeatures())
        self.assertEqual(369, detail["ROLE_ID"])
        self.assertEqual(376, detail["WATER_TYPE_ID"])
        self.assertAlmostEqual(8.0, detail["PRODUCTIVITY"])

        removable = NodeAssemblyReader(self.context).read(10)
        self.assertEqual(
            "312:369:376",
            removable.facility.variant_key,
        )
        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=removable,
                branch_type_id=None,
                ports=self._disabled_ports(removable),
                facility=FacilityConfiguration(),
            )
        )
        self.assertEqual(0, self.facility_layer.featureCount())

        clean_state = NodeAssemblyReader(self.context).read(10)
        with self.assertRaisesRegex(
            NodeConfigurationError,
            "ei vasta sõlme võrgule",
        ):
            NodeAssemblyWriter(self.context).write(
                NodeAssemblyPlan(
                    state=clean_state,
                    branch_type_id=None,
                    ports=self._disabled_ports(clean_state),
                    facility=FacilityConfiguration(
                        variant_key="314:369:376",
                        material_id=363,
                        water_source_id=373,
                    ),
                )
            )
        self.assertEqual(0, self.facility_layer.featureCount())

    def test_branch_type_compatibility_and_writer_reject_mismatch(self) -> None:
        self.assertTrue(branch_type_is_compatible(531, 1))
        self.assertTrue(branch_type_is_compatible(527, 2))
        self.assertTrue(branch_type_is_compatible(525, 3))
        self.assertTrue(branch_type_is_compatible(526, 4))
        self.assertTrue(branch_type_is_compatible(522, 7))
        self.assertTrue(branch_type_is_compatible(None, 7))
        self.assertFalse(branch_type_is_compatible(526, 3))
        self.assertFalse(branch_type_is_compatible(525, 2))

        state = NodeAssemblyReader(self.context).read(10)
        with self.assertRaisesRegex(
            NodeConfigurationError,
            "eeldab 4 toruharu",
        ):
            NodeAssemblyWriter(self.context).write(
                NodeAssemblyPlan(
                    state=state,
                    branch_type_id=526,
                    ports=self._disabled_ports(state),
                )
            )

        self.assertEqual(0, self.branch_layer.featureCount())
        self.assertEqual(1, self.edge_layer.featureCount())

    def test_writes_fitting_and_valve_by_splitting_incident_pipe(self) -> None:
        state = NodeAssemblyReader(self.context).read(10)
        plan = NodeAssemblyPlan(
            state=state,
            branch_type_id=531,
            ports=(
                PortValveConfiguration(
                    port=state.ports[0],
                    enabled=True,
                    distance=0.20,
                    valve_type_id=589,
                    valve_subtype_id=595,
                ),
            ),
        )

        progress = []
        result = NodeAssemblyWriter(self.context).write(
            plan,
            lambda current, total, message: progress.append(
                (current, total, message)
            ),
        )

        self.assertEqual(10, result.node_id)
        self.assertEqual(
            [0, 1, 2, 3, 4, 5, 6],
            [item[0] for item in progress],
        )
        self.assertTrue(all(item[1] == 6 for item in progress))
        self.assertIn("haru 1/1", progress[4][2])
        self.assertIn("redigeerimispuhvris", progress[-1][2])
        self.assertEqual((1001,), result.created_valve_node_ids)
        self.assertEqual(3, self.node_layer.featureCount())
        self.assertEqual(2, self.edge_layer.featureCount())

        branch = next(self.branch_layer.getFeatures())
        self.assertEqual(10, branch["NODE_ID"])
        self.assertEqual(531, branch["TYPE_AQUA_ID"])
        valve = next(self.valve_layer.getFeatures())
        self.assertEqual(1001, valve["NODE_ID"])
        self.assertEqual(589, valve["TYPE_AQUA_ID"])
        self.assertEqual(595, valve["TYPE_ID"])
        central_node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 10
        )
        valve_node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 1001
        )
        self.assertAlmostEqual(0.0, central_node["PNT_ROTATION"])
        self.assertAlmostEqual(0.0, valve_node["PNT_ROTATION"])

        pieces = sorted(
            self.edge_layer.getFeatures(), key=lambda feature: feature.geometry().length()
        )
        self.assertAlmostEqual(0.20, pieces[0].geometry().length())
        self.assertEqual(10, int(pieces[0]["BEGIN_NODE_ID"]))
        self.assertEqual(1001, int(pieces[0]["END_NODE_ID"]))
        self.assertAlmostEqual(9.80, pieces[1].geometry().length())
        self.assertEqual(1001, int(pieces[1]["BEGIN_NODE_ID"]))
        self.assertEqual(20, int(pieces[1]["END_NODE_ID"]))

    def test_progress_dialog_builds_activity_timeline(self) -> None:
        dialog = NodeConfigurationProgressDialog(10)
        self.assertTrue(dialog.property("evelLightTheme"))
        self.assertIn("#f6f7f8", dialog.styleSheet())
        dialog.update_progress(0, 3, "Valmistan kihid ette.")
        dialog.update_progress(1, 3, "Uuendan liitmikku.")

        self.assertEqual(3, dialog.progress_bar.maximum())
        self.assertEqual(1, dialog.progress_bar.value())
        self.assertEqual(2, dialog.timeline.count())
        self.assertTrue(dialog.timeline.item(0).text().startswith("✓"))
        self.assertTrue(dialog.timeline.item(1).text().startswith("▶"))
        dialog.close()
        dialog.deleteLater()

    def test_rotates_tee_with_east_west_main_and_north_branch(self) -> None:
        self._add_node(30, -10, 0)
        self._add_node(40, 0, 10)
        self._add_edge(502, 30, 10, [QgsPointXY(-10, 0), QgsPointXY(0, 0)])
        self._add_edge(503, 10, 40, [QgsPointXY(0, 0), QgsPointXY(0, 10)])
        state = NodeAssemblyReader(self.context).read(10)

        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=state,
                branch_type_id=525,
                ports=self._disabled_ports(state),
            )
        )

        node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 10
        )
        self.assertAlmostEqual(90.0, node["PNT_ROTATION"])

    def test_rotates_tee_with_east_west_main_and_south_branch(self) -> None:
        self._add_node(30, -10, 0)
        self._add_node(40, 0, -10)
        self._add_edge(502, 30, 10, [QgsPointXY(-10, 0), QgsPointXY(0, 0)])
        self._add_edge(503, 10, 40, [QgsPointXY(0, 0), QgsPointXY(0, -10)])
        state = NodeAssemblyReader(self.context).read(10)

        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=state,
                branch_type_id=525,
                ports=self._disabled_ports(state),
            )
        )

        node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 10
        )
        self.assertAlmostEqual(270.0, node["PNT_ROTATION"])

    def test_rotates_valve_to_vertical_pipe_axis(self) -> None:
        neighbor = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 20
        )
        self.assertTrue(
            self.node_layer.changeGeometry(
                neighbor.id(),
                QgsGeometry.fromPointXY(QgsPointXY(0, 10)),
            )
        )
        edge = next(self.edge_layer.getFeatures())
        self.assertTrue(
            self.edge_layer.changeGeometry(
                edge.id(),
                QgsGeometry.fromPolylineXY(
                    [QgsPointXY(0, 0), QgsPointXY(0, 10)]
                ),
            )
        )
        state = NodeAssemblyReader(self.context).read(10)

        result = NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=state,
                branch_type_id=531,
                ports=(
                    PortValveConfiguration(
                        port=state.ports[0],
                        enabled=True,
                        distance=0.20,
                        valve_type_id=589,
                        valve_subtype_id=592,
                    ),
                ),
            )
        )

        valve_node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == result.created_valve_node_ids[0]
        )
        self.assertAlmostEqual(90.0, valve_node["PNT_ROTATION"])

    def test_rotates_valve_to_diagonal_pipe_axis(self) -> None:
        neighbor = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 20
        )
        self.assertTrue(
            self.node_layer.changeGeometry(
                neighbor.id(),
                QgsGeometry.fromPointXY(QgsPointXY(10, 10)),
            )
        )
        edge = next(self.edge_layer.getFeatures())
        self.assertTrue(
            self.edge_layer.changeGeometry(
                edge.id(),
                QgsGeometry.fromPolylineXY(
                    [QgsPointXY(0, 0), QgsPointXY(10, 10)]
                ),
            )
        )
        state = NodeAssemblyReader(self.context).read(10)

        result = NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=state,
                branch_type_id=531,
                ports=(
                    PortValveConfiguration(
                        port=state.ports[0],
                        enabled=True,
                        distance=0.20,
                        valve_type_id=589,
                        valve_subtype_id=592,
                    ),
                ),
            )
        )

        valve_node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == result.created_valve_node_ids[0]
        )
        self.assertAlmostEqual(135.0, valve_node["PNT_ROTATION"])

    def test_rounds_non_integer_rotation_for_integer_provider_field(self) -> None:
        neighbor = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 20
        )
        self.assertTrue(
            self.node_layer.changeGeometry(
                neighbor.id(),
                QgsGeometry.fromPointXY(QgsPointXY(4, 10)),
            )
        )
        edge = next(self.edge_layer.getFeatures())
        self.assertTrue(
            self.edge_layer.changeGeometry(
                edge.id(),
                QgsGeometry.fromPolylineXY(
                    [QgsPointXY(0, 0), QgsPointXY(4, 10)]
                ),
            )
        )
        state = NodeAssemblyReader(self.context).read(10)

        result = NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=state,
                branch_type_id=531,
                ports=(
                    PortValveConfiguration(
                        port=state.ports[0],
                        enabled=True,
                        distance=0.20,
                        valve_type_id=589,
                        valve_subtype_id=592,
                    ),
                ),
            )
        )

        valve_node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == result.created_valve_node_ids[0]
        )
        self.assertEqual(112, valve_node["PNT_ROTATION"])

    def test_changes_existing_valve_distance_and_both_pipe_geometries(self) -> None:
        initial_state = NodeAssemblyReader(self.context).read(10)
        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=initial_state,
                branch_type_id=531,
                ports=(
                    PortValveConfiguration(
                        port=initial_state.ports[0],
                        enabled=True,
                        distance=0.20,
                        valve_type_id=589,
                        valve_subtype_id=595,
                    ),
                ),
            )
        )
        state = NodeAssemblyReader(self.context).read(10)
        self.assertEqual(1001, state.ports[0].existing_valve_node_id)
        self.assertAlmostEqual(0.20, state.ports[0].length)

        result = NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=state,
                branch_type_id=531,
                ports=(
                    PortValveConfiguration(
                        port=state.ports[0],
                        enabled=True,
                        distance=0.10,
                        valve_type_id=590,
                        valve_subtype_id=596,
                    ),
                ),
            )
        )

        self.assertEqual((), result.created_valve_node_ids)
        self.assertEqual(3, self.node_layer.featureCount())
        self.assertEqual(2, self.edge_layer.featureCount())
        valve_node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 1001
        )
        self.assertAlmostEqual(0.10, valve_node.geometry().asPoint().x())
        pieces = sorted(
            self.edge_layer.getFeatures(),
            key=lambda feature: feature.geometry().length(),
        )
        self.assertAlmostEqual(0.10, pieces[0].geometry().length())
        self.assertAlmostEqual(9.90, pieces[1].geometry().length())
        valve = next(self.valve_layer.getFeatures())
        self.assertEqual(590, valve["TYPE_AQUA_ID"])
        self.assertEqual(596, valve["TYPE_ID"])

    def test_changes_distance_when_central_node_is_at_pipe_end(self) -> None:
        edge = next(self.edge_layer.getFeatures())
        begin_index = self.edge_layer.fields().lookupField("BEGIN_NODE_ID")
        end_index = self.edge_layer.fields().lookupField("END_NODE_ID")
        self.assertTrue(
            self.edge_layer.changeAttributeValue(edge.id(), begin_index, 20)
        )
        self.assertTrue(
            self.edge_layer.changeAttributeValue(edge.id(), end_index, 10)
        )
        self.assertTrue(
            self.edge_layer.changeGeometry(
                edge.id(),
                QgsGeometry.fromPolylineXY(
                    [QgsPointXY(10, 0), QgsPointXY(0, 0)]
                ),
            )
        )
        initial_state = NodeAssemblyReader(self.context).read(10)
        self.assertFalse(initial_state.ports[0].central_at_start)
        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=initial_state,
                branch_type_id=531,
                ports=(
                    PortValveConfiguration(
                        port=initial_state.ports[0],
                        enabled=True,
                        distance=0.20,
                        valve_type_id=589,
                        valve_subtype_id=591,
                    ),
                ),
            )
        )
        state = NodeAssemblyReader(self.context).read(10)
        self.assertFalse(state.ports[0].central_at_start)

        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=state,
                branch_type_id=531,
                ports=(
                    PortValveConfiguration(
                        port=state.ports[0],
                        enabled=True,
                        distance=0.10,
                        valve_type_id=589,
                        valve_subtype_id=591,
                    ),
                ),
            )
        )

        valve_node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 1001
        )
        self.assertAlmostEqual(0.10, valve_node.geometry().asPoint().x())
        central_piece = next(
            feature
            for feature in self.edge_layer.getFeatures()
            if int(feature["END_NODE_ID"]) == 10
        )
        self.assertAlmostEqual(0.10, central_piece.geometry().length())
        self.assertEqual(1001, int(central_piece["BEGIN_NODE_ID"]))

    def test_distance_over_thirty_centimeters_rolls_back_existing_valve(self) -> None:
        initial_state = NodeAssemblyReader(self.context).read(10)
        NodeAssemblyWriter(self.context).write(
            NodeAssemblyPlan(
                state=initial_state,
                branch_type_id=531,
                ports=(
                    PortValveConfiguration(
                        port=initial_state.ports[0],
                        enabled=True,
                        distance=0.20,
                        valve_type_id=589,
                        valve_subtype_id=595,
                    ),
                ),
            )
        )
        state = NodeAssemblyReader(self.context).read(10)

        with self.assertRaises(NodeConfigurationError):
            NodeAssemblyWriter(self.context).write(
                NodeAssemblyPlan(
                    state=state,
                    branch_type_id=531,
                    ports=(
                        PortValveConfiguration(
                            port=state.ports[0],
                            enabled=True,
                            distance=0.31,
                            valve_type_id=590,
                            valve_subtype_id=596,
                        ),
                    ),
                )
            )

        valve_node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == 1001
        )
        self.assertAlmostEqual(0.20, valve_node.geometry().asPoint().x())
        pieces = sorted(
            self.edge_layer.getFeatures(),
            key=lambda feature: feature.geometry().length(),
        )
        self.assertAlmostEqual(0.20, pieces[0].geometry().length())
        self.assertAlmostEqual(9.80, pieces[1].geometry().length())
        valve = next(self.valve_layer.getFeatures())
        self.assertEqual(589, valve["TYPE_AQUA_ID"])
        self.assertEqual(595, valve["TYPE_ID"])

    def test_failure_rolls_back_fitting_and_all_topology_changes(self) -> None:
        state = NodeAssemblyReader(self.context).read(10)
        plan = NodeAssemblyPlan(
            state=state,
            branch_type_id=531,
            ports=(
                PortValveConfiguration(
                    port=state.ports[0],
                    enabled=True,
                    distance=state.ports[0].length,
                    valve_type_id=589,
                    valve_subtype_id=591,
                ),
            ),
        )

        with self.assertRaises(NodeConfigurationError):
            NodeAssemblyWriter(self.context).write(plan)

        self.assertEqual(0, self.branch_layer.featureCount())
        self.assertEqual(0, self.valve_layer.featureCount())
        self.assertEqual(2, self.node_layer.featureCount())
        self.assertEqual(1, self.edge_layer.featureCount())
        edge = next(self.edge_layer.getFeatures())
        self.assertAlmostEqual(10.0, edge.geometry().length())
        self.assertEqual(10, int(edge["BEGIN_NODE_ID"]))
        self.assertEqual(20, int(edge["END_NODE_ID"]))

    def _add_node(self, node_id: int, x: float, y: float) -> None:
        node = QgsFeature(self.node_layer.fields())
        node.setAttributes([node_id, 312, 308, None])
        node.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        self.assertTrue(self.node_layer.dataProvider().addFeature(node))

    def _add_edge(
        self,
        edge_id: int,
        begin_node_id: int,
        end_node_id: int,
        points: list[QgsPointXY],
    ) -> None:
        edge = QgsFeature(self.edge_layer.fields())
        edge.setAttributes(
            [
                edge_id,
                312,
                311,
                begin_node_id,
                end_node_id,
                QgsGeometry.fromPolylineXY(points).length(),
                7,
                104,
                538,
                358,
                1.0,
            ]
        )
        edge.setGeometry(QgsGeometry.fromPolylineXY(points))
        self.assertTrue(self.edge_layer.addFeature(edge))

    @staticmethod
    def _disabled_ports(state):
        return tuple(
            PortValveConfiguration(
                port=port,
                enabled=False,
                distance=0.30,
                valve_type_id=None,
                valve_subtype_id=None,
            )
            for port in state.ports
        )

    def _editable_layers(self):
        return (
            self.edge_layer,
            self.node_layer,
            self.branch_layer,
            self.valve_layer,
            self.manhole_layer,
            self.facility_layer,
        )

    @staticmethod
    def _set_default(layer, field_name: str, expression: str) -> None:
        layer.setDefaultValueDefinition(
            layer.fields().lookupField(field_name), QgsDefaultValue(expression)
        )

    @staticmethod
    def _set_value_map(
        layer,
        field_name: str,
        label: str,
        value: int,
    ) -> None:
        layer.setEditorWidgetSetup(
            layer.fields().lookupField(field_name),
            QgsEditorWidgetSetup("ValueMap", {"map": [{label: value}]}),
        )


if __name__ == "__main__":
    unittest.main()
