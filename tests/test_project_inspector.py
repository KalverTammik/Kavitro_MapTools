"""Unit tests for EVEL project and layer discovery."""

from __future__ import annotations

import unittest

from qgis.core import QgsDefaultValue, QgsProject, QgsVectorLayer

from EVEL_network_tools.layers.project_inspector import (
    EVELProjectInspector,
)
from EVEL_network_tools.tests.qgis_test_utils import start_qgis


start_qgis()


class ProjectInspectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project = QgsProject()
        self.project.writeEntry("EVEL", "/model_version", "1")
        self.project.writeEntry(
            "EVEL", "/network_tools_contract_version", "1"
        )
        self.inspector = EVELProjectInspector()

    def test_resolves_active_edge_and_unique_unfiltered_node_layer(self) -> None:
        edge = self._edge_layer()
        node = self._node_layer()
        self.project.addMapLayers([edge, node])

        result = self.inspector.inspect(
            self.project, edge, check_runtime=False
        )

        self.assertTrue(result.can_add_water_duct)
        self.assertIs(result.edge_layer, edge)
        self.assertIs(result.node_layer, node)
        self.assertEqual((), result.errors)

    def test_rejects_non_evel_active_layer(self) -> None:
        node = self._node_layer()
        other = QgsVectorLayer("Point?crs=EPSG:3301", "Muu", "memory")
        self.project.addMapLayers([node, other])

        result = self.inspector.inspect(
            self.project, other, check_runtime=False
        )

        self.assertIn("EDGE_ACTIVE_INVALID", self._error_codes(result))

    def test_rejects_multiple_explicit_base_layers(self) -> None:
        edge = self._edge_layer()
        self.project.addMapLayers(
            [edge, self._node_layer("Sõlmed 1"), self._node_layer("Sõlmed 2")]
        )

        result = self.inspector.inspect(
            self.project, edge, check_runtime=False
        )

        self.assertIn("NODE_LAYER_AMBIGUOUS", self._error_codes(result))
        self.assertIsNone(result.node_layer)

    def test_rejects_filtered_base_layer(self) -> None:
        edge = self._edge_layer()
        node = self._node_layer()
        node.setSubsetString('"NETWORK_ID" = 312')
        self.project.addMapLayers([edge, node])

        result = self.inspector.inspect(
            self.project, edge, check_runtime=False
        )

        self.assertIn("NODE_LAYER_FILTERED", self._error_codes(result))

    def test_reports_missing_required_edge_field(self) -> None:
        edge = self._edge_layer(include_end_node=False)
        node = self._node_layer()
        self.project.addMapLayers([edge, node])

        result = self.inspector.inspect(
            self.project, edge, check_runtime=False
        )

        self.assertIn("LAYER_FIELDS_MISSING", self._error_codes(result))
        diagnostic = next(
            item
            for item in result.errors
            if item.code == "LAYER_FIELDS_MISSING"
        )
        self.assertIn("END_NODE_ID", diagnostic.message)

    def test_rejects_unsupported_generated_project_version(self) -> None:
        self.project.writeEntry("EVEL", "/model_version", "2")
        edge = self._edge_layer()
        node = self._node_layer()
        self.project.addMapLayers([edge, node])

        result = self.inspector.inspect(
            self.project, edge, check_runtime=False
        )

        self.assertIn(
            "PROJECT_MODEL_VERSION_UNSUPPORTED", self._error_codes(result)
        )

    @staticmethod
    def _error_codes(result) -> set[str]:
        return {item.code for item in result.errors}

    @staticmethod
    def _edge_layer(include_end_node: bool = True) -> QgsVectorLayer:
        fields = [
            "field=MSLINK:integer64",
            "field=NETWORK_ID:integer",
            "field=NETTYPE_ID:integer",
            "field=BEGIN_NODE_ID:integer64",
        ]
        if include_end_node:
            fields.append("field=END_NODE_ID:integer64")
        fields.append("field=LENGTH_2D:double")
        layer = QgsVectorLayer(
            "LineString?crs=EPSG:3301&" + "&".join(fields),
            "Vesi",
            "memory",
        )
        layer.setCustomProperty("evel_project_layer", True)
        layer.setCustomProperty("evel_project_source", "postgres")
        layer.setCustomProperty("evel_project_schema", "evel")
        layer.setCustomProperty("evel_project_table", "sn_water_duct")
        layer.setCustomProperty("evel_topology_role", "water_edge")
        layer.setCustomProperty("evel_topology_node_network_id", 312)
        layer.setCustomProperty("evel_topology_node_nettype_id", 308)
        layer.setSubsetString('"NETWORK_ID" = 312')
        layer.setDefaultValueDefinition(
            layer.fields().lookupField("NETWORK_ID"), QgsDefaultValue("312")
        )
        layer.setDefaultValueDefinition(
            layer.fields().lookupField("NETTYPE_ID"), QgsDefaultValue("308")
        )
        layer.setDefaultValueDefinition(
            layer.fields().lookupField("LENGTH_2D"),
            QgsDefaultValue("length($geometry)", True),
        )
        return layer

    @staticmethod
    def _node_layer(name: str = "EVEL veesõlmede baaskiht") -> QgsVectorLayer:
        layer = QgsVectorLayer(
            "Point?crs=EPSG:3301&field=MSLINK:integer64&"
            "field=NETWORK_ID:integer&field=NETTYPE_ID:integer",
            name,
            "memory",
        )
        layer.setCustomProperty("evel_project_layer", True)
        layer.setCustomProperty("evel_project_support_layer", True)
        layer.setCustomProperty("evel_topology_support_layer", True)
        layer.setCustomProperty("evel_project_source", "postgres")
        layer.setCustomProperty("evel_project_schema", "evel")
        layer.setCustomProperty("evel_project_table", "sn_water_node")
        layer.setCustomProperty("evel_topology_role", "water_node")
        return layer


if __name__ == "__main__":
    unittest.main()
