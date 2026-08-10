"""Tests for the modal-free EVEL duct flow-direction tool."""

from __future__ import annotations

import unittest

from qgis.PyQt.QtWidgets import QAction, QMainWindow
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.gui import QgsMapCanvas

from EVEL_network_tools.layers import DuctLayerOption, DuctWorkflow
from EVEL_network_tools.map_tools import FlowDirectionController
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


class _TrackingMapCanvas(QgsMapCanvas):
    def __init__(self) -> None:
        super().__init__()
        self.refresh_calls = 0

    def refresh(self) -> None:
        self.refresh_calls += 1
        super().refresh()


class _Progress:
    def __init__(self) -> None:
        self.labels = []
        self.visible = False
        self.closed = False

    def setLabelText(self, text: str) -> None:  # noqa: N802
        self.labels.append(text)

    def isVisible(self) -> bool:  # noqa: N802
        return self.visible

    def show(self) -> None:
        self.visible = True

    def close(self) -> None:
        self.closed = True
        self.visible = False


class _FakeIface:
    def __init__(self, layer) -> None:
        self.canvas = _TrackingMapCanvas()
        self.canvas.setDestinationCrs(
            QgsCoordinateReferenceSystem("EPSG:3301")
        )
        self.canvas.resize(800, 800)
        self.canvas.setExtent(QgsRectangle(-20, -20, 20, 20))
        self.canvas.setLayers([layer])
        self.window = QMainWindow()
        self.messages = _MessageBar()
        self._active_layer = layer
        self.set_active_calls = 0

    def vectorLayerTools(self):  # noqa: N802
        return _LayerTools()

    def mapCanvas(self):  # noqa: N802
        return self.canvas

    def activeLayer(self):  # noqa: N802
        return self._active_layer

    def setActiveLayer(self, layer):  # noqa: N802
        self.set_active_calls += 1
        self._active_layer = layer
        return True

    def mainWindow(self):  # noqa: N802
        return self.window

    def messageBar(self):  # noqa: N802
        return self.messages


class FlowDirectionControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=FLOWDIRECTION:double",
            "Isevoolne kanal",
            "memory",
        )
        feature = QgsFeature(self.layer.fields())
        feature["MSLINK"] = 101
        feature.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            )
        )
        self.assertTrue(self.layer.dataProvider().addFeature(feature))
        self.iface = _FakeIface(self.layer)
        self.action = QAction("Pööra suund")
        self.action.setCheckable(True)
        self.option = DuctLayerOption(
            layer=self.layer,
            label="Isevoolne kanal",
            workflow=DuctWorkflow.GRAVITY_GEOMETRY,
            network_id=315,
            nettype_id=309,
            enabled=True,
            reason="Kasutatav.",
        )
        self.controller = FlowDirectionController(
            self.iface,
            self.action,
            lambda: None,
            progress_factory=self._progress_factory,
        )
        self.progresses = []

    def tearDown(self) -> None:
        self.controller.cancel()
        if self.layer.isEditable():
            self.layer.rollBack()

    def test_unknown_direction_becomes_positive_and_next_click_reverses(self) -> None:
        self.assertTrue(self.controller.activate((self.option,)))
        candidate = self.controller._candidates(QgsPointXY(5, 0))[0]

        self.controller._apply(candidate)
        self.assertEqual(
            1.0,
            self.layer.getFeature(candidate.feature_id)["FLOWDIRECTION"],
        )
        self.assertFalse(self.layer.isEditable())
        self.assertTrue(self.controller.is_active)
        self.assertEqual(0, self.iface.canvas.refresh_calls)
        self.assertEqual(0, self.iface.set_active_calls)
        self.assertTrue(self.progresses[-1].closed)
        self.assertEqual(
            [
                "Muudan toru 101 suunda…",
                "Salvestan muudatuse andmebaasi…",
                "Värskendan muudetud torukihti…",
            ],
            self.progresses[-1].labels,
        )

        self.controller._apply(candidate)
        self.assertEqual(
            -1.0,
            self.layer.getFeature(candidate.feature_id)["FLOWDIRECTION"],
        )
        self.assertFalse(self.layer.isEditable())
        self.assertTrue(
            any(
                "joone lõpust algusesse" in args[1]
                for args, _kwargs in self.iface.messages.messages
            )
        )

    def test_existing_edit_session_is_not_committed(self) -> None:
        self.assertTrue(self.layer.startEditing())
        self.assertTrue(self.controller.activate((self.option,)))
        candidate = self.controller._candidates(QgsPointXY(5, 0))[0]

        self.controller._apply(candidate)

        self.assertTrue(self.layer.isEditable())
        self.assertEqual(
            1.0,
            self.layer.getFeature(candidate.feature_id)["FLOWDIRECTION"],
        )
        self.assertTrue(
            any(
                "redigeerimispuhvrisse" in args[1]
                for args, _kwargs in self.iface.messages.messages
            )
        )

    def test_value_contract_preserves_magnitude_and_initializes_unknown(self) -> None:
        self.assertEqual(1.0, FlowDirectionController.reversed_value(None))
        self.assertEqual(1.0, FlowDirectionController.reversed_value(0))
        self.assertEqual(-2.5, FlowDirectionController.reversed_value(2.5))
        self.assertEqual(2.5, FlowDirectionController.reversed_value(-2.5))
        with self.assertRaisesRegex(ValueError, "ei ole arvuline"):
            FlowDirectionController.reversed_value("vigane")

    def test_layer_without_flowdirection_is_not_usable(self) -> None:
        layer = QgsVectorLayer(
            "LineString?field=MSLINK:integer64",
            "Toru",
            "memory",
        )
        option = DuctLayerOption(
            layer=layer,
            label="Toru",
            workflow=DuctWorkflow.GRAVITY_GEOMETRY,
            network_id=315,
            nettype_id=309,
            enabled=True,
            reason="Kasutatav.",
        )
        self.assertEqual(
            (),
            FlowDirectionController.usable_options((option,)),
        )

    def test_direction_tool_does_not_require_add_feature_readiness(self) -> None:
        disabled_for_add = DuctLayerOption(
            layer=self.layer,
            label="Isevoolne kanal",
            workflow=DuctWorkflow.GRAVITY_GEOMETRY,
            network_id=315,
            nettype_id=309,
            enabled=False,
            reason="Uute objektide lisamise õigus puudub.",
        )
        self.assertEqual(
            (disabled_for_add,),
            FlowDirectionController.usable_options((disabled_for_add,)),
        )

    def _progress_factory(self, _parent):
        progress = _Progress()
        self.progresses.append(progress)
        return progress


if __name__ == "__main__":
    unittest.main()
