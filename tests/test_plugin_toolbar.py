"""Smoke test for toolbar creation and plugin lifecycle."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from qgis.PyQt.QtCore import QObject, QSize, pyqtSignal
from qgis.PyQt.QtWidgets import QDialog, QMainWindow, QToolBar, QToolButton
from qgis.core import QgsGeometry, QgsPointXY, QgsProject, QgsVectorLayer

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
        self.assertEqual(1, len(iface.messageBar().messages))

        plugin.unload()
        self.assertIsNone(plugin.toolbar)

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
