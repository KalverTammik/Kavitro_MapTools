"""Headless integration test for the gravity-duct map controller."""

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

from EVEL_network_tools.map_tools import AddGravityDuctController
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


class AddGravityDuctControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.iface = _FakeIface()
        self.action = QAction("Lisa toru")
        self.action.setCheckable(True)
        self.finished_calls = 0
        self.layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64&"
            "field=LENGTH_2D:double",
            "Isevoolne kanal",
            "memory",
        )
        self._set_default("MSLINK", "3001")
        self._set_default("NETWORK_ID", "315")
        self._set_default("NETTYPE_ID", "309")
        self.controller = AddGravityDuctController(
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
        if self.layer.isEditable():
            self.layer.rollBack()

    def test_capture_writes_feature_and_finishes_one_shot_tool(self) -> None:
        self.assertTrue(self.controller.activate(self.layer))
        self.assertTrue(self.action.isChecked())
        self.assertTrue(self.layer.isEditable())

        captured = QgsFeature(self.layer.fields())
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
        self.assertFalse(self.layer.isEditable())
        self.assertEqual(1, self.layer.featureCount())
        feature = next(self.layer.getFeatures())
        self.assertAlmostEqual(10.0, feature["LENGTH_2D"])
        self.assertGreaterEqual(self.finished_calls, 1)

    def test_controller_uses_guided_gravity_dialog(self) -> None:
        calls = []

        class _Dialog:
            def __init__(self, layer, feature, profile, parent) -> None:
                calls.append((layer, feature, profile, parent))

            @staticmethod
            def exec_() -> int:
                return QDialog.Accepted

        controller = AddGravityDuctController(
            self.iface,
            self.action,
            self._finished,
            dialog_class=_Dialog,
        )
        feature = QgsFeature(self.layer.fields())

        self.assertTrue(controller._open_feature_form(self.layer, feature))
        self.assertEqual(1, len(calls))
        self.assertIs(self.layer, calls[0][0])
        self.assertIs(feature, calls[0][1])
        self.assertEqual("gravity", calls[0][2].value)
        self.assertIsNone(calls[0][3])
        self.assertEqual(0, self.iface.form_calls)

    def test_canceling_form_ends_plugin_owned_edit_session(self) -> None:
        controller = AddGravityDuctController(
            self.iface,
            self.action,
            self._finished,
            form_opener=lambda _layer, _feature: False,
        )
        self.assertTrue(controller.activate(self.layer))
        captured = QgsFeature(self.layer.fields())
        captured.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            )
        )

        controller._digitizing_completed(captured)

        self.assertFalse(controller.is_active)
        self.assertFalse(self.layer.isEditable())
        self.assertEqual(0, self.layer.featureCount())

    def _finished(self) -> None:
        self.finished_calls += 1

    def _set_default(self, field_name: str, expression: str) -> None:
        self.layer.setDefaultValueDefinition(
            self.layer.fields().lookupField(field_name),
            QgsDefaultValue(expression),
        )


if __name__ == "__main__":
    unittest.main()
