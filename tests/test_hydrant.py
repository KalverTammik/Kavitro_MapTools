"""Tests for EVEL hydrant discovery, resolution and writing."""

from __future__ import annotations

import unittest

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPalette
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QTabWidget,
)
from qgis.core import (
    QgsDefaultValue,
    QgsEditorWidgetSetup,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from EVEL_network_tools.layers import HydrantContext, HydrantInspector
from EVEL_network_tools.map_tools import HydrantConfiguratorController
from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.ui import EvelDateEditor, HydrantDialog
from EVEL_network_tools.topology import (
    HydrantError,
    HydrantPlan,
    HydrantReader,
    HydrantWriter,
)


start_qgis()


class _LayerTools:
    @staticmethod
    def startEditing(layer) -> bool:  # noqa: N802
        return layer.startEditing()


class _HydrantIface:
    def vectorLayerTools(self):  # noqa: N802
        return _LayerTools()

    @staticmethod
    def mainWindow():  # noqa: N802
        return None


NODE_FIELDS = (
    "field=MSLINK:integer64&field=IDENTIFICATION:string&"
    "field=NETWORK_ID:integer&field=NETTYPE_ID:integer&"
    "field=INVENTORY_NR:string&field=USAGE_STATE:integer&"
    "field=CONDITION_CLASS_ID:integer&field=BUILD_YEAR:integer&"
    "field=NOTE:string"
)
DETAIL_FIELDS = (
    "field=ID:integer64&field=NODE_ID:integer64&"
    "field=TYPE_AQUA_ID:integer&field=PLUG_TYPE_ID:integer&"
    "field=LOCATION_ID:integer&field=MANUFACTURER:string&"
    "field=DUCT_SIZE:integer&field=CAPACITY:integer&"
    "field=MEASURED_CAPACITY:integer&field=MEASURE_DATE:datetime&"
    "field=MEASURE_NR:string&field=CONNECTION_STANDARD:string"
)


class HydrantTest(unittest.TestCase):
    def setUp(self) -> None:
        QgsProject.instance().clear()
        self.node_layer = QgsVectorLayer(
            f"Point?crs=EPSG:3301&{NODE_FIELDS}",
            "EVEL veesõlmede baaskiht",
            "memory",
        )
        self.detail_layer = QgsVectorLayer(
            f"None?{DETAIL_FIELDS}",
            "Hüdrandid detailandmed",
            "memory",
        )
        self.visible_layer = QgsVectorLayer(
            f"Point?crs=EPSG:3301&{NODE_FIELDS}&{DETAIL_FIELDS}",
            "Hüdrandid",
            "memory",
        )
        self.edge_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64&"
            "field=LENGTH_2D:double&field=MATERIAL_ID:integer",
            "Vesi",
            "memory",
        )
        self._default(self.node_layer, "MSLINK", "1001")
        self._default(self.detail_layer, "ID", "2001")
        self._default(self.detail_layer, "TYPE_AQUA_ID", "159")
        self._default(self.detail_layer, "PLUG_TYPE_ID", "160")
        self._default(self.detail_layer, "LOCATION_ID", "154")
        self._default(self.visible_layer, "NETWORK_ID", "313")
        self._default(self.visible_layer, "NETTYPE_ID", "308")
        self._default(self.edge_layer, "MSLINK", "501")

        self._add_node(10, 0, 0)
        self._add_node(20, 10, 0)
        edge = QgsFeature(self.edge_layer.fields())
        edge.setAttributes([500, 312, 308, 10, 20, 10.0, 7])
        edge.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            )
        )
        self.assertTrue(self.edge_layer.dataProvider().addFeature(edge))
        self.context = HydrantContext(
            node_layer=self.node_layer,
            detail_layer=self.detail_layer,
            visible_layer=self.visible_layer,
            duct_layers=(self.edge_layer,),
            default_network_id=313,
            default_nettype_id=308,
            default_type_aqua_id=159,
            default_plug_type_id=160,
            default_location_id=154,
        )

    def tearDown(self) -> None:
        for layer in (
            self.edge_layer,
            self.detail_layer,
            self.node_layer,
        ):
            if layer.isEditable():
                layer.rollBack()
        QgsProject.instance().clear()

    def test_clicking_pipe_interior_creates_hydrant_and_splits_pipe(self) -> None:
        state = HydrantReader(self.context).resolve(
            QgsPointXY(5, 0),
            0.1,
        )
        self.assertTrue(state.is_new)
        self.assertTrue(state.splits_edge)
        for layer in (
            self.node_layer,
            self.detail_layer,
            self.edge_layer,
        ):
            self.assertTrue(layer.startEditing())

        result = HydrantWriter(self.context).write(
            HydrantPlan(
                state=state,
                node_values={
                    "IDENTIFICATION": "H-1",
                    "INVENTORY_NR": "INV-1",
                },
                detail_values={
                    "TYPE_AQUA_ID": 159,
                    "PLUG_TYPE_ID": 161,
                    "LOCATION_ID": 155,
                    "MANUFACTURER": "Test",
                    "DUCT_SIZE": 100,
                    "CAPACITY": 20,
                },
            )
        )

        self.assertEqual(1001, result.node_id)
        self.assertTrue(result.created_node)
        self.assertTrue(result.split_edge)
        self.assertEqual(3, self.node_layer.featureCount())
        self.assertEqual(2, self.edge_layer.featureCount())
        self.assertEqual(1, self.detail_layer.featureCount())
        node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if feature["MSLINK"] == 1001
        )
        self.assertEqual(313, node["NETWORK_ID"])
        self.assertEqual("H-1", node["IDENTIFICATION"])
        detail = next(self.detail_layer.getFeatures())
        self.assertEqual(1001, detail["NODE_ID"])
        self.assertEqual(161, detail["PLUG_TYPE_ID"])
        self.assertEqual(20, detail["CAPACITY"])

    def test_existing_hydrant_is_updated_without_new_node(self) -> None:
        detail = QgsFeature(self.detail_layer.fields())
        detail.setAttributes(
            [77, 10, 159, 160, 154, "Vana", 80, 10, None, None, "", ""]
        )
        self.assertTrue(self.detail_layer.dataProvider().addFeature(detail))
        state = HydrantReader(self.context).resolve(
            QgsPointXY(0, 0),
            0.1,
        )
        self.assertEqual(10, state.node_id)
        self.assertEqual("77", str(state.detail_feature["ID"]))
        self.assertTrue(self.node_layer.startEditing())
        self.assertTrue(self.detail_layer.startEditing())

        result = HydrantWriter(self.context).write(
            HydrantPlan(
                state=state,
                node_values={"IDENTIFICATION": "H-10"},
                detail_values={
                    "PLUG_TYPE_ID": 162,
                    "LOCATION_ID": 157,
                    "MANUFACTURER": "Uus",
                },
            )
        )

        self.assertFalse(result.created_node)
        self.assertFalse(result.split_edge)
        self.assertEqual(2, self.node_layer.featureCount())
        self.assertEqual("H-10", self.node_layer.getFeature(1)["IDENTIFICATION"])
        updated = next(self.detail_layer.getFeatures())
        self.assertEqual(162, updated["PLUG_TYPE_ID"])
        self.assertEqual("Uus", updated["MANUFACTURER"])

    def test_empty_map_location_is_not_accepted_as_hydrant(self) -> None:
        with self.assertRaisesRegex(HydrantError, "veesõlme ega veetoru"):
            HydrantReader(self.context).resolve(
                QgsPointXY(50, 50),
                0.1,
            )

    def test_controller_starts_editing_before_dialog_and_cancel_stops_it(
        self,
    ) -> None:
        state = HydrantReader(self.context).resolve(
            QgsPointXY(5, 0),
            0.1,
        )
        observed = {}

        class _RejectDialog:
            def __init__(_self, context, selected_state, parent) -> None:
                observed["node_editable"] = context.node_layer.isEditable()
                observed["detail_editable"] = (
                    context.detail_layer.isEditable()
                )
                observed["edge_editable"] = (
                    selected_state.edge_layer.isEditable()
                )

            @staticmethod
            def exec() -> int:
                return QDialog.Rejected

            @staticmethod
            def deleteLater() -> None:  # noqa: N802
                pass

        action = QAction("Hüdrant")
        action.setCheckable(True)
        controller = HydrantConfiguratorController(
            _HydrantIface(),
            action,
            lambda: None,
            dialog_class=_RejectDialog,
        )
        controller._context = self.context
        controller._to_layer_point = lambda point, _layer: point
        controller._layer_tolerance = lambda _layer: 0.1
        original_resolve = HydrantReader.resolve
        HydrantReader.resolve = lambda _reader, _point, _tolerance: state
        try:
            controller._canvas_clicked(QgsPointXY(5, 0), Qt.LeftButton)
        finally:
            HydrantReader.resolve = original_resolve

        self.assertEqual(
            {
                "node_editable": True,
                "detail_editable": True,
                "edge_editable": True,
            },
            observed,
        )
        self.assertFalse(self.node_layer.isEditable())
        self.assertFalse(self.detail_layer.isEditable())
        self.assertFalse(self.edge_layer.isEditable())

    def test_dialog_keeps_guided_fields_and_actions_in_light_style(
        self,
    ) -> None:
        type_index = self.detail_layer.fields().lookupField("TYPE_AQUA_ID")
        self.detail_layer.setEditorWidgetSetup(
            type_index,
            QgsEditorWidgetSetup(
                "ValueMap",
                {"map": [{"Tuletõrjehüdrant": 159}]},
            ),
        )
        state = HydrantReader(self.context).resolve(
            QgsPointXY(5, 0),
            0.1,
        )
        for layer in (
            self.node_layer,
            self.detail_layer,
            self.edge_layer,
        ):
            self.assertTrue(layer.startEditing())
        dialog = HydrantDialog(self.context, state)
        self.addCleanup(dialog.deleteLater)
        start_qgis().processEvents()

        combo = dialog.detail_editor.binding("TYPE_AQUA_ID").widget
        self.assertEqual(
            "#ffffff",
            combo.palette().color(QPalette.Base).name(),
        )
        self.assertTrue(dialog.property("evelLightTheme"))
        tabs = dialog.findChild(QTabWidget)
        self.assertIsNotNone(tabs)
        self.assertTrue(tabs.property("evelWorkflowTabs"))
        self.assertEqual("01  Hüdrant", tabs.tabText(0))
        self.assertEqual("03  Haldus", tabs.tabText(2))
        self.assertFalse(tabs.tabIcon(0).isNull())
        self.assertIsNotNone(
            dialog.findChild(QFrame, "hydrantPreviewFrame")
        )
        self.assertIsNotNone(
            dialog.findChild(QFrame, "hydrantEditorFrame")
        )
        self.assertEqual(
            "hydrantSaveButton",
            dialog.buttons.button(
                QDialogButtonBox.Save
            ).objectName(),
        )
        self.assertEqual(
            "hydrantCancelButton",
            dialog.buttons.button(
                QDialogButtonBox.Cancel
            ).objectName(),
        )
        measure_date = dialog.detail_editor.binding("MEASURE_DATE").widget
        self.assertIsInstance(
            dialog._date_editors["MEASURE_DATE"],
            EvelDateEditor,
        )
        self.assertFalse(measure_date.calendarPopup())

    def test_inspector_recognizes_generated_hydrant_layers(self) -> None:
        self.node_layer.setCustomProperty(
            "evel_project_table",
            "sn_water_node",
        )
        self.node_layer.setCustomProperty(
            "evel_topology_role",
            "water_node",
        )
        self.detail_layer.setCustomProperty(
            "evel_project_table",
            "sn_fire_plug",
        )
        self.visible_layer.setCustomProperty(
            "evel_project_table",
            "sn_water_node",
        )
        self.visible_layer.setCustomProperty(
            "evel_preview_detail_tables",
            "sn_fire_plug",
        )
        self.visible_layer.setSubsetString(
            '("MSLINK" IN (SELECT "NODE_ID" FROM '
            '"evel"."sn_fire_plug"))'
        )
        project = QgsProject.instance()
        project.addMapLayers(
            [self.node_layer, self.detail_layer, self.visible_layer]
        )

        inspector = HydrantInspector()
        self.assertTrue(inspector.is_available(project))
        context = inspector.discover(project, check_runtime=False)
        self.assertIs(self.node_layer, context.node_layer)
        self.assertIs(self.detail_layer, context.detail_layer)
        self.assertIs(self.visible_layer, context.visible_layer)
        self.assertEqual(313, context.default_network_id)
        self.assertEqual(159, context.default_type_aqua_id)

    def _add_node(self, node_id: int, x: float, y: float) -> None:
        feature = QgsFeature(self.node_layer.fields())
        feature.setAttribute("MSLINK", node_id)
        feature.setAttribute("NETWORK_ID", 312)
        feature.setAttribute("NETTYPE_ID", 308)
        feature.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(x, y))
        )
        self.assertTrue(self.node_layer.dataProvider().addFeature(feature))

    @staticmethod
    def _default(
        layer: QgsVectorLayer,
        field_name: str,
        expression: str,
    ) -> None:
        index = layer.fields().lookupField(field_name)
        layer.setDefaultValueDefinition(
            index,
            QgsDefaultValue(expression),
        )


if __name__ == "__main__":
    unittest.main()
