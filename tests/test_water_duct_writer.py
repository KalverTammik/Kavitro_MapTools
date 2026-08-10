"""Unit tests for the reversible multi-layer water-duct write operation."""

from __future__ import annotations

import unittest

from qgis.core import (
    QgsDefaultValue,
    QgsFeature,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsVectorLayer,
    QgsVariantUtils,
)

from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.topology import (
    EdgeEndpointConnection,
    EdgeSplitConnection,
    EndpointKind,
    EndpointResolution,
    WaterDuctPlan,
    WaterDuctWriteCanceled,
    WaterDuctWriter,
)


start_qgis()


class WaterDuctWriterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.edge_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64&"
            "field=LENGTH_2D:double&field=MATERIAL_ID:integer",
            "Vesi",
            "memory",
        )
        self.node_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer",
            "Veesõlmed",
            "memory",
        )
        self._set_default(self.node_layer, "MSLINK", "1001")
        self._set_default(self.edge_layer, "MSLINK", "2001")
        self._set_default(self.edge_layer, "NETWORK_ID", "312")
        self._set_default(self.edge_layer, "NETTYPE_ID", "311")

        existing = QgsFeature(self.node_layer.fields())
        existing.setAttributes([10, 312, 308])
        existing.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(0, 0)))
        self.assertTrue(self.node_layer.dataProvider().addFeature(existing))
        self.assertTrue(self.edge_layer.startEditing())
        self.assertTrue(self.node_layer.startEditing())

    def tearDown(self) -> None:
        self.edge_layer.rollBack()
        self.node_layer.rollBack()

    def test_adds_node_and_edge_with_technical_fields_before_form(self) -> None:
        observed = {}

        def accept_form(layer, feature) -> bool:
            observed["begin"] = feature["BEGIN_NODE_ID"]
            observed["end"] = feature["END_NODE_ID"]
            observed["length"] = feature["LENGTH_2D"]
            return True

        result = WaterDuctWriter(
            self.edge_layer, self.node_layer
        ).write(
            self._plan(),
            network_id=312,
            nettype_id=308,
            open_form=accept_form,
        )

        self.assertEqual(10, result.begin_node_id)
        self.assertEqual(1001, result.end_node_id)
        self.assertEqual(2, self.node_layer.featureCount())
        self.assertEqual(1, self.edge_layer.featureCount())
        self.assertEqual(10, observed["begin"])
        self.assertEqual(1001, observed["end"])
        self.assertAlmostEqual(10.0, observed["length"])

        new_node = next(
            feature
            for feature in self.node_layer.getFeatures()
            if feature["MSLINK"] == 1001
        )
        self.assertEqual(312, new_node["NETWORK_ID"])
        self.assertEqual(308, new_node["NETTYPE_ID"])

    def test_form_cancel_removes_both_node_and_edge(self) -> None:
        with self.assertRaises(WaterDuctWriteCanceled):
            WaterDuctWriter(self.edge_layer, self.node_layer).write(
                self._plan(),
                network_id=312,
                nettype_id=308,
                open_form=lambda _layer, _feature: False,
            )

        self.assertEqual(1, self.node_layer.featureCount())
        self.assertEqual(0, self.edge_layer.featureCount())

    def test_connects_and_rolls_back_existing_edge_endpoint(self) -> None:
        old_edge_id = self._add_old_edge()
        plan = self._continuation_plan(old_edge_id)

        result = WaterDuctWriter(
            self.edge_layer, self.node_layer
        ).write(
            plan,
            network_id=312,
            nettype_id=308,
            open_form=lambda _layer, _feature: True,
        )

        self.assertEqual(1001, result.begin_node_id)
        self.assertEqual(
            1001, self.edge_layer.getFeature(old_edge_id)["END_NODE_ID"]
        )

        self.edge_layer.undoStack().undo()
        self.assertTrue(
            QgsVariantUtils.isNull(
                self.edge_layer.getFeature(old_edge_id)["END_NODE_ID"]
            )
        )

    def test_form_cancel_rolls_back_old_edge_reference_too(self) -> None:
        old_edge_id = self._add_old_edge()

        with self.assertRaises(WaterDuctWriteCanceled):
            WaterDuctWriter(self.edge_layer, self.node_layer).write(
                self._continuation_plan(old_edge_id),
                network_id=312,
                nettype_id=308,
                open_form=lambda _layer, _feature: False,
            )

        self.assertEqual(1, self.edge_layer.featureCount())
        self.assertEqual(1, self.node_layer.featureCount())
        self.assertTrue(
            QgsVariantUtils.isNull(
                self.edge_layer.getFeature(old_edge_id)["END_NODE_ID"]
            )
        )

    def test_splits_existing_edge_and_preserves_its_attributes(self) -> None:
        old_edge_id = self._add_splittable_edge()

        result = WaterDuctWriter(
            self.edge_layer, self.node_layer
        ).write(
            self._split_plan(old_edge_id),
            network_id=312,
            nettype_id=308,
            open_form=lambda _layer, _feature: True,
        )

        self.assertEqual(1001, result.begin_node_id)
        self.assertEqual(3, self.edge_layer.featureCount())
        self.assertEqual(2, self.node_layer.featureCount())

        first = self.edge_layer.getFeature(old_edge_id)
        self.assertAlmostEqual(5.0, first.geometry().length())
        self.assertEqual(11, first["BEGIN_NODE_ID"])
        self.assertEqual(1001, first["END_NODE_ID"])
        self.assertEqual(7, first["MATERIAL_ID"])
        self.assertAlmostEqual(5.0, first["LENGTH_2D"])

        second = next(
            feature
            for feature in self.edge_layer.getFeatures()
            if feature.id() != old_edge_id
            and feature["BEGIN_NODE_ID"] == 1001
            and feature["END_NODE_ID"] == 22
        )
        self.assertAlmostEqual(5.0, second.geometry().length())
        self.assertEqual(7, second["MATERIAL_ID"])
        self.assertAlmostEqual(5.0, second["LENGTH_2D"])

    def test_form_cancel_rolls_back_complete_edge_split(self) -> None:
        old_edge_id = self._add_splittable_edge()

        with self.assertRaises(WaterDuctWriteCanceled):
            WaterDuctWriter(self.edge_layer, self.node_layer).write(
                self._split_plan(old_edge_id),
                network_id=312,
                nettype_id=308,
                open_form=lambda _layer, _feature: False,
            )

        self.assertEqual(1, self.edge_layer.featureCount())
        self.assertEqual(1, self.node_layer.featureCount())
        original = self.edge_layer.getFeature(old_edge_id)
        self.assertAlmostEqual(10.0, original.geometry().length())
        self.assertEqual(11, original["BEGIN_NODE_ID"])
        self.assertEqual(22, original["END_NODE_ID"])
        self.assertEqual(7, original["MATERIAL_ID"])
        self.assertAlmostEqual(10.0, original["LENGTH_2D"])

    def test_split_geometry_preserves_intermediate_vertices(self) -> None:
        geometry = QgsGeometry.fromPolylineXY(
            [
                QgsPointXY(0, 0),
                QgsPointXY(4, 0),
                QgsPointXY(10, 0),
            ]
        )

        first, second = WaterDuctWriter._split_line_geometry(
            geometry, QgsPoint(7, 0)
        )

        self.assertEqual(
            [(0.0, 0.0), (4.0, 0.0), (7.0, 0.0)],
            [(point.x(), point.y()) for point in first.asPolyline()],
        )
        self.assertEqual(
            [(7.0, 0.0), (10.0, 0.0)],
            [(point.x(), point.y()) for point in second.asPolyline()],
        )

    def _plan(self) -> WaterDuctPlan:
        return WaterDuctPlan(
            geometry=QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            ),
            start=EndpointResolution(
                EndpointKind.EXISTING_NODE, QgsPoint(0, 0), 10
            ),
            end=EndpointResolution(
                EndpointKind.NEW_NODE, QgsPoint(10, 0)
            ),
        )

    def _add_old_edge(self) -> int:
        old_edge = QgsFeature(self.edge_layer.fields())
        old_edge.setAttribute("MSLINK", 501)
        old_edge.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(-10, 0), QgsPointXY(0, 0)]
            )
        )
        self.assertTrue(self.edge_layer.addFeature(old_edge))
        return int(old_edge.id())

    def _add_splittable_edge(self) -> int:
        old_edge = QgsFeature(self.edge_layer.fields())
        old_edge.setAttribute("MSLINK", 501)
        old_edge.setAttribute("NETWORK_ID", 312)
        old_edge.setAttribute("NETTYPE_ID", 311)
        old_edge.setAttribute("BEGIN_NODE_ID", 11)
        old_edge.setAttribute("END_NODE_ID", 22)
        old_edge.setAttribute("LENGTH_2D", 10.0)
        old_edge.setAttribute("MATERIAL_ID", 7)
        old_edge.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            )
        )
        self.assertTrue(self.edge_layer.addFeature(old_edge))
        return int(old_edge.id())

    @staticmethod
    def _continuation_plan(old_edge_id: int) -> WaterDuctPlan:
        return WaterDuctPlan(
            geometry=QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            ),
            start=EndpointResolution(
                EndpointKind.NEW_NODE,
                QgsPoint(0, 0),
                edge_connections=(
                    EdgeEndpointConnection(
                        feature_id=old_edge_id,
                        edge_id=501,
                        field_name="END_NODE_ID",
                        point=QgsPoint(0, 0),
                    ),
                ),
            ),
            end=EndpointResolution(
                EndpointKind.EXISTING_NODE, QgsPoint(10, 0), 10
            ),
        )

    @staticmethod
    def _split_plan(old_edge_id: int) -> WaterDuctPlan:
        return WaterDuctPlan(
            geometry=QgsGeometry.fromPolylineXY(
                [QgsPointXY(5, 0), QgsPointXY(5, 10)]
            ),
            start=EndpointResolution(
                EndpointKind.NEW_NODE,
                QgsPoint(5, 0),
                edge_split=EdgeSplitConnection(
                    feature_id=old_edge_id,
                    edge_id=501,
                    point=QgsPoint(5, 0),
                ),
            ),
            end=EndpointResolution(
                EndpointKind.EXISTING_NODE,
                QgsPoint(5, 10),
                10,
            ),
        )

    @staticmethod
    def _set_default(layer, field_name: str, expression: str) -> None:
        layer.setDefaultValueDefinition(
            layer.fields().lookupField(field_name), QgsDefaultValue(expression)
        )


if __name__ == "__main__":
    unittest.main()
