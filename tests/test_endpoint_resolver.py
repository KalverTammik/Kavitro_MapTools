"""Unit tests for write-free water-duct endpoint planning."""

from __future__ import annotations

import unittest

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer

from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.topology import (
    EndpointKind,
    EndpointOnEdgeError,
    EndpointResolutionError,
    WaterEndpointResolver,
)


start_qgis()


class WaterEndpointResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.edge_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64",
            "Vesi",
            "memory",
        )
        self.node_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=MSLINK:integer64",
            "Veesõlmed",
            "memory",
        )

    def test_uses_one_existing_node_and_plans_one_new_node(self) -> None:
        self._add_node(42, 0.05, 0)
        geometry = QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(10, 0)]
        )

        plan = WaterEndpointResolver(
            self.edge_layer, self.node_layer, 0.2
        ).resolve(geometry)

        self.assertIs(plan.start.kind, EndpointKind.EXISTING_NODE)
        self.assertEqual(42, plan.start.node_id)
        self.assertAlmostEqual(0.05, plan.geometry.constGet().pointN(0).x())
        self.assertIs(plan.end.kind, EndpointKind.NEW_NODE)
        self.assertIsNone(plan.end.node_id)

    def test_rejects_multiple_possible_nodes(self) -> None:
        self._add_node(41, -0.05, 0)
        self._add_node(42, 0.05, 0)

        with self.assertRaisesRegex(
            EndpointResolutionError, "mitu võimalikku sõlme"
        ):
            WaterEndpointResolver(
                self.edge_layer, self.node_layer, 0.2
            ).resolve(
                QgsGeometry.fromPolylineXY(
                    [QgsPointXY(0, 0), QgsPointXY(10, 0)]
                )
            )

    def test_plans_endpoint_which_requires_edge_split(self) -> None:
        self._add_edge(9, -2, 9, 2)

        plan = WaterEndpointResolver(
            self.edge_layer, self.node_layer, 0.2
        ).resolve(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(9.1, 0), QgsPointXY(20, 0)]
            )
        )

        self.assertIs(plan.start.kind, EndpointKind.NEW_NODE)
        self.assertIsNotNone(plan.start.edge_split)
        self.assertEqual(501, plan.start.edge_split.edge_id)
        self.assertAlmostEqual(9, plan.start.point.x())
        self.assertAlmostEqual(0, plan.start.point.y())
        self.assertAlmostEqual(9, plan.geometry.constGet().startPoint().x())

    def test_rejects_multiple_possible_edges_to_split(self) -> None:
        self._add_edge(9, -2, 9, 2)
        feature = QgsFeature(self.edge_layer.fields())
        feature.setAttribute("MSLINK", 502)
        feature.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(7, 0), QgsPointXY(11, 0)]
            )
        )
        self.assertTrue(self.edge_layer.dataProvider().addFeature(feature))

        with self.assertRaisesRegex(EndpointOnEdgeError, "mitu poolitatavat"):
            WaterEndpointResolver(
                self.edge_layer, self.node_layer, 0.2
            ).resolve(
                QgsGeometry.fromPolylineXY(
                    [QgsPointXY(9, 0), QgsPointXY(20, 5)]
                )
            )

    def test_rejects_two_splits_on_same_existing_edge(self) -> None:
        self._add_edge(0, 0, 20, 0)

        with self.assertRaisesRegex(
            EndpointResolutionError, "sama olemasoleva toru kahte kohta"
        ):
            WaterEndpointResolver(
                self.edge_layer, self.node_layer, 0.2
            ).resolve(
                QgsGeometry.fromPolylineXY(
                    [QgsPointXY(5, 0), QgsPointXY(15, 0)]
                )
            )

    def test_existing_edge_end_plans_node_and_old_edge_connection(self) -> None:
        self._add_edge(9, -2, 9, 2)

        plan = WaterEndpointResolver(
            self.edge_layer, self.node_layer, 0.2
        ).resolve(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(9, -2), QgsPointXY(20, -2)]
            )
        )

        self.assertIs(plan.start.kind, EndpointKind.NEW_NODE)
        self.assertAlmostEqual(9, plan.start.point.x())
        self.assertAlmostEqual(-2, plan.start.point.y())
        self.assertEqual(1, len(plan.start.edge_connections))
        self.assertEqual(
            "BEGIN_NODE_ID", plan.start.edge_connections[0].field_name
        )

    def test_existing_node_also_repairs_empty_old_edge_reference(self) -> None:
        self._add_node(42, 0, 0)
        self._add_edge(0, 0, 5, 0)

        plan = WaterEndpointResolver(
            self.edge_layer, self.node_layer, 0.2
        ).resolve(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(-10, 0)]
            )
        )

        self.assertIs(plan.start.kind, EndpointKind.EXISTING_NODE)
        self.assertEqual(42, plan.start.node_id)
        self.assertEqual(1, len(plan.start.edge_connections))
        self.assertEqual(
            "BEGIN_NODE_ID", plan.start.edge_connections[0].field_name
        )

    def test_rejects_closed_line(self) -> None:
        with self.assertRaisesRegex(EndpointResolutionError, "suletud"):
            WaterEndpointResolver(
                self.edge_layer, self.node_layer, 0.2
            ).resolve(
                QgsGeometry.fromPolylineXY(
                    [
                        QgsPointXY(0, 0),
                        QgsPointXY(10, 0),
                        QgsPointXY(0, 0),
                    ]
                )
            )

    def _add_node(self, mslink: int, x: float, y: float) -> None:
        feature = QgsFeature(self.node_layer.fields())
        feature.setAttribute("MSLINK", mslink)
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        self.assertTrue(self.node_layer.dataProvider().addFeature(feature))

    def _add_edge(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> None:
        feature = QgsFeature(self.edge_layer.fields())
        feature.setAttribute("MSLINK", 501)
        feature.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(x1, y1), QgsPointXY(x2, y2)]
            )
        )
        self.assertTrue(self.edge_layer.dataProvider().addFeature(feature))


if __name__ == "__main__":
    unittest.main()
