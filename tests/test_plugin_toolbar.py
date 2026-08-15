"""Smoke test for toolbar creation and plugin lifecycle."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from qgis.PyQt.QtCore import QObject, QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QDialog, QMainWindow, QToolBar, QToolButton
from qgis.core import (
    QgsDefaultValue,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from EVEL_network_tools.plugin import EVELNetworkToolsPlugin
from EVEL_network_tools.layers import (
    DuctLayerOption,
    DuctWorkflow,
    ProjectInspection,
)
from EVEL_network_tools.tests.qgis_test_utils import start_qgis


start_qgis()


class _MessageBar:
    def __init__(self) -> None:
        self.messages = []

    def pushMessage(self, *args, **kwargs) -> None:  # noqa: N802
        self.messages.append((args, kwargs))


class _FakeIface(QObject):
    currentLayerChanged = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self._window = QMainWindow()
        self._message_bar = _MessageBar()
        self._active_layer = None

    def addToolBar(self, title: str) -> QToolBar:  # noqa: N802
        toolbar = QToolBar(title, self._window)
        self._window.addToolBar(toolbar)
        return toolbar

    def activeLayer(self):  # noqa: N802
        return self._active_layer

    def setActiveLayer(self, layer):  # noqa: N802
        self._active_layer = layer
        self.currentLayerChanged.emit(layer)
        return True

    def mainWindow(self) -> QMainWindow:  # noqa: N802
        return self._window

    def messageBar(self):  # noqa: N802
        return self._message_bar


class PluginToolbarTest(unittest.TestCase):
    def setUp(self) -> None:
        QgsProject.instance().clear()

    def tearDown(self) -> None:
        QgsProject.instance().clear()

    def test_init_and_unload_create_safe_disabled_tools(self) -> None:
        iface = _FakeIface()
        plugin = EVELNetworkToolsPlugin(iface)

        plugin.initGui()

        self.assertIsNotNone(plugin.toolbar)
        self.assertEqual("EVELNetworkToolsToolbar", plugin.toolbar.objectName())
        self.assertTrue(plugin.toolbar.property("evelLightTheme"))
        self.assertEqual(QSize(20, 20), plugin.toolbar.iconSize())
        self.assertIn("#f6f7f8", plugin.toolbar.styleSheet())
        self.assertIn("padding: 2px 4px", plugin.toolbar.styleSheet())
        self.assertIs(plugin.add_duct_menu, plugin.add_duct_action.menu())
        self.assertTrue(plugin.add_duct_menu.property("evelLightTheme"))
        self.assertIn("#ffffff", plugin.add_duct_menu.styleSheet())
        add_button = plugin.toolbar.widgetForAction(plugin.add_duct_action)
        self.assertIsInstance(add_button, QToolButton)
        self.assertEqual(QToolButton.InstantPopup, add_button.popupMode())
        self.assertTrue(plugin.status_action.isEnabled())
        self.assertIs(plugin.status_menu, plugin.status_action.menu())
        self.assertTrue(plugin.status_menu.toolTipsVisible())
        status_button = plugin.toolbar.widgetForAction(plugin.status_action)
        self.assertIsInstance(status_button, QToolButton)
        self.assertEqual("EVELStatusToolButton", status_button.objectName())
        self.assertEqual(QToolButton.InstantPopup, status_button.popupMode())
        self.assertEqual(
            Qt.ToolButtonTextBesideIcon,
            status_button.toolButtonStyle(),
        )
        self.assertIn("vajab tähelepanu", plugin.status_action.text())
        self.assertFalse(plugin.add_duct_action.isEnabled())
        self.assertFalse(plugin.edit_duct_action.isEnabled())
        self.assertFalse(plugin.configure_node_action.isEnabled())
        self.assertFalse(plugin.hydrant_action.isEnabled())
        self.assertFalse(plugin.connection_point_action.isEnabled())
        self.assertFalse(plugin.sewer_manhole_action.isEnabled())
        self.assertFalse(plugin.sewer_pumping_station_action.isEnabled())
        self.assertFalse(plugin.import_action.isEnabled())
        self.assertFalse(plugin.clear_data_action.isEnabled())
        self.assertFalse(hasattr(plugin, "visual_configure_node_action"))
        self.assertFalse(plugin.reverse_action.isEnabled())
        self.assertFalse(plugin.check_action.isEnabled())
        self.assertFalse(plugin.repair_action.isEnabled())
        actions = (
            plugin.status_action,
            plugin.add_duct_action,
            plugin.edit_duct_action,
            plugin.configure_node_action,
            plugin.hydrant_action,
            plugin.connection_point_action,
            plugin.sewer_manhole_action,
            plugin.sewer_pumping_station_action,
            plugin.import_action,
            plugin.clear_data_action,
            plugin.reverse_action,
            plugin.check_action,
            plugin.repair_action,
        )
        self.assertTrue(all(not action.icon().isNull() for action in actions))

        plugin.show_diagnostics()
        self.assertEqual(0, len(iface.messageBar().messages))
        self.assertIsNotNone(plugin._diagnostics_dialog)
        self.assertTrue(plugin._diagnostics_dialog.isVisible())
        self.assertIn(
            "PROJEKTIDIAGNOSTIKA",
            plugin._diagnostics_dialog.report,
        )
        self.assertIn(
            "TÖÖRIISTADE VALMISOLEK",
            plugin._diagnostics_dialog.report,
        )

        plugin.unload()
        self.assertIsNone(plugin.toolbar)
        self.assertIsNone(plugin._diagnostics_dialog)

    def test_context_status_shows_layer_active_tool_and_readiness(self) -> None:
        iface = _FakeIface()
        plugin = EVELNetworkToolsPlugin(iface)
        plugin.initGui()
        edge_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301", "Vesi", "memory"
        )
        node_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301", "Veesõlmed", "memory"
        )
        inspection = ProjectInspection(
            edge_layer=edge_layer,
            node_layer=node_layer,
            diagnostics=(),
        )
        iface._active_layer = edge_layer
        plugin._inspection = inspection
        plugin._duct_options = (
            DuctLayerOption(
                layer=edge_layer,
                label="Vesi",
                workflow=DuctWorkflow.WATER_TOPOLOGY,
                network_id=312,
                nettype_id=311,
                enabled=True,
                reason="Kasutatav.",
                inspection=inspection,
            ),
        )

        plugin._update_tool_actions()
        plugin._update_status_action()

        self.assertEqual("EVEL · Vesi — vali tööriist", plugin.status_action.text())
        self.assertIn("Aktiivne kiht: Vesi", plugin.status_action.toolTip())
        self.assertIn(
            "Järgmine samm: Vali sobiv tööriist.",
            plugin.status_action.toolTip(),
        )

        plugin.add_duct_action.setChecked(True)

        self.assertIn(
            "Lisa toru · Vesi — klõpsa alguspunktil",
            plugin.status_action.text(),
        )
        menu_texts = [action.text() for action in plugin.status_menu.actions()]
        self.assertIn("Tööriist: Lisa toru", menu_texts)
        self.assertTrue(
            any(text.startswith("Järgmine samm: Klõpsa kaardil") for text in menu_texts)
        )

        readiness_menu = next(
            action.menu()
            for action in plugin.status_menu.actions()
            if action.menu() is not None
            and action.menu().objectName() == "EVELStatusToolsMenu"
        )
        readiness = {
            action.text(): action
            for action in readiness_menu.actions()
            if not action.isSeparator()
        }
        self.assertIn("Lisa toru — valmis", readiness)
        self.assertIn("Kontrolli — pole saadaval", readiness)
        self.assertIn(
            "Vali rippmenüüst toru liik",
            readiness["Lisa toru — valmis"].toolTip(),
        )
        self.assertIn(
            "järgmistes arendusetappides",
            readiness["Kontrolli — pole saadaval"].toolTip(),
        )
        report = plugin._diagnostics_report()
        self.assertIn("Olek: VALMIS — EVEL on valmis", report)
        self.assertIn("Aktiivne kiht: Vesi", report)
        self.assertIn("Aktiivne tööriist: Lisa toru", report)
        self.assertIn("TORUKIHTIDE VALIKUD", report)
        self.assertIn("[VALMIS] Vesi", report)
        self.assertIn("Võrgu ID: 312", report)
        self.assertIn("[POLE SAADAVAL] Kontrolli", report)

        message_count = len(iface.messageBar().messages)
        readiness["Kontrolli — pole saadaval"].trigger()
        self.assertEqual(message_count + 1, len(iface.messageBar().messages))
        self.assertIn(
            "Kontrolli:",
            iface.messageBar().messages[-1][0][1],
        )

        plugin.add_duct_action.setChecked(False)
        plugin.unload()

    def test_facility_layer_keeps_usable_water_project_ready(self) -> None:
        iface = _FakeIface()
        plugin = EVELNetworkToolsPlugin(iface)
        plugin.initGui()
        edge_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301", "Vesi", "memory"
        )
        raw_water_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301", "Toorvesi", "memory"
        )
        node_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301", "EVEL veesõlmede baaskiht", "memory"
        )
        facility_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=NETWORK_ID:integer",
            "Puurkaevud ja veeallikad",
            "memory",
        )
        facility_layer.setCustomProperty("evel_project_layer", True)
        facility_layer.setCustomProperty(
            "evel_project_table",
            "sn_water_node",
        )
        facility_layer.setDefaultValueDefinition(
            facility_layer.fields().lookupField("NETWORK_ID"),
            QgsDefaultValue("314"),
        )
        inspection = ProjectInspection(
            edge_layer=edge_layer,
            node_layer=node_layer,
            diagnostics=(),
        )
        raw_water_inspection = ProjectInspection(
            edge_layer=raw_water_layer,
            node_layer=node_layer,
            diagnostics=(),
        )
        option = DuctLayerOption(
            layer=edge_layer,
            label="Vesi",
            workflow=DuctWorkflow.WATER_TOPOLOGY,
            network_id=312,
            nettype_id=308,
            enabled=True,
            reason="Kasutatav.",
            inspection=inspection,
        )
        raw_water_option = DuctLayerOption(
            layer=raw_water_layer,
            label="Toorvesi",
            workflow=DuctWorkflow.WATER_TOPOLOGY,
            network_id=314,
            nettype_id=308,
            enabled=True,
            reason="Kasutatav.",
            inspection=raw_water_inspection,
        )
        iface._active_layer = facility_layer
        plugin._duct_catalog.discover = Mock(
            return_value=(option, raw_water_option)
        )

        plugin.refresh_state()

        self.assertIs(raw_water_inspection, plugin._inspection)
        self.assertTrue(plugin.configure_node_action.isEnabled())
        self.assertNotIn("vajab tähelepanu", plugin.status_action.text())
        self.assertIn(
            "Aktiivne EVEL-i kiht „Puurkaevud ja veeallikad“",
            plugin.status_action.toolTip(),
        )
        report = plugin._diagnostics_report()
        self.assertIn("Olek: VALMIS — EVEL on valmis", report)
        self.assertIn("Aktiivne kiht: Puurkaevud ja veeallikad", report)
        self.assertIn("Diagnostikakirjeid pole.", report)
        self.assertNotIn("EDGE_ACTIVE_INVALID", report)

        plugin.unload()

    def test_facility_context_can_resolve_water_layer_outside_catalog(self) -> None:
        iface = _FakeIface()
        plugin = EVELNetworkToolsPlugin(iface)
        plugin.initGui()
        edge_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301", "Vesi", "memory"
        )
        edge_layer.setCustomProperty("evel_topology_role", "water_edge")
        edge_layer.setCustomProperty("evel_project_table", "sn_water_duct")
        abandoned_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301",
            "Mahajäetud veetorud",
            "memory",
        )
        abandoned_layer.setCustomProperty(
            "evel_topology_role",
            "water_edge",
        )
        abandoned_layer.setCustomProperty(
            "evel_project_table",
            "sn_water_duct",
        )
        abandoned_layer.setCustomProperty(
            "evel_preview_checkbox",
            "cbWaterAbandoned",
        )
        node_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301", "EVEL veesõlmede baaskiht", "memory"
        )
        facility_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301",
            "Puurkaevud ja veeallikad",
            "memory",
        )
        facility_layer.setCustomProperty("evel_project_layer", True)
        facility_layer.setCustomProperty(
            "evel_project_table",
            "sn_water_node",
        )
        inspection = ProjectInspection(
            edge_layer=edge_layer,
            node_layer=node_layer,
            diagnostics=(),
        )
        plugin._duct_catalog.discover = Mock(return_value=())
        plugin._inspector.inspect = Mock(return_value=inspection)
        QgsProject.instance().addMapLayers(
            (abandoned_layer, edge_layer, node_layer, facility_layer)
        )
        iface._active_layer = facility_layer

        plugin.refresh_state()

        self.assertIs(inspection, plugin._inspection)
        self.assertTrue(plugin.configure_node_action.isEnabled())
        self.assertEqual("EVEL on valmis", plugin._status_headline())
        self.assertNotIn("EDGE_ACTIVE_INVALID", plugin._diagnostics_report())
        self.assertTrue(
            any(
                len(call.args) >= 2 and call.args[1] is edge_layer
                for call in plugin._inspector.inspect.call_args_list
            )
        )
        self.assertFalse(
            any(
                len(call.args) >= 2 and call.args[1] is abandoned_layer
                for call in plugin._inspector.inspect.call_args_list
            )
        )

        plugin.unload()

    def test_add_action_is_enabled_after_successful_preflight(self) -> None:
        iface = _FakeIface()
        plugin = EVELNetworkToolsPlugin(iface)
        plugin.initGui()
        plugin._inspection = ProjectInspection(
            edge_layer=QgsVectorLayer(
                "LineString?crs=EPSG:3301", "Vesi", "memory"
            ),
            node_layer=QgsVectorLayer(
                "Point?crs=EPSG:3301", "Veesõlmed", "memory"
            ),
            diagnostics=(),
        )
        plugin._duct_options = (
            DuctLayerOption(
                layer=plugin._inspection.edge_layer,
                label="Vesi",
                workflow=DuctWorkflow.WATER_TOPOLOGY,
                network_id=312,
                nettype_id=311,
                enabled=True,
                reason="Kasutatav.",
                inspection=plugin._inspection,
            ),
        )

        plugin._rebuild_add_duct_menu()
        plugin._update_tool_actions()

        self.assertTrue(plugin.add_duct_action.isEnabled())
        self.assertTrue(plugin.edit_duct_action.isEnabled())
        self.assertTrue(plugin.edit_duct_action.isCheckable())
        self.assertTrue(plugin.add_duct_action.isCheckable())
        self.assertTrue(plugin.configure_node_action.isEnabled())
        self.assertTrue(plugin.configure_node_action.isCheckable())
        self.assertTrue(plugin.hydrant_action.isCheckable())
        self.assertTrue(plugin.connection_point_action.isCheckable())
        self.assertTrue(plugin.sewer_manhole_action.isCheckable())
        self.assertTrue(plugin.sewer_pumping_station_action.isCheckable())
        self.assertFalse(plugin.import_action.isEnabled())
        self.assertFalse(plugin.clear_data_action.isEnabled())
        self.assertEqual(
            "EVELSewerPumpingStationAction",
            plugin.sewer_pumping_station_action.objectName(),
        )
        self.assertEqual(
            "EVELConfigureWaterNodeAction",
            plugin.configure_node_action.objectName(),
        )
        self.assertEqual(
            "EVELHydrantAction",
            plugin.hydrant_action.objectName(),
        )
        self.assertEqual(
            "EVELConnectionPointAction",
            plugin.connection_point_action.objectName(),
        )
        self.assertEqual(
            1,
            sum(
                action.text() == "Konfigureeri sõlm"
                for action in plugin.toolbar.actions()
            ),
        )
        self.assertFalse(plugin.reverse_action.isEnabled())
        plugin.unload()

    def test_gravity_menu_selection_activates_layer_and_controller(self) -> None:
        iface = _FakeIface()
        plugin = EVELNetworkToolsPlugin(iface)
        plugin.initGui()
        layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301",
            "Isevoolne kanal",
            "memory",
        )
        QgsProject.instance().addMapLayer(layer)
        option = DuctLayerOption(
            layer=layer,
            label="Isevoolne kanal",
            workflow=DuctWorkflow.GRAVITY_GEOMETRY,
            network_id=315,
            nettype_id=309,
            enabled=True,
            reason="Kasutatav.",
        )
        plugin._duct_options = (option,)
        plugin._rebuild_add_duct_menu()

        class _Controller:
            def __init__(self) -> None:
                self.activated_layer = None

            def activate(self, selected_layer) -> bool:
                self.activated_layer = selected_layer
                return True

            def cancel(self) -> None:
                pass

        controller = _Controller()
        plugin._gravity_controller = controller
        menu_action = next(
            action
            for action in plugin.add_duct_menu.actions()
            if action.text() == "Isevoolne kanal"
        )
        coordinate_action = next(
            action
            for action in plugin.add_duct_menu.actions()
            if action.objectName() == "EVELAddDuctCoordinatesAction"
        )
        self.assertTrue(coordinate_action.isEnabled())
        self.assertFalse(coordinate_action.icon().isNull())

        menu_action.trigger()

        self.assertIs(layer, iface.activeLayer())
        self.assertIs(layer, controller.activated_layer)
        self.assertEqual(layer.id(), plugin._selected_duct_layer_id)
        plugin.unload()

    def test_flow_direction_action_is_enabled_for_supported_field(self) -> None:
        iface = _FakeIface()
        plugin = EVELNetworkToolsPlugin(iface)
        plugin.initGui()
        layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=FLOWDIRECTION:double",
            "Isevoolne kanal",
            "memory",
        )
        option = DuctLayerOption(
            layer=layer,
            label="Isevoolne kanal",
            workflow=DuctWorkflow.GRAVITY_GEOMETRY,
            network_id=315,
            nettype_id=309,
            enabled=True,
            reason="Kasutatav.",
        )
        plugin._duct_options = (option,)

        plugin._update_tool_actions()

        self.assertTrue(plugin.reverse_action.isEnabled())
        self.assertTrue(plugin.reverse_action.isCheckable())
        self.assertIn(
            "Määramata suunaks",
            plugin.reverse_action.toolTip(),
        )
        plugin.unload()

    def test_coordinate_dialog_routes_geometry_to_selected_layer(self) -> None:
        iface = _FakeIface()
        plugin = EVELNetworkToolsPlugin(iface)
        plugin.initGui()
        layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301",
            "Isevoolne kanal",
            "memory",
        )
        QgsProject.instance().addMapLayer(layer)
        option = DuctLayerOption(
            layer=layer,
            label="Isevoolne kanal",
            workflow=DuctWorkflow.GRAVITY_GEOMETRY,
            network_id=315,
            nettype_id=309,
            enabled=True,
            reason="Kasutatav.",
        )
        geometry = QgsGeometry.fromPolylineXY(
            [QgsPointXY(500000, 6580000), QgsPointXY(500010, 6580010)]
        )
        calls = []

        class _Controller:
            @staticmethod
            def cancel() -> None:
                pass

            @staticmethod
            def add_geometry(selected_layer, selected_geometry) -> bool:
                calls.append((selected_layer, selected_geometry))
                return True

        dialog = Mock()
        dialog.exec_.return_value = QDialog.Accepted
        dialog.selected_option = option
        dialog.duct_geometry.return_value = geometry
        plugin._duct_options = (option,)
        plugin._gravity_controller = _Controller()

        with patch(
            "EVEL_network_tools.plugin.CoordinateDuctDialog",
            return_value=dialog,
        ):
            plugin._open_coordinate_duct_dialog()

        self.assertEqual(1, len(calls))
        self.assertIs(layer, calls[0][0])
        self.assertEqual(geometry.asWkt(), calls[0][1].asWkt())
        self.assertIs(layer, iface.activeLayer())
        plugin.unload()


if __name__ == "__main__":
    unittest.main()
