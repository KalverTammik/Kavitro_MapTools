"""Unit tests for the project-backed duct layer catalogue."""

from __future__ import annotations

import unittest

from qgis.core import QgsDefaultValue, QgsProject, QgsVectorLayer

from EVEL_network_tools.layers import DuctLayerCatalog, DuctWorkflow
from EVEL_network_tools.tests.qgis_test_utils import start_qgis


start_qgis()


class DuctLayerCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project = QgsProject()

    def test_discovers_only_supported_gravity_layer_types(self) -> None:
        layers = [
            self._sewer_layer(
                "Isevoolne kanal",
                network_id=315,
                nettype_id=309,
                component="cbSewage",
            ),
            self._sewer_layer(
                "Isevoolsed torud",
                network_id=316,
                nettype_id=309,
                component="cbRainwater",
            ),
            self._sewer_layer(
                "Ühisvoolne kanal",
                network_id=318,
                component="cbCombinedSewer",
            ),
            self._sewer_layer(
                "Drenaaž",
                network_id=317,
                component="cbDrainage",
            ),
            self._sewer_layer(
                "Survekanal",
                network_id=315,
                nettype_id=308,
                component="cbPressureSewage",
            ),
        ]
        self.project.addMapLayers(layers)

        options = DuctLayerCatalog().discover(
            self.project,
            check_runtime=False,
        )

        self.assertEqual(
            {
                "Isevoolne kanal",
                "Isevoolsed torud",
                "Ühisvoolne kanal",
                "Drenaaž",
            },
            {option.label for option in options},
        )
        self.assertTrue(
            all(
                option.workflow is DuctWorkflow.GRAVITY_GEOMETRY
                for option in options
            )
        )
        self.assertTrue(all(option.enabled for option in options))
        combined = next(
            option
            for option in options
            if option.label == "Ühisvoolne kanal"
        )
        self.assertEqual(318, combined.network_id)
        self.assertIsNone(combined.nettype_id)

    def test_rejects_layer_without_generated_filter(self) -> None:
        layer = self._sewer_layer(
            "Isevoolne kanal",
            network_id=315,
            nettype_id=309,
            component="cbSewage",
        )
        layer.setSubsetString("")
        self.project.addMapLayer(layer)

        option = DuctLayerCatalog().discover(
            self.project,
            check_runtime=False,
        )[0]

        self.assertFalse(option.enabled)
        self.assertIn("alamfilter", option.reason)

    @staticmethod
    def _sewer_layer(
        name: str,
        *,
        network_id: int,
        component: str,
        nettype_id: int | None = None,
    ) -> QgsVectorLayer:
        layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer&"
            "field=BEGIN_NODE_ID:integer64&field=END_NODE_ID:integer64&"
            "field=LENGTH_2D:double",
            name,
            "memory",
        )
        layer.setCustomProperty("evel_project_table", "sn_sewer_duct")
        layer.setCustomProperty("evel_preview_component", name)
        layer.setCustomProperty("evel_preview_checkbox", component)
        layer.setDefaultValueDefinition(
            layer.fields().lookupField("NETWORK_ID"),
            QgsDefaultValue(str(network_id)),
        )
        if nettype_id is not None:
            layer.setDefaultValueDefinition(
                layer.fields().lookupField("NETTYPE_ID"),
                QgsDefaultValue(str(nettype_id)),
            )
        layer.setSubsetString(f'"NETWORK_ID" = {network_id}')
        return layer


if __name__ == "__main__":
    unittest.main()
