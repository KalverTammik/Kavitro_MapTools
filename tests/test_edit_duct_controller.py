"""Tests for selecting and editing an existing EVEL duct."""

from __future__ import annotations

import unittest

from qgis.PyQt.QtWidgets import QAction, QDialog, QMainWindow
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
from EVEL_network_tools.map_tools import EditDuctController
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
    def __init__(self, layer) -> None:
        self.canvas = QgsMapCanvas()
        self.canvas.setDestinationCrs(
            QgsCoordinateReferenceSystem("EPSG:3301")
        )
        self.canvas.resize(800, 800)
        self.canvas.setExtent(QgsRectangle(-20, -20, 20, 20))
        self.canvas.setLayers([layer])
        self.window = QMainWindow()
        self.messages = _MessageBar()
        self._active_layer = layer

    def vectorLayerTools(self):  # noqa: N802
        return _LayerTools()

    def mapCanvas(self):  # noqa: N802
        return self.canvas

    def activeLayer(self):  # noqa: N802
        return self._active_layer

    def setActiveLayer(self, layer):  # noqa: N802
        self._active_layer = layer
        return True

    def mainWindow(self):  # noqa: N802
        return self.window

    def messageBar(self):  # noqa: N802
        return self.messages


class EditDuctControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=IDENTIFICATION:string&field=NETWORK_ID:integer&"
            "field=NETTYPE_ID:integer&field=BEGIN_NODE_ID:integer64&"
            "field=END_NODE_ID:integer64&field=LENGTH_2D:double&"
            "field=NOTE:string",
            "Isevoolne kanal",
            "memory",
        )
        self.layer.setCustomProperty("evel_project_table", "sn_sewer_duct")
        feature = QgsFeature(self.layer.fields())
        feature.setAttributes(
            [101, "K-101", 315, 309, 10, 11, 10.0, "algne"]
        )
        feature.setGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(0, 0), QgsPointXY(10, 0)]
            )
        )
        self.assertTrue(self.layer.dataProvider().addFeature(feature))
        self.iface = _FakeIface(self.layer)
        self.action = QAction("Vaata/muuda toru")
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
        self.controller = None

    def tearDown(self) -> None:
        if self.controller is not None:
            self.controller.cancel()
        if self.layer.isEditable():
            self.layer.rollBack()

    def test_click_candidate_is_found_and_change_is_committed(self) -> None:
        class _AcceptingDialog:
            def __init__(
                dialog_self,
                layer,
                feature,
                profile,
                parent,
                *,
                read_only=False,
            ) -> None:
                self.assertEqual("gravity", profile.value)
                self.assertFalse(read_only)
                note_index = layer.fields().lookupField("NOTE")
                layer.changeAttributeValue(
                    feature.id(), note_index, "muudetud"
                )

            @staticmethod
            def exec_() -> int:
                return QDialog.Accepted

        self.controller = EditDuctController(
            self.iface,
            self.action,
            lambda: None,
            dialog_class=_AcceptingDialog,
        )
        self.assertTrue(self.controller.activate((self.option,)))
        candidates = self.controller._candidates(QgsPointXY(5, 0))
        self.assertEqual(1, len(candidates))
        self.assertEqual("101", str(candidates[0].mslink))

        self.controller._open_candidate(candidates[0])

        updated = self.layer.getFeature(candidates[0].feature_id)
        self.assertEqual("muudetud", updated["NOTE"])
        self.assertFalse(self.layer.isEditable())
        self.assertTrue(
            any(
                "salvestati andmebaasi" in args[1]
                for args, _kwargs in self.iface.messages.messages
            )
        )

    def test_canceling_dialog_rolls_back_its_edit_command(self) -> None:
        class _RejectingDialog:
            def __init__(
                dialog_self,
                layer,
                feature,
                _profile,
                _parent,
                *,
                read_only=False,
            ) -> None:
                note_index = layer.fields().lookupField("NOTE")
                layer.changeAttributeValue(
                    feature.id(), note_index, "ei jää alles"
                )

            @staticmethod
            def exec_() -> int:
                return QDialog.Rejected

        self.controller = EditDuctController(
            self.iface,
            self.action,
            lambda: None,
            dialog_class=_RejectingDialog,
        )
        self.assertTrue(self.controller.activate((self.option,)))
        candidate = self.controller._candidates(QgsPointXY(5, 0))[0]

        self.controller._open_candidate(candidate)

        self.assertEqual(
            "algne",
            self.layer.getFeature(candidate.feature_id)["NOTE"],
        )
        self.assertFalse(self.layer.isEditable())

    def test_preexisting_edit_session_is_not_committed_implicitly(self) -> None:
        class _AcceptingDialog:
            def __init__(
                dialog_self,
                layer,
                feature,
                _profile,
                _parent,
                *,
                read_only=False,
            ) -> None:
                note_index = layer.fields().lookupField("NOTE")
                layer.changeAttributeValue(
                    feature.id(), note_index, "kasutaja puhvris"
                )

            @staticmethod
            def exec_() -> int:
                return QDialog.Accepted

        self.assertTrue(self.layer.startEditing())
        self.controller = EditDuctController(
            self.iface,
            self.action,
            lambda: None,
            dialog_class=_AcceptingDialog,
        )
        self.assertTrue(self.controller.activate((self.option,)))
        candidate = self.controller._candidates(QgsPointXY(5, 0))[0]

        self.controller._open_candidate(candidate)

        self.assertTrue(self.layer.isEditable())
        self.assertEqual(
            "kasutaja puhvris",
            self.layer.getFeature(candidate.feature_id)["NOTE"],
        )
        self.assertTrue(
            any(
                "varem juba redigeerimisel" in args[1]
                for args, _kwargs in self.iface.messages.messages
            )
        )


if __name__ == "__main__":
    unittest.main()
