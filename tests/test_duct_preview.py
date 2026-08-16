"""Tests for the map-free geometry and topology preview context."""

from __future__ import annotations

import unittest

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from EVEL_network_tools.layers.duct_preview import DuctPreviewContextBuilder
from EVEL_network_tools.tests.qgis_test_utils import start_qgis


start_qgis()


class DuctPreviewContextTest(unittest.TestCase):
    def setUp(self) -> None:
        QgsProject.instance().clear()

    def tearDown(self) -> None:
        QgsProject.instance().clear()

    def test_reads_actual_geometry_neighbours_and_water_node_states(
        self,
    ) -> None:
        edge_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64&"
            "field=LENGTH_2D:double",
            "Vesi",
            "memory",
        )
        neighbour = QgsFeature(edge_layer.fields())
        neighbour.setAttribute("MSLINK", 99)
        neighbour.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, -3), QgsPointXY(20, -3)]
            )
        )
        self.assertTrue(edge_layer.dataProvider().addFeature(neighbour))

        node_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=IDENTIFICATION:string",
            "EVEL veesõlmede baaskiht",
            "memory",
        )
        node_layer.setCustomProperty("evel_project_table", "sn_water_node")
        node_layer.setCustomProperty("evel_topology_role", "water_node")
        existing = QgsFeature(node_layer.fields())
        existing.setAttributes([10, "N-10"])
        existing.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        self.assertTrue(node_layer.dataProvider().addFeature(existing))
        QgsProject.instance().addMapLayers([edge_layer, node_layer])

        self.assertTrue(node_layer.startEditing())
        new_node = QgsFeature(node_layer.fields())
        new_node.setAttributes([20, "N-20"])
        new_node.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(20, 5)))
        self.assertTrue(node_layer.addFeature(new_node))

        self.assertTrue(edge_layer.startEditing())
        active = QgsFeature(edge_layer.fields())
        active.setAttributes([100, 10, 20, 0.0])
        active.setGeometry(
            QgsGeometry.fromPolylineXY(
                [
                    QgsPointXY(0, 0),
                    QgsPointXY(10, 5),
                    QgsPointXY(20, 5),
                ]
            )
        )
        self.assertTrue(edge_layer.addFeature(active))

        context = DuctPreviewContextBuilder().build(
            edge_layer,
            active,
            "water",
        )

        self.assertEqual(((0.0, 0.0), (10.0, 5.0), (20.0, 5.0)), context.active_points)
        self.assertEqual(1, len(context.background_lines))
        self.assertEqual(2, len(context.background_nodes))
        self.assertEqual("Sõlm N-10", context.begin.title)
        self.assertEqual("Olemasolev", context.begin.status)
        self.assertEqual("Sõlm N-20", context.end.title)
        self.assertEqual("Uus sõlm", context.end.status)
        self.assertGreater(context.length_2d, 20.0)

        edge_layer.rollBack()
        node_layer.rollBack()

    def test_extracts_true_vertex_profile_only_from_z_geometry(self) -> None:
        layer = QgsVectorLayer(
            "LineStringZ?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64",
            "Ruumiline toru",
            "memory",
        )
        QgsProject.instance().addMapLayer(layer)
        self.assertTrue(layer.startEditing())
        feature = QgsFeature(layer.fields())
        feature.setAttribute("MSLINK", 1)
        feature.setGeometry(
            QgsGeometry.fromPolyline(
                [
                    QgsPoint(0, 0, 10),
                    QgsPoint(3, 4, 11),
                    QgsPoint(6, 4, 13),
                ]
            )
        )
        self.assertTrue(layer.addFeature(feature))

        context = DuctPreviewContextBuilder().build(
            layer,
            feature,
            "gravity",
        )

        self.assertTrue(context.has_z_geometry)
        self.assertEqual(((0.0, 10.0), (5.0, 11.0), (8.0, 13.0)), context.z_profile)
        self.assertEqual("Sidumata", context.begin.status)
        self.assertEqual("Sidumata", context.end.status)
        layer.rollBack()


if __name__ == "__main__":
    unittest.main()
