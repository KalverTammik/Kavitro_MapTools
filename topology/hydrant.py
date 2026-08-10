"""Resolve and atomically write EVEL water hydrants."""

from __future__ import annotations

from dataclasses import dataclass

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsRectangle,
    QgsVectorLayer,
    QgsVectorLayerUtils,
    QgsVariantUtils,
)

from ..layers import HydrantContext
from .endpoint_resolver import (
    EndpointKind,
    EndpointResolution,
    EndpointResolutionError,
    WaterEndpointResolver,
)
from .water_duct_writer import WaterDuctWriteError, WaterDuctWriter


class HydrantError(RuntimeError):
    """Raised when a hydrant cannot be resolved or written safely."""


@dataclass(frozen=True)
class HydrantState:
    node_id: int | None
    node_feature_id: int | None
    node_feature: QgsFeature
    detail_feature_id: int | None
    detail_feature: QgsFeature
    point: QgsPoint
    endpoint: EndpointResolution
    edge_layer: QgsVectorLayer | None

    @property
    def is_new(self) -> bool:
        return self.node_id is None

    @property
    def splits_edge(self) -> bool:
        return self.endpoint.edge_split is not None


@dataclass(frozen=True)
class HydrantPlan:
    state: HydrantState
    node_values: dict[str, object]
    detail_values: dict[str, object]


@dataclass(frozen=True)
class HydrantWriteResult:
    node_id: int
    created_node: bool
    split_edge: bool


class HydrantReader:
    """Resolve a click to an existing node or prospective hydrant node."""

    def __init__(self, context: HydrantContext) -> None:
        self.context = context

    def resolve(
        self,
        point: QgsPointXY,
        tolerance: float,
    ) -> HydrantState:
        map_point = QgsPoint(point.x(), point.y())
        nodes = self._node_candidates(map_point, tolerance)
        if len(nodes) > 1:
            ids = ", ".join(str(item[1]) for item in nodes)
            raise HydrantError(
                f"Klõpsu lähedal on mitu veesõlme ({ids}). "
                "Suumi lähemale ja vali üks sõlm."
            )
        if nodes:
            _distance, node_id, feature = nodes[0]
            endpoint = EndpointResolution(
                EndpointKind.EXISTING_NODE,
                QgsPoint(
                    feature.geometry().asPoint().x(),
                    feature.geometry().asPoint().y(),
                ),
                node_id=node_id,
            )
            return self._state(endpoint, None, feature)

        edge_hits: list[
            tuple[QgsVectorLayer, EndpointResolution]
        ] = []
        for layer in self.context.duct_layers:
            try:
                resolution = WaterEndpointResolver(
                    layer,
                    self.context.node_layer,
                    tolerance,
                ).resolve_point(map_point, "hüdrandi asukoht")
            except EndpointResolutionError as error:
                raise HydrantError(str(error)) from error
            if (
                resolution.edge_connections
                or resolution.edge_split is not None
            ):
                edge_hits.append((layer, resolution))

        if len(edge_hits) > 1:
            labels = ", ".join(
                f"{layer.name()} "
                f"({self._edge_label(resolution)})"
                for layer, resolution in edge_hits
            )
            raise HydrantError(
                "Klõpsu lähedal on mitu võimalikku veetoru: "
                f"{labels}. Suumi lähemale või vali ühesem koht."
            )
        if edge_hits:
            layer, endpoint = edge_hits[0]
            return self._state(endpoint, layer, None)

        raise HydrantError(
            "Klõpsu lähedalt ei leitud veesõlme ega veetoru. "
            "Uus hüdrant peab paiknema olemasoleval torul või toruotsal."
        )

    def _state(
        self,
        endpoint: EndpointResolution,
        edge_layer: QgsVectorLayer | None,
        node_feature: QgsFeature | None,
    ) -> HydrantState:
        node_id = endpoint.node_id
        if node_id is not None and node_feature is None:
            node_feature = self._node_feature(node_id)
        if node_feature is None:
            node_feature = QgsFeature(self.context.node_layer.fields())
            node_feature.setGeometry(
                QgsGeometry.fromPoint(endpoint.point)
            )
            node_feature.setAttribute(
                "NETWORK_ID",
                self.context.default_network_id,
            )
            node_feature.setAttribute(
                "NETTYPE_ID",
                self.context.default_nettype_id,
            )
        detail = self._detail(node_id) if node_id is not None else None
        if detail is None:
            detail = QgsFeature(self.context.detail_layer.fields())
            if node_id is not None:
                detail.setAttribute("NODE_ID", node_id)
            detail.setAttribute(
                "TYPE_AQUA_ID",
                self.context.default_type_aqua_id,
            )
            detail.setAttribute(
                "PLUG_TYPE_ID",
                self.context.default_plug_type_id,
            )
            detail.setAttribute(
                "LOCATION_ID",
                self.context.default_location_id,
            )
        return HydrantState(
            node_id=node_id,
            node_feature_id=(
                int(node_feature.id()) if node_id is not None else None
            ),
            node_feature=node_feature,
            detail_feature_id=(
                int(detail.id())
                if node_id is not None and detail.id() >= 0
                else None
            ),
            detail_feature=detail,
            point=endpoint.point,
            endpoint=endpoint,
            edge_layer=edge_layer,
        )

    def _node_candidates(
        self,
        point: QgsPoint,
        tolerance: float,
    ) -> list[tuple[float, int, QgsFeature]]:
        request = QgsFeatureRequest().setFilterRect(
            QgsRectangle(
                point.x() - tolerance,
                point.y() - tolerance,
                point.x() + tolerance,
                point.y() + tolerance,
            )
        )
        result: list[tuple[float, int, QgsFeature]] = []
        for feature in self.context.node_layer.getFeatures(request):
            if not feature.hasGeometry():
                continue
            distance = feature.geometry().distance(
                QgsGeometry.fromPoint(point)
            )
            if distance > tolerance:
                continue
            value = feature["MSLINK"]
            if QgsVariantUtils.isNull(value):
                continue
            try:
                node_id = int(value)
            except (TypeError, ValueError):
                continue
            result.append((distance, node_id, QgsFeature(feature)))
        result.sort(key=lambda item: (item[0], item[1]))
        return result

    def _node_feature(self, node_id: int) -> QgsFeature:
        request = QgsFeatureRequest().setFilterExpression(
            f'"MSLINK" = {int(node_id)}'
        )
        features = list(self.context.node_layer.getFeatures(request))
        if len(features) != 1:
            raise HydrantError(
                f"Veesõlme {node_id} baaskirjet ei leitud üheselt."
            )
        return QgsFeature(features[0])

    def _detail(self, node_id: int) -> QgsFeature | None:
        request = QgsFeatureRequest().setFilterExpression(
            f'"NODE_ID" = {int(node_id)}'
        )
        features = list(self.context.detail_layer.getFeatures(request))
        if len(features) > 1:
            raise HydrantError(
                f"Veesõlmega {node_id} on seotud mitu hüdrandi "
                "detailkirjet. Paranda andmed enne muutmist."
            )
        return QgsFeature(features[0]) if features else None

    @staticmethod
    def _edge_label(resolution: EndpointResolution) -> str:
        if resolution.edge_split is not None:
            item = resolution.edge_split
            return str(item.edge_id or f"FID {item.feature_id}")
        if resolution.edge_connections:
            item = resolution.edge_connections[0]
            return str(item.edge_id or f"FID {item.feature_id}")
        return "tundmatu"

    @staticmethod
    def _field_index(layer: QgsVectorLayer, name: str) -> int:
        index = layer.fields().lookupField(name)
        if index < 0:
            raise HydrantError(
                f"Kihil „{layer.name()}” puudub väli {name}."
            )
        return index


class HydrantWriter:
    """Create or update a node and its single SN_FIRE_PLUG detail."""

    COMMAND_TEXT = "Lisa või muuda EVEL-i hüdranti"

    def __init__(self, context: HydrantContext) -> None:
        self.context = context

    def write(self, plan: HydrantPlan) -> HydrantWriteResult:
        state = plan.state
        layers = self._unique_layers(
            (
                self.context.node_layer,
                self.context.detail_layer,
                state.edge_layer,
            )
        )
        if any(not layer.isEditable() for layer in layers):
            raise HydrantError(
                "Hüdrandi kirjutamiseks vajalikud kihid peavad olema "
                "redigeerimisrežiimis."
            )
        for layer in layers:
            layer.beginEditCommand(self.COMMAND_TEXT)
        try:
            node_id = self._materialize_node(state)
            node_feature_id = self._node_feature_id(node_id)
            self._change_values(
                self.context.node_layer,
                node_feature_id,
                plan.node_values,
                excluded={"MSLINK", "NETWORK_ID", "NETTYPE_ID"},
            )
            self._write_detail(plan, node_id)
            for layer in reversed(layers):
                layer.endEditCommand()
        except Exception:
            for layer in reversed(layers):
                layer.destroyEditCommand()
            raise

        for layer in layers:
            layer.triggerRepaint()
        self.context.visible_layer.triggerRepaint()
        return HydrantWriteResult(
            node_id=node_id,
            created_node=state.node_id is None,
            split_edge=state.splits_edge,
        )

    def _materialize_node(self, state: HydrantState) -> int:
        if state.node_id is not None:
            return int(state.node_id)
        if state.edge_layer is not None:
            writer = WaterDuctWriter(
                state.edge_layer,
                self.context.node_layer,
            )
        else:
            writer = WaterDuctWriter(
                self.context.duct_layers[0]
                if self.context.duct_layers
                else self.context.node_layer,
                self.context.node_layer,
            )
        try:
            return writer.materialize_endpoint(
                state.endpoint,
                self.context.default_network_id,
                self.context.default_nettype_id,
            )
        except WaterDuctWriteError as error:
            raise HydrantError(str(error)) from error

    def _write_detail(self, plan: HydrantPlan, node_id: int) -> None:
        layer = self.context.detail_layer
        if plan.state.detail_feature_id is not None:
            self._change_values(
                layer,
                plan.state.detail_feature_id,
                plan.detail_values,
                excluded={"ID", "NODE_ID"},
            )
            return
        attributes = {
            self._field_index(layer, "NODE_ID"): node_id,
        }
        for name, value in plan.detail_values.items():
            if name in {"ID", "NODE_ID"}:
                continue
            index = layer.fields().lookupField(name)
            if index >= 0:
                attributes[index] = value
        feature = QgsVectorLayerUtils.createFeature(
            layer,
            QgsGeometry(),
            attributes,
        )
        if not layer.addFeature(feature):
            raise HydrantError(
                "Hüdrandi detailkirje lisamine ebaõnnestus."
            )
        value = feature["ID"]
        if QgsVariantUtils.isNull(value):
            raise HydrantError(
                "Andmepakkuja ei tagastanud hüdrandi detailkirje ID-d."
            )

    def _node_feature_id(self, node_id: int) -> int:
        request = QgsFeatureRequest().setFilterExpression(
            f'"MSLINK" = {int(node_id)}'
        )
        features = list(self.context.node_layer.getFeatures(request))
        if len(features) != 1:
            raise HydrantError(
                f"Veesõlme {node_id} kirjet ei leitud pärast lisamist."
            )
        return int(features[0].id())

    def _change_values(
        self,
        layer: QgsVectorLayer,
        feature_id: int,
        values: dict[str, object],
        *,
        excluded: set[str],
    ) -> None:
        feature = layer.getFeature(feature_id)
        if not feature.isValid():
            raise HydrantError(
                f"Kihi „{layer.name()}” muudetavat kirjet ei leitud."
            )
        changes = {}
        old_values = {}
        for name, value in values.items():
            if name in excluded:
                continue
            index = layer.fields().lookupField(name)
            if index < 0 or feature.attribute(index) == value:
                continue
            changes[index] = value
            old_values[index] = feature.attribute(index)
        if changes and not layer.changeAttributeValues(
            feature_id,
            changes,
            old_values,
            False,
        ):
            raise HydrantError(
                f"Kihi „{layer.name()}” atribuutide muutmine ebaõnnestus."
            )

    @staticmethod
    def _field_index(layer: QgsVectorLayer, name: str) -> int:
        index = layer.fields().lookupField(name)
        if index < 0:
            raise HydrantError(
                f"Kihil „{layer.name()}” puudub väli {name}."
            )
        return index

    @staticmethod
    def _unique_layers(layers) -> tuple[QgsVectorLayer, ...]:
        result = []
        seen = set()
        for layer in layers:
            if layer is None or layer.id() in seen:
                continue
            seen.add(layer.id())
            result.append(layer)
        return tuple(result)
