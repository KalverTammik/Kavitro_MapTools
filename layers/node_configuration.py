"""Discovery of generated layers needed by the node assembly configurator."""

from __future__ import annotations

from dataclasses import dataclass

from qgis.core import (
    Qgis,
    QgsDataSourceUri,
    QgsFeatureRequest,
    QgsProject,
    QgsProviderRegistry,
    QgsVectorLayer,
    QgsVariantUtils,
)

from .project_inspector import ProjectInspection


BRANCH_TABLE = "sn_water_branch"
VALVE_TABLE = "sn_water_valve"
MANHOLE_TABLE = "sn_water_manhole"
FACILITY_TABLE = "sn_water_pumping_station"
CONSTANT_TABLE = "sn_constant"

_MANHOLE_FIELDS = {
    "ID",
    "NODE_ID",
    "TYPE_ID",
    "MATERIAL_ID",
    "DIAMETER_TYPE_ID",
    "DIAMETER_ID",
    "FIRMNESS_CLASS_ID",
    "ANCHOR_PLATE",
    "LOAD_LEVELING_PLATE",
    "LID_TYPE_ID",
    "LID_MATERIAL_ID",
    "LID_SHAPE_ID",
    "LID_DIAMETER_ID",
    "LID_CAPACITY_ID",
    "LID_INSULATION",
    "ACCESS_DUCT_DIAM",
}

_FACILITY_FIELDS = {
    "ID",
    "NODE_ID",
    "MATERIAL_ID",
    "ROLE_ID",
    "PRODUCTIVITY",
    "PRESSURE_INCREASE",
    "P_REG_CODE",
    "P_PASPORT_NR",
    "P_DEPTH",
    "WATER_TYPE_ID",
    "WATER_SOURCE_ID",
    "WIPEOUT_DATE",
    "RENEWAL_DATE",
    "IS_CONTROLLED",
    "IS_SIGNALISATION",
    "PROTECTION_ZONE",
    "MANTLE_DIAM",
}


class NodeConfigurationContextError(RuntimeError):
    """Raised when generated detail or lookup layers are unavailable."""


@dataclass(frozen=True)
class LookupOption:
    value: int
    label: str


@dataclass(frozen=True)
class ManholeConfigurationOptions:
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


@dataclass(frozen=True)
class FacilityVariant:
    """One generated presentation of an SN_WATER_PUMPING_STATION detail."""

    key: str
    label: str
    network_id: int
    role_id: int
    water_type_id: int
    detail_layer: QgsVectorLayer
    visible_layer: QgsVectorLayer
    default_material_id: int | None
    default_water_source_id: int | None


@dataclass(frozen=True)
class FacilityConfigurationOptions:
    variants: tuple[FacilityVariant, ...]
    material_options: tuple[LookupOption, ...]
    water_source_options: tuple[LookupOption, ...]


@dataclass(frozen=True)
class NodeConfigurationContext:
    edge_layer: QgsVectorLayer
    node_layer: QgsVectorLayer
    branch_detail_layer: QgsVectorLayer
    valve_detail_layer: QgsVectorLayer
    manhole_detail_layer: QgsVectorLayer
    constant_layer: QgsVectorLayer
    branch_options: tuple[LookupOption, ...]
    valve_options: tuple[LookupOption, ...]
    valve_subtype_options: tuple[LookupOption, ...]
    valve_default_type_id: int
    valve_default_subtype_id: int
    manhole_options: ManholeConfigurationOptions
    visible_branch_layer: QgsVectorLayer | None = None
    visible_valve_layer: QgsVectorLayer | None = None
    visible_manhole_layer: QgsVectorLayer | None = None
    facility_options: FacilityConfigurationOptions | None = None


class NodeConfigurationInspector:
    """Resolve configurator layers from the generated QGIS project."""

    def discover(
        self,
        project: QgsProject,
        inspection: ProjectInspection,
    ) -> NodeConfigurationContext:
        if not inspection.can_add_water_duct:
            raise NodeConfigurationContextError(
                "Veetoru projekti käivitusdiagnostika ei ole edukas."
            )
        edge_layer = inspection.edge_layer
        node_layer = inspection.node_layer
        if edge_layer is None or node_layer is None:
            raise NodeConfigurationContextError(
                "Toru- või veesõlmede baaskiht puudub."
            )
        self._require_fields(node_layer, {"PNT_ROTATION"})

        layers = [
            layer
            for layer in project.mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
        ]
        branch_detail = self._unique_table_layer(layers, BRANCH_TABLE)
        valve_detail = self._unique_table_layer(layers, VALVE_TABLE)
        manhole_detail = self._unique_table_layer(layers, MANHOLE_TABLE)
        constant_layer = self._unique_table_layer(layers, CONSTANT_TABLE)
        facility_variants = self._facility_variants(project, layers)
        self._require_fields(
            branch_detail, {"ID", "NODE_ID", "TYPE_AQUA_ID"}
        )
        self._require_fields(
            valve_detail, {"ID", "NODE_ID", "TYPE_AQUA_ID", "TYPE_ID"}
        )
        self._require_fields(manhole_detail, _MANHOLE_FIELDS)
        self._require_fields(
            constant_layer, {"ID", "GROUPNAME", "TXT"}
        )
        self._validate_edit_layers(
            project,
            edge_layer,
            node_layer,
            branch_detail,
            valve_detail,
            manhole_detail,
            tuple(
                self._unique_layers(
                    variant.detail_layer for variant in facility_variants
                )
            ),
        )

        branch_options = self._value_relation_options(
            project,
            branch_detail,
            "TYPE_AQUA_ID",
            constant_layer,
        )
        valve_options = self._value_relation_options(
            project,
            valve_detail,
            "TYPE_AQUA_ID",
            constant_layer,
        )
        valve_subtype_options = self._value_relation_options(
            project,
            valve_detail,
            "TYPE_ID",
            constant_layer,
        )
        if not branch_options:
            raise NodeConfigurationContextError(
                "Liitmiku tüüpide W_BRANCH_TYPE lookup-väärtused puuduvad."
            )
        if not valve_options:
            raise NodeConfigurationContextError(
                "Sulgeseadme tüüpide W_VALVE_TYPE lookup-väärtused puuduvad."
            )
        if not valve_subtype_options:
            raise NodeConfigurationContextError(
                "Sulgeseadme alamtüüpide W_VALVE_TYPE_SUB "
                "lookup-väärtused puuduvad."
            )
        valve_default_type_id = self._lookup_default(
            valve_detail,
            "TYPE_AQUA_ID",
            valve_options,
        )
        valve_default_subtype_id = self._lookup_default(
            valve_detail,
            "TYPE_ID",
            valve_subtype_options,
        )
        manhole_type_options = self._required_options(
            project,
            manhole_detail,
            "TYPE_ID",
            constant_layer,
            "Kaevu liikide W_MANHOLE_TYPE",
        )
        manhole_options = ManholeConfigurationOptions(
            type_options=manhole_type_options,
            material_options=self._required_options(
                project,
                manhole_detail,
                "MATERIAL_ID",
                constant_layer,
                "Kaevu materjalide MANHOLE_MATERIAL",
            ),
            diameter_type_options=self._required_options(
                project,
                manhole_detail,
                "DIAMETER_TYPE_ID",
                constant_layer,
                "Läbimõõdu tüüpide DIAMETER_TYPE",
            ),
            diameter_options=self._required_options(
                project,
                manhole_detail,
                "DIAMETER_ID",
                constant_layer,
                "Kaevu läbimõõtude W_MANHOLE_DIAMETER",
            ),
            firmness_options=self._required_options(
                project,
                manhole_detail,
                "FIRMNESS_CLASS_ID",
                constant_layer,
                "Ringjäikuse FIRMNESS_CLASS",
            ),
            lid_type_options=self._required_options(
                project,
                manhole_detail,
                "LID_TYPE_ID",
                constant_layer,
                "Kaane tüüpide LID_TYPE",
            ),
            lid_material_options=self._required_options(
                project,
                manhole_detail,
                "LID_MATERIAL_ID",
                constant_layer,
                "Kaane materjalide LID_MATERIAL",
            ),
            lid_shape_options=self._required_options(
                project,
                manhole_detail,
                "LID_SHAPE_ID",
                constant_layer,
                "Kaane kujude LID_SHAPE",
            ),
            lid_diameter_options=self._required_options(
                project,
                manhole_detail,
                "LID_DIAMETER_ID",
                constant_layer,
                "Kaane läbimõõtude LID_DIAMETER",
            ),
            lid_capacity_options=self._required_options(
                project,
                manhole_detail,
                "LID_CAPACITY_ID",
                constant_layer,
                "Kaane kandevõime LID_CAPACITY",
            ),
            default_type_id=self._lookup_default(
                manhole_detail,
                "TYPE_ID",
                manhole_type_options,
            ),
        )
        facility_options = None
        if facility_variants:
            facility_lookup_layer = facility_variants[0].detail_layer
            facility_options = FacilityConfigurationOptions(
                variants=facility_variants,
                material_options=self._required_options(
                    project,
                    facility_lookup_layer,
                    "MATERIAL_ID",
                    constant_layer,
                    "Rajatise materjalide PS_MATERIAL",
                ),
                water_source_options=self._required_options(
                    project,
                    facility_lookup_layer,
                    "WATER_SOURCE_ID",
                    constant_layer,
                    "Veeallikate PS_WATER_SOURCE",
                ),
            )

        return NodeConfigurationContext(
            edge_layer=edge_layer,
            node_layer=node_layer,
            branch_detail_layer=branch_detail,
            valve_detail_layer=valve_detail,
            manhole_detail_layer=manhole_detail,
            constant_layer=constant_layer,
            branch_options=branch_options,
            valve_options=valve_options,
            valve_subtype_options=valve_subtype_options,
            valve_default_type_id=valve_default_type_id,
            valve_default_subtype_id=valve_default_subtype_id,
            manhole_options=manhole_options,
            visible_branch_layer=self._visible_node_layer(
                layers, BRANCH_TABLE
            ),
            visible_valve_layer=self._visible_node_layer(
                layers, VALVE_TABLE
            ),
            visible_manhole_layer=self._visible_node_layer(
                layers, MANHOLE_TABLE
            ),
            facility_options=facility_options,
        )

    def _facility_variants(
        self,
        project: QgsProject,
        layers: list[QgsVectorLayer],
    ) -> tuple[FacilityVariant, ...]:
        """Discover filtered facility detail layers through their relations."""

        detail_layers = [
            layer
            for layer in layers
            if self._source_table(layer) == FACILITY_TABLE
        ]
        if not detail_layers:
            return ()

        relations = tuple(project.relationManager().relations().values())
        variants: list[FacilityVariant] = []
        seen_keys: set[str] = set()
        for detail_layer in detail_layers:
            if not detail_layer.isValid():
                raise NodeConfigurationContextError(
                    f"Rajatiste detailkiht „{detail_layer.name()}“ ei ole "
                    "kasutatav."
                )
            self._require_fields(detail_layer, _FACILITY_FIELDS)
            matches = [
                relation
                for relation in relations
                if relation.referencingLayer() is detail_layer
                and isinstance(relation.referencedLayer(), QgsVectorLayer)
                and self._source_table(relation.referencedLayer())
                == "sn_water_node"
                and relation.fieldPairs().get("NODE_ID") == "MSLINK"
            ]
            if len(matches) != 1:
                raise NodeConfigurationContextError(
                    f"Rajatiste detailkihil „{detail_layer.name()}“ peab olema "
                    "täpselt üks NODE_ID → MSLINK seos veesõlmekihiga."
                )
            visible_layer = matches[0].referencedLayer()
            network_id = self._integer_default(
                visible_layer,
                "NETWORK_ID",
                "rajatise sõlmevõrk",
            )
            role_id = self._integer_default(
                detail_layer,
                "ROLE_ID",
                "rajatise roll",
            )
            water_type_id = self._integer_default(
                detail_layer,
                "WATER_TYPE_ID",
                "rajatise veeliik",
            )
            key = f"{network_id}:{role_id}:{water_type_id}"
            if key in seen_keys:
                raise NodeConfigurationContextError(
                    "Projektis on mitu sama tehnilise määratlusega rajatise "
                    f"varianti ({key})."
                )
            seen_keys.add(key)
            label = str(
                detail_layer.customProperty("evel_component_name", "")
            ).strip()
            if not label:
                label = str(
                    visible_layer.customProperty(
                        "evel_preview_component",
                        visible_layer.name(),
                    )
                ).strip()
            variants.append(
                FacilityVariant(
                    key=key,
                    label=label or visible_layer.name(),
                    network_id=network_id,
                    role_id=role_id,
                    water_type_id=water_type_id,
                    detail_layer=detail_layer,
                    visible_layer=visible_layer,
                    default_material_id=self._optional_integer_default(
                        detail_layer,
                        "MATERIAL_ID",
                    ),
                    default_water_source_id=self._optional_integer_default(
                        detail_layer,
                        "WATER_SOURCE_ID",
                    ),
                )
            )
        variants.sort(key=lambda item: (item.network_id, item.label.casefold()))
        return tuple(variants)

    def _required_options(
        self,
        project: QgsProject,
        detail_layer: QgsVectorLayer,
        field_name: str,
        fallback_layer: QgsVectorLayer,
        label: str,
    ) -> tuple[LookupOption, ...]:
        options = self._value_relation_options(
            project,
            detail_layer,
            field_name,
            fallback_layer,
        )
        if not options:
            raise NodeConfigurationContextError(
                f"{label} lookup-väärtused puuduvad."
            )
        return options

    def _unique_table_layer(
        self,
        layers: list[QgsVectorLayer],
        table_name: str,
    ) -> QgsVectorLayer:
        matches = [
            layer
            for layer in layers
            if self._source_table(layer) == table_name
        ]
        if len(matches) != 1:
            raise NodeConfigurationContextError(
                f"Projektis peab olema täpselt üks evel.{table_name} kiht; "
                f"leiti {len(matches)}."
            )
        layer = matches[0]
        if not layer.isValid():
            raise NodeConfigurationContextError(
                f"Kiht evel.{table_name} ei ole kasutatav."
            )
        return layer

    def _value_relation_options(
        self,
        project: QgsProject,
        detail_layer: QgsVectorLayer,
        field_name: str,
        fallback_layer: QgsVectorLayer,
    ) -> tuple[LookupOption, ...]:
        field_index = detail_layer.fields().lookupField(field_name)
        if field_index < 0:
            return ()
        setup = detail_layer.editorWidgetSetup(field_index)
        config = setup.config()
        lookup_layer = project.mapLayer(str(config.get("Layer", "")))
        if not isinstance(lookup_layer, QgsVectorLayer):
            lookup_layer = fallback_layer

        key_name = str(config.get("Key", "ID"))
        value_name = str(config.get("Value", "TXT"))
        filter_expression = str(config.get("FilterExpression", "")).strip()
        request = QgsFeatureRequest()
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
        return tuple(options)

    def _visible_node_layer(
        self,
        layers: list[QgsVectorLayer],
        detail_table: str,
    ) -> QgsVectorLayer | None:
        token = f'"evel"."{detail_table}"'.lower()
        for layer in layers:
            if self._source_table(layer) != "sn_water_node":
                continue
            if token in layer.subsetString().lower():
                return layer
        return None

    @staticmethod
    def _lookup_default(
        layer: QgsVectorLayer,
        field_name: str,
        options: tuple[LookupOption, ...],
    ) -> int:
        field_index = layer.fields().lookupField(field_name)
        expression = layer.defaultValueDefinition(
            field_index
        ).expression().strip()
        try:
            value = int(expression.strip("'\""))
        except (TypeError, ValueError) as error:
            raise NodeConfigurationContextError(
                f"Kihi „{layer.name()}“ välja {field_name} vaikeväärtus "
                "ei ole täisarv."
            ) from error
        if value not in {option.value for option in options}:
            raise NodeConfigurationContextError(
                f"Kihi „{layer.name()}“ välja {field_name} vaikeväärtus "
                "puudub lookup-valikute hulgast."
            )
        return value

    def _validate_edit_layers(
        self,
        project: QgsProject,
        edge_layer: QgsVectorLayer,
        node_layer: QgsVectorLayer,
        branch_layer: QgsVectorLayer,
        valve_layer: QgsVectorLayer,
        manhole_layer: QgsVectorLayer,
        facility_layers: tuple[QgsVectorLayer, ...] = (),
    ) -> None:
        base_connection = self._connection_info(edge_layer)
        if not base_connection:
            raise NodeConfigurationContextError(
                "Aktiivse torukihi PostGIS-i ühendust ei õnnestunud tuvastada."
            )

        node_provider = node_layer.dataProvider()
        node_required = (
            Qgis.VectorProviderCapability.ChangeGeometries
            | Qgis.VectorProviderCapability.ChangeAttributeValues
        )
        if (
            node_layer.readOnly()
            or node_provider is None
            or node_provider.capabilities() & node_required != node_required
        ):
            raise NodeConfigurationContextError(
                f"Sõlmekihil „{node_layer.name()}“ puudub geomeetria või "
                "pöördenurga muutmise õigus."
            )

        requirements = (
            (
                branch_layer,
                Qgis.VectorProviderCapability.AddFeatures
                | Qgis.VectorProviderCapability.ChangeAttributeValues
                | Qgis.VectorProviderCapability.DeleteFeatures,
            ),
            (
                valve_layer,
                Qgis.VectorProviderCapability.AddFeatures
                | Qgis.VectorProviderCapability.ChangeAttributeValues,
            ),
            (
                manhole_layer,
                Qgis.VectorProviderCapability.AddFeatures
                | Qgis.VectorProviderCapability.ChangeAttributeValues
                | Qgis.VectorProviderCapability.DeleteFeatures,
            ),
        ) + tuple(
            (
                layer,
                Qgis.VectorProviderCapability.AddFeatures
                | Qgis.VectorProviderCapability.ChangeAttributeValues
                | Qgis.VectorProviderCapability.DeleteFeatures,
            )
            for layer in facility_layers
        )
        for layer, required in requirements:
            if layer.providerType() != "postgres":
                raise NodeConfigurationContextError(
                    f"Detailkiht „{layer.name()}“ peab kasutama PostGIS-i."
                )
            if layer.readOnly():
                raise NodeConfigurationContextError(
                    f"Detailkiht „{layer.name()}“ on kirjutuskaitstud."
                )
            provider = layer.dataProvider()
            if provider is None or provider.capabilities() & required != required:
                raise NodeConfigurationContextError(
                    f"Detailkihil „{layer.name()}“ puuduvad konfiguraatori "
                    "redigeerimisõigused."
                )
            if self._connection_info(layer) != base_connection:
                raise NodeConfigurationContextError(
                    "Toru- ja sõlmedetailide kihid ei kasuta sama "
                    "PostGIS-i ühendust."
                )

        group = project.transactionGroup(
            edge_layer.providerType(), base_connection
        )
        if group is None or any(
            layer not in group.layers()
            for layer in (
                branch_layer,
                valve_layer,
                manhole_layer,
                *facility_layers,
            )
        ):
            raise NodeConfigurationContextError(
                "Sõlmedetailide kihid ei kuulu torukihiga samasse "
                "automaatsesse tehingugruppi."
            )

    @staticmethod
    def _unique_layers(layers) -> list[QgsVectorLayer]:
        result: list[QgsVectorLayer] = []
        seen: set[str] = set()
        for layer in layers:
            if layer.id() in seen:
                continue
            seen.add(layer.id())
            result.append(layer)
        return result

    def _integer_default(
        self,
        layer: QgsVectorLayer,
        field_name: str,
        label: str,
    ) -> int:
        value = self._optional_integer_default(layer, field_name)
        if value is None:
            raise NodeConfigurationContextError(
                f"Kihi „{layer.name()}“ {label} ({field_name}) "
                "vaikeväärtus ei ole täisarv."
            )
        return value

    @staticmethod
    def _optional_integer_default(
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
    def _require_fields(layer: QgsVectorLayer, required: set[str]) -> None:
        actual = {field.name().upper() for field in layer.fields()}
        missing = sorted(required - actual)
        if missing:
            raise NodeConfigurationContextError(
                f"Kihil „{layer.name()}“ puuduvad väljad: "
                f"{', '.join(missing)}."
            )

    @staticmethod
    def _source_table(layer: QgsVectorLayer) -> str:
        try:
            decoded = QgsProviderRegistry.instance().decodeUri(
                layer.providerType(), layer.source()
            )
        except (AttributeError, TypeError, ValueError):
            return ""
        return str(decoded.get("table", "")).lower()

    @staticmethod
    def _connection_info(layer: QgsVectorLayer) -> str:
        if layer.providerType() != "postgres":
            return ""
        try:
            return QgsDataSourceUri(layer.source()).connectionInfo(False)
        except (TypeError, ValueError):
            return ""
