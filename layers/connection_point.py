"""Discovery of generated EVEL layers required by the connection-point tool."""

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


CONSUMER_POINT_TABLE = "consumer_point"
CUSTOMER_TABLE = "customer"
WATER_NODE_TABLE = "sn_water_node"
SEWER_NODE_TABLE = "sn_sewer_node"

CONSUMER_POINT_FIELDS = {
    "ID",
    "IDENTIFICATION",
    "OWNER_ID",
    "INVOICING_ID",
    "CONSUMERPOINT_GROUP",
    "REAL_ESTATE_NR",
    "WATER_JUNCTION",
    "SEWER_JUNCTION",
    "STORM_WATER_JUNCTION",
    "WATER_NETWORK_NODE",
    "SEWER_NETWORK_NODE",
    "RAIN_NETWORK_NODE",
    "CRITICALCUSTOMER_IS",
    "SPRINKLERCUSTOMER_IS",
    "INDUSTRIALWWCONT_IS",
    "CP_TYPE_ID",
    "CP_STATE_ID",
    "RESIDENTS",
    "COMMENTS",
}
NODE_FIELDS = {"MSLINK"}


class ConnectionPointContextError(RuntimeError):
    """Raised when the generated project cannot edit connection points."""


@dataclass(frozen=True)
class ConnectionPointContext:
    point_layer: QgsVectorLayer
    water_node_layer: QgsVectorLayer | None
    sewer_node_layer: QgsVectorLayer | None
    customer_layer: QgsVectorLayer | None

    @property
    def node_layers(self) -> tuple[tuple[str, QgsVectorLayer], ...]:
        result = []
        if self.water_node_layer is not None:
            result.append(("water", self.water_node_layer))
        if self.sewer_node_layer is not None:
            result.append(("sewer", self.sewer_node_layer))
        return tuple(result)


class ConnectionPointInspector:
    """Resolve the visible connection points and hidden reference layers."""

    def discover(
        self,
        project: QgsProject,
        *,
        check_runtime: bool = True,
    ) -> ConnectionPointContext:
        layers = tuple(
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
        )
        point_layer = self._point_layer(layers)
        water_node_layer = self._reference_layer(layers, WATER_NODE_TABLE)
        sewer_node_layer = self._reference_layer(layers, SEWER_NODE_TABLE)
        customer_layer = self._optional_reference_layer(layers, CUSTOMER_TABLE)

        self._require_fields(point_layer, CONSUMER_POINT_FIELDS)
        if water_node_layer is not None:
            self._require_fields(water_node_layer, NODE_FIELDS)
        if sewer_node_layer is not None:
            self._require_fields(sewer_node_layer, NODE_FIELDS)
        if water_node_layer is None and sewer_node_layer is None:
            raise ConnectionPointContextError(
                "Projektis puudub liitumispunktiga seotav filtreerimata "
                "vee- või kanalisatsioonisõlmede baaskiht."
            )
        if check_runtime:
            self._validate_runtime(
                project,
                point_layer,
                water_node_layer,
                sewer_node_layer,
            )
        return ConnectionPointContext(
            point_layer=point_layer,
            water_node_layer=water_node_layer,
            sewer_node_layer=sewer_node_layer,
            customer_layer=customer_layer,
        )

    def is_available(self, project: QgsProject) -> bool:
        try:
            self.discover(project, check_runtime=False)
        except ConnectionPointContextError:
            return False
        return True

    def _point_layer(
        self,
        layers: tuple[QgsVectorLayer, ...],
    ) -> QgsVectorLayer:
        matches = [
            layer
            for layer in layers
            if self._source_table(layer) == CONSUMER_POINT_TABLE
            and not layer.customProperty("evel_connection_support_layer")
        ]
        if len(matches) != 1:
            raise ConnectionPointContextError(
                "Projektis peab olema täpselt üks nähtav generaatori "
                "Liitumispunktid kiht."
            )
        return matches[0]

    def _reference_layer(
        self,
        layers: tuple[QgsVectorLayer, ...],
        table_name: str,
    ) -> QgsVectorLayer | None:
        matches = [
            layer
            for layer in layers
            if self._source_table(layer) == table_name
            and not layer.subsetString().strip()
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda layer: (
                not bool(layer.customProperty("evel_connection_support_layer")),
                not bool(layer.customProperty("evel_topology_support_layer")),
                bool(layer.vectorJoins()),
            )
        )
        preferred = matches[0]
        equally_preferred = [
            layer
            for layer in matches
            if (
                bool(layer.customProperty("evel_connection_support_layer")),
                bool(layer.customProperty("evel_topology_support_layer")),
                bool(layer.vectorJoins()),
            )
            == (
                bool(preferred.customProperty("evel_connection_support_layer")),
                bool(preferred.customProperty("evel_topology_support_layer")),
                bool(preferred.vectorJoins()),
            )
        ]
        if len(equally_preferred) > 1:
            raise ConnectionPointContextError(
                f"Projektis on mitu võimalikku filtreerimata {table_name} "
                "baaskihti."
            )
        return preferred

    def _optional_reference_layer(
        self,
        layers: tuple[QgsVectorLayer, ...],
        table_name: str,
    ) -> QgsVectorLayer | None:
        matches = [
            layer
            for layer in layers
            if self._source_table(layer) == table_name
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda layer: not bool(
                layer.customProperty("evel_connection_support_layer")
            )
        )
        return matches[0]

    def _validate_runtime(
        self,
        project: QgsProject,
        point_layer: QgsVectorLayer,
        water_node_layer: QgsVectorLayer | None,
        sewer_node_layer: QgsVectorLayer | None,
    ) -> None:
        required = (
            Qgis.VectorProviderCapability.AddFeatures
            | Qgis.VectorProviderCapability.ChangeAttributeValues
        )
        if point_layer.providerType() != "postgres":
            raise ConnectionPointContextError(
                "Liitumispunktide kiht peab kasutama PostGIS-i."
            )
        if point_layer.readOnly():
            raise ConnectionPointContextError(
                "Liitumispunktide kiht on kirjutuskaitstud."
            )
        provider = point_layer.dataProvider()
        if provider is None or provider.capabilities() & required != required:
            raise ConnectionPointContextError(
                "Liitumispunktide kihil puuduvad lisamise või muutmise õigused."
            )
        if not bool(
            provider.providerProperty(
                QgsDataProvider.EvaluateDefaultValues,
                False,
            )
        ):
            raise ConnectionPointContextError(
                "Liitumispunktide kihil ei hinnata serveripoolseid "
                "vaikeväärtusi."
            )

        connection = self._connection_info(point_layer)
        for node_layer in (water_node_layer, sewer_node_layer):
            if node_layer is None:
                continue
            if self._connection_info(node_layer) != connection:
                raise ConnectionPointContextError(
                    f"Kiht „{node_layer.name()}” ei kasuta liitumispunktidega "
                    "sama PostGIS-i ühendust."
                )
        group = project.transactionGroup(
            point_layer.providerType(),
            connection,
        )
        if group is None or point_layer not in group.layers():
            raise ConnectionPointContextError(
                "Liitumispunktide kiht ei kuulu automaatsesse tehingugruppi."
            )

    @staticmethod
    def _require_fields(layer: QgsVectorLayer, required: set[str]) -> None:
        actual = {field.name().upper() for field in layer.fields()}
        missing = sorted(required - actual)
        if missing:
            raise ConnectionPointContextError(
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
        table = str(layer.customProperty("evel_project_table", "")).strip()
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
