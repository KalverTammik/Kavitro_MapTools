"""Tests for EVEL connection-point discovery, editing and UI."""

from __future__ import annotations

import unittest

from qgis.PyQt.QtGui import QPalette
from qgis.PyQt.QtWidgets import QDialogButtonBox, QTabWidget
from qgis.core import (
    QgsDefaultValue,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from EVEL_network_tools.layers import (
    ConnectionPointContext,
    ConnectionPointInspector,
)
from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.topology import (
    ConnectionPointPlan,
    ConnectionPointReader,
    ConnectionPointWriter,
)
from EVEL_network_tools.ui import ConnectionPointDialog


start_qgis()


POINT_FIELDS = (
    "field=ID:integer64&field=IDENTIFICATION:string&"
    "field=OWNER_ID:integer64&field=INVOICING_ID:integer64&"
    "field=CONSUMERPOINT_GROUP:integer&field=REAL_ESTATE_NR:string&"
    "field=WATER_JUNCTION:boolean&field=SEWER_JUNCTION:boolean&"
    "field=STORM_WATER_JUNCTION:boolean&"
    "field=WATER_NETWORK_NODE:integer64&"
    "field=SEWER_NETWORK_NODE:integer64&"
    "field=RAIN_NETWORK_NODE:integer64&"
    "field=CRITICALCUSTOMER_IS:boolean&"
    "field=SPRINKLERCUSTOMER_IS:boolean&"
    "field=INDUSTRIALWWCONT_IS:boolean&"
    "field=CP_TYPE_ID:integer&field=CP_STATE_ID:integer&"
    "field=RESIDENTS:integer&field=COMMENTS:string"
)


class ConnectionPointTest(unittest.TestCase):
    def setUp(self) -> None:
        QgsProject.instance().clear()
        self.point_layer = QgsVectorLayer(
            f"Point?crs=EPSG:3301&{POINT_FIELDS}",
            "Liitumispunktid",
            "memory",
        )
        self.water_nodes = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=IDENTIFICATION:string",
            "EVEL veesõlmede baaskiht",
            "memory",
        )
        self.sewer_nodes = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=IDENTIFICATION:string",
            "EVEL kanalisatsioonisõlmede baaskiht",
            "memory",
        )
        self.point_layer.setDefaultValueDefinition(
            self.point_layer.fields().lookupField("ID"),
            QgsDefaultValue("1001"),
        )
        self._add_node(self.water_nodes, 10, 0, 0)
        self._add_node(self.sewer_nodes, 20, 10, 0)
        self.context = ConnectionPointContext(
            point_layer=self.point_layer,
            water_node_layer=self.water_nodes,
            sewer_node_layer=self.sewer_nodes,
            customer_layer=None,
        )

    def tearDown(self) -> None:
        if self.point_layer.isEditable():
            self.point_layer.rollBack()
        QgsProject.instance().clear()

    def test_water_node_creates_linked_connection_point(self) -> None:
        reader = ConnectionPointReader(self.context)
        candidates = reader.node_candidates(QgsPointXY(0, 0), 0.1)
        self.assertEqual(["water"], [item.network_kind for item in candidates])
        state = reader.new_state(candidates[0])

        self.assertTrue(self.point_layer.startEditing())
        result = ConnectionPointWriter(self.context).write(
            ConnectionPointPlan(
                state=state,
                values={
                    "IDENTIFICATION": "LP-1",
                    "WATER_NETWORK_NODE": 10,
                    "WATER_JUNCTION": True,
                    "SEWER_JUNCTION": False,
                    "STORM_WATER_JUNCTION": False,
                },
            )
        )

        self.assertTrue(result.created)
        self.assertEqual(1001, result.point_id)
        feature = next(self.point_layer.getFeatures())
        self.assertEqual("LP-1", feature["IDENTIFICATION"])
        self.assertEqual(10, feature["WATER_NETWORK_NODE"])
        self.assertTrue(feature["WATER_JUNCTION"])
        self.assertEqual(QgsPointXY(0, 0), feature.geometry().asPoint())

    def test_sewer_node_offers_wastewater_and_stormwater_roles(self) -> None:
        candidates = ConnectionPointReader(self.context).node_candidates(
            QgsPointXY(10, 0),
            0.1,
        )
        self.assertEqual(
            {"sewer", "rain"},
            {candidate.network_kind for candidate in candidates},
        )
        self.assertEqual({20}, {candidate.node_id for candidate in candidates})

    def test_existing_connection_point_is_updated(self) -> None:
        feature = QgsFeature(self.point_layer.fields())
        feature["ID"] = 77
        feature["IDENTIFICATION"] = "Vana"
        feature["WATER_NETWORK_NODE"] = 10
        feature["WATER_JUNCTION"] = True
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        self.assertTrue(self.point_layer.dataProvider().addFeature(feature))

        reader = ConnectionPointReader(self.context)
        state = reader.existing(QgsPointXY(0, 0), 0.1)
        self.assertIsNotNone(state)
        self.assertTrue(self.point_layer.startEditing())
        result = ConnectionPointWriter(self.context).write(
            ConnectionPointPlan(
                state=state,
                values={"IDENTIFICATION": "Uus"},
            )
        )

        self.assertFalse(result.created)
        self.assertEqual(77, result.point_id)
        self.assertEqual(
            "Uus",
            self.point_layer.getFeature(state.feature_id)["IDENTIFICATION"],
        )

    def test_dialog_uses_light_style_and_keeps_network_link(self) -> None:
        QgsProject.instance().addMapLayers(
            [self.point_layer, self.water_nodes, self.sewer_nodes]
        )
        state = ConnectionPointReader(self.context).new_state(
            ConnectionPointReader(self.context).node_candidates(
                QgsPointXY(0, 0),
                0.1,
            )[0]
        )
        self.assertTrue(self.point_layer.startEditing())
        dialog = ConnectionPointDialog(self.context, state)
        self.addCleanup(dialog.deleteLater)
        start_qgis().processEvents()

        self.assertTrue(dialog.property("evelLightTheme"))
        tabs = dialog.findChild(QTabWidget)
        self.assertIsNotNone(tabs)
        self.assertTrue(tabs.property("evelWorkflowTabs"))
        self.assertEqual("01  Põhiandmed", tabs.tabText(0))
        self.assertEqual("04  Märkused", tabs.tabText(3))
        self.assertFalse(tabs.tabIcon(0).isNull())
        self.assertEqual(
            "#ffffff",
            dialog.palette().color(QPalette.Base).name(),
        )
        self.assertEqual(
            "connectionPointSaveButton",
            dialog.buttons.button(
                QDialogButtonBox.Save
            ).objectName(),
        )
        plan = dialog.plan()
        self.assertEqual(10, plan.values["WATER_NETWORK_NODE"])
        self.assertTrue(plan.values["WATER_JUNCTION"])
        self.assertFalse(plan.values["SEWER_JUNCTION"])

    def test_inspector_finds_generated_visible_and_support_layers(self) -> None:
        self.point_layer.setCustomProperty(
            "evel_project_table",
            "consumer_point",
        )
        self.water_nodes.setCustomProperty(
            "evel_project_table",
            "sn_water_node",
        )
        self.water_nodes.setCustomProperty(
            "evel_connection_support_layer",
            True,
        )
        self.sewer_nodes.setCustomProperty(
            "evel_project_table",
            "sn_sewer_node",
        )
        self.sewer_nodes.setCustomProperty(
            "evel_connection_support_layer",
            True,
        )
        QgsProject.instance().addMapLayers(
            [self.point_layer, self.water_nodes, self.sewer_nodes]
        )

        inspector = ConnectionPointInspector()
        self.assertTrue(inspector.is_available(QgsProject.instance()))
        context = inspector.discover(
            QgsProject.instance(),
            check_runtime=False,
        )
        self.assertIs(self.point_layer, context.point_layer)
        self.assertIs(self.water_nodes, context.water_node_layer)
        self.assertIs(self.sewer_nodes, context.sewer_node_layer)

    @staticmethod
    def _add_node(
        layer: QgsVectorLayer,
        node_id: int,
        x: float,
        y: float,
    ) -> None:
        feature = QgsFeature(layer.fields())
        feature["MSLINK"] = node_id
        feature["IDENTIFICATION"] = f"S-{node_id}"
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        if not layer.dataProvider().addFeature(feature):
            raise AssertionError("Test node could not be added")


if __name__ == "__main__":
    unittest.main()
