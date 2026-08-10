"""Discovery of generated EVEL layers required by the sewer manhole clock."""

from __future__ import annotations

from dataclasses import dataclass

from qgis.core import (
    Qgis,
    QgsDataProvider,
    QgsDataSourceUri,
    QgsExpression,
    QgsFeatureRequest,
    QgsMapLayer,
    QgsProject,
    QgsProviderRegistry,
    QgsVectorLayer,
    QgsVariantUtils,
)

from .duct_catalog import DuctLayerCatalog, DuctWorkflow
from .node_configuration import LookupOption


SEWER_NODE_TABLE = "sn_sewer_node"
SEWER_MANHOLE_TABLE = "sn_sewer_manhole"
SEWER_BRANCH_TABLE = "sn_sewer_branch"
SEWER_PUMPING_STATION_TABLE = "sn_sewer_pumping_station"
SEWER_PUMP_TABLE = "sn_sewer_pump"
CONSTANT_TABLE = "sn_constant"

_NODE_FIELDS = {
    "MSLINK",
    "IDENTIFICATION",
    "NETWORK_ID",
    "NETTYPE_ID",
    "Z_COORD1",
    "Z_COORD2",
    "Z_COORD3",
}
_MANHOLE_FIELDS = {
    "ID",
    "NODE_ID",
    "TYPE_ID",
    "MATERIAL_ID",
    "DIAMETER_TYPE_ID",
    "DIAMETER_ID",
    "FIRMNESS_CLASS_ID",
    "LID_TYPE_ID",
    "LID_MATERIAL_ID",
    "LID_SHAPE_ID",
    "LID_DIAMETER_ID",
    "LID_CAPACITY_ID",
    "ACCESS_DUCT_DIAM",
}
_DUCT_FIELDS = {
    "MSLINK",
    "IDENTIFICATION",
    "NETWORK_ID",
    "NETTYPE_ID",
    "MATERIAL_ID",
    "DIAMETER_ID",
    "BEGIN_NODE_ID",
    "END_NODE_ID",
    "BEGIN_Z_COORD",
    "END_Z_COORD",
    "FLOWDIRECTION",
    "LENGTH_2D",
}
_BRANCH_FIELDS = {
    "ID",
    "NODE_ID",
    "TYPE_AQUA_ID",
    "TYPE_ID",
}
_PUMPING_STATION_FIELDS = {
    "ID",
    "NODE_ID",
    "TYPE_AQUA_ID",
    "MATERIAL_ID",
    "ROLE_ID",
    "NAME",
    "PRODUCTIVITY",
    "PRESSURE_INCREASE",
    "POWER_CONSUMPTION",
    "EL_MAX_CURRENT",
    "CONTROL_ID",
    "PARCEL_NR",
    "ADDRESS_ID",
}
_PUMP_FIELDS = {
    "ID",
    "PSTATION_ID",
    "TYPE_ID",
    "INSTALL_METHOD_ID",
    "INSTALL_DATE",
    "POWER_W",
    "MANUFACTURER",
    "MARK",
    "PRODUCTIVITY",
    "PUMP_HEAD",
    "RUNNING_TIME",
    "IN_DIAMETER",
    "OUT_DIAMETER",
    "ENGINE_CURRENT",
    "ENGINE_VOLTAGE",
    "REMARKS",
}


class SewerManholeContextError(RuntimeError):
    """Raised when generated sewer layers cannot support the manhole clock."""


@dataclass(frozen=True)
class SewerManholeOptions:
    type_options: tuple[LookupOption, ...]
    material_options: tuple[LookupOption, ...]
    diameter_type_options: tuple[LookupOption, ...]
    diameter_options: tuple[LookupOption, ...]
    firmness_options: tuple[LookupOption, ...]
    lid_type_options: tuple[LookupOption, ...]
    lid_material_options: tuple[LookupOption, ...]
    lid_shape_options: tuple[LookupOption, ...]
    lid_diameter_options: tuple[LookupOption, ...]
    lid_capacity_options: tuple[LookupOption, ...]
    default_type_id: int
    branch_type_options: tuple[LookupOption, ...]
    branch_subtype_options: tuple[LookupOption, ...]
    default_branch_type_id: int
    default_branch_subtype_id: int
    connection_branch_type_id: int


@dataclass(frozen=True)
class SewerPumpingStationOptions:
    type_options: tuple[LookupOption, ...]
    material_options: tuple[LookupOption, ...]
    role_options: tuple[LookupOption, ...]
    control_options: tuple[LookupOption, ...]
    pump_type_options: tuple[LookupOption, ...]
    pump_install_method_options: tuple[LookupOption, ...]
    pump_diameter_options: tuple[float, ...]
    default_type_id: int
    default_material_id: int
    default_role_id: int
    default_control_id: int


@dataclass(frozen=True)
class SewerManholeContext:
    node_layer: QgsVectorLayer
    node_source_layers: tuple[QgsVectorLayer, ...]
    manhole_layer: QgsVectorLayer
    branch_layer: QgsVectorLayer
    constant_layer: QgsVectorLayer
    duct_layers: tuple[QgsVectorLayer, ...]
    options: SewerManholeOptions
    visible_manhole_layer: QgsVectorLayer | None = None
    visible_branch_layer: QgsVectorLayer | None = None
    pumping_station_layer: QgsVectorLayer | None = None
    visible_pumping_station_layer: QgsVectorLayer | None = None


@dataclass(frozen=True)
class SewerPumpingStationContext:
    topology_context: SewerManholeContext
    detail_layer: QgsVectorLayer
    pump_layer: QgsVectorLayer
    visible_layer: QgsVectorLayer
    options: SewerPumpingStationOptions


class SewerManholeInspector:
    """Resolve the manhole clock's layers from the generated project."""

    def discover(
        self,
        project: QgsProject,
        *,
        check_runtime: bool = True,
    ) -> SewerManholeContext:
        layers = tuple(
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
        )
        node_sources = tuple(
            layer
            for layer in layers
            if self._source_table(layer) == SEWER_NODE_TABLE
        )
        visible_manhole_layer = self._manhole_node_layer(node_sources)
        visible_branch_layer = self._branch_node_layer(node_sources)
        visible_pumping_station_layer = self._pumping_station_node_layer(
            node_sources
        )
        node_layer = self._base_node_layer(node_sources)
        if check_runtime and node_layer.readOnly():
            node_layer = self._runtime_base_node_layer(
                project,
                visible_manhole_layer,
            )
        ordered_node_sources = (
            node_layer,
            *(
                layer
                for layer in node_sources
                if layer.id() != node_layer.id()
            ),
        )
        manhole_layer = self._unique_table_layer(
            layers,
            SEWER_MANHOLE_TABLE,
        )
        branch_layer = self._unique_table_layer(
            layers,
            SEWER_BRANCH_TABLE,
        )
        pumping_station_layer = self._optional_unique_table_layer(
            layers,
            SEWER_PUMPING_STATION_TABLE,
        )
        constant_layer = self._unique_table_layer(layers, CONSTANT_TABLE)
        duct_options = tuple(
            option
            for option in DuctLayerCatalog().discover(
                project,
                check_runtime=check_runtime,
            )
            if option.workflow is DuctWorkflow.GRAVITY_GEOMETRY
            and option.enabled
        )
        if not duct_options:
            raise SewerManholeContextError(
                "Projektis puudub kasutatav isevoolse toru kiht."
            )
        duct_layers = tuple(option.layer for option in duct_options)

        self._require_fields(node_layer, _NODE_FIELDS)
        self._require_fields(manhole_layer, _MANHOLE_FIELDS)
        self._require_fields(branch_layer, _BRANCH_FIELDS)
        self._require_fields(constant_layer, {"ID", "GROUPNAME", "TXT"})
        for duct_layer in duct_layers:
            self._require_fields(duct_layer, _DUCT_FIELDS)

        type_options = self._required_options(
            project,
            manhole_layer,
            "TYPE_ID",
            constant_layer,
            "Kaevu liikide SW_MANHOLE_TYPE",
        )
        branch_type_options = self._required_options(
            project,
            branch_layer,
            "TYPE_AQUA_ID",
            constant_layer,
            "Kanalisatsiooni liitmike SW_BRANCH_TYPE",
        )
        branch_subtype_options = self._required_options(
            project,
            branch_layer,
            "TYPE_ID",
            constant_layer,
            "Kanalisatsiooni liitmike SW_BRANCH_TYPE_SUB",
        )
        connection_branch_type_id = next(
            (
                option.value
                for option in branch_type_options
                if option.label.casefold() == "ühenduskoht"
            ),
            None,
        )
        if connection_branch_type_id is None:
            raise SewerManholeContextError(
                "Kanalisatsiooni liitmike lookup-valik „Ühenduskoht“ puudub."
            )
        options = SewerManholeOptions(
            type_options=type_options,
            material_options=self._required_options(
                project,
                manhole_layer,
                "MATERIAL_ID",
                constant_layer,
                "Kaevu materjalide MANHOLE_MATERIAL",
            ),
            diameter_type_options=self._required_options(
                project,
                manhole_layer,
                "DIAMETER_TYPE_ID",
                constant_layer,
                "Läbimõõdu tüüpide DIAMETER_TYPE",
            ),
            diameter_options=self._required_options(
                project,
                manhole_layer,
                "DIAMETER_ID",
                constant_layer,
                "Kaevu läbimõõtude SW_MANHOLE_DIAMETER",
            ),
            firmness_options=self._required_options(
                project,
                manhole_layer,
                "FIRMNESS_CLASS_ID",
                constant_layer,
                "Ringjäikuse FIRMNESS_CLASS",
            ),
            lid_type_options=self._required_options(
                project,
                manhole_layer,
                "LID_TYPE_ID",
                constant_layer,
                "Kaane tüüpide LID_TYPE",
            ),
            lid_material_options=self._required_options(
                project,
                manhole_layer,
                "LID_MATERIAL_ID",
                constant_layer,
                "Kaane materjalide LID_MATERIAL",
            ),
            lid_shape_options=self._required_options(
                project,
                manhole_layer,
                "LID_SHAPE_ID",
                constant_layer,
                "Kaane kujude LID_SHAPE",
            ),
            lid_diameter_options=self._required_options(
                project,
                manhole_layer,
                "LID_DIAMETER_ID",
                constant_layer,
                "Kaane läbimõõtude LID_DIAMETER",
            ),
            lid_capacity_options=self._required_options(
                project,
                manhole_layer,
                "LID_CAPACITY_ID",
                constant_layer,
                "Kaane kandevõime LID_CAPACITY",
            ),
            default_type_id=self._integer_default(
                manhole_layer,
                "TYPE_ID",
            ),
            branch_type_options=branch_type_options,
            branch_subtype_options=branch_subtype_options,
            default_branch_type_id=self._integer_default(
                branch_layer,
                "TYPE_AQUA_ID",
            ),
            default_branch_subtype_id=self._integer_default(
                branch_layer,
                "TYPE_ID",
            ),
            connection_branch_type_id=connection_branch_type_id,
        )

        if check_runtime:
            self._validate_runtime(
                project,
                node_layer,
                manhole_layer,
                branch_layer,
                duct_layers,
            )
        return SewerManholeContext(
            node_layer=node_layer,
            node_source_layers=ordered_node_sources,
            manhole_layer=manhole_layer,
            branch_layer=branch_layer,
            constant_layer=constant_layer,
            duct_layers=duct_layers,
            options=options,
            visible_manhole_layer=visible_manhole_layer,
            visible_branch_layer=visible_branch_layer,
            pumping_station_layer=pumping_station_layer,
            visible_pumping_station_layer=visible_pumping_station_layer,
        )

    def is_available(self, project: QgsProject) -> bool:
        """Cheap structural readiness check for the toolbar action."""

        layers = tuple(
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
        )
        tables = [self._source_table(layer) for layer in layers]
        node_token = f'"evel"."{SEWER_MANHOLE_TABLE}"'.casefold()
        has_manhole_node = any(
            table == SEWER_NODE_TABLE
            and node_token in layer.subsetString().casefold()
            for layer, table in zip(layers, tables)
        )
        has_base_node = any(
            table == SEWER_NODE_TABLE
            and not layer.vectorJoins()
            for layer, table in zip(layers, tables)
        )
        return (
            has_manhole_node
            and has_base_node
            and tables.count(SEWER_MANHOLE_TABLE) == 1
            and tables.count(SEWER_BRANCH_TABLE) == 1
            and tables.count(CONSTANT_TABLE) == 1
            and any(
                table == "sn_sewer_duct"
                and layer.geometryType() == Qgis.GeometryType.Line
                for layer, table in zip(layers, tables)
            )
        )

    def _manhole_node_layer(
        self,
        node_layers: tuple[QgsVectorLayer, ...],
    ) -> QgsVectorLayer:
        token = f'"evel"."{SEWER_MANHOLE_TABLE}"'.casefold()
        matches = [
            layer
            for layer in node_layers
            if token in layer.subsetString().casefold()
        ]
        if len(matches) != 1:
            raise SewerManholeContextError(
                "Projektis peab olema täpselt üks generaatori Kaevud kiht "
                f"(leiti {len(matches)})."
            )
        layer = matches[0]
        if not layer.isValid():
            raise SewerManholeContextError(
                "Kanalisatsiooni Kaevud kiht ei ole kasutatav."
            )
        return layer

    def _branch_node_layer(
        self,
        node_layers: tuple[QgsVectorLayer, ...],
    ) -> QgsVectorLayer | None:
        """Return the generated visible sewer connection layer when present."""

        token = f'"evel"."{SEWER_BRANCH_TABLE}"'.casefold()
        matches = [
            layer
            for layer in node_layers
            if token in layer.subsetString().casefold()
        ]
        if len(matches) > 1:
            raise SewerManholeContextError(
                "Projektis on mitu generaatori kanalisatsiooni Liitmikud "
                f"kihti (leiti {len(matches)})."
            )
        if not matches:
            return None
        layer = matches[0]
        if not layer.isValid():
            raise SewerManholeContextError(
                "Kanalisatsiooni Liitmikud kiht ei ole kasutatav."
            )
        return layer

    def _pumping_station_node_layer(
        self,
        node_layers: tuple[QgsVectorLayer, ...],
    ) -> QgsVectorLayer | None:
        """Return the generated visible sewer pumping-station layer."""

        token = f'"evel"."{SEWER_PUMPING_STATION_TABLE}"'.casefold()
        matches = [
            layer
            for layer in node_layers
            if token in layer.subsetString().casefold()
        ]
        if len(matches) > 1:
            raise SewerManholeContextError(
                "Projektis on mitu generaatori kanalisatsiooni Pumplad "
                f"kihti (leiti {len(matches)})."
            )
        if not matches:
            return None
        layer = matches[0]
        if not layer.isValid():
            raise SewerManholeContextError(
                "Kanalisatsiooni Pumplad kiht ei ole kasutatav."
            )
        return layer

    def _base_node_layer(
        self,
        node_layers: tuple[QgsVectorLayer, ...],
    ) -> QgsVectorLayer:
        explicit = [
            layer
            for layer in node_layers
            if str(
                layer.customProperty("evel_topology_role", "")
            ).strip().casefold()
            == "sewer_node"
        ]
        if len(explicit) > 1:
            raise SewerManholeContextError(
                "Projektis on mitu sewer_node rolliga kanalisatsiooni "
                "baassõlmekihti."
            )
        candidates = explicit or [
            layer
            for layer in node_layers
            if not layer.vectorJoins()
        ]
        unfiltered = [
            layer
            for layer in candidates
            if not layer.subsetString().strip()
        ]
        if len(unfiltered) == 1:
            layer = unfiltered[0]
        elif len(candidates) == 1:
            layer = candidates[0]
        else:
            raise SewerManholeContextError(
                "Projektis peab olema üks join'ita kanalisatsiooni "
                f"baassõlmekiht; leiti {len(candidates)}."
            )
        if not layer.isValid():
            raise SewerManholeContextError(
                "Kanalisatsiooni baassõlmekiht ei ole kasutatav."
            )
        return layer

    def _runtime_base_node_layer(
        self,
        project: QgsProject,
        source_layer: QgsVectorLayer,
    ) -> QgsVectorLayer:
        existing = [
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
            and self._source_table(layer) == SEWER_NODE_TABLE
            and str(
                layer.customProperty("evel_topology_role", "")
            ).strip().casefold()
            == "sewer_node"
            and not layer.vectorJoins()
        ]
        if len(existing) == 1:
            return existing[0]
        if len(existing) > 1:
            raise SewerManholeContextError(
                "Projektis on mitu privaatset kanalisatsiooni "
                "baassõlmekihti."
            )

        uri = QgsDataSourceUri(source_layer.source())
        uri.setSql("")
        layer = QgsVectorLayer(
            uri.uri(False),
            "EVEL kanalisatsioonisõlmede baaskiht",
            "postgres",
        )
        if not layer.isValid():
            raise SewerManholeContextError(
                "Kirjutatavat kanalisatsiooni baassõlmekihti ei "
                "õnnestunud PostGIS-i allikast avada."
            )
        layer.setCustomProperty("evel_project_table", SEWER_NODE_TABLE)
        layer.setCustomProperty("evel_topology_role", "sewer_node")
        layer.setCustomProperty("evel_runtime_private_layer", True)
        layer.setFlags(layer.flags() | QgsMapLayer.LayerFlag.Private)
        provider = layer.dataProvider()
        if provider is not None:
            provider.setProviderProperty(
                QgsDataProvider.EvaluateDefaultValues,
                True,
            )
        was_dirty = project.isDirty()
        project.addMapLayer(layer, False)
        if not was_dirty:
            project.setDirty(False)
        return layer

    def _required_options(
        self,
        project: QgsProject,
        layer: QgsVectorLayer,
        field_name: str,
        fallback_layer: QgsVectorLayer,
        label: str,
    ) -> tuple[LookupOption, ...]:
        field_index = layer.fields().lookupField(field_name)
        if field_index < 0:
            raise SewerManholeContextError(
                f"Kihil „{layer.name()}“ puudub väli {field_name}."
            )
        setup = layer.editorWidgetSetup(field_index)
        config = setup.config()
        lookup_layer = project.mapLayer(str(config.get("Layer", "")))
        if not isinstance(lookup_layer, QgsVectorLayer):
            lookup_layer = fallback_layer

        key_name = str(config.get("Key", "ID"))
        value_name = str(config.get("Value", "TXT"))
        request = QgsFeatureRequest()
        filter_expression = str(
            config.get("FilterExpression", "")
        ).strip()
        if filter_expression:
            request.setFilterExpression(filter_expression)

        options: list[LookupOption] = []
        for feature in lookup_layer.getFeatures(request):
            raw_value = feature[key_name]
            if QgsVariantUtils.isNull(raw_value):
                continue
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                continue
            options.append(LookupOption(value, str(feature[value_name])))
        options.sort(key=lambda item: (item.label.casefold(), item.value))
        if not options:
            raise SewerManholeContextError(
                f"{label} lookup-väärtused puuduvad."
            )
        return tuple(options)

    def _validate_runtime(
        self,
        project: QgsProject,
        node_layer: QgsVectorLayer,
        manhole_layer: QgsVectorLayer,
        branch_layer: QgsVectorLayer,
        duct_layers: tuple[QgsVectorLayer, ...],
    ) -> None:
        edit_layers = (
            node_layer,
            manhole_layer,
            branch_layer,
            *duct_layers,
        )
        base_connection = self._connection_info(node_layer)
        if not base_connection:
            raise SewerManholeContextError(
                "Kaevukihi PostGIS-i ühendust ei õnnestunud tuvastada."
            )
        for layer in edit_layers:
            if layer.providerType() != "postgres":
                raise SewerManholeContextError(
                    f"Kiht „{layer.name()}“ ei kasuta PostGIS-i."
                )
            if layer.readOnly():
                raise SewerManholeContextError(
                    f"Kiht „{layer.name()}“ on kirjutuskaitstud."
                )
            if self._connection_info(layer) != base_connection:
                raise SewerManholeContextError(
                    "Kaevu-, sõlme- ja torukihid ei kasuta sama "
                    "PostGIS-i ühendust."
                )
            provider = layer.dataProvider()
            required = Qgis.VectorProviderCapability.AddFeatures
            required |= Qgis.VectorProviderCapability.ChangeAttributeValues
            if layer in duct_layers:
                required |= Qgis.VectorProviderCapability.ChangeGeometries
            if provider is None or provider.capabilities() & required != required:
                raise SewerManholeContextError(
                    f"Kihil „{layer.name()}“ puuduvad vajalikud "
                    "redigeerimisõigused."
                )
            if not bool(
                provider.providerProperty(
                    QgsDataProvider.EvaluateDefaultValues,
                    False,
                )
            ):
                raise SewerManholeContextError(
                    f"Kihil „{layer.name()}“ on serveri vaikeväärtuste "
                    "hindamine välja lülitatud."
                )
        if project.transactionMode() != Qgis.TransactionMode.AutomaticGroups:
            raise SewerManholeContextError(
                "Projekti tehingurežiim peab olema Automatic Transaction Groups."
            )

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
            raise SewerManholeContextError(
                f"Projektis peab olema täpselt üks evel.{table_name} kiht; "
                f"leiti {len(matches)}."
            )
        if not matches[0].isValid():
            raise SewerManholeContextError(
                f"Kiht evel.{table_name} ei ole kasutatav."
            )
        return matches[0]

    def _optional_unique_table_layer(
        self,
        layers: tuple[QgsVectorLayer, ...],
        table_name: str,
    ) -> QgsVectorLayer | None:
        matches = [
            layer
            for layer in layers
            if self._source_table(layer) == table_name
        ]
        if len(matches) > 1:
            raise SewerManholeContextError(
                f"Projektis on mitu evel.{table_name} kihti; "
                f"leiti {len(matches)}."
            )
        if not matches:
            return None
        if not matches[0].isValid():
            raise SewerManholeContextError(
                f"Kiht evel.{table_name} ei ole kasutatav."
            )
        return matches[0]

    @staticmethod
    def _require_fields(
        layer: QgsVectorLayer,
        required: set[str],
    ) -> None:
        actual = {field.name().upper() for field in layer.fields()}
        missing = sorted(required - actual)
        if missing:
            raise SewerManholeContextError(
                f"Kihil „{layer.name()}“ puuduvad väljad: "
                f"{', '.join(missing)}."
            )

    @staticmethod
    def _integer_default(
        layer: QgsVectorLayer,
        field_name: str,
    ) -> int:
        index = layer.fields().lookupField(field_name)
        expression = layer.defaultValueDefinition(index).expression().strip()
        try:
            return int(expression.strip("'\""))
        except (TypeError, ValueError) as error:
            raise SewerManholeContextError(
                f"Kihi „{layer.name()}“ välja {field_name} vaikeväärtus "
                "ei ole täisarv."
            ) from error

    @staticmethod
    def _source_table(layer: QgsVectorLayer) -> str:
        metadata = str(
            layer.customProperty("evel_project_table", "")
        ).strip()
        if metadata:
            return metadata.casefold()
        try:
            decoded = QgsProviderRegistry.instance().decodeUri(
                layer.providerType(),
                layer.source(),
            )
        except (AttributeError, TypeError, ValueError):
            return ""
        return str(decoded.get("table", "")).casefold()

    @staticmethod
    def _connection_info(layer: QgsVectorLayer) -> str:
        if layer.providerType() != "postgres":
            return ""
        try:
            return QgsDataSourceUri(layer.source()).connectionInfo(False)
        except (TypeError, ValueError):
            return ""


class SewerPumpingStationInspector:
    """Resolve the dedicated sewer pumping-station project contract."""

    def discover(
        self,
        project: QgsProject,
        *,
        check_runtime: bool = True,
    ) -> SewerPumpingStationContext:
        inspector = SewerManholeInspector()
        topology_context = inspector.discover(
            project,
            check_runtime=check_runtime,
        )
        detail_layer = topology_context.pumping_station_layer
        visible_layer = topology_context.visible_pumping_station_layer
        if detail_layer is None:
            raise SewerManholeContextError(
                "Projektis puudub evel.sn_sewer_pumping_station detailkiht."
            )
        if visible_layer is None:
            raise SewerManholeContextError(
                "Projektis puudub generaatori nähtav Pumplad kiht."
            )

        inspector._require_fields(detail_layer, _PUMPING_STATION_FIELDS)
        pump_layer = self._runtime_pump_layer(project, detail_layer)
        inspector._require_fields(pump_layer, _PUMP_FIELDS)
        options = SewerPumpingStationOptions(
            type_options=inspector._required_options(
                project,
                detail_layer,
                "TYPE_AQUA_ID",
                topology_context.constant_layer,
                "Pumpla liikide SW_PS_TYPE",
            ),
            material_options=inspector._required_options(
                project,
                detail_layer,
                "MATERIAL_ID",
                topology_context.constant_layer,
                "Pumpla materjalide PS_MATERIAL",
            ),
            role_options=inspector._required_options(
                project,
                detail_layer,
                "ROLE_ID",
                topology_context.constant_layer,
                "Pumpla rollide SW_PS_ROLE",
            ),
            control_options=inspector._required_options(
                project,
                detail_layer,
                "CONTROL_ID",
                topology_context.constant_layer,
                "Pumpla juhtimisviiside SW_PS_CONTROL",
            ),
            pump_type_options=self._constant_group_options(
                topology_context.constant_layer,
                "SW_PUMP_TYPE",
                "Kanalisatsioonipumba tüüpide SW_PUMP_TYPE",
            ),
            pump_install_method_options=self._constant_group_options(
                topology_context.constant_layer,
                "PUMP_INSTALL_METHOD",
                "Pumba paigaldusviiside PUMP_INSTALL_METHOD",
            ),
            pump_diameter_options=self._numeric_constant_group_values(
                topology_context.constant_layer,
                "SW_DUCT_DIAMETER",
                "Kanalisatsioonitorude läbimõõtude SW_DUCT_DIAMETER",
            ),
            default_type_id=inspector._integer_default(
                detail_layer,
                "TYPE_AQUA_ID",
            ),
            default_material_id=inspector._integer_default(
                detail_layer,
                "MATERIAL_ID",
            ),
            default_role_id=inspector._integer_default(
                detail_layer,
                "ROLE_ID",
            ),
            default_control_id=inspector._integer_default(
                detail_layer,
                "CONTROL_ID",
            ),
        )
        if check_runtime:
            self._validate_runtime(
                topology_context,
                detail_layer,
                pump_layer,
            )
        return SewerPumpingStationContext(
            topology_context=topology_context,
            detail_layer=detail_layer,
            pump_layer=pump_layer,
            visible_layer=visible_layer,
            options=options,
        )

    @staticmethod
    def _constant_group_options(
        constant_layer: QgsVectorLayer,
        group_name: str,
        label: str,
    ) -> tuple[LookupOption, ...]:
        request = QgsFeatureRequest().setFilterExpression(
            '"GROUPNAME" = '
            + QgsExpression.quotedValue(group_name)
        )
        options: list[LookupOption] = []
        for feature in constant_layer.getFeatures(request):
            raw_value = feature["ID"]
            if QgsVariantUtils.isNull(raw_value):
                continue
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                continue
            options.append(LookupOption(value, str(feature["TXT"]).strip()))
        options.sort(key=lambda item: (item.label.casefold(), item.value))
        if not options:
            raise SewerManholeContextError(
                f"{label} lookup-väärtused puuduvad."
            )
        return tuple(options)

    @classmethod
    def _numeric_constant_group_values(
        cls,
        constant_layer: QgsVectorLayer,
        group_name: str,
        label: str,
    ) -> tuple[float, ...]:
        options = cls._constant_group_options(
            constant_layer,
            group_name,
            label,
        )
        values: set[float] = set()
        for option in options:
            text = option.label.strip().replace(",", ".")
            try:
                value = float(text)
            except ValueError as error:
                raise SewerManholeContextError(
                    f"{label} sisaldab mittearvulist väärtust "
                    f"„{option.label}“."
                ) from error
            if value <= 0:
                raise SewerManholeContextError(
                    f"{label} sisaldab sobimatut väärtust "
                    f"„{option.label}“."
                )
            values.add(value)
        return tuple(sorted(values))

    @staticmethod
    def _runtime_pump_layer(
        project: QgsProject,
        detail_layer: QgsVectorLayer,
    ) -> QgsVectorLayer:
        inspector = SewerManholeInspector()
        existing = [
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
            and inspector._source_table(layer) == SEWER_PUMP_TABLE
        ]
        if len(existing) > 1:
            raise SewerManholeContextError(
                "Projektis on mitu evel.sn_sewer_pump tehnilist kihti."
            )
        if existing:
            layer = existing[0]
        else:
            decoded = QgsProviderRegistry.instance().decodeUri(
                detail_layer.providerType(),
                detail_layer.source(),
            )
            schema = str(decoded.get("schema", "")).strip() or "evel"
            uri = QgsDataSourceUri(detail_layer.source())
            uri.setDataSource(schema, SEWER_PUMP_TABLE, "", "", "ID")
            uri.setSql("")
            layer = QgsVectorLayer(
                uri.uri(False),
                "EVEL kanalisatsioonipumbad (tehniline)",
                "postgres",
            )
            if not layer.isValid():
                raise SewerManholeContextError(
                    "EVEL-i kanalisatsioonipumpade tabelit "
                    "evel.sn_sewer_pump ei õnnestunud avada."
                )
            layer.setCustomProperty("evel_project_table", SEWER_PUMP_TABLE)
            layer.setCustomProperty("evel_topology_role", "sewer_pump")
            layer.setCustomProperty("evel_runtime_private_layer", True)
            layer.setFlags(layer.flags() | QgsMapLayer.LayerFlag.Private)
            was_dirty = project.isDirty()
            project.addMapLayer(layer, False)
            if not was_dirty:
                project.setDirty(False)

        provider = layer.dataProvider()
        if provider is not None:
            provider.setProviderProperty(
                QgsDataProvider.EvaluateDefaultValues,
                True,
            )
        return layer

    def is_available(self, project: QgsProject) -> bool:
        inspector = SewerManholeInspector()
        if not inspector.is_available(project):
            return False
        layers = tuple(
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
        )
        detail_count = sum(
            inspector._source_table(layer) == SEWER_PUMPING_STATION_TABLE
            for layer in layers
        )
        token = f'"evel"."{SEWER_PUMPING_STATION_TABLE}"'.casefold()
        has_visible_layer = any(
            inspector._source_table(layer) == SEWER_NODE_TABLE
            and token in layer.subsetString().casefold()
            for layer in layers
        )
        if detail_count != 1 or not has_visible_layer:
            return False
        detail_layer = next(
            layer
            for layer in layers
            if inspector._source_table(layer) == SEWER_PUMPING_STATION_TABLE
        )
        try:
            return self._runtime_pump_layer(
                project,
                detail_layer,
            ).isValid()
        except SewerManholeContextError:
            return False

    @staticmethod
    def _validate_runtime(
        topology_context: SewerManholeContext,
        detail_layer: QgsVectorLayer,
        pump_layer: QgsVectorLayer,
    ) -> None:
        node_layer = topology_context.node_layer
        if detail_layer.providerType() != "postgres":
            raise SewerManholeContextError(
                "Kanalisatsiooni Pumplad detailkiht ei kasuta PostGIS-i."
            )
        if detail_layer.readOnly():
            raise SewerManholeContextError(
                "Kanalisatsiooni Pumplad detailkiht on kirjutuskaitstud."
            )
        if (
            SewerManholeInspector._connection_info(detail_layer)
            != SewerManholeInspector._connection_info(node_layer)
        ):
            raise SewerManholeContextError(
                "Pumpla detail- ja kanalisatsioonisõlme kiht ei kasuta "
                "sama PostGIS-i ühendust."
            )
        if pump_layer.providerType() != "postgres":
            raise SewerManholeContextError(
                "Kanalisatsioonipumpade tehniline kiht ei kasuta PostGIS-i."
            )
        if pump_layer.readOnly():
            raise SewerManholeContextError(
                "Kanalisatsioonipumpade tehniline kiht on kirjutuskaitstud."
            )
        if (
            SewerManholeInspector._connection_info(pump_layer)
            != SewerManholeInspector._connection_info(node_layer)
        ):
            raise SewerManholeContextError(
                "Pumpla ja pumpade tabelid ei kasuta sama PostGIS-i "
                "ühendust."
            )
        for layer, label, allow_delete in (
            (detail_layer, "Pumplad detailkihil", False),
            (pump_layer, "kanalisatsioonipumpade tehnilisel kihil", True),
        ):
            provider = layer.dataProvider()
            required = Qgis.VectorProviderCapability.AddFeatures
            required |= Qgis.VectorProviderCapability.ChangeAttributeValues
            if allow_delete:
                required |= Qgis.VectorProviderCapability.DeleteFeatures
            if (
                provider is None
                or provider.capabilities() & required != required
            ):
                raise SewerManholeContextError(
                    f"{label.capitalize()} puuduvad vajalikud "
                    "redigeerimisõigused."
                )
            if not bool(
                provider.providerProperty(
                    QgsDataProvider.EvaluateDefaultValues,
                    False,
                )
            ):
                raise SewerManholeContextError(
                    f"{label.capitalize()} on serveri vaikeväärtuste "
                    "hindamine välja lülitatud."
                )
