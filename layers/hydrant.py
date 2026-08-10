"""Discovery of generated EVEL layers required by the hydrant tool."""

from __future__ import annotations

from dataclasses import dataclass

from qgis.core import (
    Qgis,
    QgsDataProvider,
    QgsDataSourceUri,
    QgsProject,
    QgsProviderRegistry,
    QgsVectorLayer,
)

from .duct_catalog import DuctLayerCatalog, DuctWorkflow


WATER_NODE_TABLE = "sn_water_node"
FIRE_PLUG_TABLE = "sn_fire_plug"

_NODE_FIELDS = {
    "MSLINK",
    "IDENTIFICATION",
    "NETWORK_ID",
    "NETTYPE_ID",
    "INVENTORY_NR",
    "USAGE_STATE",
    "CONDITION_CLASS_ID",
    "BUILD_YEAR",
    "NOTE",
}
_DETAIL_FIELDS = {
    "ID",
    "NODE_ID",
    "TYPE_AQUA_ID",
    "PLUG_TYPE_ID",
    "LOCATION_ID",
    "MANUFACTURER",
    "DUCT_SIZE",
    "CAPACITY",
    "MEASURED_CAPACITY",
    "MEASURE_DATE",
    "MEASURE_NR",
    "CONNECTION_STANDARD",
}


class HydrantContextError(RuntimeError):
    """Raised when a generated project cannot support hydrant editing."""


@dataclass(frozen=True)
class HydrantContext:
    node_layer: QgsVectorLayer
    detail_layer: QgsVectorLayer
    visible_layer: QgsVectorLayer
    duct_layers: tuple[QgsVectorLayer, ...]
    default_network_id: int
    default_nettype_id: int
    default_type_aqua_id: int
    default_plug_type_id: int
    default_location_id: int


class HydrantInspector:
    """Resolve the hydrant base, detail, visible and optional duct layers."""

    def discover(
        self,
        project: QgsProject,
        *,
        check_runtime: bool = True,
    ) -> HydrantContext:
        layers = tuple(
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
        )
        node_sources = tuple(
            layer
            for layer in layers
            if self._source_table(layer) == WATER_NODE_TABLE
        )
        node_layer = self._base_node_layer(node_sources)
        detail_layer = self._unique_table_layer(layers, FIRE_PLUG_TABLE)
        visible_layer = self._visible_hydrant_layer(node_sources)
        duct_layers = tuple(
            option.layer
            for option in DuctLayerCatalog().discover(
                project,
                check_runtime=check_runtime,
            )
            if option.workflow is DuctWorkflow.WATER_TOPOLOGY
            and option.enabled
        )

        self._require_fields(node_layer, _NODE_FIELDS)
        self._require_fields(detail_layer, _DETAIL_FIELDS)
        self._require_fields(
            visible_layer,
            _NODE_FIELDS | (_DETAIL_FIELDS - {"ID", "NODE_ID"}),
        )
        default_network_id = self._integer_default(
            visible_layer,
            "NETWORK_ID",
            "hüdrandi sõlmevõrk",
        )
        default_nettype_id = self._integer_default(
            visible_layer,
            "NETTYPE_ID",
            "hüdrandi võrgutüüp",
        )
        default_type_aqua_id = self._integer_default(
            detail_layer,
            "TYPE_AQUA_ID",
            "hüdrandi liigi vaikeväärtus",
        )
        default_plug_type_id = self._integer_default(
            detail_layer,
            "PLUG_TYPE_ID",
            "hüdrandi alamtüübi vaikeväärtus",
        )
        default_location_id = self._integer_default(
            detail_layer,
            "LOCATION_ID",
            "hüdrandi paiknemise vaikeväärtus",
        )

        if check_runtime:
            self._validate_runtime(
                project,
                node_layer,
                detail_layer,
                duct_layers,
            )
        return HydrantContext(
            node_layer=node_layer,
            detail_layer=detail_layer,
            visible_layer=visible_layer,
            duct_layers=duct_layers,
            default_network_id=default_network_id,
            default_nettype_id=default_nettype_id,
            default_type_aqua_id=default_type_aqua_id,
            default_plug_type_id=default_plug_type_id,
            default_location_id=default_location_id,
        )

    def is_available(self, project: QgsProject) -> bool:
        """Return a cheap structural readiness flag for the toolbar."""

        layers = tuple(
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
        )
        node_sources = tuple(
            layer
            for layer in layers
            if self._source_table(layer) == WATER_NODE_TABLE
        )
        try:
            self._base_node_layer(node_sources)
            self._visible_hydrant_layer(node_sources)
            self._unique_table_layer(layers, FIRE_PLUG_TABLE)
        except HydrantContextError:
            return False
        return True

    def _base_node_layer(
        self,
        layers: tuple[QgsVectorLayer, ...],
    ) -> QgsVectorLayer:
        explicit = [
            layer
            for layer in layers
            if str(
                layer.customProperty("evel_topology_role", "")
            ).casefold()
            == "water_node"
            and not layer.subsetString().strip()
        ]
        if len(explicit) == 1:
            return explicit[0]
        fallback = [
            layer
            for layer in layers
            if not layer.subsetString().strip()
            and not layer.vectorJoins()
        ]
        if len(fallback) == 1:
            return fallback[0]
        if len(explicit) > 1 or len(fallback) > 1:
            raise HydrantContextError(
                "Projektis on mitu võimalikku filtreerimata veesõlmede "
                "baaskihti."
            )
        raise HydrantContextError(
            "Projektis puudub filtreerimata veesõlmede baaskiht."
        )

    def _visible_hydrant_layer(
        self,
        layers: tuple[QgsVectorLayer, ...],
    ) -> QgsVectorLayer:
        token = f'"evel"."{FIRE_PLUG_TABLE}"'.casefold()
        matches = [
            layer
            for layer in layers
            if (
                token in layer.subsetString().casefold()
                or str(
                    layer.customProperty(
                        "evel_preview_detail_tables",
                        "",
                    )
                ).strip().casefold()
                == FIRE_PLUG_TABLE
            )
        ]
        if len(matches) != 1:
            raise HydrantContextError(
                "Projektis peab olema täpselt üks generaatori Hüdrandid kiht."
            )
        return matches[0]

    def _unique_table_layer(
        self,
        layers: tuple[QgsVectorLayer, ...],
        table_name: str,
    ) -> QgsVectorLayer:
        matches = [
            layer
            for layer in layers
            if self._source_table(layer) == table_name
        ]
        if len(matches) != 1:
            raise HydrantContextError(
                f"Projektis peab olema täpselt üks {table_name} detailkiht."
            )
        return matches[0]

    def _validate_runtime(
        self,
        project: QgsProject,
        node_layer: QgsVectorLayer,
        detail_layer: QgsVectorLayer,
        duct_layers: tuple[QgsVectorLayer, ...],
    ) -> None:
        requirements = (
            (
                node_layer,
                Qgis.VectorProviderCapability.AddFeatures
                | Qgis.VectorProviderCapability.ChangeAttributeValues,
            ),
            (
                detail_layer,
                Qgis.VectorProviderCapability.AddFeatures
                | Qgis.VectorProviderCapability.ChangeAttributeValues,
            ),
        )
        for layer, required in requirements:
            if layer.providerType() != "postgres":
                raise HydrantContextError(
                    f"Kiht „{layer.name()}” peab kasutama PostGIS-i."
                )
            if layer.readOnly():
                raise HydrantContextError(
                    f"Kiht „{layer.name()}” on kirjutuskaitstud."
                )
            provider = layer.dataProvider()
            if provider is None or provider.capabilities() & required != required:
                raise HydrantContextError(
                    f"Kihil „{layer.name()}” puuduvad hüdrandi "
                    "redigeerimisõigused."
                )
            if not bool(
                provider.providerProperty(
                    QgsDataProvider.EvaluateDefaultValues,
                    False,
                )
            ):
                raise HydrantContextError(
                    f"Kihil „{layer.name()}” ei hinnata serveripoolseid "
                    "vaikeväärtusi."
                )

        base_connection = self._connection_info(node_layer)
        if not base_connection or self._connection_info(detail_layer) != base_connection:
            raise HydrantContextError(
                "Hüdrandi sõlme- ja detailkiht ei kasuta sama "
                "PostGIS-i ühendust."
            )
        for layer in duct_layers:
            if self._connection_info(layer) != base_connection:
                raise HydrantContextError(
                    f"Veetorukiht „{layer.name()}” ei kasuta hüdrandikihtidega "
                    "sama PostGIS-i ühendust."
                )

        group = project.transactionGroup(
            node_layer.providerType(),
            base_connection,
        )
        if group is None or any(
            layer not in group.layers()
            for layer in (node_layer, detail_layer, *duct_layers)
        ):
            raise HydrantContextError(
                "Hüdrandi sõlme-, detail- ja veetorukihid ei kuulu samasse "
                "automaatsesse tehingugruppi."
            )

    @staticmethod
    def _integer_default(
        layer: QgsVectorLayer,
        field_name: str,
        label: str,
    ) -> int:
        index = layer.fields().lookupField(field_name)
        expression = (
            layer.defaultValueDefinition(index).expression().strip()
            if index >= 0
            else ""
        )
        try:
            return int(expression.strip("'\""))
        except (TypeError, ValueError) as error:
            raise HydrantContextError(
                f"Kihi „{layer.name()}” {label} ei ole määratud."
            ) from error

    @staticmethod
    def _require_fields(layer: QgsVectorLayer, required: set[str]) -> None:
        actual = {field.name().upper() for field in layer.fields()}
        missing = sorted(required - actual)
        if missing:
            raise HydrantContextError(
                f"Kihil „{layer.name()}” puuduvad väljad: "
                f"{', '.join(missing)}."
            )

    @staticmethod
    def _connection_info(layer: QgsVectorLayer) -> str:
        try:
            return QgsDataSourceUri(layer.source()).connectionInfo(False)
        except (AttributeError, TypeError, ValueError):
            return ""

    @staticmethod
    def _source_table(layer: QgsVectorLayer) -> str:
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
