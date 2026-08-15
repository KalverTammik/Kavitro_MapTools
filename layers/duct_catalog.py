"""Discover water and gravity duct layers offered by the add menu."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from qgis.core import (
    Qgis,
    QgsDataProvider,
    QgsProject,
    QgsProviderRegistry,
    QgsVectorLayer,
)

from .project_inspector import EVELProjectInspector, ProjectInspection


WATER_DUCT_TABLE = "sn_water_duct"
SEWER_DUCT_TABLE = "sn_sewer_duct"
ABANDONED_WATER_COMPONENT_KEYS = frozenset({"cbwaterabandoned"})
GRAVITY_NETTYPE_ID = 309
GRAVITY_COMPONENT_KEYS = frozenset(
    {"cbcombinedsewer", "cbdrainage"}
)
DUCT_REQUIRED_FIELDS = frozenset(
    {
        "MSLINK",
        "NETWORK_ID",
        "NETTYPE_ID",
        "BEGIN_NODE_ID",
        "END_NODE_ID",
        "LENGTH_2D",
    }
)


class DuctWorkflow(str, Enum):
    WATER_TOPOLOGY = "water_topology"
    GRAVITY_GEOMETRY = "gravity_geometry"


@dataclass(frozen=True)
class DuctLayerOption:
    layer: QgsVectorLayer
    label: str
    workflow: DuctWorkflow
    network_id: int
    nettype_id: int | None
    enabled: bool
    reason: str
    inspection: ProjectInspection | None = None


class DuctLayerCatalog:
    """Build the project-backed choices for the ``Lisa toru`` menu."""

    def __init__(self, water_inspector: EVELProjectInspector | None = None):
        self.water_inspector = water_inspector or EVELProjectInspector()

    def discover(
        self,
        project: QgsProject,
        *,
        check_runtime: bool = True,
    ) -> tuple[DuctLayerOption, ...]:
        water: list[DuctLayerOption] = []
        gravity: list[DuctLayerOption] = []
        for layer in project.mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            table = self._layer_table(layer)
            if table == WATER_DUCT_TABLE:
                option = self._water_option(
                    project,
                    layer,
                    check_runtime=check_runtime,
                )
                if option is not None:
                    water.append(option)
            elif table == SEWER_DUCT_TABLE:
                option = self._gravity_option(
                    layer,
                    check_runtime=check_runtime,
                )
                if option is not None:
                    gravity.append(option)
        water.sort(key=lambda item: item.label.casefold())
        gravity.sort(key=lambda item: item.label.casefold())
        return tuple((*water, *gravity))

    def _water_option(
        self,
        project: QgsProject,
        layer: QgsVectorLayer,
        *,
        check_runtime: bool,
    ) -> DuctLayerOption | None:
        network_id = self._default_int(layer, "NETWORK_ID")
        component_key = str(
            layer.customProperty("evel_preview_checkbox", "")
        ).strip().casefold()
        if (
            network_id is None
            or component_key in ABANDONED_WATER_COMPONENT_KEYS
            or "REMOVAL_YEAR" in layer.subsetString().upper()
        ):
            return None
        inspection = self.water_inspector.inspect(
            project,
            layer,
            check_runtime=check_runtime,
        )
        enabled = inspection.can_add_water_duct
        return DuctLayerOption(
            layer=layer,
            label=self._label(layer),
            workflow=DuctWorkflow.WATER_TOPOLOGY,
            network_id=network_id,
            nettype_id=self._default_int(layer, "NETTYPE_ID"),
            enabled=enabled,
            reason=(
                "Topoloogiline veetoru koos automaatsete baassõlmedega."
                if enabled
                else inspection.short_message()
            ),
            inspection=inspection,
        )

    def _gravity_option(
        self,
        layer: QgsVectorLayer,
        *,
        check_runtime: bool,
    ) -> DuctLayerOption | None:
        network_id = self._default_int(layer, "NETWORK_ID")
        nettype_id = self._default_int(layer, "NETTYPE_ID")
        component_key = str(
            layer.customProperty("evel_preview_checkbox", "")
        ).strip().casefold()
        if network_id is None:
            return None
        if (
            nettype_id != GRAVITY_NETTYPE_ID
            and component_key not in GRAVITY_COMPONENT_KEYS
        ):
            return None

        errors: list[str] = []
        if layer.geometryType() != Qgis.GeometryType.Line:
            errors.append("kiht ei ole joongeomeetriaga")
        actual_fields = {field.name().upper() for field in layer.fields()}
        missing = sorted(DUCT_REQUIRED_FIELDS - actual_fields)
        if missing:
            errors.append(f"puuduvad väljad: {', '.join(missing)}")
        if not layer.subsetString().strip():
            errors.append("generaatori alamfilter puudub")
        if check_runtime:
            if layer.providerType() != "postgres":
                errors.append("andmepakkuja ei ole PostGIS")
            if layer.readOnly():
                errors.append("kiht on kirjutuskaitstud")
            provider = layer.dataProvider()
            if provider is None or not bool(
                provider.capabilities()
                & Qgis.VectorProviderCapability.AddFeatures
            ):
                errors.append("objektide lisamise õigus puudub")
            elif not bool(
                provider.providerProperty(
                    QgsDataProvider.EvaluateDefaultValues,
                    False,
                )
            ):
                errors.append(
                    "serveripoolsete vaikeväärtuste hindamine on väljas"
                )
        enabled = not errors
        return DuctLayerOption(
            layer=layer,
            label=self._label(layer),
            workflow=DuctWorkflow.GRAVITY_GEOMETRY,
            network_id=network_id,
            nettype_id=nettype_id,
            enabled=enabled,
            reason=(
                "Isevoolne toru; sõlmede genereerimine lisatakse eraldi."
                if enabled
                else "; ".join(errors)
            ),
        )

    @staticmethod
    def _default_int(
        layer: QgsVectorLayer,
        field_name: str,
    ) -> int | None:
        field_index = layer.fields().lookupField(field_name)
        if field_index < 0:
            return None
        expression = layer.defaultValueDefinition(
            field_index
        ).expression().strip()
        if not expression:
            return None
        try:
            return int(expression.strip("'\""))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _label(layer: QgsVectorLayer) -> str:
        label = str(
            layer.customProperty("evel_preview_component", "")
        ).strip()
        return label or layer.name()

    @staticmethod
    def _layer_table(layer: QgsVectorLayer) -> str:
        table = str(
            layer.customProperty("evel_project_table", "")
        ).strip()
        if table:
            return table.casefold()
        try:
            decoded = QgsProviderRegistry.instance().decodeUri(
                layer.providerType(),
                layer.source(),
            )
        except (AttributeError, TypeError, ValueError):
            return ""
        return str(decoded.get("table", "")).casefold()
