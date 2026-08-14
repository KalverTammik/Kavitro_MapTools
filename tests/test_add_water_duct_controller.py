"""Headless integration test for the add-water-duct map controller."""

from __future__ import annotations

import unittest

from qgis.PyQt.QtWidgets import QAction, QDialog
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsDefaultValue,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.gui import QgsAdvancedDigitizingDockWidget, QgsMapCanvas

from EVEL_network_tools.layers import ProjectInspection
from EVEL_network_tools.map_tools import AddWaterDuctController
from EVEL_network_tools.tests.qgis_test_utils import start_qgis


start_qgis()


class _MessageBar:
    def __init__(self) -> None:
        self.messages = []

    def pushMessage(self, *args, **kwargs) -> None:  # noqa: N802
        self.messages.append((args, kwargs))


class _LayerTools:
    @staticmethod
    def startEditing(layer) -> bool:  # noqa: N802
        return layer.startEditing()


class _FakeIface:
    def __init__(self) -> None:
        self.canvas = QgsMapCanvas()
        self.canvas.setDestinationCrs(
            QgsCoordinateReferenceSystem("EPSG:3301")
        )
        self.canvas.resize(800, 800)
        self.canvas.setExtent(QgsRectangle(-20, -20, 20, 20))
        self.cad = QgsAdvancedDigitizingDockWidget(self.canvas)
        self.messages = _MessageBar()
        self.form_calls = 0

    def vectorLayerTools(self):  # noqa: N802
        return _LayerTools()

    def mapCanvas(self):  # noqa: N802
        return self.canvas

    def cadDockWidget(self):  # noqa: N802
        return self.cad

    def messageBar(self):  # noqa: N802
        return self.messages

    def openFeatureForm(  # noqa: N802
        self, _layer, _feature, _update_only, _modal
    ) -> bool:
        self.form_calls += 1
        return True


class AddWaterDuctControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.iface = _FakeIface()
        self.action = QAction("Lisa toru")
        self.action.setCheckable(True)
        self.finished_calls = 0
        self.edge_layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64&"
            "field=LENGTH_2D:double",
            "Vesi",
            "memory",
        )
        self.node_layer = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer",
            "Veesõlmed",
            "memory",
        )
        self.edge_layer.setCustomProperty(
            "evel_topology_node_network_id", 312
        )
        self.edge_layer.setCustomProperty(
            "evel_topology_node_nettype_id", 308
        )
        self._set_default(self.node_layer, "MSLINK", "1001")
        self._set_default(self.edge_layer, "MSLINK", "2001")
        self._set_default(self.edge_layer, "NETWORK_ID", "312")
        self._set_default(self.edge_layer, "NETTYPE_ID", "311")

        existing = QgsFeature(self.node_layer.fields())
        existing.setAttributes([10, 312, 308])
        existing.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(10, 0)))
        self.assertTrue(self.node_layer.dataProvider().addFeature(existing))

        old_edge = QgsFeature(self.edge_layer.fields())
        old_edge.setAttribute("MSLINK", 501)
        old_edge.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(-10, 0), QgsPointXY(0, 0)]
            )
        )
        self.assertTrue(self.edge_layer.dataProvider().addFeature(old_edge))
        self.old_edge_id = int(old_edge.id())

        self.inspection = ProjectInspection(
            self.edge_layer, self.node_layer, ()
        )
        self.controller = AddWaterDuctController(
            self.iface,
            self.action,
            self._finished,
            form_opener=lambda layer, feature: self.iface.openFeatureForm(
                layer,
                feature,
                False,
                True,
            ),
        )

    def tearDown(self) -> None:
        self.controller.cancel()
        if self.edge_layer.isEditable():
            self.edge_layer.rollBack()
        if self.node_layer.isEditable():
            self.node_layer.rollBack()

    def test_capture_writes_feature_and_returns_to_previous_tool(self) -> None:
        self.assertTrue(self.controller.activate(self.inspection))
        self.assertTrue(self.action.isChecked())
        self.assertTrue(self.edge_layer.isEditable())
        self.assertTrue(self.node_layer.isEditable())

        captured = QgsFeature(self.edge_layer.fields())
        captured.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            )
        )
        self.controller._digitizing_completed(captured)

        self.assertFalse(
            self.controller.is_active,
            self.iface.messages.messages,
        )
        self.assertFalse(self.action.isChecked())
        self.assertEqual(1, self.iface.form_calls)
        self.assertFalse(self.edge_layer.isEditable())
        self.assertFalse(self.node_layer.isEditable())
        self.assertEqual(2, self.edge_layer.featureCount())
        self.assertEqual(2, self.node_layer.featureCount())
        self.assertEqual(
            "1001",
            str(self.edge_layer.getFeature(self.old_edge_id)["END_NODE_ID"]),
        )
        self.assertGreaterEqual(self.finished_calls, 1)

    def test_capture_from_edge_interior_splits_old_edge(self) -> None:
        self.assertTrue(self.controller.activate(self.inspection))
        captured = QgsFeature(self.edge_layer.fields())
        captured.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(-5, 0), QgsPointXY(10, 0)]
            )
        )

        self.controller._digitizing_completed(captured)

        self.assertFalse(
            self.controller.is_active,
            self.iface.messages.messages,
        )
        self.assertFalse(self.edge_layer.isEditable())
        self.assertFalse(self.node_layer.isEditable())
        self.assertEqual(1, self.iface.form_calls)
        self.assertEqual(3, self.edge_layer.featureCount())
        self.assertEqual(2, self.node_layer.featureCount())
        first = self.edge_layer.getFeature(self.old_edge_id)
        self.assertAlmostEqual(5.0, first.geometry().length())
        self.assertEqual("1001", str(first["END_NODE_ID"]))
        split_part = next(
            feature
            for feature in self.edge_layer.getFeatures()
            if feature.id() != self.old_edge_id
            and str(feature["BEGIN_NODE_ID"]) == "1001"
            and feature["END_NODE_ID"] is None
        )
        self.assertAlmostEqual(5.0, split_part.geometry().length())

    def test_coordinate_geometry_uses_same_topology_writer(self) -> None:
        geometry = QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(5, 2), QgsPointXY(10, 0)]
        )

        self.assertTrue(
            self.controller.add_geometry(self.inspection, geometry),
            self.iface.messages.messages,
        )

        self.assertEqual(1, self.iface.form_calls)
        self.assertFalse(self.edge_layer.isEditable())
        self.assertFalse(self.node_layer.isEditable())
        created = max(
            self.edge_layer.getFeatures(),
            key=lambda feature: feature.geometry().length(),
        )
        self.assertEqual(3, len(created.geometry().asPolyline()))
        self.assertEqual("10", str(created["END_NODE_ID"]))

    def test_controller_uses_guided_water_dialog(self) -> None:
        calls = []

        class _Dialog:
            def __init__(self, layer, feature, profile, parent) -> None:
                calls.append((layer, feature, profile, parent))

            @staticmethod
            def exec_() -> int:
                return QDialog.Accepted

        controller = AddWaterDuctController(
            self.iface,
            self.action,
            self._finished,
            dialog_class=_Dialog,
        )
        feature = QgsFeature(self.edge_layer.fields())

        self.assertTrue(controller._open_feature_form(self.edge_layer, feature))
        self.assertEqual(1, len(calls))
        self.assertIs(self.edge_layer, calls[0][0])
        self.assertIs(feature, calls[0][1])
        self.assertEqual("water", calls[0][2].value)
        self.assertIsNone(calls[0][3])
        self.assertEqual(0, self.iface.form_calls)

    def _finished(self) -> None:
        self.finished_calls += 1

    @staticmethod
    def _set_default(layer, field_name: str, expression: str) -> None:
        layer.setDefaultValueDefinition(
            layer.fields().lookupField(field_name), QgsDefaultValue(expression)
        )


if __name__ == "__main__":
    unittest.main()
