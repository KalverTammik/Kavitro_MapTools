"""Unit tests for the gravity-duct edit operation."""

from __future__ import annotations

import unittest

from qgis.core import (
    QgsDefaultValue,
    QgsGeometry,
    QgsPointXY,
    QgsVariantUtils,
    QgsVectorLayer,
)

from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.topology import (
    GravityDuctWriteCanceled,
    GravityDuctWriter,
)


start_qgis()


class GravityDuctWriterTest(unittest.TestCase):
    def setUp(self) -> None:
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
        self.assertTrue(self.layer.startEditing())

    def tearDown(self) -> None:
        if self.layer.isEditable():
            self.layer.rollBack()

    def test_adds_geometry_defaults_and_length_before_form(self) -> None:
        observed = {}

        def accept_form(_layer, feature) -> bool:
            observed["network"] = feature["NETWORK_ID"]
            observed["nettype"] = feature["NETTYPE_ID"]
            observed["length"] = feature["LENGTH_2D"]
            observed["begin"] = feature["BEGIN_NODE_ID"]
            observed["end"] = feature["END_NODE_ID"]
            return True

        result = GravityDuctWriter(self.layer).write(
            self._geometry(),
            accept_form,
        )

        self.assertEqual(3001, result.mslink)
        self.assertEqual(1, self.layer.featureCount())
        self.assertEqual(315, observed["network"])
        self.assertEqual(309, observed["nettype"])
        self.assertAlmostEqual(10.0, observed["length"])
        self.assertTrue(QgsVariantUtils.isNull(observed["begin"]))
        self.assertTrue(QgsVariantUtils.isNull(observed["end"]))

    def test_canceling_form_rolls_back_feature(self) -> None:
        with self.assertRaises(GravityDuctWriteCanceled):
            GravityDuctWriter(self.layer).write(
                self._geometry(),
                lambda _layer, _feature: False,
            )

        self.assertEqual(0, self.layer.featureCount())

    def test_clears_legacy_endpoint_defaults_before_insert(self) -> None:
        self._set_default("BEGIN_NODE_ID", "2")
        self._set_default("END_NODE_ID", "3")
        observed = {}

        def accept_form(_layer, feature) -> bool:
            observed["begin"] = feature["BEGIN_NODE_ID"]
            observed["end"] = feature["END_NODE_ID"]
            return True

        result = GravityDuctWriter(self.layer).write(
            self._geometry(),
            accept_form,
        )

        saved = self.layer.getFeature(result.feature_id)
        self.assertTrue(QgsVariantUtils.isNull(observed["begin"]))
        self.assertTrue(QgsVariantUtils.isNull(observed["end"]))
        self.assertTrue(QgsVariantUtils.isNull(saved["BEGIN_NODE_ID"]))
        self.assertTrue(QgsVariantUtils.isNull(saved["END_NODE_ID"]))

    @staticmethod
    def _geometry() -> QgsGeometry:
        return QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(10, 0)]
        )

    def _set_default(self, field_name: str, expression: str) -> None:
        self.layer.setDefaultValueDefinition(
            self.layer.fields().lookupField(field_name),
            QgsDefaultValue(expression),
        )


if __name__ == "__main__":
    unittest.main()
