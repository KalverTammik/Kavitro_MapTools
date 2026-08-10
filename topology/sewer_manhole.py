"""Read, visualize and atomically write an EVEL sewer manhole clock."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsDataSourceUri,
    QgsExpression,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
    QgsProviderRegistry,
    QgsRectangle,
    QgsVectorLayer,
    QgsVectorLayerUtils,
    QgsVariantUtils,
)

from ..layers import SewerManholeContext
from .water_duct_writer import WaterDuctWriter


GRAVITY_NETTYPE_ID = 309
DETAIL_KIND_MANHOLE = "manhole"
DETAIL_KIND_CONNECTION = "connection"


class SewerManholeError(RuntimeError):
    """Raised when a sewer manhole cannot be resolved or written safely."""


@dataclass(frozen=True)
class SewerManholeConfiguration:
    detail_kind: str = DETAIL_KIND_MANHOLE
    identification: str = ""
    element_height: float | None = None
    bottom_height: float | None = None
    ground_height: float | None = None
    type_id: int | None = None
    material_id: int | None = None
    diameter_type_id: int | None = None
    diameter_id: int | None = None
    firmness_class_id: int | None = None
    lid_type_id: int | None = None
    lid_material_id: int | None = None
    lid_shape_id: int | None = None
    lid_diameter_id: int | None = None
    lid_capacity_id: int | None = None
    access_duct_diam: int | None = None
    branch_type_id: int | None = None
    branch_subtype_id: int | None = None


@dataclass(frozen=True)
class SewerEndpointConnection:
    layer: QgsVectorLayer
    feature_id: int
    node_field: str
    port_key: str


@dataclass(frozen=True)
class _EndpointCandidate:
    layer: QgsVectorLayer
    feature: QgsFeature
    at_start: bool
    point: QgsPoint
    node_id: int | None


@dataclass(frozen=True)
class SewerManholePort:
    key: str
    layer: QgsVectorLayer
    feature_id: int
    edge_id: int | None
    central_at_start: bool
    bearing: float
    identification: str
    diameter_label: str
    material_label: str
    height: float | None
    flow_direction: float | None
    split_side: str | None = None

    @property
    def height_field(self) -> str:
        return "BEGIN_Z_COORD" if self.central_at_start else "END_Z_COORD"

    @property
    def is_outgoing(self) -> bool | None:
        """Return whether flow leaves the node through this pipe port."""

        if self.flow_direction is None or abs(self.flow_direction) < 1e-9:
            return None
        follows_geometry = self.flow_direction > 0
        return (
            self.central_at_start
            if follows_geometry
            else not self.central_at_start
        )


def select_sewer_reference_outlet(
    ports: tuple[SewerManholePort, ...],
    heights: dict[str, float | None] | None = None,
) -> SewerManholePort | None:
    """Choose the deepest outgoing pipe as the manhole-clock reference."""

    outgoing = [port for port in ports if port.is_outgoing is True]
    if not outgoing:
        return None
    current_heights = heights or {}

    def sort_key(port: SewerManholePort) -> tuple[bool, float, float, str]:
        height = current_heights.get(port.key, port.height)
        return (
            height is None,
            height if height is not None else math.inf,
            port.bearing,
            port.key,
        )

    return min(
        outgoing,
        key=sort_key,
    )


def sewer_clock_angle(
    port: SewerManholePort,
    reference_outlet: SewerManholePort | None,
) -> float:
    """Return clockwise angle from the outlet, or north when unknown."""

    if reference_outlet is None:
        return port.bearing % 360.0
    return (port.bearing - reference_outlet.bearing) % 360.0


@dataclass(frozen=True)
class SewerManholeState:
    node_id: int | None
    node_feature_layer: QgsVectorLayer | None
    node_feature_id: int | None
    point: QgsPoint
    network_id: int
    nettype_id: int | None
    manhole_detail_feature_id: int | None
    branch_detail_feature_id: int | None
    configuration: SewerManholeConfiguration
    ports: tuple[SewerManholePort, ...]
    split_layer: QgsVectorLayer | None = None
    split_feature_id: int | None = None
    endpoint_connections: tuple[SewerEndpointConnection, ...] = ()
    pumping_station_detail_feature_id: int | None = None


@dataclass(frozen=True)
class SewerManholePlan:
    state: SewerManholeState
    configuration: SewerManholeConfiguration
    port_heights: tuple[tuple[str, float | None], ...]

    def height_for(self, port: SewerManholePort) -> float | None:
        return dict(self.port_heights).get(port.key)


@dataclass(frozen=True)
class SewerManholeWriteResult:
    node_id: int
    created_node: bool
    split_edge: bool


class SewerManholeReader:
    """Resolve a map click into one existing or prospective sewer manhole."""

    def __init__(self, context: SewerManholeContext) -> None:
        self.context = context
        self._value_relation_cache: dict[tuple[str, str], str | None] = {}

    def resolve(
        self,
        point: QgsPointXY,
        tolerance: float,
    ) -> SewerManholeState:
        node_candidates = self._node_candidates(point, tolerance)
        if len(node_candidates) > 1:
            labels = ", ".join(str(item[0]) for item in node_candidates)
            raise SewerManholeError(
                f"Klõpsu lähedal on mitu kanalisatsioonisõlme ({labels}). "
                "Suumi lähemale ja vali üks sõlm."
            )
        if node_candidates:
            node_id, _distance, layer, feature_id = node_candidates[0]
            return self._state_for_node(node_id, layer, feature_id)

        edge_candidates = self._edge_candidates(point, tolerance)
        if not edge_candidates:
            raise SewerManholeError(
                "Klõpsu lähedalt ei leitud kanalisatsioonisõlme ega "
                "isevoolset toru."
            )
        endpoints: list[_EndpointCandidate] = []
        interiors: list[tuple[QgsVectorLayer, QgsFeature, QgsPoint]] = []
        for _distance, layer, feature in edge_candidates:
            endpoint, projected = self._classify_edge_click(
                layer,
                feature,
                point,
                tolerance,
            )
            if endpoint is not None:
                endpoints.append(endpoint)
            else:
                interiors.append((layer, feature, projected))

        if len(interiors) > 1:
            raise self._ambiguous_edges(edge_candidates)
        anchor = (
            interiors[0][2]
            if interiors
            else endpoints[0].point
        )
        if any(
            candidate.point.distance(anchor) > tolerance * 2.0
            for candidate in endpoints
        ):
            raise self._ambiguous_edges(edge_candidates)
        if len(edge_candidates) > 1 and not endpoints:
            raise self._ambiguous_edges(edge_candidates)
        return self._junction_state(
            endpoints,
            interiors[0] if interiors else None,
            anchor,
        )

    def _state_for_node(
        self,
        node_id: int,
        node_layer: QgsVectorLayer,
        node_feature_id: int,
    ) -> SewerManholeState:
        node_feature = node_layer.getFeature(node_feature_id)
        if not node_feature.isValid() or not node_feature.hasGeometry():
            raise SewerManholeError(
                f"Kanalisatsioonisõlmel {node_id} puudub punktgeomeetria."
            )
        network_id = self._required_int(
            node_feature,
            "NETWORK_ID",
            "sõlme võrk",
        )
        detail = self._single_detail(node_id)
        branch_detail = self._single_branch_detail(node_id)
        pumping_station_detail = self._single_pumping_station_detail(node_id)
        ports = self._ports_for_node(node_id)
        if not ports:
            raise SewerManholeError(
                f"Sõlmel {node_id} ei ole toetatud isevoolseid torusid."
            )
        point_xy = node_feature.geometry().asPoint()
        return SewerManholeState(
            node_id=node_id,
            node_feature_layer=node_layer,
            node_feature_id=node_feature_id,
            point=QgsPoint(point_xy.x(), point_xy.y()),
            network_id=network_id,
            nettype_id=self._optional_int(node_feature["NETTYPE_ID"]),
            manhole_detail_feature_id=(
                int(detail.id()) if detail is not None else None
            ),
            branch_detail_feature_id=(
                int(branch_detail.id())
                if branch_detail is not None
                else None
            ),
            configuration=self._configuration(
                node_feature,
                detail,
                branch_detail,
            ),
            ports=ports,
            pumping_station_detail_feature_id=(
                int(pumping_station_detail.id())
                if pumping_station_detail is not None
                else None
            ),
        )

    def _new_endpoint_state(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        point: QgsPoint,
        at_start: bool,
    ) -> SewerManholeState:
        port = self._port(
            layer,
            feature,
            central_at_start=at_start,
        )
        return SewerManholeState(
            node_id=None,
            node_feature_layer=None,
            node_feature_id=None,
            point=point,
            network_id=self._required_int(
                feature,
                "NETWORK_ID",
                "toru võrk",
            ),
            nettype_id=self._optional_int(feature["NETTYPE_ID"]),
            manhole_detail_feature_id=None,
            branch_detail_feature_id=None,
            configuration=self._default_configuration(),
            ports=(port,),
            endpoint_connections=(
                SewerEndpointConnection(
                    layer=layer,
                    feature_id=int(feature.id()),
                    node_field=(
                        "BEGIN_NODE_ID" if at_start else "END_NODE_ID"
                    ),
                    port_key=port.key,
                ),
            ),
        )

    def _new_split_state(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        point: QgsPoint,
    ) -> SewerManholeState:
        first_geometry, second_geometry = WaterDuctWriter._split_line_geometry(
            feature.geometry(),
            point,
        )
        height = self._interpolated_height(feature, point)
        edge_id = self._optional_int(feature["MSLINK"])
        base = dict(
            layer=layer,
            feature_id=int(feature.id()),
            edge_id=edge_id,
            identification=self._text(feature["IDENTIFICATION"]),
            diameter_label=self._display_attribute(
                layer,
                feature,
                "DIAMETER_ID",
            ),
            material_label=self._display_attribute(
                layer,
                feature,
                "MATERIAL_ID",
            ),
            height=height,
            flow_direction=self._optional_float(feature["FLOWDIRECTION"]),
        )
        before = SewerManholePort(
            key=f"{layer.id()}:{feature.id()}:before",
            central_at_start=False,
            bearing=self._port_bearing(first_geometry, False, edge_id),
            split_side="before",
            **base,
        )
        after = SewerManholePort(
            key=f"{layer.id()}:{feature.id()}:after",
            central_at_start=True,
            bearing=self._port_bearing(second_geometry, True, edge_id),
            split_side="after",
            **base,
        )
        return SewerManholeState(
            node_id=None,
            node_feature_layer=None,
            node_feature_id=None,
            point=point,
            network_id=self._required_int(
                feature,
                "NETWORK_ID",
                "toru võrk",
            ),
            nettype_id=self._optional_int(feature["NETTYPE_ID"]),
            manhole_detail_feature_id=None,
            branch_detail_feature_id=None,
            configuration=self._default_configuration(),
            ports=(before, after),
            split_layer=layer,
            split_feature_id=int(feature.id()),
        )

    def _junction_state(
        self,
        endpoints: list[_EndpointCandidate],
        interior: tuple[QgsVectorLayer, QgsFeature, QgsPoint] | None,
        anchor: QgsPoint,
    ) -> SewerManholeState:
        features = [candidate.feature for candidate in endpoints]
        if interior is not None:
            features.append(interior[1])
        network_ids = {
            self._required_int(feature, "NETWORK_ID", "toru võrk")
            for feature in features
        }
        if len(network_ids) != 1:
            raise SewerManholeError(
                "Samas punktis olevad torud kuuluvad eri võrkudesse. "
                "Tööriist ei ühenda neid vaikimisi."
            )
        node_ids = {
            candidate.node_id
            for candidate in endpoints
            if candidate.node_id is not None
        }
        if len(node_ids) > 1:
            raise SewerManholeError(
                "Samas punktis olevad toruotsad viitavad erinevatele "
                "sõlmedele. Paranda topoloogia enne elemendi lisamist."
            )

        state: SewerManholeState
        if node_ids:
            node_id = next(iter(node_ids))
            found = self._find_node_feature(node_id)
            if found is None:
                raise SewerManholeError(
                    f"Toru viitab sõlmele {node_id}, kuid generaatori "
                    "projektikihtides ei ole see sõlm loetav."
                )
            state = self._state_for_node(node_id, found[0], found[1])
        elif interior is not None:
            state = self._new_split_state(
                interior[0],
                interior[1],
                interior[2],
            )
        elif endpoints:
            first = endpoints[0]
            state = self._new_endpoint_state(
                first.layer,
                first.feature,
                first.point,
                first.at_start,
            )
        else:
            raise SewerManholeError("Sõlmpunkti torusid ei leitud.")

        ports = list(state.ports)
        connections = list(state.endpoint_connections)
        existing_keys = {port.key for port in ports}
        for candidate in endpoints:
            if candidate.node_id is not None:
                continue
            port = self._port(
                candidate.layer,
                candidate.feature,
                candidate.at_start,
            )
            if port.key in existing_keys:
                continue
            existing_keys.add(port.key)
            ports.append(port)
            connections.append(
                SewerEndpointConnection(
                    layer=candidate.layer,
                    feature_id=int(candidate.feature.id()),
                    node_field=(
                        "BEGIN_NODE_ID"
                        if candidate.at_start
                        else "END_NODE_ID"
                    ),
                    port_key=port.key,
                )
            )

        if interior is not None and state.split_layer is None:
            split_state = self._new_split_state(
                interior[0],
                interior[1],
                interior[2],
            )
            for port in split_state.ports:
                if port.key not in existing_keys:
                    existing_keys.add(port.key)
                    ports.append(port)
            state = replace(
                state,
                split_layer=split_state.split_layer,
                split_feature_id=split_state.split_feature_id,
            )
        ports.sort(key=lambda port: (port.bearing, port.key))
        return replace(
            state,
            point=anchor,
            ports=tuple(ports),
            endpoint_connections=tuple(connections),
        )

    def _classify_edge_click(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        point: QgsPointXY,
        tolerance: float,
    ) -> tuple[_EndpointCandidate | None, QgsPoint]:
        geometry = feature.geometry()
        _distance, nearest, _after, _left = (
            geometry.closestSegmentWithContext(point)
        )
        projected = QgsPoint(nearest.x(), nearest.y())
        curve = geometry.constGet()
        if not isinstance(curve, QgsLineString) or curve.numPoints() < 2:
            raise SewerManholeError(
                f"{self._edge_label(layer, feature)} peab olema "
                "üheosaline LineString."
            )
        start = curve.startPoint()
        end = curve.endPoint()
        start_distance = QgsPointXY(start).distance(point)
        end_distance = QgsPointXY(end).distance(point)
        if min(start_distance, end_distance) > tolerance:
            return None, projected
        at_start = start_distance <= end_distance
        selected_endpoint = start if at_start else end
        endpoint = QgsPoint(
            selected_endpoint.x(),
            selected_endpoint.y(),
        )
        node_field = "BEGIN_NODE_ID" if at_start else "END_NODE_ID"
        return (
            _EndpointCandidate(
                layer=layer,
                feature=feature,
                at_start=at_start,
                point=endpoint,
                node_id=self._optional_int(feature[node_field]),
            ),
            endpoint,
        )

    def _ambiguous_edges(
        self,
        candidates: list[tuple[float, QgsVectorLayer, QgsFeature]],
    ) -> SewerManholeError:
        labels = ", ".join(
            self._edge_label(layer, feature)
            for _distance, layer, feature in candidates
        )
        return SewerManholeError(
            f"Klõpsu lähedal on mitu eri asukohaga võimalikku toru "
            f"({labels}). Suumi lähemale ja vali üks asukoht."
        )

    def _ports_for_node(
        self,
        node_id: int,
    ) -> tuple[SewerManholePort, ...]:
        ports: list[SewerManholePort] = []
        request = QgsFeatureRequest().setFilterExpression(
            f'"BEGIN_NODE_ID" = {node_id} OR "END_NODE_ID" = {node_id}'
        )
        for layer in self.context.duct_layers:
            for feature in layer.getFeatures(request):
                begin = self._optional_int(feature["BEGIN_NODE_ID"])
                end = self._optional_int(feature["END_NODE_ID"])
                if begin == node_id and end == node_id:
                    raise SewerManholeError(
                        f"{self._edge_label(layer, feature)} mõlemad otsad "
                        f"viitavad sõlmele {node_id}."
                    )
                if begin == node_id:
                    ports.append(self._port(layer, feature, True))
                elif end == node_id:
                    ports.append(self._port(layer, feature, False))
        ports.sort(key=lambda item: (item.bearing, item.key))
        return tuple(ports)

    def _port(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        central_at_start: bool,
    ) -> SewerManholePort:
        edge_id = self._optional_int(feature["MSLINK"])
        height_field = (
            "BEGIN_Z_COORD" if central_at_start else "END_Z_COORD"
        )
        return SewerManholePort(
            key=f"{layer.id()}:{feature.id()}:{'start' if central_at_start else 'end'}",
            layer=layer,
            feature_id=int(feature.id()),
            edge_id=edge_id,
            central_at_start=central_at_start,
            bearing=self._port_bearing(
                feature.geometry(),
                central_at_start,
                edge_id,
            ),
            identification=self._text(feature["IDENTIFICATION"]),
            diameter_label=self._display_attribute(
                layer,
                feature,
                "DIAMETER_ID",
            ),
            material_label=self._display_attribute(
                layer,
                feature,
                "MATERIAL_ID",
            ),
            height=self._optional_float(feature[height_field]),
            flow_direction=self._optional_float(feature["FLOWDIRECTION"]),
        )

    def _node_candidates(
        self,
        point: QgsPointXY,
        tolerance: float,
    ) -> list[tuple[int, float, QgsVectorLayer, int]]:
        rectangle = QgsRectangle(
            point.x() - tolerance,
            point.y() - tolerance,
            point.x() + tolerance,
            point.y() + tolerance,
        )
        request = QgsFeatureRequest().setFilterRect(rectangle)
        point_geometry = QgsGeometry.fromPointXY(point)
        best: dict[int, tuple[int, float, QgsVectorLayer, int]] = {}
        for layer in self.context.node_source_layers:
            for feature in layer.getFeatures(request):
                if not feature.hasGeometry():
                    continue
                node_id = self._optional_int(feature["MSLINK"])
                if node_id is None:
                    continue
                distance = feature.geometry().distance(point_geometry)
                if distance > tolerance:
                    continue
                candidate = (
                    node_id,
                    distance,
                    layer,
                    int(feature.id()),
                )
                if node_id not in best or distance < best[node_id][1]:
                    best[node_id] = candidate
        return sorted(best.values(), key=lambda item: (item[1], item[0]))

    def _edge_candidates(
        self,
        point: QgsPointXY,
        tolerance: float,
    ) -> list[tuple[float, QgsVectorLayer, QgsFeature]]:
        rectangle = QgsRectangle(
            point.x() - tolerance,
            point.y() - tolerance,
            point.x() + tolerance,
            point.y() + tolerance,
        )
        request = QgsFeatureRequest().setFilterRect(rectangle)
        point_geometry = QgsGeometry.fromPointXY(point)
        candidates = []
        for layer in self.context.duct_layers:
            for feature in layer.getFeatures(request):
                if not feature.hasGeometry():
                    continue
                distance = feature.geometry().distance(point_geometry)
                if distance <= tolerance:
                    candidates.append((distance, layer, feature))
        candidates.sort(
            key=lambda item: (
                item[0],
                self._edge_label(item[1], item[2]),
            )
        )
        return candidates

    def _find_node_feature(
        self,
        node_id: int,
    ) -> tuple[QgsVectorLayer, int] | None:
        request = QgsFeatureRequest().setFilterExpression(
            f'"MSLINK" = {node_id}'
        )
        for layer in self.context.node_source_layers:
            feature = next(layer.getFeatures(request), None)
            if feature is not None:
                return layer, int(feature.id())
        return None

    def _single_detail(self, node_id: int) -> QgsFeature | None:
        return self._single_detail_from_layer(
            self.context.manhole_layer,
            node_id,
            "kaevu",
        )

    def _single_branch_detail(self, node_id: int) -> QgsFeature | None:
        return self._single_detail_from_layer(
            self.context.branch_layer,
            node_id,
            "liitmiku",
        )

    def _single_pumping_station_detail(
        self,
        node_id: int,
    ) -> QgsFeature | None:
        layer = self.context.pumping_station_layer
        if layer is None:
            return None
        return self._single_detail_from_layer(
            layer,
            node_id,
            "pumpla",
        )

    @staticmethod
    def _single_detail_from_layer(
        layer: QgsVectorLayer,
        node_id: int,
        label: str,
    ) -> QgsFeature | None:
        request = QgsFeatureRequest().setFilterExpression(
            f'"NODE_ID" = {node_id}'
        )
        matches = list(layer.getFeatures(request))
        if len(matches) > 1:
            raise SewerManholeError(
                f"Sõlmel {node_id} on mitu {label} detailkirjet."
            )
        return matches[0] if matches else None

    def _configuration(
        self,
        node: QgsFeature,
        detail: QgsFeature | None,
        branch_detail: QgsFeature | None,
    ) -> SewerManholeConfiguration:
        default = self._default_configuration()
        return SewerManholeConfiguration(
            detail_kind=(
                DETAIL_KIND_MANHOLE
                if detail is not None or branch_detail is None
                else DETAIL_KIND_CONNECTION
            ),
            identification=self._text(node["IDENTIFICATION"]),
            element_height=self._optional_float(node["Z_COORD1"]),
            bottom_height=self._optional_float(node["Z_COORD2"]),
            ground_height=self._optional_float(node["Z_COORD3"]),
            type_id=(
                self._optional_int(detail["TYPE_ID"])
                if detail is not None
                else default.type_id
            ),
            material_id=self._detail_int(detail, "MATERIAL_ID"),
            diameter_type_id=self._detail_int(
                detail,
                "DIAMETER_TYPE_ID",
            ),
            diameter_id=self._detail_int(detail, "DIAMETER_ID"),
            firmness_class_id=self._detail_int(
                detail,
                "FIRMNESS_CLASS_ID",
            ),
            lid_type_id=self._detail_int(detail, "LID_TYPE_ID"),
            lid_material_id=self._detail_int(
                detail,
                "LID_MATERIAL_ID",
            ),
            lid_shape_id=self._detail_int(detail, "LID_SHAPE_ID"),
            lid_diameter_id=self._detail_int(
                detail,
                "LID_DIAMETER_ID",
            ),
            lid_capacity_id=self._detail_int(
                detail,
                "LID_CAPACITY_ID",
            ),
            access_duct_diam=self._detail_int(
                detail,
                "ACCESS_DUCT_DIAM",
            ),
            branch_type_id=(
                self._optional_int(branch_detail["TYPE_AQUA_ID"])
                if branch_detail is not None
                else default.branch_type_id
            ),
            branch_subtype_id=(
                self._optional_int(branch_detail["TYPE_ID"])
                if branch_detail is not None
                else default.branch_subtype_id
            ),
        )

    def _default_configuration(self) -> SewerManholeConfiguration:
        return SewerManholeConfiguration(
            type_id=self.context.options.default_type_id,
            branch_type_id=self.context.options.connection_branch_type_id,
            branch_subtype_id=(
                self.context.options.default_branch_subtype_id
            ),
        )

    def _display_attribute(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        field_name: str,
    ) -> str:
        index = layer.fields().lookupField(field_name)
        raw_value = feature.attribute(index)
        if QgsVariantUtils.isNull(raw_value):
            return "—"
        setup = layer.editorWidgetSetup(index)
        if setup.type() == "ValueRelation":
            config = setup.config()
            key = (field_name, str(raw_value))
            if key not in self._value_relation_cache:
                key_name = str(config.get("Key", "ID"))
                value_name = str(config.get("Value", "TXT"))
                request = QgsFeatureRequest().setFilterExpression(
                    f'"{key_name}" = {QgsExpression.quotedValue(raw_value)}'
                )
                match = next(
                    self.context.constant_layer.getFeatures(request),
                    None,
                )
                self._value_relation_cache[key] = (
                    str(match[value_name]).strip() if match is not None else None
                )
            value = self._value_relation_cache[key]
            if value:
                return value
        formatter = QgsApplication.fieldFormatterRegistry().fieldFormatter(
            setup.type()
        )
        try:
            value = formatter.representValue(
                layer,
                index,
                setup.config(),
                None,
                raw_value,
            )
        except Exception:
            value = raw_value
        return str(value).strip() or "—"

    @staticmethod
    def _interpolated_height(
        feature: QgsFeature,
        point: QgsPoint,
    ) -> float | None:
        start = SewerManholeReader._optional_float(
            feature["BEGIN_Z_COORD"]
        )
        end = SewerManholeReader._optional_float(
            feature["END_Z_COORD"]
        )
        if start is None or end is None:
            return start if start is not None else end
        geometry = feature.geometry()
        length = geometry.length()
        if length <= 0:
            return start
        offset = geometry.lineLocatePoint(QgsGeometry.fromPoint(point))
        ratio = min(max(offset / length, 0.0), 1.0)
        return start + (end - start) * ratio

    @staticmethod
    def _port_bearing(
        geometry: QgsGeometry,
        central_at_start: bool,
        edge_id: int | None,
    ) -> float:
        curve = geometry.constGet()
        if not isinstance(curve, QgsLineString) or curve.numPoints() < 2:
            raise SewerManholeError(
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
            dx = target.x() - origin.x()
            dy = target.y() - origin.y()
            if math.hypot(dx, dy) > 1e-9:
                return math.degrees(math.atan2(dx, dy)) % 360.0
        raise SewerManholeError(
            f"Torul {edge_id if edge_id is not None else '?'} puudub "
            "sõlmest väljuv lõik."
        )

    @staticmethod
    def _edge_label(layer: QgsVectorLayer, feature: QgsFeature) -> str:
        edge_id = SewerManholeReader._optional_int(feature["MSLINK"])
        return f"{layer.name()} {edge_id if edge_id is not None else feature.id()}"

    @staticmethod
    def _required_int(
        feature: QgsFeature,
        field_name: str,
        label: str,
    ) -> int:
        value = SewerManholeReader._optional_int(feature[field_name])
        if value is None:
            raise SewerManholeError(f"{label.capitalize()} on määramata.")
        return value

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if QgsVariantUtils.isNull(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _text(value: object) -> str:
        if QgsVariantUtils.isNull(value):
            return ""
        return str(value).strip()

    @classmethod
    def _detail_int(
        cls,
        detail: QgsFeature | None,
        field_name: str,
    ) -> int | None:
        return cls._optional_int(detail[field_name]) if detail is not None else None


class SewerManholeWriter:
    """Apply one manhole clock configuration as reversible edit commands."""

    COMMAND_TEXT = "Lisa või muuda EVEL-i kanalisatsioonisõlme"

    def __init__(self, context: SewerManholeContext) -> None:
        self.context = context

    def write(self, plan: SewerManholePlan) -> SewerManholeWriteResult:
        self._validate_plan(plan)
        layers = self._command_layers(plan.state)
        for layer in layers:
            if not layer.isEditable():
                raise SewerManholeError(
                    f"Kiht „{layer.name()}“ ei ole redigeerimisrežiimis."
                )
            layer.beginEditCommand(self.COMMAND_TEXT)
        try:
            node_id, created = self._materialize_node(plan)
            self._write_node_attributes(plan, node_id)
            handled_keys: set[str] = set()
            if plan.state.split_layer is not None:
                self._split_edge(plan, node_id)
                handled_keys.update(
                    port.key
                    for port in plan.state.ports
                    if port.split_side is not None
                )
            if plan.state.endpoint_connections:
                self._connect_endpoints(plan, node_id)
                handled_keys.update(
                    connection.port_key
                    for connection in plan.state.endpoint_connections
                )
            self._write_port_heights(plan, handled_keys)
            self._write_detail(plan, node_id)
            for layer in reversed(layers):
                layer.endEditCommand()
                layer.triggerRepaint()
            command_layer_ids = {layer.id() for layer in layers}
            for visible_layer in (
                self.context.visible_manhole_layer,
                self.context.visible_branch_layer,
            ):
                if (
                    visible_layer is not None
                    and visible_layer.id() not in command_layer_ids
                ):
                    visible_layer.triggerRepaint()
            return SewerManholeWriteResult(
                node_id=node_id,
                created_node=created,
                split_edge=plan.state.split_layer is not None,
            )
        except Exception:
            for layer in reversed(layers):
                layer.destroyEditCommand()
                layer.triggerRepaint()
            raise

    def _materialize_node(
        self,
        plan: SewerManholePlan,
    ) -> tuple[int, bool]:
        state = plan.state
        if state.node_id is not None:
            return state.node_id, False
        layer = self.context.node_layer
        config = plan.configuration
        attributes = {
            self._field_index(layer, "NETWORK_ID"): state.network_id,
            self._field_index(layer, "NETTYPE_ID"): (
                state.nettype_id
                if state.nettype_id is not None
                else GRAVITY_NETTYPE_ID
            ),
            self._field_index(layer, "IDENTIFICATION"): (
                config.identification or None
            ),
            self._field_index(layer, "Z_COORD1"): config.element_height,
            self._field_index(layer, "Z_COORD2"): config.bottom_height,
            self._field_index(layer, "Z_COORD3"): config.ground_height,
        }
        feature = self._create_feature_with_server_key(
            layer,
            QgsGeometry.fromPoint(state.point),
            attributes,
            "MSLINK",
        )
        if not layer.addFeature(feature):
            raise SewerManholeError(
                "Kanalisatsioonisõlme baaskirje lisamine ebaõnnestus."
            )
        return self._required_integer_attribute(
            layer,
            feature,
            "MSLINK",
            "uuele kanalisatsioonisõlmele",
        ), True

    def _write_node_attributes(
        self,
        plan: SewerManholePlan,
        node_id: int,
    ) -> None:
        state = plan.state
        if state.node_id is None:
            return
        layer = state.node_feature_layer
        feature_id = state.node_feature_id
        if layer is None or feature_id is None:
            raise SewerManholeError(
                f"Sõlme {node_id} baaskirje ei ole projektikihis muudetav."
            )
        config = plan.configuration
        values = {
            "IDENTIFICATION": config.identification or None,
            "Z_COORD1": config.element_height,
            "Z_COORD2": config.bottom_height,
            "Z_COORD3": config.ground_height,
        }
        for field_name, value in values.items():
            if not layer.changeAttributeValue(
                feature_id,
                self._field_index(layer, field_name),
                value,
            ):
                raise SewerManholeError(
                    f"Sõlme välja {field_name} uuendamine ebaõnnestus."
                )

    def _connect_endpoints(
        self,
        plan: SewerManholePlan,
        node_id: int,
    ) -> None:
        state = plan.state
        ports = {port.key: port for port in state.ports}
        for connection in state.endpoint_connections:
            port = ports.get(connection.port_key)
            if port is None:
                raise SewerManholeError(
                    "Toruotsa ühenduse toruharu puudub sõlmeskeemist."
                )
            values = {
                connection.node_field: node_id,
                port.height_field: plan.height_for(port),
            }
            for field_name, value in values.items():
                if not connection.layer.changeAttributeValue(
                    connection.feature_id,
                    self._field_index(connection.layer, field_name),
                    value,
                ):
                    raise SewerManholeError(
                        f"Toruotsa välja {field_name} uuendamine ebaõnnestus."
                    )

    def _split_edge(
        self,
        plan: SewerManholePlan,
        node_id: int,
    ) -> None:
        state = plan.state
        layer = state.split_layer
        feature_id = state.split_feature_id
        if layer is None or feature_id is None:
            raise SewerManholeError("Toru poolitamise plaan ei ole täielik.")
        original = layer.getFeature(feature_id)
        if not original.isValid() or not original.hasGeometry():
            raise SewerManholeError("Poolitatavat isevoolset toru ei leitud.")
        first_geometry, second_geometry = WaterDuctWriter._split_line_geometry(
            original.geometry(),
            state.point,
        )
        before = next(
            port for port in state.ports if port.split_side == "before"
        )
        after = next(
            port for port in state.ports if port.split_side == "after"
        )

        if not layer.changeGeometry(feature_id, first_geometry):
            raise SewerManholeError(
                "Poolitatava toru esimese osa geomeetria muutmine ebaõnnestus."
            )
        original_updates = {
            "END_NODE_ID": node_id,
            "END_Z_COORD": plan.height_for(before),
            "LENGTH_2D": first_geometry.length(),
        }
        for field_name, value in original_updates.items():
            if not layer.changeAttributeValue(
                feature_id,
                self._field_index(layer, field_name),
                value,
            ):
                raise SewerManholeError(
                    f"Poolitatud toru välja {field_name} uuendamine ebaõnnestus."
                )

        attributes: dict[int, object] = {}
        excluded = set(layer.primaryKeyAttributes())
        excluded.add(self._field_index(layer, "MSLINK"))
        for index, _field in enumerate(layer.fields()):
            if index in excluded:
                continue
            if layer.fields().fieldOrigin(index) != Qgis.FieldOrigin.Provider:
                continue
            attributes[index] = original.attribute(index)
        attributes.update(
            {
                self._field_index(layer, "BEGIN_NODE_ID"): node_id,
                self._field_index(layer, "BEGIN_Z_COORD"): plan.height_for(after),
                self._field_index(layer, "LENGTH_2D"): second_geometry.length(),
            }
        )
        second = self._create_feature_with_server_key(
            layer,
            second_geometry,
            attributes,
            "MSLINK",
        )
        if not layer.addFeature(second):
            raise SewerManholeError(
                "Poolitatud toru teise osa lisamine ebaõnnestus."
            )
        self._required_integer_attribute(
            layer,
            second,
            "MSLINK",
            "poolitatud toru teisele osale",
        )

    def _write_port_heights(
        self,
        plan: SewerManholePlan,
        handled_keys: set[str],
    ) -> None:
        for port in plan.state.ports:
            if port.key in handled_keys:
                continue
            if not port.layer.changeAttributeValue(
                port.feature_id,
                self._field_index(port.layer, port.height_field),
                plan.height_for(port),
            ):
                raise SewerManholeError(
                    f"Toru {port.edge_id or port.feature_id} kõrguse "
                    "uuendamine ebaõnnestus."
                )

    def _write_detail(
        self,
        plan: SewerManholePlan,
        node_id: int,
    ) -> None:
        config = plan.configuration
        if config.detail_kind == DETAIL_KIND_CONNECTION:
            self._write_branch_detail(plan, node_id)
            return
        if config.detail_kind != DETAIL_KIND_MANHOLE:
            raise SewerManholeError(
                "Sõlme elemendi liik peab olema kaev või ühenduskoht."
            )

        layer = self.context.manhole_layer
        values = {
            "TYPE_ID": config.type_id,
            "MATERIAL_ID": config.material_id,
            "DIAMETER_TYPE_ID": config.diameter_type_id,
            "DIAMETER_ID": config.diameter_id,
            "FIRMNESS_CLASS_ID": config.firmness_class_id,
            "LID_TYPE_ID": config.lid_type_id,
            "LID_MATERIAL_ID": config.lid_material_id,
            "LID_SHAPE_ID": config.lid_shape_id,
            "LID_DIAMETER_ID": config.lid_diameter_id,
            "LID_CAPACITY_ID": config.lid_capacity_id,
            "ACCESS_DUCT_DIAM": config.access_duct_diam,
        }
        if config.type_id is None:
            raise SewerManholeError("Kaevu liik peab olema valitud.")
        existing_id = plan.state.manhole_detail_feature_id
        if existing_id is not None:
            self._ensure_feature_server_key(
                layer,
                existing_id,
                "ID",
                "olemasolevale kanalisatsioonikaevule",
            )
            for field_name, value in values.items():
                if not layer.changeAttributeValue(
                    existing_id,
                    self._field_index(layer, field_name),
                    value,
                ):
                    raise SewerManholeError(
                        f"Kaevu välja {field_name} uuendamine ebaõnnestus."
                    )
            return

        attributes = {
            self._field_index(layer, "NODE_ID"): node_id,
        }
        attributes.update(
            {
                self._field_index(layer, field_name): value
                for field_name, value in values.items()
            }
        )
        feature = self._create_feature_with_server_key(
            layer,
            QgsGeometry(),
            attributes,
            "ID",
        )
        reserved_id = self._required_integer_attribute(
            layer,
            feature,
            "ID",
            "uuele kanalisatsioonikaevule",
        )
        if not layer.addFeature(feature):
            provider_errors = "; ".join(layer.dataProvider().errors())
            detail = (
                f" Andmepakkuja: {provider_errors}"
                if provider_errors
                else ""
            )
            raise SewerManholeError(
                "Kanalisatsioonikaevu detailkirje lisamine ebaõnnestus "
                f"(reserveeritud ID {reserved_id}).{detail}"
            )
        self._required_integer_attribute(
            layer,
            feature,
            "ID",
            "uuele kanalisatsioonikaevule",
        )

    def _write_branch_detail(
        self,
        plan: SewerManholePlan,
        node_id: int,
    ) -> None:
        layer = self.context.branch_layer
        config = plan.configuration
        branch_type_id = (
            config.branch_type_id
            if config.branch_type_id is not None
            else self.context.options.connection_branch_type_id
        )
        branch_subtype_id = (
            config.branch_subtype_id
            if config.branch_subtype_id is not None
            else self.context.options.default_branch_subtype_id
        )
        allowed_types = {
            option.value for option in self.context.options.branch_type_options
        }
        allowed_subtypes = {
            option.value
            for option in self.context.options.branch_subtype_options
        }
        if branch_type_id not in allowed_types:
            raise SewerManholeError(
                "Valitud kanalisatsiooniliitmiku tüüp ei ole lookup-loendis."
            )
        if branch_subtype_id not in allowed_subtypes:
            raise SewerManholeError(
                "Valitud kanalisatsiooniliitmiku alamtüüp ei ole lookup-loendis."
            )
        values = {
            "TYPE_AQUA_ID": branch_type_id,
            "TYPE_ID": branch_subtype_id,
        }
        existing_id = plan.state.branch_detail_feature_id
        if existing_id is not None:
            self._ensure_feature_server_key(
                layer,
                existing_id,
                "ID",
                "olemasolevale kanalisatsiooni ühenduskohale",
            )
            for field_name, value in values.items():
                if not layer.changeAttributeValue(
                    existing_id,
                    self._field_index(layer, field_name),
                    value,
                ):
                    raise SewerManholeError(
                        f"Liitmiku välja {field_name} uuendamine ebaõnnestus."
                    )
            return

        attributes = {
            self._field_index(layer, "NODE_ID"): node_id,
            self._field_index(layer, "TYPE_AQUA_ID"): branch_type_id,
            self._field_index(layer, "TYPE_ID"): branch_subtype_id,
        }
        feature = self._create_feature_with_server_key(
            layer,
            QgsGeometry(),
            attributes,
            "ID",
        )
        reserved_id = self._required_integer_attribute(
            layer,
            feature,
            "ID",
            "uuele kanalisatsiooni ühenduskohale",
        )
        if not layer.addFeature(feature):
            provider_errors = "; ".join(layer.dataProvider().errors())
            detail = (
                f" Andmepakkuja: {provider_errors}"
                if provider_errors
                else ""
            )
            raise SewerManholeError(
                "Kanalisatsiooni ühenduskoha detailkirje lisamine "
                f"ebaõnnestus (reserveeritud ID {reserved_id}).{detail}"
            )
        self._required_integer_attribute(
            layer,
            feature,
            "ID",
            "uuele kanalisatsiooni ühenduskohale",
        )

    def _validate_plan(self, plan: SewerManholePlan) -> None:
        expected = {port.key for port in plan.state.ports}
        actual = {key for key, _height in plan.port_heights}
        if expected != actual:
            raise SewerManholeError(
                "Sõlmeskeemi torukõrguste loend ei vasta sõlme "
                "toruharudele."
            )
        if len(actual) != len(plan.port_heights):
            raise SewerManholeError(
                "Sõlmeskeemis on sama toruharu kõrgus mitu korda."
            )
        if plan.configuration.detail_kind not in {
            DETAIL_KIND_MANHOLE,
            DETAIL_KIND_CONNECTION,
        }:
            raise SewerManholeError(
                "Sõlme elemendi liik peab olema kaev või ühenduskoht."
            )

    def _command_layers(
        self,
        state: SewerManholeState,
    ) -> list[QgsVectorLayer]:
        candidates = [
            self.context.manhole_layer,
            self.context.branch_layer,
            (
                state.node_feature_layer
                if state.node_id is not None
                else self.context.node_layer
            ),
            state.split_layer,
            *(
                connection.layer
                for connection in state.endpoint_connections
            ),
            *(port.layer for port in state.ports),
        ]
        layers: list[QgsVectorLayer] = []
        seen: set[str] = set()
        for layer in candidates:
            if layer is None or layer.id() in seen:
                continue
            seen.add(layer.id())
            layers.append(layer)
        return layers

    @staticmethod
    def _required_integer_attribute(
        layer: QgsVectorLayer,
        feature: QgsFeature,
        field_name: str,
        object_label: str,
    ) -> int:
        index = SewerManholeWriter._field_index(layer, field_name)
        value = feature.attribute(index)
        if QgsVariantUtils.isNull(value):
            raise SewerManholeError(
                f"Andmepakkuja ei tagastanud {object_label} "
                f"{field_name} väärtust."
            )
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise SewerManholeError(
                f"{object_label.capitalize()} {field_name} ei ole täisarv."
            ) from error

    @classmethod
    def _create_feature_with_server_key(
        cls,
        layer: QgsVectorLayer,
        geometry: QgsGeometry,
        attributes: dict[int, object],
        key_field_name: str,
    ) -> QgsFeature:
        feature = QgsVectorLayerUtils.createFeature(
            layer,
            geometry,
            attributes,
        )
        if layer.providerType() == "postgres":
            feature.setAttribute(
                cls._field_index(layer, key_field_name),
                cls._next_server_identity(layer, key_field_name),
            )
        return feature

    @classmethod
    def _ensure_feature_server_key(
        cls,
        layer: QgsVectorLayer,
        feature_id: int,
        key_field_name: str,
        object_label: str,
    ) -> int:
        key_index = cls._field_index(layer, key_field_name)
        feature = layer.getFeature(feature_id)
        if not feature.isValid():
            raise SewerManholeError(
                f"{object_label.capitalize()} vastavat detailkirjet ei leitud."
            )
        value = feature.attribute(key_index)
        if not QgsVariantUtils.isNull(value):
            try:
                return int(value)
            except (TypeError, ValueError) as error:
                raise SewerManholeError(
                    f"{object_label.capitalize()} {key_field_name} "
                    "ei ole täisarv."
                ) from error

        if layer.providerType() == "postgres":
            value = cls._next_server_identity(layer, key_field_name)
        else:
            default_feature = QgsVectorLayerUtils.createFeature(
                layer,
                QgsGeometry(),
                {},
            )
            value = default_feature.attribute(key_index)
        if QgsVariantUtils.isNull(value):
            raise SewerManholeError(
                f"{object_label.capitalize()} puudub {key_field_name} ning "
                "serveri vaikeväärtust ei õnnestunud luua."
            )
        try:
            integer_value = int(value)
        except (TypeError, ValueError) as error:
            raise SewerManholeError(
                f"{object_label.capitalize()} loodud {key_field_name} "
                "ei ole täisarv."
            ) from error
        if not layer.changeAttributeValue(
            feature_id,
            key_index,
            integer_value,
        ):
            raise SewerManholeError(
                f"{object_label.capitalize()} {key_field_name} "
                "parandamine ebaõnnestus."
            )
        return integer_value

    @staticmethod
    def _next_server_identity(
        layer: QgsVectorLayer,
        key_field_name: str,
    ) -> int:
        registry = QgsProviderRegistry.instance()
        decoded = registry.decodeUri("postgres", layer.source())
        schema_name = str(decoded.get("schema", "")).strip()
        table_name = str(decoded.get("table", "")).strip()
        if not schema_name or not table_name:
            raise SewerManholeError(
                f"Kihi „{layer.name()}“ PostGIS-i tabelit ei õnnestunud "
                "serveri-ID loomiseks tuvastada."
            )
        escaped_schema = schema_name.replace('"', '""')
        escaped_table = table_name.replace('"', '""')
        quoted_table = f'"{escaped_schema}"."{escaped_table}"'
        sql = (
            "SELECT nextval(pg_get_serial_sequence("
            f"{QgsExpression.quotedValue(quoted_table)}, "
            f"{QgsExpression.quotedValue(key_field_name)}))"
        )
        metadata = registry.providerMetadata("postgres")
        if metadata is None:
            raise SewerManholeError(
                "QGIS-i PostGIS-i ühenduse liidest ei leitud."
            )
        connection_uri = QgsDataSourceUri(
            layer.source()
        ).connectionInfo(False)
        try:
            connection = metadata.createConnection(connection_uri, {})
            rows = connection.executeSql(sql)
        except Exception as error:
            raise SewerManholeError(
                f"Kihi „{layer.name()}“ serveri-ID küsimine ebaõnnestus."
            ) from error
        if not rows or not rows[0] or QgsVariantUtils.isNull(rows[0][0]):
            raise SewerManholeError(
                f"Tabeli {quoted_table} väljal {key_field_name} puudub "
                "IDENTITY/sequence generaator."
            )
        try:
            return int(rows[0][0])
        except (TypeError, ValueError) as error:
            raise SewerManholeError(
                f"Tabeli {quoted_table} serveri-ID ei ole täisarv."
            ) from error

    @staticmethod
    def _field_index(layer: QgsVectorLayer, field_name: str) -> int:
        index = layer.fields().lookupField(field_name)
        if index < 0:
            raise SewerManholeError(
                f"Kihil „{layer.name()}“ puudub väli {field_name}."
            )
        return index
