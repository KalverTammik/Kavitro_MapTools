"""Tests for entering duct vertices as coordinates."""

from __future__ import annotations

import unittest

from qgis.core import QgsCoordinateReferenceSystem, QgsVectorLayer

from EVEL_network_tools.layers import DuctLayerOption, DuctWorkflow
from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.ui import (
    CoordinateDuctDialog,
    CoordinateDuctInputError,
)


start_qgis()


class CoordinateDuctDialogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64",
            "Veetorud",
            "memory",
        )
        self.option = DuctLayerOption(
            layer=self.layer,
            label="Veetorud",
            workflow=DuctWorkflow.WATER_TOPOLOGY,
            network_id=312,
            nettype_id=311,
            enabled=True,
            reason="Kasutatav.",
        )
        self.dialog = CoordinateDuctDialog(
            (self.option,),
            project_crs=QgsCoordinateReferenceSystem("EPSG:3301"),
        )

    def tearDown(self) -> None:
        self.dialog.close()

    def test_builds_ordered_multivertex_geometry_in_layer_crs(self) -> None:
        self.dialog.set_coordinates(
            (
                (500000.25, 6580000.5),
                (500010.0, 6580010.0),
                (500025.75, 6580015.25),
            )
        )

        geometry = self.dialog.duct_geometry()
        points = geometry.asPolyline()

        self.assertEqual(3, len(points))
        self.assertAlmostEqual(500000.25, points[0].x())
        self.assertAlmostEqual(6580015.25, points[-1].y())

    def test_accepts_estonian_decimal_comma(self) -> None:
        first_x, first_y = self.dialog.coordinate_edits(0)
        second_x, second_y = self.dialog.coordinate_edits(1)
        first_x.setText("500000,25")
        first_y.setText("6580000,50")
        second_x.setText("500010,75")
        second_y.setText("6580010,25")

        points = self.dialog.duct_geometry().asPolyline()

        self.assertAlmostEqual(500000.25, points[0].x())
        self.assertAlmostEqual(6580010.25, points[1].y())

    def test_transforms_wgs84_input_to_layer_crs(self) -> None:
        wgs_index = next(
            index
            for index, crs in enumerate(self.dialog._crs_choices)
            if crs.authid() == "EPSG:4326"
        )
        self.dialog.crs_combo.setCurrentIndex(wgs_index)
        self.dialog.set_coordinates(
            ((24.75, 59.44), (24.751, 59.441))
        )

        points = self.dialog.duct_geometry().asPolyline()

        self.assertGreater(points[0].x(), 400000)
        self.assertGreater(points[0].y(), 6500000)

    def test_rejects_missing_or_overlapping_coordinates(self) -> None:
        with self.assertRaisesRegex(CoordinateDuctInputError, "puudu"):
            self.dialog.duct_geometry()

        self.dialog.set_coordinates(((500000, 6580000), (500000, 6580000)))
        with self.assertRaisesRegex(CoordinateDuctInputError, "kattuda"):
            self.dialog.duct_geometry()

    def test_parses_common_clipboard_formats(self) -> None:
        points = CoordinateDuctDialog._parse_clipboard(
            "500000,25;6580000,5\n500010.75\t6580010.25"
        )

        self.assertEqual(
            ((500000.25, 6580000.5), (500010.75, 6580010.25)),
            points,
        )


if __name__ == "__main__":
    unittest.main()
