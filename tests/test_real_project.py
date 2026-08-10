"""Read-only integration test for a generator-created QGIS project."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from qgis.core import QgsGeometry, QgsMapLayer, QgsPointXY, QgsProject

from EVEL_network_tools.layers import (
    DuctLayerCatalog,
    DuctWorkflow,
    EVELProjectInspector,
    NodeConfigurationInspector,
    SewerManholeInspector,
    SewerPumpingStationInspector,
)
from EVEL_network_tools.tests.qgis_test_utils import start_qgis
from EVEL_network_tools.topology import (
    EndpointResolutionError,
    NodeAssemblyReader,
    NodeConfigurationError,
    SewerManholeReader,
    WaterEndpointResolver,
    branch_type_is_compatible,
)
from EVEL_network_tools.ui import VisualNodeConfiguratorDialog


start_qgis()


class GeneratedProjectIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        configured = os.environ.get("EVEL_TEST_PROJECT", "")
        cls.project_path = Path(configured) if configured else None

    def test_generated_water_layers_pass_add_preflight(self) -> None:
        if self.project_path is None or not self.project_path.is_file():
            self.skipTest("EVEL_TEST_PROJECT does not point to a QGZ/QGS file")

        project = QgsProject()
        self.assertTrue(project.read(str(self.project_path)), project.error())

        # The fixture has multiple valid water_edge layers.  The display name
        # is used only to select the intended fixture layer for this test;
        # production discovery never relies on it.
        edge = next(
            (
                layer
                for layer in project.mapLayers().values()
                if layer.name() == "Vesi"
                and str(
                    layer.customProperty("evel_topology_role", "")
                ).lower()
                == "water_edge"
            ),
            None,
        )
        self.assertIsNotNone(edge, "Testprojektis puudub Vesi water_edge kiht")

        result = EVELProjectInspector().inspect(project, edge)

        messages = "\n".join(
            f"{item.code}: {item.message}" for item in result.errors
        )
        self.assertTrue(result.can_add_water_duct, messages)
        self.assertEqual("sn_water_duct", edge.customProperty("evel_project_table"))
        self.assertEqual(
            "sn_water_node",
            result.node_layer.customProperty("evel_project_table"),
        )
        self.assertFalse(result.node_layer.subsetString())

    def test_generated_project_exposes_expected_add_duct_choices(self) -> None:
        if self.project_path is None or not self.project_path.is_file():
            self.skipTest("EVEL_TEST_PROJECT does not point to a QGZ/QGS file")

        project = QgsProject()
        self.assertTrue(project.read(str(self.project_path)), project.error())

        options = DuctLayerCatalog().discover(project)
        enabled = {
            (option.label, option.network_id, option.nettype_id)
            for option in options
            if option.enabled
            and option.workflow is DuctWorkflow.GRAVITY_GEOMETRY
        }

        self.assertEqual(
            {
                ("Isevoolne kanal", 315, 309),
                ("Isevoolsed torud", 316, 309),
                ("Ühisvoolne kanal", 318, None),
                ("Drenaaž", 317, None),
            },
            enabled,
        )

    def test_generated_project_supports_sewer_manhole_clock(self) -> None:
        if self.project_path is None or not self.project_path.is_file():
            self.skipTest("EVEL_TEST_PROJECT does not point to a QGZ/QGS file")

        project = QgsProject()
        self.assertTrue(project.read(str(self.project_path)), project.error())

        context = SewerManholeInspector().discover(project)
        self.assertEqual(
            "EVEL kanalisatsioonisõlmede baaskiht",
            context.node_layer.name(),
        )
        self.assertFalse(context.node_layer.vectorJoins())
        self.assertFalse(context.node_layer.subsetString())
        self.assertTrue(
            bool(
                context.node_layer.flags()
                & QgsMapLayer.LayerFlag.Private
            )
        )
        self.assertIsNotNone(context.visible_manhole_layer)
        self.assertEqual(
            "Kaevud",
            context.visible_manhole_layer.name(),
        )
        self.assertTrue(context.visible_manhole_layer.vectorJoins())
        self.assertIsNotNone(context.visible_branch_layer)
        self.assertEqual(
            "Liitmikud",
            context.visible_branch_layer.name(),
        )
        self.assertTrue(context.visible_branch_layer.vectorJoins())
        self.assertEqual(
            "sn_sewer_manhole",
            context.manhole_layer.customProperty("evel_project_table"),
        )
        self.assertEqual(
            "sn_sewer_branch",
            context.branch_layer.customProperty("evel_project_table"),
        )
        self.assertEqual(
            {
                "Drenaaž",
                "Isevoolne kanal",
                "Isevoolsed torud",
                "Ühisvoolne kanal",
            },
            {layer.name() for layer in context.duct_layers},
        )
        self.assertTrue(context.options.type_options)
        self.assertEqual(456, context.options.default_type_id)
        self.assertEqual(395, context.options.connection_branch_type_id)

        state = None
        last_error = None
        feature_found = False
        reader = SewerManholeReader(context)
        for layer in context.duct_layers:
            for feature in layer.getFeatures():
                feature_found = True
                geometry = feature.geometry()
                if not feature.hasGeometry() or geometry.length() <= 0:
                    continue
                point = geometry.interpolate(
                    geometry.length() / 2.0
                ).asPoint()
                try:
                    candidate = reader.resolve(
                        QgsPointXY(point.x(), point.y()),
                        0.001,
                    )
                except Exception as error:
                    last_error = error
                    continue
                if candidate.split_layer is not None:
                    state = candidate
                    break
            if state is not None:
                break
        if not feature_found:
            self.skipTest(
                "Pärisprojekti isevoolsetes torukihtides pole näidisobjekte"
            )
        self.assertIsNotNone(
            state,
            f"Pärisprojektist ei leitud kaevukellale torulõiku: {last_error}",
        )
        self.assertEqual(2, len(state.ports))

    def test_generated_project_supports_sewer_pumping_station(self) -> None:
        if self.project_path is None or not self.project_path.is_file():
            self.skipTest("EVEL_TEST_PROJECT does not point to a QGZ/QGS file")

        project = QgsProject()
        self.assertTrue(project.read(str(self.project_path)), project.error())

        context = SewerPumpingStationInspector().discover(project)

        self.assertEqual(
            "Pumplad detailandmed",
            context.detail_layer.name(),
        )
        self.assertEqual("Pumplad", context.visible_layer.name())
        self.assertTrue(context.visible_layer.vectorJoins())
        self.assertTrue(context.pump_layer.isValid())
        self.assertTrue(
            context.pump_layer.flags() & QgsMapLayer.LayerFlag.Private
        )
        self.assertIsNone(
            project.layerTreeRoot().findLayer(context.pump_layer.id())
        )
        self.assertEqual(479, context.options.default_type_id)
        self.assertEqual(363, context.options.default_material_id)
        self.assertEqual(474, context.options.default_role_id)
        self.assertEqual(470, context.options.default_control_id)
        self.assertTrue(context.options.type_options)
        self.assertTrue(context.options.material_options)
        self.assertTrue(context.options.role_options)
        self.assertTrue(context.options.control_options)
        self.assertTrue(context.options.pump_type_options)
        self.assertTrue(context.options.pump_install_method_options)
        self.assertIn(100.0, context.options.pump_diameter_options)
        self.assertEqual(
            tuple(sorted(context.options.pump_diameter_options)),
            context.options.pump_diameter_options,
        )

    def test_generated_project_resolves_coincident_sewer_pipe_ends(self) -> None:
        if self.project_path is None or not self.project_path.is_file():
            self.skipTest("EVEL_TEST_PROJECT does not point to a QGZ/QGS file")

        project = QgsProject()
        self.assertTrue(project.read(str(self.project_path)), project.error())
        context = SewerManholeInspector().discover(project)
        endpoints = []
        for layer in context.duct_layers:
            for feature in layer.getFeatures():
                if not feature.hasGeometry():
                    continue
                curve = feature.geometry().constGet()
                if curve is None or curve.numPoints() < 2:
                    continue
                endpoints.extend(
                    (
                        (layer, feature, curve.startPoint()),
                        (layer, feature, curve.endPoint()),
                    )
                )

        match = None
        for index, first in enumerate(endpoints):
            for second in endpoints[index + 1 :]:
                if first[0].id() == second[0].id() and (
                    first[1].id() == second[1].id()
                ):
                    continue
                first_point = QgsPointXY(first[2])
                second_point = QgsPointXY(second[2])
                if first_point.distance(second_point) <= 0.001:
                    match = first_point
                    break
            if match is not None:
                break
        if match is None:
            self.skipTest(
                "Pärisprojekti isevoolsetel torudel pole ühist toruotspunkti"
            )

        state = SewerManholeReader(context).resolve(match, 0.01)

        self.assertGreaterEqual(len(state.ports), 2)

    def test_existing_edge_endpoint_can_start_a_new_segment(self) -> None:
        if self.project_path is None or not self.project_path.is_file():
            self.skipTest("EVEL_TEST_PROJECT does not point to a QGZ/QGS file")

        project = QgsProject()
        self.assertTrue(project.read(str(self.project_path)), project.error())
        edge = next(
            layer
            for layer in project.mapLayers().values()
            if layer.name() == "Vesi"
            and str(layer.customProperty("evel_topology_role", "")).lower()
            == "water_edge"
        )
        inspection = EVELProjectInspector().inspect(project, edge)
        self.assertTrue(inspection.can_add_water_duct)

        extent = edge.extent()
        remote_point = QgsPointXY(
            extent.xMaximum() + 1000,
            extent.yMaximum() + 1000,
        )
        planned = None
        last_error = None
        for feature in edge.getFeatures():
            curve = feature.geometry().constGet()
            for endpoint in (curve.startPoint(), curve.endPoint()):
                geometry = QgsGeometry.fromPolylineXY(
                    [QgsPointXY(endpoint.x(), endpoint.y()), remote_point]
                )
                try:
                    planned = WaterEndpointResolver(
                        edge, inspection.node_layer, 0.001
                    ).resolve(geometry)
                    break
                except EndpointResolutionError as error:
                    last_error = error
            if planned is not None:
                break

        self.assertIsNotNone(
            planned,
            f"Ühtegi jätkatavat Vesi toruotsa ei leitud: {last_error}",
        )
        self.assertTrue(
            planned.start.node_id is not None
            or bool(planned.start.edge_connections)
        )

        split_planned = None
        last_split_error = None
        for feature in edge.getFeatures():
            source_geometry = feature.geometry()
            if source_geometry.length() <= 0:
                continue
            midpoint = source_geometry.interpolate(
                source_geometry.length() / 2
            ).asPoint()
            geometry = QgsGeometry.fromPolylineXY(
                [QgsPointXY(midpoint.x(), midpoint.y()), remote_point]
            )
            try:
                candidate = WaterEndpointResolver(
                    edge, inspection.node_layer, 0.001
                ).resolve(geometry)
            except EndpointResolutionError as error:
                last_split_error = error
                continue
            if candidate.start.edge_split is not None:
                split_planned = candidate
                break

        self.assertIsNotNone(
            split_planned,
            "Ühtegi kirjutamiseta planeeritavat Vesi toru "
            f"poolitamiskohta ei leitud: {last_split_error}",
        )

    def test_node_configurator_discovers_generated_detail_layers(self) -> None:
        if self.project_path is None or not self.project_path.is_file():
            self.skipTest("EVEL_TEST_PROJECT does not point to a QGZ/QGS file")

        project = QgsProject()
        self.assertTrue(project.read(str(self.project_path)), project.error())
        edge = next(
            layer
            for layer in project.mapLayers().values()
            if layer.name() == "Vesi"
            and str(layer.customProperty("evel_topology_role", "")).lower()
            == "water_edge"
        )
        inspection = EVELProjectInspector().inspect(project, edge)
        self.assertTrue(inspection.can_add_water_duct)

        context = NodeConfigurationInspector().discover(project, inspection)

        self.assertTrue(context.branch_detail_layer.isValid())
        self.assertTrue(context.valve_detail_layer.isValid())
        self.assertTrue(context.manhole_detail_layer.isValid())
        rotation_field_index = context.node_layer.fields().lookupField(
            "PNT_ROTATION"
        )
        self.assertGreaterEqual(rotation_field_index, 0)
        self.assertIn(
            context.node_layer.fields()[rotation_field_index]
            .typeName()
            .casefold(),
            {"int", "integer", "int4"},
        )
        self.assertTrue(
            any(option.label.casefold() == "kolmik" for option in context.branch_options)
        )
        self.assertGreater(len(context.valve_options), 0)
        self.assertTrue(
            any(
                option.label.casefold() == "korkkraan"
                for option in context.valve_subtype_options
            )
        )
        self.assertEqual(589, context.valve_default_type_id)
        self.assertEqual(591, context.valve_default_subtype_id)
        self.assertEqual(570, context.manhole_options.default_type_id)
        self.assertTrue(
            any(
                option.label.casefold() == "hoolduskaev"
                for option in context.manhole_options.type_options
            )
        )
        self.assertTrue(
            any(
                option.label.casefold() == "betoon rõngas"
                for option in context.manhole_options.material_options
            )
        )
        self.assertIsNotNone(context.visible_manhole_layer)
        self.assertIsNotNone(context.facility_options)
        self.assertEqual(
            {
                ("Veevõrgupumplad", 312, 370, 378),
                ("Veetöötlusjaamad", 312, 369, 376),
                ("Puurkaevud ja veeallikad", 314, 369, 376),
            },
            {
                (
                    variant.label,
                    variant.network_id,
                    variant.role_id,
                    variant.water_type_id,
                )
                for variant in context.facility_options.variants
            },
        )
        self.assertTrue(context.facility_options.material_options)
        self.assertTrue(context.facility_options.water_source_options)

    def test_visual_configurator_reads_real_pipe_directions(self) -> None:
        if self.project_path is None or not self.project_path.is_file():
            self.skipTest("EVEL_TEST_PROJECT does not point to a QGZ/QGS file")

        project = QgsProject()
        self.assertTrue(project.read(str(self.project_path)), project.error())
        edge = next(
            layer
            for layer in project.mapLayers().values()
            if layer.name() == "Vesi"
            and str(layer.customProperty("evel_topology_role", "")).lower()
            == "water_edge"
        )
        inspection = EVELProjectInspector().inspect(project, edge)
        context = NodeConfigurationInspector().discover(project, inspection)

        reader = NodeAssemblyReader(context)
        state = None
        fallback_state = None
        last_error = None
        for feature in edge.getFeatures():
            for field_name in ("BEGIN_NODE_ID", "END_NODE_ID"):
                try:
                    node_id = int(feature[field_name])
                    candidate = reader.read(node_id)
                except (TypeError, ValueError, NodeConfigurationError) as error:
                    last_error = error
                    continue
                if fallback_state is None:
                    fallback_state = candidate
                if any(
                    port.technical_parameters for port in candidate.ports
                ):
                    state = candidate
                    break
            if state is not None:
                break
        if state is None:
            state = fallback_state
        self.assertIsNotNone(
            state,
            f"Päris projektist ei leitud loetavat torusõlme: {last_error}",
        )
        self.assertTrue(
            all(0.0 <= port.bearing < 360.0 for port in state.ports)
        )
        self.assertTrue(
            any(port.technical_parameters for port in state.ports),
            "Pärisprojekti toruharudelt ei loetud tehnilisi parameetreid.",
        )
        self.assertFalse(
            any(
                parameter.startswith("(") and parameter.endswith(")")
                for port in state.ports
                for parameter in port.technical_parameters
            ),
            "ValueRelation-väljad kuvavad loetava teksti asemel lookup-ID-d.",
        )

        dialog = VisualNodeConfiguratorDialog(
            state,
            context.branch_options,
            context.valve_options,
            context.valve_subtype_options,
            context.valve_default_type_id,
            context.valve_default_subtype_id,
            context.manhole_options,
            context.facility_options,
        )
        self.assertEqual(len(state.ports), len(dialog.configuration().ports))
        self.assertIsNotNone(dialog.facility_section)
        self.assertTrue(
            all(
                variant.network_id == state.node_network_id
                for variant in dialog.facility_section._variants
            )
        )
        self.assertTrue(
            all(
                branch_type_is_compatible(
                    dialog.branch_combo.itemData(index),
                    len(state.ports),
                )
                for index in range(dialog.branch_combo.count())
            )
        )
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
