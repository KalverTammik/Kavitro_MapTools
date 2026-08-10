"""Read and atomically write an EVEL water-node assembly configuration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from itertools import combinations
import math

from qgis.core import (
    QgsApplication,
    QgsExpression,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsVectorLayer,
    QgsVectorLayerUtils,
    QgsVariantUtils,
)

from ..layers import NodeConfigurationContext
from .endpoint_resolver import (
    EdgeSplitConnection,
    EndpointKind,
    EndpointResolution,
)
from .water_duct_writer import WaterDuctWriteError, WaterDuctWriter


MAX_VALVE_DISTANCE_METERS = 0.30
_MIN_VALVE_DISTANCE_METERS = 0.001

_BRANCH_UNSPECIFIED = 522
_BRANCH_ELBOW = 523
_BRANCH_COLLAR = 524
_BRANCH_TEE = 525
_BRANCH_CROSS = 526
_BRANCH_GENERIC = 527
_BRANCH_TRANSITION = 528
_BRANCH_FLANGE = 529
_BRANCH_SADDLE = 530
_BRANCH_END_CAP = 531

_BRANCH_REQUIRED_PORT_COUNTS = {
    _BRANCH_ELBOW: 2,
    _BRANCH_COLLAR: 2,
    _BRANCH_TEE: 3,
    _BRANCH_CROSS: 4,
    _BRANCH_GENERIC: 2,
    _BRANCH_TRANSITION: 2,
    _BRANCH_FLANGE: 2,
    _BRANCH_SADDLE: 3,
    _BRANCH_END_CAP: 1,
}


def branch_type_expected_port_count(branch_type_id: int) -> int | None:
    """Return a fitting's required port count, or None for unspecified."""

    return _BRANCH_REQUIRED_PORT_COUNTS.get(branch_type_id)


def branch_type_is_compatible(
    branch_type_id: int | None,
    port_count: int,
) -> bool:
    """Return whether a branch detail may represent this node degree."""

    if branch_type_id is None or branch_type_id == _BRANCH_UNSPECIFIED:
        return True
    expected = branch_type_expected_port_count(branch_type_id)
    return expected is not None and expected == port_count


class NodeConfigurationError(RuntimeError):
    """Raised when an assembly cannot be read or changed safely."""


@dataclass(frozen=True)
class IncidentPort:
    edge_feature_id: int
    edge_id: int | None
    central_at_start: bool
    other_node_id: int | None
    length: float
    label: str
    bearing: float
    technical_parameters: tuple[str, ...] = ()
    flow_direction: float | None = None
    existing_valve_node_id: int | None = None
    existing_valve_detail_feature_id: int | None = None
    existing_valve_type_id: int | None = None
    existing_valve_subtype_id: int | None = None


@dataclass(frozen=True)
class ManholeConfiguration:
    enabled: bool = False
    type_id: int | None = None
    material_id: int | None = None
    diameter_type_id: int | None = None
    diameter_id: int | None = None
    firmness_class_id: int | None = None
    anchor_plate: bool = False
    load_leveling_plate: bool = False
    lid_type_id: int | None = None
    lid_material_id: int | None = None
    lid_shape_id: int | None = None
    lid_diameter_id: int | None = None
    lid_capacity_id: int | None = None
    lid_insulation: bool = False
    access_duct_diam: int | None = None


@dataclass(frozen=True)
class FacilityConfiguration:
    """Parameters of one optional SN_WATER_PUMPING_STATION detail."""

    variant_key: str | None = None
    material_id: int | None = None
    productivity: float | None = None
    pressure_increase: float | None = None
    registry_code: str | None = None
    passport_number: str | None = None
    depth: float | None = None
    water_source_id: int | None = None
    wipeout_date: datetime | None = None
    renewal_date: datetime | None = None
    is_controlled: bool = False
    is_signalisation: bool = False
    protection_zone: float | None = None
    mantle_diam: float | None = None


@dataclass(frozen=True)
class NodeAssemblyState:
    node_id: int
    point: QgsPoint
    branch_detail_feature_id: int | None
    branch_type_id: int | None
    ports: tuple[IncidentPort, ...]
    manhole_detail_feature_id: int | None
    manhole: ManholeConfiguration
    node_network_id: int | None = None
    facility_detail_feature_id: int | None = None
    facility_source_variant_key: str | None = None
    facility: FacilityConfiguration = FacilityConfiguration()


@dataclass(frozen=True)
class PortValveConfiguration:
    port: IncidentPort
    enabled: bool
    distance: float
    valve_type_id: int | None
    valve_subtype_id: int | None


@dataclass(frozen=True)
class NodeAssemblyPlan:
    state: NodeAssemblyState
    branch_type_id: int | None
    ports: tuple[PortValveConfiguration, ...]
    manhole: ManholeConfiguration | None = None
    facility: FacilityConfiguration | None = None


@dataclass(frozen=True)
class NodeAssemblyWriteResult:
    node_id: int
    created_valve_node_ids: tuple[int, ...]
    manhole_enabled: bool
    facility_variant_key: str | None = None


class NodeAssemblyReader:
    """Describe one base node, its fitting detail and incident pipe ports."""

    def __init__(self, context: NodeConfigurationContext) -> None:
        self.context = context
        self._field_formatter_caches: dict[tuple[str, int], object] = {}
        self._value_relation_cache: dict[
            tuple[str, str, str, str], str | None
        ] = {}

    def read(self, node_id: int) -> NodeAssemblyState:
        node_feature = self._single_feature_by_value(
            self.context.node_layer,
            "MSLINK",
            node_id,
            required=True,
        )
        geometry = node_feature.geometry()
        if geometry.isNull() or geometry.isEmpty():
            raise NodeConfigurationError(
                f"Veesõlmel {node_id} puudub punktgeomeetria."
            )
        point_xy = geometry.asPoint()
        point = QgsPoint(point_xy.x(), point_xy.y())
        node_network_id = self._feature_optional_int(
            node_feature,
            "NETWORK_ID",
        )

        branch_detail = self._single_feature_by_value(
            self.context.branch_detail_layer,
            "NODE_ID",
            node_id,
            required=False,
        )
        branch_type = (
            self._optional_int(branch_detail["TYPE_AQUA_ID"])
            if branch_detail is not None
            else None
        )
        manhole_detail = self._single_feature_by_value(
            self.context.manhole_detail_layer,
            "NODE_ID",
            node_id,
            required=False,
        )
        manhole = self._manhole_configuration(manhole_detail)
        (
            facility_detail,
            facility_source_variant_key,
            facility,
        ) = self._facility_configuration(node_id, node_network_id)

        begin_index = self._field_index(
            self.context.edge_layer, "BEGIN_NODE_ID"
        )
        end_index = self._field_index(
            self.context.edge_layer, "END_NODE_ID"
        )
        mslink_index = self._field_index(self.context.edge_layer, "MSLINK")
        request = QgsFeatureRequest().setFilterExpression(
            f'"BEGIN_NODE_ID" = {int(node_id)} OR '
            f'"END_NODE_ID" = {int(node_id)}'
        )
        ports: list[IncidentPort] = []
        for feature in self.context.edge_layer.getFeatures(request):
            begin_node_id = self._optional_int(feature.attribute(begin_index))
            end_node_id = self._optional_int(feature.attribute(end_index))
            if begin_node_id == node_id and end_node_id == node_id:
                raise NodeConfigurationError(
                    f"Toru {self._edge_label(feature, mslink_index)} mõlemad "
                    f"otsad viitavad sõlmele {node_id}."
                )
            central_at_start = begin_node_id == node_id
            if not central_at_start and end_node_id != node_id:
                continue
            other_node_id = end_node_id if central_at_start else begin_node_id
            valve_detail = (
                self._single_feature_by_value(
                    self.context.valve_detail_layer,
                    "NODE_ID",
                    other_node_id,
                    required=False,
                )
                if other_node_id is not None
                else None
            )
            edge_id = self._optional_int(feature.attribute(mslink_index))
            direction = "algus" if central_at_start else "lõpp"
            length = feature.geometry().length()
            bearing = self._port_bearing(
                feature.geometry(), central_at_start, edge_id
            )
            ports.append(
                IncidentPort(
                    edge_feature_id=int(feature.id()),
                    edge_id=edge_id,
                    central_at_start=central_at_start,
                    other_node_id=other_node_id,
                    length=length,
                    label=(
                        f"Toru {edge_id if edge_id is not None else feature.id()} "
                        f"• {direction} • {length:.2f} m"
                    ),
                    bearing=bearing,
                    technical_parameters=self._technical_parameters(feature),
                    flow_direction=self._optional_float_attribute(
                        feature,
                        self.context.edge_layer,
                        "FLOWDIRECTION",
                    ),
                    existing_valve_node_id=(
                        other_node_id if valve_detail is not None else None
                    ),
                    existing_valve_detail_feature_id=(
                        int(valve_detail.id())
                        if valve_detail is not None
                        else None
                    ),
                    existing_valve_type_id=(
                        self._optional_int(valve_detail["TYPE_AQUA_ID"])
                        if valve_detail is not None
                        else None
                    ),
                    existing_valve_subtype_id=(
                        self._optional_int(valve_detail["TYPE_ID"])
                        if valve_detail is not None
                        else None
                    ),
                )
            )

        ports.sort(
            key=lambda port: (
                port.edge_id if port.edge_id is not None else port.edge_feature_id
            )
        )
        if not ports:
            raise NodeConfigurationError(
                f"Sõlmel {node_id} ei ole aktiivses torukihis seotud torusid."
            )
        return NodeAssemblyState(
            node_id=int(node_id),
            point=point,
            branch_detail_feature_id=(
                int(branch_detail.id()) if branch_detail is not None else None
            ),
            branch_type_id=branch_type,
            ports=tuple(ports),
            manhole_detail_feature_id=(
                int(manhole_detail.id())
                if manhole_detail is not None
                else None
            ),
            manhole=manhole,
            node_network_id=node_network_id,
            facility_detail_feature_id=(
                int(facility_detail.id())
                if facility_detail is not None
                else None
            ),
            facility_source_variant_key=facility_source_variant_key,
            facility=facility,
        )

    def _facility_configuration(
        self,
        node_id: int,
        node_network_id: int | None,
    ) -> tuple[QgsFeature | None, str | None, FacilityConfiguration]:
        options = self.context.facility_options
        if options is None or node_network_id is None:
            return None, None, FacilityConfiguration()

        variants = tuple(
            variant
            for variant in options.variants
            if variant.network_id == node_network_id
        )
        if not variants:
            return None, None, FacilityConfiguration()

        matches: list[tuple[QgsFeature, object]] = []
        seen_rows: set[tuple[str, int]] = set()
        for variant in variants:
            feature = self._single_feature_by_value(
                variant.detail_layer,
                "NODE_ID",
                node_id,
                required=False,
            )
            if feature is None:
                continue
            database_id = self._feature_optional_int(feature, "ID")
            row_key = (
                self._source_table_key(variant.detail_layer),
                database_id if database_id is not None else int(feature.id()),
            )
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)
            matches.append((feature, variant))
        if len(matches) > 1:
            raise NodeConfigurationError(
                f"Veesõlmel {node_id} on mitu rajatise detailkirjet."
            )
        if not matches:
            return None, None, FacilityConfiguration()

        feature, source_variant = matches[0]
        role_id = self._feature_optional_int(feature, "ROLE_ID")
        water_type_id = self._feature_optional_int(
            feature,
            "WATER_TYPE_ID",
        )
        matching_variant = next(
            (
                variant
                for variant in variants
                if variant.role_id == role_id
                and variant.water_type_id == water_type_id
            ),
            None,
        )
        if matching_variant is None:
            raise NodeConfigurationError(
                f"Veesõlme {node_id} rajatise ROLE_ID={role_id} ja "
                f"WATER_TYPE_ID={water_type_id} ei vasta ühelegi selle võrgu "
                "projektivariandile."
            )
        return (
            feature,
            source_variant.key,
            FacilityConfiguration(
                variant_key=matching_variant.key,
                material_id=self._feature_optional_int(
                    feature,
                    "MATERIAL_ID",
                ),
                productivity=self._feature_optional_float(
                    feature,
                    "PRODUCTIVITY",
                ),
                pressure_increase=self._feature_optional_float(
                    feature,
                    "PRESSURE_INCREASE",
                ),
                registry_code=self._feature_optional_text(
                    feature,
                    "P_REG_CODE",
                ),
                passport_number=self._feature_optional_text(
                    feature,
                    "P_PASPORT_NR",
                ),
                depth=self._feature_optional_float(feature, "P_DEPTH"),
                water_source_id=self._feature_optional_int(
                    feature,
                    "WATER_SOURCE_ID",
                ),
                wipeout_date=self._feature_optional_datetime(
                    feature,
                    "WIPEOUT_DATE",
                ),
                renewal_date=self._feature_optional_datetime(
                    feature,
                    "RENEWAL_DATE",
                ),
                is_controlled=self._feature_bool(
                    feature,
                    "IS_CONTROLLED",
                ),
                is_signalisation=self._feature_bool(
                    feature,
                    "IS_SIGNALISATION",
                ),
                protection_zone=self._feature_optional_float(
                    feature,
                    "PROTECTION_ZONE",
                ),
                mantle_diam=self._feature_optional_float(
                    feature,
                    "MANTLE_DIAM",
                ),
            ),
        )

    def _manhole_configuration(
        self,
        feature: QgsFeature | None,
    ) -> ManholeConfiguration:
        if feature is None:
            return ManholeConfiguration(
                enabled=False,
                type_id=self.context.manhole_options.default_type_id,
            )
        type_id = self._feature_optional_int(feature, "TYPE_ID")
        return ManholeConfiguration(
            enabled=True,
            type_id=(
                type_id
                if type_id is not None
                else self.context.manhole_options.default_type_id
            ),
            material_id=self._feature_optional_int(feature, "MATERIAL_ID"),
            diameter_type_id=self._feature_optional_int(
                feature, "DIAMETER_TYPE_ID"
            ),
            diameter_id=self._feature_optional_int(feature, "DIAMETER_ID"),
            firmness_class_id=self._feature_optional_int(
                feature, "FIRMNESS_CLASS_ID"
            ),
            anchor_plate=self._feature_bool(feature, "ANCHOR_PLATE"),
            load_leveling_plate=self._feature_bool(
                feature, "LOAD_LEVELING_PLATE"
            ),
            lid_type_id=self._feature_optional_int(feature, "LID_TYPE_ID"),
            lid_material_id=self._feature_optional_int(
                feature, "LID_MATERIAL_ID"
            ),
            lid_shape_id=self._feature_optional_int(
                feature, "LID_SHAPE_ID"
            ),
            lid_diameter_id=self._feature_optional_int(
                feature, "LID_DIAMETER_ID"
            ),
            lid_capacity_id=self._feature_optional_int(
                feature, "LID_CAPACITY_ID"
            ),
            lid_insulation=self._feature_bool(feature, "LID_INSULATION"),
            access_duct_diam=self._feature_optional_int(
                feature, "ACCESS_DUCT_DIAM"
            ),
        )

    @staticmethod
    def _feature_optional_int(
        feature: QgsFeature,
        field_name: str,
    ) -> int | None:
        value = feature[field_name]
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _feature_bool(feature: QgsFeature, field_name: str) -> bool:
        value = feature[field_name]
        if QgsVariantUtils.isNull(value):
            return False
        return bool(value)

    @staticmethod
    def _feature_optional_float(
        feature: QgsFeature,
        field_name: str,
    ) -> float | None:
        value = feature[field_name]
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _feature_optional_text(
        feature: QgsFeature,
        field_name: str,
    ) -> str | None:
        value = feature[field_name]
        if QgsVariantUtils.isNull(value):
            return None
        text_value = str(value).strip()
        return text_value or None

    @staticmethod
    def _feature_optional_datetime(
        feature: QgsFeature,
        field_name: str,
    ) -> datetime | None:
        value = feature[field_name]
        if QgsVariantUtils.isNull(value):
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time())
        to_python = getattr(value, "toPyDateTime", None)
        if callable(to_python):
            converted = to_python()
            return converted if isinstance(converted, datetime) else None
        return None

    @staticmethod
    def _source_table_key(layer: QgsVectorLayer) -> str:
        return f"{layer.providerType()}:{layer.source().split(' sql=')[0]}"

    def _technical_parameters(
        self,
        feature: QgsFeature,
    ) -> tuple[str, ...]:
        """Return compact, human-readable parameters for a pipe arm."""

        layer = self.context.edge_layer
        diameter_type = self._display_attribute(
            layer, feature, "DIAMETER_TYPE_ID"
        )
        diameter = self._display_attribute(layer, feature, "DIAMETER_ID")
        material = self._display_attribute(layer, feature, "MATERIAL_ID")
        pressure_class = self._display_attribute(
            layer, feature, "PRESSURE_CLASS_ID"
        )

        parameters: list[str] = []
        if diameter_type and diameter:
            parameters.append(f"{diameter_type} {diameter}")
        elif diameter:
            parameters.append(f"Läbimõõt {diameter}")
        elif diameter_type:
            parameters.append(diameter_type)
        if material:
            parameters.append(material)
        if pressure_class:
            parameters.append(pressure_class)
        return tuple(parameters)

    def _display_attribute(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        field_name: str,
    ) -> str | None:
        """Format an optional attribute exactly as its QGIS widget does."""

        field_index = layer.fields().lookupField(field_name)
        if field_index < 0:
            return None
        raw_value = feature.attribute(field_index)
        if QgsVariantUtils.isNull(raw_value):
            return None

        setup = layer.editorWidgetSetup(field_index)
        if setup.type() == "ValueRelation":
            related_text = self._value_relation_text(
                setup.config(),
                raw_value,
            )
            if related_text is not None:
                return related_text
        formatter = QgsApplication.fieldFormatterRegistry().fieldFormatter(
            setup.type()
        )
        cache_key = (layer.id(), field_index)
        if cache_key not in self._field_formatter_caches:
            try:
                cache = formatter.createCache(
                    layer,
                    field_index,
                    setup.config(),
                )
            except Exception:
                cache = None
            self._field_formatter_caches[cache_key] = cache
        try:
            displayed = formatter.representValue(
                layer,
                field_index,
                setup.config(),
                self._field_formatter_caches[cache_key],
                raw_value,
            )
        except Exception:
            displayed = raw_value

        text = str(displayed).strip()
        if not text or text.casefold() in {"null", "<null>"}:
            return None
        return text

    def _value_relation_text(
        self,
        config: dict,
        raw_value: object,
    ) -> str | None:
        """Resolve generator lookups without depending on a global project."""

        relation_layer = self.context.constant_layer
        configured_layer_id = str(config.get("Layer", ""))
        configured_layer_name = str(config.get("LayerName", ""))
        if (
            configured_layer_id
            and configured_layer_id != relation_layer.id()
            and configured_layer_name != relation_layer.name()
        ):
            return None

        key_name = str(config.get("Key", ""))
        value_name = str(config.get("Value", ""))
        key_index = relation_layer.fields().lookupField(key_name)
        value_index = relation_layer.fields().lookupField(value_name)
        if key_index < 0 or value_index < 0:
            return None

        cache_key = (
            relation_layer.id(),
            key_name,
            value_name,
            str(raw_value),
        )
        if cache_key in self._value_relation_cache:
            return self._value_relation_cache[cache_key]

        request = QgsFeatureRequest().setFilterExpression(
            f'"{key_name}" = {QgsExpression.quotedValue(raw_value)}'
        )
        match = next(relation_layer.getFeatures(request), None)
        if match is None:
            self._value_relation_cache[cache_key] = None
            return None
        related_value = match.attribute(value_index)
        if QgsVariantUtils.isNull(related_value):
            self._value_relation_cache[cache_key] = None
            return None
        text = str(related_value).strip()
        result = text if text else None
        self._value_relation_cache[cache_key] = result
        return result

    @staticmethod
    def _optional_float_attribute(
        feature: QgsFeature,
        layer: QgsVectorLayer,
        field_name: str,
    ) -> float | None:
        field_index = layer.fields().lookupField(field_name)
        if field_index < 0:
            return None
        value = feature.attribute(field_index)
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _port_bearing(
        geometry: QgsGeometry,
        central_at_start: bool,
        edge_id: int | None,
    ) -> float:
        """Return the first non-zero pipe direction away from the node."""

        curve = geometry.constGet()
        if not isinstance(curve, QgsLineString) or curve.numPoints() < 2:
            raise NodeConfigurationError(
                f"Toru {edge_id if edge_id is not None else '?'} peab olema "
                "üheosaline LineString."
            )
        if central_at_start:
            origin = curve.pointN(0)
            candidates = range(1, curve.numPoints())
        else:
            origin = curve.pointN(curve.numPoints() - 1)
            candidates = range(curve.numPoints() - 2, -1, -1)
        for index in candidates:
            target = curve.pointN(index)
            delta_x = target.x() - origin.x()
            delta_y = target.y() - origin.y()
            if math.hypot(delta_x, delta_y) > 1e-9:
                return math.degrees(math.atan2(delta_x, delta_y)) % 360.0
        raise NodeConfigurationError(
            f"Torul {edge_id if edge_id is not None else '?'} puudub "
            "sõlmest väljuv lõik."
        )

    def _single_feature_by_value(
        self,
        layer: QgsVectorLayer,
        field_name: str,
        value: int | None,
        *,
        required: bool,
    ) -> QgsFeature | None:
        if value is None:
            return None
        field_index = self._field_index(layer, field_name)
        request = QgsFeatureRequest().setFilterExpression(
            f'"{field_name}" = {int(value)}'
        )
        matches = list(layer.getFeatures(request))
        if len(matches) > 1:
            raise NodeConfigurationError(
                f"Kihis „{layer.name()}“ on väärtusega {field_name}={value} "
                "mitu kirjet."
            )
        if not matches:
            if required:
                raise NodeConfigurationError(
                    f"Kihis „{layer.name()}“ puudub {field_name}={value}."
                )
            return None
        feature = matches[0]
        if QgsVariantUtils.isNull(feature.attribute(field_index)):
            return None
        return feature

    @staticmethod
    def _field_index(layer: QgsVectorLayer, field_name: str) -> int:
        index = layer.fields().lookupField(field_name)
        if index < 0:
            raise NodeConfigurationError(
                f"Kihil „{layer.name()}“ puudub väli {field_name}."
            )
        return index

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _edge_label(cls, feature: QgsFeature, mslink_index: int) -> str:
        value = cls._optional_int(feature.attribute(mslink_index))
        return str(value if value is not None else feature.id())


class NodeAssemblyWriter:
    """Apply a central fitting and optional per-port valve nodes atomically."""

    COMMAND_TEXT = "Konfigureeri EVEL-i veesõlme"

    def __init__(self, context: NodeConfigurationContext) -> None:
        self.context = context

    def write(
        self,
        plan: NodeAssemblyPlan,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> NodeAssemblyWriteResult:
        layers = self._unique_layers(
            [
            self.context.node_layer,
            self.context.edge_layer,
            self.context.branch_detail_layer,
            self.context.valve_detail_layer,
            self.context.manhole_detail_layer,
            *self._facility_layers(),
            ]
        )
        if any(not layer.isEditable() for layer in layers):
            raise NodeConfigurationError(
                "Toru-, sõlme- ja detailkihid peavad olema "
                "redigeerimisrežiimis."
            )

        has_facilities = self.context.facility_options is not None
        total_steps = len(plan.ports) + (5 if has_facilities else 4)
        self._report_progress(
            progress_callback,
            0,
            total_steps,
            "Valmistan ühise redigeerimistehingu ette.",
        )
        for layer in layers:
            layer.beginEditCommand(self.COMMAND_TEXT)
        try:
            self._report_progress(
                progress_callback,
                1,
                total_steps,
                "Uuendan keskset liitmikku ja selle pöördenurka.",
            )
            self._write_central_branch(plan)
            self._report_progress(
                progress_callback,
                2,
                total_steps,
                "Uuendan keskse sõlme kaevu andmeid.",
            )
            manhole = self._write_manhole(plan)
            facility = plan.state.facility
            port_progress_offset = 2
            if has_facilities:
                self._report_progress(
                    progress_callback,
                    3,
                    total_steps,
                    "Uuendan keskse sõlme rajatise andmeid.",
                )
                facility = self._write_facility(plan)
                port_progress_offset = 3
            created_node_ids = self._write_port_valves(
                plan,
                progress_callback,
                total_steps,
                port_progress_offset,
            )
            self._report_progress(
                progress_callback,
                len(plan.ports) + port_progress_offset + 1,
                total_steps,
                "Lõpetan tehingu ja värskendan kaardikihte.",
            )
            for layer in reversed(layers):
                layer.endEditCommand()
        except Exception:
            for layer in reversed(layers):
                layer.destroyEditCommand()
            self._repaint()
            raise

        self._repaint()
        self._report_progress(
            progress_callback,
            total_steps,
            total_steps,
            "Veesõlme konfiguratsioon on redigeerimispuhvris.",
        )
        return NodeAssemblyWriteResult(
            node_id=plan.state.node_id,
            created_valve_node_ids=tuple(created_node_ids),
            manhole_enabled=manhole.enabled,
            facility_variant_key=facility.variant_key,
        )

    def _write_central_branch(self, plan: NodeAssemblyPlan) -> None:
        layer = self.context.branch_detail_layer
        existing_id = plan.state.branch_detail_feature_id
        if plan.branch_type_id is None:
            if existing_id is not None and not layer.deleteFeature(existing_id):
                raise NodeConfigurationError(
                    "Olemasoleva liitmiku detailkirje eemaldamine ebaõnnestus."
                )
            return

        allowed = {option.value for option in self.context.branch_options}
        if plan.branch_type_id not in allowed:
            raise NodeConfigurationError("Valitud liitmiku tüüp ei ole kehtiv.")
        port_count = len(plan.state.ports)
        if not branch_type_is_compatible(plan.branch_type_id, port_count):
            expected = branch_type_expected_port_count(plan.branch_type_id)
            if expected is None:
                raise NodeConfigurationError(
                    f"Liitmiku tüübil {plan.branch_type_id} puudub toetatud "
                    "toruharude arvu reegel."
                )
            raise NodeConfigurationError(
                f"Valitud liitmiku tüüp eeldab {expected} toruharu, "
                f"kuid sõlmel on {port_count}."
            )
        type_index = self._field_index(layer, "TYPE_AQUA_ID")
        if existing_id is not None:
            if not layer.changeAttributeValue(
                existing_id, type_index, plan.branch_type_id
            ):
                raise NodeConfigurationError(
                    "Liitmiku tüübi uuendamine ebaõnnestus."
                )
        else:
            self._add_detail(
                layer,
                plan.state.node_id,
                plan.branch_type_id,
                "liitmikule",
            )
        self._set_node_rotation(
            plan.state.node_id,
            self._branch_rotation(plan.state, plan.branch_type_id),
        )

    def _write_manhole(
        self,
        plan: NodeAssemblyPlan,
    ) -> ManholeConfiguration:
        configuration = plan.manhole or plan.state.manhole
        layer = self.context.manhole_detail_layer
        existing_id = plan.state.manhole_detail_feature_id
        if not configuration.enabled:
            if existing_id is not None and not layer.deleteFeature(existing_id):
                raise NodeConfigurationError(
                    "Olemasoleva kaevu detailkirje eemaldamine ebaõnnestus."
                )
            return configuration

        options = self.context.manhole_options
        self._validate_lookup_value(
            configuration.type_id,
            options.type_options,
            "Kaevu liik",
            required=True,
        )
        for value, allowed, label in (
            (
                configuration.material_id,
                options.material_options,
                "Kaevu materjal",
            ),
            (
                configuration.diameter_type_id,
                options.diameter_type_options,
                "Kaevu läbimõõdu tüüp",
            ),
            (
                configuration.diameter_id,
                options.diameter_options,
                "Kaevu läbimõõt",
            ),
            (
                configuration.firmness_class_id,
                options.firmness_options,
                "Kaevu ringjäikus",
            ),
            (
                configuration.lid_type_id,
                options.lid_type_options,
                "Kaane tüüp",
            ),
            (
                configuration.lid_material_id,
                options.lid_material_options,
                "Kaane materjal",
            ),
            (
                configuration.lid_shape_id,
                options.lid_shape_options,
                "Kaane kuju",
            ),
            (
                configuration.lid_diameter_id,
                options.lid_diameter_options,
                "Kaane läbimõõt",
            ),
            (
                configuration.lid_capacity_id,
                options.lid_capacity_options,
                "Kaane kandevõime",
            ),
        ):
            self._validate_lookup_value(value, allowed, label)
        if (
            configuration.access_duct_diam is not None
            and configuration.access_duct_diam <= 0
        ):
            raise NodeConfigurationError(
                "Tõusutoru läbimõõt peab olema positiivne täisarv."
            )

        values = {
            "TYPE_ID": configuration.type_id,
            "MATERIAL_ID": configuration.material_id,
            "DIAMETER_TYPE_ID": configuration.diameter_type_id,
            "DIAMETER_ID": configuration.diameter_id,
            "FIRMNESS_CLASS_ID": configuration.firmness_class_id,
            "ANCHOR_PLATE": configuration.anchor_plate,
            "LOAD_LEVELING_PLATE": configuration.load_leveling_plate,
            "LID_TYPE_ID": configuration.lid_type_id,
            "LID_MATERIAL_ID": configuration.lid_material_id,
            "LID_SHAPE_ID": configuration.lid_shape_id,
            "LID_DIAMETER_ID": configuration.lid_diameter_id,
            "LID_CAPACITY_ID": configuration.lid_capacity_id,
            "LID_INSULATION": configuration.lid_insulation,
            "ACCESS_DUCT_DIAM": configuration.access_duct_diam,
        }
        if existing_id is None:
            attributes = {
                self._field_index(layer, "NODE_ID"): int(plan.state.node_id)
            }
            attributes.update(
                {
                    self._field_index(layer, field_name): value
                    for field_name, value in values.items()
                }
            )
            feature = QgsVectorLayerUtils.createFeature(
                layer,
                QgsGeometry(),
                attributes,
            )
            if not layer.addFeature(feature):
                raise NodeConfigurationError(
                    "Kaevu detailkirje lisamine ebaõnnestus."
                )
            self._required_integer_attribute(
                layer,
                feature,
                "ID",
                "kaevule",
            )
            return configuration

        for field_name, value in values.items():
            if not layer.changeAttributeValue(
                existing_id,
                self._field_index(layer, field_name),
                value,
            ):
                raise NodeConfigurationError(
                    f"Kaevu välja „{field_name}“ uuendamine ebaõnnestus."
                )
        return configuration

    def _write_facility(
        self,
        plan: NodeAssemblyPlan,
    ) -> FacilityConfiguration:
        configuration = plan.facility or plan.state.facility
        options = self.context.facility_options
        if options is None:
            if configuration.variant_key is not None:
                raise NodeConfigurationError(
                    "Projektis puuduvad rajatise detailkihid."
                )
            return configuration

        source_variant = next(
            (
                variant
                for variant in options.variants
                if variant.key == plan.state.facility_source_variant_key
            ),
            None,
        )
        existing_id = plan.state.facility_detail_feature_id
        if existing_id is not None and source_variant is None:
            raise NodeConfigurationError(
                "Olemasoleva rajatise lähtekihti ei õnnestunud tuvastada."
            )
        if configuration.variant_key is None:
            if (
                existing_id is not None
                and source_variant is not None
                and not source_variant.detail_layer.deleteFeature(existing_id)
            ):
                raise NodeConfigurationError(
                    "Olemasoleva rajatise detailkirje eemaldamine ebaõnnestus."
                )
            return configuration

        target_variant = next(
            (
                variant
                for variant in options.variants
                if variant.key == configuration.variant_key
            ),
            None,
        )
        if target_variant is None:
            raise NodeConfigurationError(
                "Valitud rajatise tüüp ei kuulu projekti valikutesse."
            )
        if target_variant.network_id != plan.state.node_network_id:
            raise NodeConfigurationError(
                f"Rajatise „{target_variant.label}“ võrk "
                f"({target_variant.network_id}) ei vasta sõlme võrgule "
                f"({plan.state.node_network_id})."
            )
        self._validate_lookup_value(
            configuration.material_id,
            options.material_options,
            "Rajatise materjal",
        )
        self._validate_lookup_value(
            configuration.water_source_id,
            options.water_source_options,
            "Rajatise veeallikas",
        )
        for value, label in (
            (configuration.productivity, "Tootlikkus"),
            (configuration.pressure_increase, "Surve tõus"),
            (configuration.depth, "Puurkaevu sügavus"),
            (configuration.protection_zone, "Sanitaarkaitse ulatus"),
            (configuration.mantle_diam, "Mantli läbimõõt"),
        ):
            if value is not None and value < 0:
                raise NodeConfigurationError(
                    f"{label} ei tohi olla negatiivne."
                )

        values = {
            "MATERIAL_ID": configuration.material_id,
            "ROLE_ID": target_variant.role_id,
            "PRODUCTIVITY": configuration.productivity,
            "PRESSURE_INCREASE": configuration.pressure_increase,
            "P_REG_CODE": self._optional_text(configuration.registry_code),
            "P_PASPORT_NR": self._optional_text(
                configuration.passport_number
            ),
            "P_DEPTH": configuration.depth,
            "WATER_TYPE_ID": target_variant.water_type_id,
            "WATER_SOURCE_ID": configuration.water_source_id,
            "WIPEOUT_DATE": configuration.wipeout_date,
            "RENEWAL_DATE": configuration.renewal_date,
            "IS_CONTROLLED": configuration.is_controlled,
            "IS_SIGNALISATION": configuration.is_signalisation,
            "PROTECTION_ZONE": configuration.protection_zone,
            "MANTLE_DIAM": configuration.mantle_diam,
        }
        if existing_id is None:
            layer = target_variant.detail_layer
            attributes = {
                self._field_index(layer, "NODE_ID"): int(plan.state.node_id)
            }
            attributes.update(
                {
                    self._field_index(layer, field_name): value
                    for field_name, value in values.items()
                }
            )
            feature = QgsVectorLayerUtils.createFeature(
                layer,
                QgsGeometry(),
                attributes,
            )
            if not layer.addFeature(feature):
                raise NodeConfigurationError(
                    "Rajatise detailkirje lisamine ebaõnnestus."
                )
            self._required_integer_attribute(
                layer,
                feature,
                "ID",
                "rajatisele",
            )
            return configuration

        layer = source_variant.detail_layer
        for field_name, value in values.items():
            if not layer.changeAttributeValue(
                existing_id,
                self._field_index(layer, field_name),
                value,
            ):
                raise NodeConfigurationError(
                    f"Rajatise välja „{field_name}“ uuendamine ebaõnnestus."
                )
        return configuration

    @staticmethod
    def _validate_lookup_value(
        value: int | None,
        options,
        label: str,
        *,
        required: bool = False,
    ) -> None:
        if value is None:
            if required:
                raise NodeConfigurationError(f"{label} peab olema valitud.")
            return
        if value not in {option.value for option in options}:
            raise NodeConfigurationError(
                f"{label} väärtus {value} ei kuulu projekti valikutesse."
            )

    def _write_port_valves(
        self,
        plan: NodeAssemblyPlan,
        progress_callback: Callable[[int, int, str], None] | None,
        total_steps: int,
        progress_offset: int = 2,
    ) -> list[int]:
        created_node_ids: list[int] = []
        allowed = {option.value for option in self.context.valve_options}
        allowed_subtypes = {
            option.value for option in self.context.valve_subtype_options
        }
        network_id = self._positive_property(
            self.context.edge_layer, "evel_topology_node_network_id"
        )
        nettype_id = self._positive_property(
            self.context.edge_layer, "evel_topology_node_nettype_id"
        )
        duct_writer = WaterDuctWriter(
            self.context.edge_layer, self.context.node_layer
        )

        port_count = len(plan.ports)
        for index, configuration in enumerate(plan.ports, start=1):
            port = configuration.port
            if not configuration.enabled:
                activity = "Jätan muutmata"
            elif port.existing_valve_detail_feature_id is not None:
                activity = "Uuendan sulgeseadet"
            else:
                activity = "Lisan sulgeseadme"
            self._report_progress(
                progress_callback,
                index + progress_offset,
                total_steps,
                f"{activity}: haru {index}/{port_count} — {port.label}",
            )
            if not configuration.enabled:
                continue
            if configuration.valve_type_id not in allowed:
                raise NodeConfigurationError(
                    f"Harul „{port.label}“ puudub kehtiv sulgeseadme liik."
                )
            if configuration.valve_subtype_id not in allowed_subtypes:
                raise NodeConfigurationError(
                    f"Harul „{port.label}“ puudub kehtiv sulgeseadme alamliik."
                )

            if port.existing_valve_detail_feature_id is not None:
                type_index = self._field_index(
                    self.context.valve_detail_layer, "TYPE_AQUA_ID"
                )
                subtype_index = self._field_index(
                    self.context.valve_detail_layer, "TYPE_ID"
                )
                if not self.context.valve_detail_layer.changeAttributeValue(
                    port.existing_valve_detail_feature_id,
                    type_index,
                    configuration.valve_type_id,
                ):
                    raise NodeConfigurationError(
                        f"Harul „{port.label}“ oleva sulgeseadme tüübi "
                        "uuendamine ebaõnnestus."
                    )
                if not self.context.valve_detail_layer.changeAttributeValue(
                    port.existing_valve_detail_feature_id,
                    subtype_index,
                    configuration.valve_subtype_id,
                ):
                    raise NodeConfigurationError(
                        f"Harul „{port.label}“ oleva sulgeseadme alamliigi "
                        "uuendamine ebaõnnestus."
                    )
                self._move_existing_valve(
                    plan.state,
                    port,
                    float(configuration.distance),
                )
                continue

            edge_feature = self.context.edge_layer.getFeature(
                port.edge_feature_id
            )
            if not edge_feature.isValid() or not edge_feature.hasGeometry():
                raise NodeConfigurationError(
                    f"Harul „{port.label}“ olevat toru ei leitud."
                )
            geometry = edge_feature.geometry()
            length = geometry.length()
            distance = float(configuration.distance)
            self._validate_valve_distance(port, distance, length)
            measure = distance if port.central_at_start else length - distance
            point_xy = geometry.interpolate(measure).asPoint()
            point = QgsPoint(point_xy.x(), point_xy.y())
            rotation = self._inline_rotation_at_point(geometry, point)
            endpoint = EndpointResolution(
                EndpointKind.NEW_NODE,
                point,
                edge_split=EdgeSplitConnection(
                    feature_id=port.edge_feature_id,
                    edge_id=port.edge_id,
                    point=point,
                ),
            )
            try:
                valve_node_id = duct_writer.materialize_endpoint(
                    endpoint,
                    network_id,
                    nettype_id,
                )
            except WaterDuctWriteError as error:
                raise NodeConfigurationError(str(error)) from error
            self._set_node_rotation(valve_node_id, rotation)
            self._add_detail(
                self.context.valve_detail_layer,
                valve_node_id,
                int(configuration.valve_type_id),
                "sulgeseadmele",
                extra_attributes={
                    "TYPE_ID": int(configuration.valve_subtype_id)
                },
            )
            created_node_ids.append(valve_node_id)
        return created_node_ids

    @staticmethod
    def _report_progress(
        callback: Callable[[int, int, str], None] | None,
        current: int,
        total: int,
        message: str,
    ) -> None:
        if callback is not None:
            callback(current, total, message)

    def _move_existing_valve(
        self,
        state: NodeAssemblyState,
        port: IncidentPort,
        distance: float,
    ) -> None:
        valve_node_id = port.existing_valve_node_id
        if valve_node_id is None:
            raise NodeConfigurationError(
                f"Harul „{port.label}“ oleva sulgeseadme sõlme ID puudub."
            )

        central_edge = self.context.edge_layer.getFeature(
            port.edge_feature_id
        )
        if not central_edge.isValid() or not central_edge.hasGeometry():
            raise NodeConfigurationError(
                f"Harul „{port.label}“ olevat toru ei leitud."
            )
        continuation = self._valve_continuation_edge(
            valve_node_id,
            port.edge_feature_id,
        )
        central_points, central_at_geometry_start = self._oriented_edge_points(
            central_edge,
            state.node_id,
        )
        continuation_points, valve_at_geometry_start = (
            self._oriented_edge_points(continuation, valve_node_id)
        )
        if central_points[-1].distance(continuation_points[0]) > 1e-6:
            raise NodeConfigurationError(
                f"Harul „{port.label}“ ei kattu sulgeseadmega seotud "
                "toruosade geomeetria."
            )

        combined_points = central_points + continuation_points[1:]
        combined = QgsGeometry(QgsLineString(combined_points))
        self._validate_valve_distance(port, distance, combined.length())
        current_point = central_points[-1]
        if abs(distance - central_edge.geometry().length()) <= 1e-9:
            self._set_node_rotation(
                valve_node_id,
                self._inline_rotation_at_point(combined, current_point),
            )
            return

        point_xy = combined.interpolate(distance).asPoint()
        split_point = QgsPoint(point_xy.x(), point_xy.y())
        first, second = WaterDuctWriter._split_line_geometry(
            combined, split_point
        )
        central_geometry = (
            first
            if central_at_geometry_start
            else self._reversed_geometry(first)
        )
        continuation_geometry = (
            second
            if valve_at_geometry_start
            else self._reversed_geometry(second)
        )

        node_feature = self._single_feature_by_value(
            self.context.node_layer,
            "MSLINK",
            valve_node_id,
        )
        if not self.context.node_layer.changeGeometry(
            int(node_feature.id()), QgsGeometry.fromPoint(split_point)
        ):
            raise NodeConfigurationError(
                f"Sulgeseadme sõlme {valve_node_id} nihutamine ebaõnnestus."
            )
        self._set_node_rotation(
            valve_node_id,
            self._inline_rotation_at_point(combined, split_point),
        )
        self._change_edge_geometry_and_length(
            central_edge,
            central_geometry,
        )
        self._change_edge_geometry_and_length(
            continuation,
            continuation_geometry,
        )

    def _branch_rotation(
        self,
        state: NodeAssemblyState,
        branch_type_id: int,
    ) -> float:
        bearings = self._port_bearings(state)
        expected = branch_type_expected_port_count(branch_type_id)
        if not branch_type_is_compatible(branch_type_id, len(bearings)):
            if expected is None:
                raise NodeConfigurationError(
                    f"Liitmiku tüübil {branch_type_id} puudub toetatud "
                    "toruharude arvu reegel."
                )
            raise NodeConfigurationError(
                f"Valitud liitmiku tüüp eeldab {expected} toruharu, "
                f"kuid sõlmel on {len(bearings)}."
            )

        if branch_type_id == _BRANCH_TEE:
            branch_bearing = self._tee_branch_bearing(bearings)
            # The QML tee at zero has its side arm pointing west (270°).
            return self._normalize_angle(branch_bearing - 270.0)
        if branch_type_id == _BRANCH_SADDLE:
            # The QML saddle at zero has its side arm pointing north.
            return self._normalize_angle(self._tee_branch_bearing(bearings))
        if branch_type_id == _BRANCH_CROSS:
            return self._cross_rotation(bearings)
        if branch_type_id == _BRANCH_ELBOW:
            return self._elbow_rotation(bearings)
        if branch_type_id == _BRANCH_END_CAP:
            # The QML end cap at zero connects to a pipe extending east.
            return self._normalize_angle(bearings[0] - 90.0)
        if branch_type_id in {
            _BRANCH_COLLAR,
            _BRANCH_GENERIC,
            _BRANCH_TRANSITION,
            _BRANCH_FLANGE,
        }:
            # These symbols use a horizontal pipe axis at zero rotation.
            return self._normalize_half_turn(bearings[0] - 90.0)
        return 0.0

    def _port_bearings(self, state: NodeAssemblyState) -> list[float]:
        bearings: list[float] = []
        for port in state.ports:
            feature = self.context.edge_layer.getFeature(
                port.edge_feature_id
            )
            if not feature.isValid() or not feature.hasGeometry():
                raise NodeConfigurationError(
                    f"Harul „{port.label}“ olevat toru ei leitud."
                )
            curve = feature.geometry().constGet()
            if not isinstance(curve, QgsLineString) or curve.numPoints() < 2:
                raise NodeConfigurationError(
                    f"Harul „{port.label}“ peab toru olema üheosaline LineString."
                )
            if port.central_at_start:
                origin = curve.pointN(0)
                candidates = range(1, curve.numPoints())
            else:
                origin = curve.pointN(curve.numPoints() - 1)
                candidates = range(curve.numPoints() - 2, -1, -1)
            bearing = None
            for index in candidates:
                target = curve.pointN(index)
                if origin.distance(target) > 1e-9:
                    bearing = self._bearing(origin, target)
                    break
            if bearing is None:
                raise NodeConfigurationError(
                    f"Harul „{port.label}“ puudub sõlmest väljuv lõik."
                )
            bearings.append(bearing)
        return bearings

    @classmethod
    def _tee_branch_bearing(cls, bearings: list[float]) -> float:
        if len(bearings) != 3:
            raise NodeConfigurationError(
                "Kolmiku või sadula suuna määramiseks on vaja kolme toruharu."
            )
        main_pair = min(
            combinations(range(3), 2),
            key=lambda pair: abs(
                180.0
                - cls._angular_separation(
                    bearings[pair[0]], bearings[pair[1]]
                )
            ),
        )
        branch_index = next(
            index for index in range(3) if index not in main_pair
        )
        return bearings[branch_index]

    @classmethod
    def _cross_rotation(cls, bearings: list[float]) -> float:
        if len(bearings) != 4:
            raise NodeConfigurationError(
                "Neliku suuna määramiseks on vaja nelja toruharu."
            )
        best_rotation = 0.0
        best_score = float("inf")
        for bearing in bearings:
            rotation = bearing % 90.0
            template = [rotation + step for step in (0.0, 90.0, 180.0, 270.0)]
            score = sum(
                min(cls._angular_distance(value, target) for target in template)
                for value in bearings
            )
            if score < best_score:
                best_score = score
                best_rotation = rotation
        return cls._normalize_angle(best_rotation)

    @classmethod
    def _elbow_rotation(cls, bearings: list[float]) -> float:
        if len(bearings) != 2:
            raise NodeConfigurationError(
                "Kääniku suuna määramiseks on vaja kahte toruharu."
            )
        # The zero-angle QML elbow has arms pointing north and west.
        templates = (0.0, 270.0)
        candidates: list[tuple[float, float]] = []
        for first, second in ((bearings[0], bearings[1]), (bearings[1], bearings[0])):
            for first_template, second_template in (
                (templates[0], templates[1]),
                (templates[1], templates[0]),
            ):
                rotation = cls._normalize_angle(first - first_template)
                error = cls._angular_distance(
                    second,
                    second_template + rotation,
                )
                candidates.append((error, rotation))
        return min(candidates, key=lambda item: item[0])[1]

    @classmethod
    def _inline_rotation_at_point(
        cls,
        geometry: QgsGeometry,
        point: QgsPoint,
    ) -> float:
        curve = geometry.constGet()
        if not isinstance(curve, QgsLineString) or curve.numPoints() < 2:
            raise NodeConfigurationError(
                "Sulgeseadme toru peab olema üheosaline LineString."
            )
        _distance, _nearest, after_vertex, _left = (
            geometry.closestSegmentWithContext(
                QgsPointXY(point.x(), point.y())
            )
        )
        if after_vertex <= 0 or after_vertex >= curve.numPoints():
            raise NodeConfigurationError(
                "Sulgeseadme kohalikku torusuunda ei õnnestunud määrata."
            )
        bearing = cls._bearing(
            curve.pointN(after_vertex - 1),
            curve.pointN(after_vertex),
        )
        # The QML valve at zero has a horizontal east-west axis.
        return cls._normalize_half_turn(bearing - 90.0)

    def _set_node_rotation(self, node_id: int, rotation: float) -> None:
        feature = self._single_feature_by_value(
            self.context.node_layer,
            "MSLINK",
            node_id,
        )
        field_index = self._field_index(
            self.context.node_layer, "PNT_ROTATION"
        )
        # EVEL stores PNT_ROTATION as an integer number of degrees.  QGIS
        # bearings are floating-point values, so round to the nearest whole
        # degree before handing the value to the PostGIS provider.
        rotation_value = int(
            math.floor(self._normalize_angle(rotation) + 0.5)
        ) % 360
        if not self.context.node_layer.changeAttributeValue(
            int(feature.id()),
            field_index,
            rotation_value,
        ):
            raise NodeConfigurationError(
                f"Sõlme {node_id} pöördenurga uuendamine ebaõnnestus."
            )

    @staticmethod
    def _bearing(start: QgsPoint, end: QgsPoint) -> float:
        delta_x = end.x() - start.x()
        delta_y = end.y() - start.y()
        if math.hypot(delta_x, delta_y) <= 1e-12:
            raise NodeConfigurationError(
                "Nullpikkusega lõigu suunda ei saa arvutada."
            )
        return math.degrees(math.atan2(delta_x, delta_y)) % 360.0

    @staticmethod
    def _normalize_angle(angle: float) -> float:
        return angle % 360.0

    @staticmethod
    def _normalize_half_turn(angle: float) -> float:
        return angle % 180.0

    @staticmethod
    def _angular_separation(first: float, second: float) -> float:
        difference = abs((first - second) % 360.0)
        return min(difference, 360.0 - difference)

    @classmethod
    def _angular_distance(cls, first: float, second: float) -> float:
        return cls._angular_separation(first, second)

    def _valve_continuation_edge(
        self,
        valve_node_id: int,
        central_edge_feature_id: int,
    ) -> QgsFeature:
        request = QgsFeatureRequest().setFilterExpression(
            f'"BEGIN_NODE_ID" = {int(valve_node_id)} OR '
            f'"END_NODE_ID" = {int(valve_node_id)}'
        )
        matches = [
            feature
            for feature in self.context.edge_layer.getFeatures(request)
            if int(feature.id()) != int(central_edge_feature_id)
        ]
        if len(matches) != 1:
            raise NodeConfigurationError(
                f"Sulgeseadme sõlme {valve_node_id} kaugust saab muuta "
                "ainult siis, kui sõlmega on seotud täpselt kaks toruosa; "
                f"jätkuvaid toruosi leiti {len(matches)}."
            )
        continuation = matches[0]
        if not continuation.hasGeometry():
            raise NodeConfigurationError(
                f"Sulgeseadme sõlme {valve_node_id} jätkuval torul "
                "puudub geomeetria."
            )
        return continuation

    def _oriented_edge_points(
        self,
        feature: QgsFeature,
        from_node_id: int,
    ) -> tuple[list[QgsPoint], bool]:
        begin_index = self._field_index(
            self.context.edge_layer, "BEGIN_NODE_ID"
        )
        end_index = self._field_index(
            self.context.edge_layer, "END_NODE_ID"
        )
        begin_node_id = self._optional_int(feature.attribute(begin_index))
        end_node_id = self._optional_int(feature.attribute(end_index))
        curve = feature.geometry().constGet()
        if not isinstance(curve, QgsLineString) or curve.numPoints() < 2:
            raise NodeConfigurationError(
                "Sulgeseadmega seotud toru peab olema üheosaline LineString."
            )
        points = [
            QgsPoint(curve.pointN(index).x(), curve.pointN(index).y())
            for index in range(curve.numPoints())
        ]
        if begin_node_id == from_node_id and end_node_id != from_node_id:
            return points, True
        if end_node_id == from_node_id and begin_node_id != from_node_id:
            return list(reversed(points)), False
        raise NodeConfigurationError(
            f"Toru {self._feature_label(feature)} sõlmeviited ei määra "
            f"üheselt ühendust sõlmega {from_node_id}."
        )

    def _change_edge_geometry_and_length(
        self,
        feature: QgsFeature,
        geometry: QgsGeometry,
    ) -> None:
        feature_id = int(feature.id())
        if not self.context.edge_layer.changeGeometry(feature_id, geometry):
            raise NodeConfigurationError(
                f"Toru {self._feature_label(feature)} geomeetria "
                "uuendamine ebaõnnestus."
            )
        length_index = self._field_index(
            self.context.edge_layer, "LENGTH_2D"
        )
        if not self.context.edge_layer.changeAttributeValue(
            feature_id,
            length_index,
            geometry.length(),
        ):
            raise NodeConfigurationError(
                f"Toru {self._feature_label(feature)} pikkuse uuendamine "
                "ebaõnnestus."
            )

    def _single_feature_by_value(
        self,
        layer: QgsVectorLayer,
        field_name: str,
        value: int,
    ) -> QgsFeature:
        request = QgsFeatureRequest().setFilterExpression(
            f'"{field_name}" = {int(value)}'
        )
        matches = list(layer.getFeatures(request))
        if len(matches) != 1:
            raise NodeConfigurationError(
                f"Kihis „{layer.name()}“ peab olema täpselt üks "
                f"{field_name}={value} kirje; leiti {len(matches)}."
            )
        return matches[0]

    @staticmethod
    def _reversed_geometry(geometry: QgsGeometry) -> QgsGeometry:
        curve = geometry.constGet()
        if not isinstance(curve, QgsLineString):
            raise NodeConfigurationError(
                "Pööratav torugeomeetria ei ole LineString."
            )
        points = [
            QgsPoint(curve.pointN(index).x(), curve.pointN(index).y())
            for index in reversed(range(curve.numPoints()))
        ]
        return QgsGeometry(QgsLineString(points))

    @staticmethod
    def _validate_valve_distance(
        port: IncidentPort,
        distance: float,
        available_length: float,
    ) -> None:
        if distance <= _MIN_VALVE_DISTANCE_METERS:
            raise NodeConfigurationError(
                f"Harul „{port.label}“ peab sulgeseadme kaugus olema "
                "suurem kui 0 m."
            )
        if distance > MAX_VALVE_DISTANCE_METERS + 1e-9:
            raise NodeConfigurationError(
                f"Harul „{port.label}“ ei tohi sulgeseadme kaugus "
                f"ületada {MAX_VALVE_DISTANCE_METERS:.2f} m."
            )
        if distance >= available_length - _MIN_VALVE_DISTANCE_METERS:
            raise NodeConfigurationError(
                f"Harul „{port.label}“ peab sulgeseadme kaugus olema "
                f"väiksem kui {available_length:.3f} m."
            )

    def _feature_label(self, feature: QgsFeature) -> str:
        index = self._field_index(self.context.edge_layer, "MSLINK")
        value = self._optional_int(feature.attribute(index))
        return str(value if value is not None else feature.id())

    def _add_detail(
        self,
        layer: QgsVectorLayer,
        node_id: int,
        type_id: int,
        object_label: str,
        *,
        extra_attributes: dict[str, int] | None = None,
    ) -> QgsFeature:
        attributes = {
            self._field_index(layer, "NODE_ID"): int(node_id),
            self._field_index(layer, "TYPE_AQUA_ID"): int(type_id),
        }
        for field_name, value in (extra_attributes or {}).items():
            attributes[self._field_index(layer, field_name)] = int(value)
        feature = QgsVectorLayerUtils.createFeature(
            layer, QgsGeometry(), attributes
        )
        if not layer.addFeature(feature):
            raise NodeConfigurationError(
                f"Detailkirje lisamine {object_label} ebaõnnestus."
            )
        self._required_integer_attribute(layer, feature, "ID", object_label)
        return feature

    def _repaint(self) -> None:
        for layer in self._unique_layers(
            (
            self.context.node_layer,
            self.context.edge_layer,
            self.context.branch_detail_layer,
            self.context.valve_detail_layer,
            self.context.manhole_detail_layer,
            self.context.visible_branch_layer,
            self.context.visible_valve_layer,
            self.context.visible_manhole_layer,
            *self._facility_layers(),
            *self._visible_facility_layers(),
            )
        ):
            if layer is not None:
                layer.triggerRepaint()

    def _facility_layers(self) -> list[QgsVectorLayer]:
        options = self.context.facility_options
        if options is None:
            return []
        return self._unique_layers(
            variant.detail_layer for variant in options.variants
        )

    def _visible_facility_layers(self) -> list[QgsVectorLayer]:
        options = self.context.facility_options
        if options is None:
            return []
        return self._unique_layers(
            variant.visible_layer for variant in options.variants
        )

    @staticmethod
    def _unique_layers(layers) -> list[QgsVectorLayer]:
        result: list[QgsVectorLayer] = []
        seen: set[str] = set()
        for layer in layers:
            if layer is None or layer.id() in seen:
                continue
            seen.add(layer.id())
            result.append(layer)
        return result

    @staticmethod
    def _optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _field_index(layer: QgsVectorLayer, field_name: str) -> int:
        index = layer.fields().lookupField(field_name)
        if index < 0:
            raise NodeConfigurationError(
                f"Kihil „{layer.name()}“ puudub väli {field_name}."
            )
        return index

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _required_integer_attribute(
        cls,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        field_name: str,
        object_label: str,
    ) -> int:
        value = feature.attribute(cls._field_index(layer, field_name))
        if QgsVariantUtils.isNull(value):
            raise NodeConfigurationError(
                f"Andmepakkuja ei tagastanud {object_label} serveri-ID-d."
            )
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise NodeConfigurationError(
                f"Andmepakkuja tagastatud {object_label} ID ei ole täisarv."
            ) from error

    @staticmethod
    def _positive_property(layer: QgsVectorLayer, key: str) -> int:
        try:
            value = int(layer.customProperty(key, ""))
        except (TypeError, ValueError) as error:
            raise NodeConfigurationError(
                f"Torukihi tehniline omadus {key} ei ole kehtiv."
            ) from error
        if value <= 0:
            raise NodeConfigurationError(
                f"Torukihi tehniline omadus {key} ei ole kehtiv."
            )
        return value
