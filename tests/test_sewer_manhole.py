"""Tests for the sewer manhole clock reader, UI and writer."""

from __future__ import annotations

from dataclasses import replace
import unittest

from qgis.PyQt.QtCore import QDate, Qt
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QApplication, QTableWidget
from qgis.core import (
    QgsDefaultValue,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsVariantUtils,
)

from EVEL_network_tools.layers import (
    LookupOption,
    SewerManholeContext,
    SewerManholeOptions,
    SewerPumpingStationContext,
    SewerPumpingStationOptions,
)
from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.topology import (
    DETAIL_KIND_CONNECTION,
    PUMP_NODE_NETTYPE_ID,
    SewerManholePlan,
    SewerManholeReader,
    SewerManholeWriter,
    SewerPumpingStationReader,
    SewerPumpingStationWriter,
    select_sewer_reference_outlet,
    sewer_clock_angle,
)
from EVEL_network_tools.ui import (
    SewerManholeClockDialog,
    SewerPumpingStationDialog,
)


start_qgis()


class SewerManholeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.node_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=IDENTIFICATION:string&field=NETWORK_ID:integer&"
            "field=NETTYPE_ID:integer&field=Z_COORD1:double&"
            "field=Z_COORD2:double&field=Z_COORD3:double",
            "Kaevud",
            "memory",
        )
        self.manhole_layer = QgsVectorLayer(
            "None?field=ID:integer64&field=NODE_ID:integer64&"
            "field=TYPE_ID:integer&field=MATERIAL_ID:integer&"
            "field=DIAMETER_TYPE_ID:integer&field=DIAMETER_ID:integer&"
            "field=FIRMNESS_CLASS_ID:integer&field=LID_TYPE_ID:integer&"
            "field=LID_MATERIAL_ID:integer&field=LID_SHAPE_ID:integer&"
            "field=LID_DIAMETER_ID:integer&field=LID_CAPACITY_ID:integer&"
            "field=ACCESS_DUCT_DIAM:integer",
            "Kaevud detailandmed",
            "memory",
        )
        self.branch_layer = QgsVectorLayer(
            "None?field=ID:integer64&field=NODE_ID:integer64&"
            "field=TYPE_AQUA_ID:integer&field=TYPE_ID:integer",
            "Liitmikud detailandmed",
            "memory",
        )
        self.pumping_station_layer = QgsVectorLayer(
            "None?field=ID:integer64&field=NODE_ID:integer64&"
            "field=TYPE_AQUA_ID:integer&field=MATERIAL_ID:integer&"
            "field=ROLE_ID:integer&field=NAME:string&"
            "field=PRODUCTIVITY:double&field=PRESSURE_INCREASE:double&"
            "field=POWER_CONSUMPTION:double&field=EL_MAX_CURRENT:double&"
            "field=CONTROL_ID:integer&field=PARCEL_NR:string&"
            "field=ADDRESS_ID:integer64",
            "Pumplad detailandmed",
            "memory",
        )
        self.pump_layer = QgsVectorLayer(
            "None?field=ID:integer64&field=PSTATION_ID:integer64&"
            "field=TYPE_ID:integer&field=INSTALL_METHOD_ID:integer&"
            "field=INSTALL_DATE:datetime&field=POWER_W:double&"
            "field=MANUFACTURER:string&field=MARK:string&"
            "field=PRODUCTIVITY:double&field=PUMP_HEAD:double&"
            "field=RUNNING_TIME:double&field=IN_DIAMETER:double&"
            "field=OUT_DIAMETER:double&field=ENGINE_CURRENT:double&"
            "field=ENGINE_VOLTAGE:double&field=REMARKS:string",
            "Kanalisatsioonipumbad (tehniline)",
            "memory",
        )
        self.constant_layer = QgsVectorLayer(
            "None?field=ID:integer&field=GROUPNAME:string&field=TXT:string",
            "Konstandid",
            "memory",
        )
        self.duct_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=IDENTIFICATION:string&field=NETWORK_ID:integer&"
            "field=NETTYPE_ID:integer&field=MATERIAL_ID:integer&"
            "field=DIAMETER_ID:integer&field=BEGIN_NODE_ID:integer64&"
            "field=END_NODE_ID:integer64&field=BEGIN_Z_COORD:double&"
            "field=END_Z_COORD:double&field=FLOWDIRECTION:double&"
            "field=LENGTH_2D:double",
            "Isevoolne kanal",
            "memory",
        )
        self._set_default(self.node_layer, "MSLINK", "1001")
        self._set_default(self.manhole_layer, "ID", "5001")
        self._set_default(self.manhole_layer, "TYPE_ID", "456")
        self._set_default(self.branch_layer, "ID", "6001")
        self._set_default(self.branch_layer, "TYPE_AQUA_ID", "392")
        self._set_default(self.branch_layer, "TYPE_ID", "396")
        self._set_default(self.pumping_station_layer, "ID", "7001")
        self._set_default(
            self.pumping_station_layer,
            "TYPE_AQUA_ID",
            "479",
        )
        self._set_default(self.pumping_station_layer, "MATERIAL_ID", "363")
        self._set_default(self.pumping_station_layer, "ROLE_ID", "474")
        self._set_default(self.pumping_station_layer, "CONTROL_ID", "470")
        self._set_default(self.pump_layer, "ID", "8001")
        self._set_default(self.duct_layer, "MSLINK", "2002")

        edge = QgsFeature(self.duct_layer.fields())
        edge.setAttribute("MSLINK", 501)
        edge.setAttribute("IDENTIFICATION", "KV-1")
        edge.setAttribute("NETWORK_ID", 315)
        edge.setAttribute("NETTYPE_ID", 309)
        edge.setAttribute("MATERIAL_ID", 10)
        edge.setAttribute("DIAMETER_ID", 20)
        edge.setAttribute("BEGIN_Z_COORD", 10.0)
        edge.setAttribute("END_Z_COORD", 9.0)
        edge.setAttribute("FLOWDIRECTION", 1.0)
        edge.setAttribute("LENGTH_2D", 10.0)
        edge.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            )
        )
        self.assertTrue(self.duct_layer.dataProvider().addFeature(edge))
        self.original_edge_id = int(edge.id())

        one = (LookupOption(1, "Valik"),)
        self.context = SewerManholeContext(
            node_layer=self.node_layer,
            node_source_layers=(self.node_layer,),
            manhole_layer=self.manhole_layer,
            branch_layer=self.branch_layer,
            constant_layer=self.constant_layer,
            duct_layers=(self.duct_layer,),
            options=SewerManholeOptions(
                type_options=(LookupOption(456, "Kontrollkaev"),),
                material_options=one,
                diameter_type_options=one,
                diameter_options=one,
                firmness_options=one,
                lid_type_options=one,
                lid_material_options=one,
                lid_shape_options=one,
                lid_diameter_options=one,
                lid_capacity_options=one,
                default_type_id=456,
                branch_type_options=(
                    LookupOption(392, "Määramata"),
                    LookupOption(395, "Ühenduskoht"),
                ),
                branch_subtype_options=(
                    LookupOption(396, "Määramata"),
                ),
                default_branch_type_id=392,
                default_branch_subtype_id=396,
                connection_branch_type_id=395,
            ),
            pumping_station_layer=self.pumping_station_layer,
            visible_pumping_station_layer=self.node_layer,
        )
        self.pumping_context = SewerPumpingStationContext(
            topology_context=self.context,
            detail_layer=self.pumping_station_layer,
            pump_layer=self.pump_layer,
            visible_layer=self.node_layer,
            options=SewerPumpingStationOptions(
                type_options=(LookupOption(479, "Reoveepumpla"),),
                material_options=(LookupOption(363, "Plast"),),
                role_options=(LookupOption(474, "Võrgupumpla"),),
                control_options=(LookupOption(470, "Automaatne"),),
                pump_type_options=(
                    LookupOption(482, "Määramata"),
                    LookupOption(487, "Vortex"),
                ),
                pump_install_method_options=(
                    LookupOption(381, "Määramata"),
                    LookupOption(382, "Kuiv"),
                    LookupOption(383, "Märg"),
                ),
                pump_diameter_options=(
                    100.0,
                    110.0,
                    125.0,
                    150.0,
                    160.0,
                    200.0,
                ),
                default_type_id=479,
                default_material_id=363,
                default_role_id=474,
                default_control_id=470,
            ),
        )

    def tearDown(self) -> None:
        for layer in (
            self.duct_layer,
            self.node_layer,
            self.manhole_layer,
            self.branch_layer,
            self.pumping_station_layer,
            self.pump_layer,
        ):
            if layer.isEditable():
                layer.rollBack()

    def test_clock_resolves_split_and_writer_creates_atomic_manhole(self) -> None:
        state = SewerManholeReader(self.context).resolve(
            QgsPointXY(5, 0),
            0.01,
        )

        self.assertIsNone(state.node_id)
        self.assertEqual(2, len(state.ports))
        self.assertEqual({90.0, 270.0}, {port.bearing for port in state.ports})
        self.assertTrue(
            all(abs(port.height - 9.5) < 1e-9 for port in state.ports)
        )

        dialog = SewerManholeClockDialog(
            state,
            self.context.options,
        )
        self.assertTrue(dialog.property("evelLightTheme"))
        self.assertIn("#f6f7f8", dialog.styleSheet())
        self.assertEqual(2, dialog.table.rowCount())
        reference = dialog.clock.reference_outlet()
        self.assertIsNotNone(reference)
        self.assertTrue(reference.is_outgoing)
        self.assertEqual(0.0, sewer_clock_angle(reference, reference))
        self.assertEqual("Välja · referents", dialog.table.item(0, 4).text())
        self.assertEqual("0.0°", dialog.table.item(0, 5).text())
        self.assertEqual("Sisse", dialog.table.item(1, 4).text())
        self.assertEqual("180.0°", dialog.table.item(1, 5).text())
        dialog.identification_edit.setText("KK-1")
        dialog.bottom_height_edit.setText("8.500")
        dialog.height_edits[state.ports[0].key].setText("9.450")
        dialog.height_edits[state.ports[1].key].setText("9.400")
        plan = dialog.plan()
        dialog.clock.grab()
        dialog.deleteLater()

        for layer in (
            self.node_layer,
            self.manhole_layer,
            self.branch_layer,
            self.duct_layer,
        ):
            self.assertTrue(layer.startEditing())
        result = SewerManholeWriter(self.context).write(plan)

        self.assertTrue(result.created_node)
        self.assertTrue(result.split_edge)
        self.assertEqual(1001, result.node_id)
        self.assertEqual(1, self.node_layer.featureCount())
        self.assertEqual(1, self.manhole_layer.featureCount())
        self.assertEqual(2, self.duct_layer.featureCount())

        node = next(self.node_layer.getFeatures())
        self.assertEqual("KK-1", node["IDENTIFICATION"])
        self.assertEqual(8.5, node["Z_COORD2"])
        detail = next(self.manhole_layer.getFeatures())
        self.assertEqual(1001, detail["NODE_ID"])
        self.assertEqual(456, detail["TYPE_ID"])

        first = self.duct_layer.getFeature(self.original_edge_id)
        second = next(
            feature
            for feature in self.duct_layer.getFeatures()
            if feature.id() != self.original_edge_id
        )
        self.assertEqual(1001, first["END_NODE_ID"])
        self.assertEqual(1001, second["BEGIN_NODE_ID"])
        self.assertAlmostEqual(5.0, first["LENGTH_2D"])
        self.assertAlmostEqual(5.0, second["LENGTH_2D"])
        self.assertEqual(
            {9.4, 9.45},
            {first["END_Z_COORD"], second["BEGIN_Z_COORD"]},
        )

        self.duct_layer.undoStack().undo()
        self.manhole_layer.undoStack().undo()
        self.node_layer.undoStack().undo()
        self.assertEqual(1, self.duct_layer.featureCount())
        self.assertEqual(0, self.manhole_layer.featureCount())
        self.assertEqual(0, self.node_layer.featureCount())

    def test_coincident_pipe_ends_form_one_connection_node(self) -> None:
        second = QgsFeature(self.duct_layer.fields())
        second.setAttribute("MSLINK", 502)
        second.setAttribute("IDENTIFICATION", "KV-2")
        second.setAttribute("NETWORK_ID", 315)
        second.setAttribute("NETTYPE_ID", 309)
        second.setAttribute("BEGIN_Z_COORD", 9.0)
        second.setAttribute("END_Z_COORD", 8.0)
        second.setAttribute("FLOWDIRECTION", 1.0)
        second.setAttribute("LENGTH_2D", 10.0)
        second.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(10, 0), QgsPointXY(10, 10)]
            )
        )
        self.assertTrue(self.duct_layer.dataProvider().addFeature(second))
        second_id = int(second.id())

        state = SewerManholeReader(self.context).resolve(
            QgsPointXY(10, 0),
            0.01,
        )

        self.assertIsNone(state.node_id)
        self.assertIsNone(state.split_layer)
        self.assertEqual(2, len(state.ports))
        self.assertEqual(2, len(state.endpoint_connections))
        plan = SewerManholePlan(
            state=state,
            configuration=replace(
                state.configuration,
                detail_kind=DETAIL_KIND_CONNECTION,
                identification="P-1",
                branch_type_id=395,
                branch_subtype_id=396,
            ),
            port_heights=tuple(
                (port.key, 9.0) for port in state.ports
            ),
        )
        for layer in (
            self.node_layer,
            self.manhole_layer,
            self.branch_layer,
            self.duct_layer,
        ):
            self.assertTrue(layer.startEditing())

        result = SewerManholeWriter(self.context).write(plan)

        self.assertTrue(result.created_node)
        self.assertFalse(result.split_edge)
        self.assertEqual(0, self.manhole_layer.featureCount())
        self.assertEqual(1, self.branch_layer.featureCount())
        branch = next(self.branch_layer.getFeatures())
        self.assertEqual(result.node_id, branch["NODE_ID"])
        self.assertEqual(395, branch["TYPE_AQUA_ID"])
        first = self.duct_layer.getFeature(self.original_edge_id)
        updated_second = self.duct_layer.getFeature(second_id)
        self.assertEqual(result.node_id, first["END_NODE_ID"])
        self.assertEqual(result.node_id, updated_second["BEGIN_NODE_ID"])

    def test_repairs_missing_id_on_pending_manhole_detail(self) -> None:
        node = QgsFeature(self.node_layer.fields())
        node.setAttribute("MSLINK", 77)
        node.setAttribute("NETWORK_ID", 315)
        node.setAttribute("NETTYPE_ID", 309)
        node.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(10, 0)))
        self.assertTrue(self.node_layer.dataProvider().addFeature(node))
        end_node_index = self.duct_layer.fields().lookupField("END_NODE_ID")
        self.assertTrue(
            self.duct_layer.dataProvider().changeAttributeValues(
                {self.original_edge_id: {end_node_index: 77}}
            )
        )

        for layer in (
            self.node_layer,
            self.manhole_layer,
            self.branch_layer,
            self.duct_layer,
        ):
            self.assertTrue(layer.startEditing())
        pending = QgsFeature(self.manhole_layer.fields())
        pending.setAttribute("NODE_ID", 77)
        pending.setAttribute("TYPE_ID", 456)
        self.assertTrue(self.manhole_layer.addFeature(pending))
        self.assertTrue(QgsVariantUtils.isNull(pending["ID"]))

        state = SewerManholeReader(self.context).resolve(
            QgsPointXY(10, 0),
            0.01,
        )
        self.assertIsNotNone(state.manhole_detail_feature_id)
        plan = SewerManholePlan(
            state=state,
            configuration=state.configuration,
            port_heights=tuple(
                (port.key, port.height) for port in state.ports
            ),
        )

        result = SewerManholeWriter(self.context).write(plan)

        self.assertEqual(77, result.node_id)
        self.assertFalse(result.created_node)
        details = list(self.manhole_layer.getFeatures())
        self.assertEqual(1, len(details))
        self.assertEqual(5001, details[0]["ID"])
        self.assertEqual(77, details[0]["NODE_ID"])
        self.assertEqual(456, details[0]["TYPE_ID"])

    def test_existing_polyline_vertex_becomes_split_connection(self) -> None:
        feature = self.duct_layer.getFeature(self.original_edge_id)
        feature.setGeometry(
            QgsGeometry.fromPolylineXY(
                [
                    QgsPointXY(0, 0),
                    QgsPointXY(5, 5),
                    QgsPointXY(10, 5),
                ]
            )
        )
        self.assertTrue(
            self.duct_layer.dataProvider().changeGeometryValues(
                {self.original_edge_id: feature.geometry()}
            )
        )

        state = SewerManholeReader(self.context).resolve(
            QgsPointXY(5, 5),
            0.01,
        )

        self.assertIs(self.duct_layer, state.split_layer)
        self.assertEqual(2, len(state.ports))
        self.assertAlmostEqual(5.0, state.point.x())
        self.assertAlmostEqual(5.0, state.point.y())

    def test_branch_endpoint_and_main_pipe_form_one_three_way_node(self) -> None:
        branch = QgsFeature(self.duct_layer.fields())
        branch.setAttribute("MSLINK", 502)
        branch.setAttribute("IDENTIFICATION", "KV-HARU")
        branch.setAttribute("NETWORK_ID", 315)
        branch.setAttribute("NETTYPE_ID", 309)
        branch.setAttribute("BEGIN_Z_COORD", 9.5)
        branch.setAttribute("END_Z_COORD", 9.0)
        branch.setAttribute("FLOWDIRECTION", 1.0)
        branch.setAttribute("LENGTH_2D", 5.0)
        branch.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(5, 0), QgsPointXY(5, 5)]
            )
        )
        self.assertTrue(self.duct_layer.dataProvider().addFeature(branch))
        branch_id = int(branch.id())

        state = SewerManholeReader(self.context).resolve(
            QgsPointXY(5, 0),
            0.01,
        )

        self.assertIs(self.duct_layer, state.split_layer)
        self.assertEqual(3, len(state.ports))
        self.assertEqual(1, len(state.endpoint_connections))
        plan = SewerManholePlan(
            state=state,
            configuration=replace(
                state.configuration,
                detail_kind=DETAIL_KIND_CONNECTION,
                identification="Y-1",
                branch_type_id=395,
                branch_subtype_id=396,
            ),
            port_heights=tuple(
                (port.key, 9.5) for port in state.ports
            ),
        )
        for layer in (
            self.node_layer,
            self.manhole_layer,
            self.branch_layer,
            self.duct_layer,
        ):
            self.assertTrue(layer.startEditing())

        result = SewerManholeWriter(self.context).write(plan)

        self.assertTrue(result.created_node)
        self.assertTrue(result.split_edge)
        self.assertEqual(3, self.duct_layer.featureCount())
        self.assertEqual(
            result.node_id,
            self.duct_layer.getFeature(branch_id)["BEGIN_NODE_ID"],
        )
        self.assertEqual(
            result.node_id,
            self.duct_layer.getFeature(self.original_edge_id)["END_NODE_ID"],
        )
        split_part = next(
            feature
            for feature in self.duct_layer.getFeatures()
            if feature.id() not in {self.original_edge_id, branch_id}
        )
        self.assertEqual(result.node_id, split_part["BEGIN_NODE_ID"])
        detail = next(self.branch_layer.getFeatures())
        self.assertEqual(result.node_id, detail["NODE_ID"])
        self.assertEqual(395, detail["TYPE_AQUA_ID"])

    def test_pumping_station_has_separate_dialog_and_detail(self) -> None:
        state = SewerPumpingStationReader(self.pumping_context).resolve(
            QgsPointXY(5, 0),
            0.01,
        )
        self.assertEqual("Reovesi", state.network_label)

        dialog = SewerPumpingStationDialog(
            state,
            self.pumping_context.options,
        )
        self.assertTrue(dialog.property("evelLightTheme"))
        self.assertIn("#f6f7f8", dialog.styleSheet())
        self.assertNotIn("#0a1220", dialog.styleSheet())
        self.assertEqual(4, dialog.tabs.count())
        self.assertIn("Pumbad", dialog.tabs.tabText(0))
        self.assertIn("\n", dialog.tabs.tabText(0))
        self.assertTrue(dialog.next_button.isEnabled())
        self.assertIn("Juhtimine", dialog.next_button.text())
        dialog.next_button.click()
        self.assertEqual(1, dialog.tabs.currentIndex())
        dialog.preview.sectionSelected.emit(2)
        self.assertEqual(2, dialog.tabs.currentIndex())
        dialog.next_button.click()
        self.assertEqual(2, dialog.tabs.currentIndex())
        self.assertFalse(dialog.required_errors["name"].isHidden())
        dialog.element_height_spin.setValue(20.0)
        self.assertIn("Rajatis ja asukoht", dialog.tabs.tabText(2))
        dialog.element_height_spin.set_null()
        self.assertFalse(dialog.preview_frame.isHidden())
        dialog.preview_toggle_button.click()
        self.assertTrue(dialog.preview_frame.isHidden())
        self.assertFalse(dialog.preview_show_button.isHidden())
        dialog.preview_show_button.click()
        self.assertFalse(dialog.preview_frame.isHidden())
        self.assertTrue(dialog.preview_show_button.isHidden())
        dialog.preview.sectionSelected.emit(1)
        self.assertEqual(1, dialog.tabs.currentIndex())
        dialog.tabs.setCurrentIndex(0)
        self.assertEqual(0, dialog.preview.selected_section)
        dialog.pump_add_button.click()
        self.assertEqual(1, dialog.pump_list.count())
        self.assertEqual(1, dialog.preview.pump_count)
        self.assertIn("Kontrolli", dialog.tabs.tabText(0))
        dialog.next_button.click()
        self.assertEqual(0, dialog.tabs.currentIndex())
        self.assertFalse(dialog.pump_type_error.isHidden())
        dialog.pump_type_combo.setCurrentIndex(
            dialog.pump_type_combo.findData(487)
        )
        dialog.pump_install_combo.setCurrentIndex(
            dialog.pump_install_combo.findData(383)
        )
        dialog.pump_manufacturer_edit.setText("Grundfos")
        dialog.pump_mark_edit.setText("SE1")
        dialog.show()
        dialog.pump_productivity_edit.setText("99")
        dialog.pump_productivity_edit.setFocus(Qt.OtherFocusReason)
        QApplication.processEvents()
        QTest.keyClicks(dialog.pump_productivity_edit, "8,5")
        self.assertEqual("8,5", dialog.pump_productivity_edit.text())
        dialog.pump_head_edit.setText("12")
        dialog.pump_power_edit.setText("1500")
        dialog.pump_current_edit.setText("4,2")
        dialog.pump_voltage_edit.setText("400")
        self.assertFalse(dialog.pump_in_diameter_combo.isEditable())
        self.assertGreater(dialog.pump_in_diameter_combo.count(), 1)
        dialog.pump_in_diameter_combo.setCurrentIndex(
            dialog.pump_in_diameter_combo.findData(100.0)
        )
        dialog.pump_out_diameter_combo.setCurrentIndex(
            dialog.pump_out_diameter_combo.findData(110.0)
        )
        dialog.pump_date_known.setChecked(True)
        dialog.pump_date_edit.setDate(QDate(2024, 5, 17))
        self.assertIn("1 pump", dialog.tabs.tabText(0))
        dialog.name_edit.setText("RP-1")
        self.assertIn("Valmis", dialog.tabs.tabText(2))
        self.assertTrue(dialog.next_button.isEnabled())
        self.assertEqual("RP-1", dialog.preview.facility_name)
        dialog.productivity_spin.setValue(12.5)
        self.assertEqual(12.5, dialog.preview.productivity)
        self.assertEqual(2, dialog.preview.port_count)
        dialog.tabs.setCurrentIndex(3)
        self.assertIn("2 toruühendust", dialog.preview._summary_lines()[0])
        pipe_table = dialog.tabs.widget(3).findChild(QTableWidget)
        self.assertIsNotNone(pipe_table)
        self.assertEqual(
            Qt.ScrollBarAlwaysOff,
            pipe_table.horizontalScrollBarPolicy(),
        )
        self.assertIn(
            "sõlmepoolne põhjakõrgus",
            next(iter(dialog.port_height_spins.values()))
            .accessibleName()
            .casefold(),
        )
        plan = dialog.plan()
        dialog.deleteLater()

        for layer in (
            self.node_layer,
            self.pumping_station_layer,
            self.pump_layer,
            self.duct_layer,
        ):
            self.assertTrue(layer.startEditing())
        result = SewerPumpingStationWriter(self.pumping_context).write(plan)

        self.assertTrue(result.created_node)
        detail = next(self.pumping_station_layer.getFeatures())
        self.assertEqual(result.node_id, int(detail["NODE_ID"]))
        self.assertEqual("RP-1", detail["NAME"])
        self.assertAlmostEqual(12.5, float(detail["PRODUCTIVITY"]))
        node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if int(feature["MSLINK"]) == result.node_id
        )
        self.assertEqual(PUMP_NODE_NETTYPE_ID, int(node["NETTYPE_ID"]))
        self.assertEqual(0, self.manhole_layer.featureCount())
        self.assertEqual(0, self.branch_layer.featureCount())
        pump = next(self.pump_layer.getFeatures())
        self.assertEqual(int(detail["ID"]), int(pump["PSTATION_ID"]))
        self.assertEqual(487, int(pump["TYPE_ID"]))
        self.assertEqual(383, int(pump["INSTALL_METHOD_ID"]))
        self.assertEqual("Grundfos", pump["MANUFACTURER"])
        self.assertEqual("SE1", pump["MARK"])
        self.assertAlmostEqual(8.5, float(pump["PRODUCTIVITY"]))
        self.assertAlmostEqual(12.0, float(pump["PUMP_HEAD"]))
        self.assertAlmostEqual(1500.0, float(pump["POWER_W"]))
        self.assertAlmostEqual(4.2, float(pump["ENGINE_CURRENT"]))
        self.assertAlmostEqual(400.0, float(pump["ENGINE_VOLTAGE"]))
        self.assertAlmostEqual(100.0, float(pump["IN_DIAMETER"]))
        self.assertAlmostEqual(110.0, float(pump["OUT_DIAMETER"]))

        existing = SewerPumpingStationReader(self.pumping_context).resolve(
            QgsPointXY(5, 0),
            0.01,
        )
        self.assertIsNotNone(
            existing.topology.pumping_station_detail_feature_id
        )
        self.assertEqual("RP-1", existing.configuration.name)
        self.assertEqual(1, len(existing.pumps))
        self.assertEqual("SE1", existing.pumps[0].mark)
        self.assertEqual("2024-05-17", existing.pumps[0].install_date.isoformat())
        update_dialog = SewerPumpingStationDialog(
            existing,
            self.pumping_context.options,
        )
        update_dialog.name_edit.setText("RP-2")
        update_dialog.pump_mark_edit.setText("SE1.1")
        SewerPumpingStationWriter(self.pumping_context).write(
            update_dialog.plan()
        )
        update_dialog.deleteLater()
        self.assertEqual(1, self.pumping_station_layer.featureCount())
        self.assertEqual(
            "RP-2",
            next(self.pumping_station_layer.getFeatures())["NAME"],
        )
        self.assertEqual("SE1.1", next(self.pump_layer.getFeatures())["MARK"])
        removal_state = SewerPumpingStationReader(
            self.pumping_context
        ).resolve(QgsPointXY(5, 0), 0.01)
        removal_dialog = SewerPumpingStationDialog(
            removal_state,
            self.pumping_context.options,
        )
        removal_dialog.pump_duplicate_button.click()
        self.assertEqual(2, removal_dialog.pump_list.count())
        removal_dialog.pump_remove_button.click()
        self.assertEqual(1, removal_dialog.pump_list.count())
        removal_dialog.pump_remove_button.click()
        SewerPumpingStationWriter(self.pumping_context).write(
            removal_dialog.plan()
        )
        removal_dialog.deleteLater()
        self.assertEqual(0, self.pump_layer.featureCount())

    def test_pumping_station_requires_explicit_classification(self) -> None:
        state = SewerPumpingStationReader(self.pumping_context).resolve(
            QgsPointXY(5, 0),
            0.01,
        )
        state = replace(
            state,
            configuration=replace(
                state.configuration,
                address_id=12345,
            ),
        )
        options = replace(
            self.pumping_context.options,
            type_options=(
                LookupOption(479, "Määramata"),
                LookupOption(480, "Reoveepumpla"),
            ),
        )
        dialog = SewerPumpingStationDialog(state, options)
        dialog.name_edit.setText("RP-1")
        dialog.tabs.setCurrentIndex(2)

        self.assertIsNone(dialog.type_combo.currentData())
        self.assertTrue(dialog.next_button.isEnabled())
        self.assertIn("3/4", dialog.tabs.tabText(2))
        dialog.type_combo.setCurrentIndex(1)
        self.assertEqual(479, dialog.type_combo.currentData())
        self.assertIn("3/4", dialog.tabs.tabText(2))
        dialog.next_button.click()
        self.assertEqual(2, dialog.tabs.currentIndex())
        self.assertFalse(dialog.required_errors["type"].isHidden())
        dialog.type_combo.setCurrentIndex(2)
        self.assertEqual(480, dialog.type_combo.currentData())
        self.assertTrue(dialog.next_button.isEnabled())
        self.assertIn("Valmis", dialog.tabs.tabText(2))
        self.assertFalse(hasattr(dialog, "address_edit"))
        self.assertEqual(12345, dialog.plan().configuration.address_id)
        dialog.deleteLater()

    def test_pumping_station_nullable_numbers_and_parcel_feedback(self) -> None:
        state = SewerPumpingStationReader(self.pumping_context).resolve(
            QgsPointXY(5, 0),
            0.01,
        )
        dialog = SewerPumpingStationDialog(
            state,
            self.pumping_context.options,
        )

        dialog.element_height_spin.setValue(-0.5)
        self.assertEqual(
            -0.5,
            dialog.plan().configuration.element_height,
        )
        dialog.element_height_spin.set_null()
        self.assertIsNone(dialog.plan().configuration.element_height)
        dialog.productivity_spin.set_null()
        dialog.tabs.setCurrentIndex(2)
        dialog.show()
        dialog.productivity_spin.setFocus(Qt.OtherFocusReason)
        QApplication.processEvents()
        QTest.keyClicks(dialog.productivity_spin, "12")
        dialog.productivity_spin.interpretText()
        self.assertEqual(
            12.0,
            dialog.plan().configuration.productivity,
        )
        dialog.productivity_spin.setValue(300.0)
        dialog.name_edit.setFocus(Qt.OtherFocusReason)
        QApplication.processEvents()
        dialog.productivity_spin.setFocus(Qt.OtherFocusReason)
        QApplication.processEvents()
        QTest.keyClicks(dialog.productivity_spin, "45")
        dialog.productivity_spin.interpretText()
        self.assertEqual(
            45.0,
            dialog.plan().configuration.productivity,
        )
        dialog.productivity_spin.set_null()
        dialog.productivity_spin.stepUp()
        self.assertEqual(
            0.0,
            dialog.plan().configuration.productivity,
        )

        dialog.name_edit.setText("RP-1")
        dialog.parcel_edit.setText("vale tunnus")
        self.assertFalse(dialog.parcel_warning.isHidden())
        self.assertIn("Kontrolli asukohta", dialog.tabs.tabText(2))
        dialog.parcel_edit.setText("78401:101:1234")
        self.assertTrue(dialog.parcel_warning.isHidden())
        self.assertIn("Valmis", dialog.tabs.tabText(2))

        dialog.set_busy(True, "Kirjutan pumpla andmeid…", 60)
        self.assertTrue(dialog._busy)
        self.assertFalse(dialog.busy_frame.isHidden())
        self.assertFalse(dialog.next_button.isEnabled())
        dialog.set_busy(False, "Kirjutamine ebaõnnestus.")
        self.assertFalse(dialog._busy)
        self.assertFalse(dialog.busy_frame.isHidden())
        self.assertTrue(dialog.busy_progress.isHidden())
        self.assertTrue(dialog.next_button.isEnabled())
        dialog.deleteLater()

    def test_deepest_outgoing_pipe_is_clock_reference(self) -> None:
        state = SewerManholeReader(self.context).resolve(
            QgsPointXY(5, 0),
            0.01,
        )
        first = replace(
            state.ports[0],
            key="out-high",
            central_at_start=True,
            flow_direction=1.0,
            height=9.25,
            bearing=30.0,
        )
        second = replace(
            state.ports[1],
            key="out-low",
            central_at_start=True,
            flow_direction=1.0,
            height=8.75,
            bearing=210.0,
        )

        reference = select_sewer_reference_outlet((first, second))

        self.assertEqual("out-low", reference.key)
        self.assertEqual(0.0, sewer_clock_angle(second, reference))
        self.assertEqual(180.0, sewer_clock_angle(first, reference))
        changed_reference = select_sewer_reference_outlet(
            (first, second),
            {"out-high": 8.5, "out-low": 8.75},
        )
        self.assertEqual("out-high", changed_reference.key)

    @staticmethod
    def _set_default(
        layer: QgsVectorLayer,
        field_name: str,
        expression: str,
    ) -> None:
        layer.setDefaultValueDefinition(
            layer.fields().lookupField(field_name),
            QgsDefaultValue(expression),
        )


if __name__ == "__main__":
    unittest.main()
